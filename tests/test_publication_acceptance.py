"""Independent acceptance checks for frozen publication and the fake-only boundary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import test_approvals as existing
import publication_proposal as proposal
from publication_fake import FakeGitHub
from publication_operator import Operator


ROOT = Path(__file__).resolve().parents[1]


class PublicationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = existing.ApprovalTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.fixture.root
        self.bundle = self.root / 'bundle'
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        record = self.fixture.approved()
        record['source_repository'] = 'https://github.com/simulation/independent-acceptance'
        self.fixture.save(record)
        config = json.loads((self.stage/'config/repository.json').read_bytes())
        config.update(base_url=proposal.SIM_DESTINATION['base_url'],
                      github_repository=proposal.SIM_DESTINATION['repository'])
        (self.stage/'config/repository.json').write_bytes(existing.r.json_bytes(config))
        for name, raw in existing.r.installer(config, 'production').items():
            (self.stage/'packages/repository.ai.kodi'/name).write_bytes(raw)
        existing.r.build('production')
        evidence = self.stage/'evidence/synthetic-only.txt'
        evidence.parent.mkdir()
        evidence.write_bytes(b'Synthetic acceptance-test evidence. No native test performed.\n')
        qualification = {
            lane: {kind: {'status': 'passed', 'target': target,
                          'scope': 'Synthetic test only; no actual native or interpreter result',
                          'evidence': [{'path': 'evidence/synthetic-only.txt',
                                        'sha256': proposal.sha(evidence.read_bytes())}]}
                   for kind in ('static', 'interpreter', 'native')}
            for lane, target in [('nexus', '20.5'), ('omega', '21.3')]}
        self.expected = {'main_sha': '1'*40, 'pages_sha': '2'*40, 'pages_tree': '3'*40,
                         'ledger_sha256': proposal.sha((self.stage/'releases/manifest.json').read_bytes()),
                         'site_files': {}}
        proposal.prepare(self.stage, self.bundle,
                         source={'repository': 'simulation/independent-acceptance',
                                 'repository_id': 800, 'owner_id': 801, 'commit': 'a'*40},
                         lanes=['nexus', 'omega'], expected=self.expected,
                         release_tag='plugin.video.example-1.0.0',
                         qualification=qualification, synthetic=True, now=self.now)

    def payload(self):
        return proposal.strict_load((self.bundle/'payload.json').read_bytes())

    def rewrite_payload(self, value):
        (self.bundle/'payload.json').write_bytes(proposal.canonical(value))

    def frozen(self):
        proposal.seal_review(self.bundle, b'Independent synthetic acceptance review.', now=self.now)
        return proposal.seal_execution(self.bundle, audience=proposal.SIM_AUDIENCE,
                                       lifetime=3600, now=self.now)

    def operator(self, fault=None):
        ledger = (self.stage/'releases/manifest.json').read_bytes()
        fake = FakeGitHub.create(self.root/'fake', self.expected, {}, ledger)
        fake.fault = fault
        return Operator(self.root/'operator', fake, clock=lambda: self.now), fake

    def cli_arguments(self, command, frozen=None, bundle=None, extra=()):
        args = [command, '--store', str(self.root/'operator'), '--fake', str(self.root/'fake'),
                '--now', proposal.utc(self.now)]
        if frozen is not None:
            args += ['--bundle', str(bundle or self.bundle), '--digest', frozen['digest']]
        return args + list(extra)

    def cli(self, command, frozen=None, *, bundle=None, extra=(), success=True):
        args = [sys.executable, '-I', '-B', str(ROOT/'scripts/publication_operator.py'),
                *self.cli_arguments(command, frozen, bundle, extra)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=self.root,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                                     'PYTHONPATH': str(self.root/'untrusted-pythonpath'),
                                     'GH_TOKEN': 'LOCAL_SIMULATION_TEST_SENTINEL'})
        self.assertNotIn('LOCAL_SIMULATION_TEST_SENTINEL', result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr + result.stdout)
        value = json.loads(result.stdout)
        self.assertFalse(value['publication_authorized'])
        return value

    def test_verifier_rederives_source_package_binding_before_review(self):
        value = self.payload()
        value['source']['repository'] = 'simulation/unrelated-source'
        self.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.bundle)

    def test_verifier_rederives_package_lane_scope_before_review(self):
        value = self.payload()
        value['lanes'] = ['nexus']
        value['qualification'].pop('omega')
        self.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.bundle)

    def test_verifier_requires_exact_release_assets_before_review(self):
        value = self.payload()
        value['release']['assets'] = {}
        self.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.bundle)

    def test_verifier_rederives_original_ledger_content(self):
        value = self.payload()
        value['retention']['before'] = value['retention']['after']
        self.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.bundle)

    def test_verifier_rederives_finalization_commit(self):
        value = self.payload()
        value['retention']['main_commit'] = 'f'*40
        self.rewrite_payload(value)
        with self.assertRaises(ValueError):
            proposal.verify_payload(self.bundle)

    def test_fake_only_success_has_no_production_or_native_claim(self):
        frozen = self.frozen()
        operator, fake = self.operator()
        operator.request(self.bundle, frozen['digest'])
        operator.simulate_approve(frozen['execution']['nonce'])
        result = operator.execute(self.bundle, frozen['digest'])
        self.assertEqual(result['status'], 'RECORDED')
        self.assertTrue(result['simulation_only'])
        self.assertFalse(result['publication_authorized'])
        self.assertIsNone(operator.status()['active'])
        self.assertTrue(fake.snapshot()['releases']['plugin.video.example-1.0.0']['immutable'])

    def test_expired_transaction_remains_reconcilable_without_writes(self):
        frozen = self.frozen()
        operator, fake = self.operator(('after', 'publish_release'))
        operator.request(self.bundle, frozen['digest'])
        operator.simulate_approve(frozen['execution']['nonce'])
        with self.assertRaises(TimeoutError):
            operator.execute(self.bundle, frozen['digest'])
        before = fake.snapshot()
        self.now += timedelta(hours=2)
        # Read-only observations remain possible while an expired approval
        # cannot authorize another mutation.
        result = operator.reconcile(self.bundle, frozen['digest'])
        self.assertTrue(result['simulation_only'])
        self.assertEqual(fake.snapshot(), before)
        with self.assertRaises(ValueError):
            operator.execute(self.bundle, frozen['digest'])

    def test_real_cli_success_and_replay_rejection(self):
        frozen = self.frozen()
        self.assertEqual(self.cli('init', frozen)['status'], 'FAKE_INITIALIZED')
        requested = self.cli('request', frozen)
        self.cli('approve-test', extra=['--request-id', requested['request_id']])
        self.assertEqual(self.cli('execute', frozen)['status'], 'RECORDED')
        before = FakeGitHub(self.root/'fake').snapshot()
        self.assertEqual(self.cli('execute', frozen, success=False)['status'], 'BLOCKED')
        self.assertEqual(FakeGitHub(self.root/'fake').snapshot(), before)
        self.assertIsNone(self.cli('status')['active'])

    def test_isolated_cli_ignores_untrusted_pythonpath_and_working_directory(self):
        frozen = self.frozen()
        shadow = self.root/'untrusted-pythonpath'
        shadow.mkdir()
        (shadow/'json.py').write_text("raise RuntimeError('Untrusted PYTHONPATH module executed')\n")
        (self.root/'json.py').write_text("raise RuntimeError('Untrusted working-directory module executed')\n")
        self.assertEqual(self.cli('init', frozen)['status'], 'FAKE_INITIALIZED')
        self.assertEqual(self.cli('request', frozen)['status'], 'AWAITING_SIMULATED_OWNER')

    def test_fake_remote_numeric_identity_rejects_boolean_spoof(self):
        frozen = self.frozen()
        operator, fake = self.operator()
        state_path = self.root/'fake/state.json'
        original = state_path.read_bytes()
        mutations = [('destination', 'repository_id', True), ('destination', 'owner_id', True),
                     ('policy', 'owner_id', True), ('policy', 'protected', 1),
                     ('policy', 'immutable_releases', 1), (None, 'schema', True)]
        for group, field, bad in mutations:
            value = proposal.strict_load(original)
            target = value if group is None else value[group]
            target[field] = bad
            state_path.write_bytes(proposal.canonical(value))
            with self.subTest(group=group, field=field), self.assertRaises(ValueError):
                fake.snapshot()

    def test_real_cli_recovery_requires_new_frozen_approval(self):
        frozen = self.frozen()
        self.cli('init', frozen)
        requested = self.cli('request', frozen)
        self.cli('approve-test', extra=['--request-id', requested['request_id']])
        self.cli('execute', frozen, extra=['--fault', 'after:publish_release'], success=False)
        before = FakeGitHub(self.root/'fake').snapshot()
        recovery = self.cli('reconcile', frozen)['recovery']
        self.assertEqual(FakeGitHub(self.root/'fake').snapshot(), before)
        self.cli('execute', frozen, success=False)
        recovered_bundle = self.root/'recovered-bundle'
        shutil.copytree(self.bundle, recovered_bundle)
        (recovered_bundle/'execution.json').unlink()
        recovered = proposal.seal_execution(recovered_bundle, audience=proposal.SIM_AUDIENCE,
                                            now=self.now, recovery=recovery)
        new_request = self.cli('request', recovered, bundle=recovered_bundle)
        self.cli('execute', recovered, bundle=recovered_bundle, success=False)
        self.cli('approve-test', extra=['--request-id', new_request['request_id']])
        self.assertEqual(self.cli('execute', recovered, bundle=recovered_bundle)['status'], 'RECORDED')
        after = FakeGitHub(self.root/'fake').snapshot()
        self.assertEqual(after['releases'], before['releases'])
        self.assertEqual(len(after['releases']), 1)
        self.assertIsNone(self.cli('status')['active'])

    def test_actual_writer_termination_retains_consumption_and_remote_effect(self):
        frozen = self.frozen()
        self.cli('init', frozen)
        requested = self.cli('request', frozen)
        self.cli('approve-test', extra=['--request-id', requested['request_id']])
        marker = self.root/'published-effect.marker'
        bootstrap = '''import sys,runpy,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from publication_fake import FakeGitHub
marker=Path(sys.argv[2])
original=FakeGitHub._fault
def pause_after_effect(self,when,kind):
    original(self,when,kind)
    if (when,kind)==('after','publish_release'):
        marker.write_text('Publication effect is durable; writer paused before receipt')
        while True: time.sleep(0.02)
FakeGitHub._fault=pause_after_effect
script=Path(sys.argv[1])/'publication_operator.py'
sys.argv=[str(script),*sys.argv[3:]]
runpy.run_path(str(script),run_name='__main__')
'''
        process = subprocess.Popen([sys.executable, '-I', '-B', '-c', bootstrap,
                                    str(ROOT/'scripts'), str(marker),
                                    *self.cli_arguments('execute', frozen)],
                                   cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.exists(), 'Writer did not reach the injected durable-effect boundary')
            process.terminate()
            process.communicate(timeout=10)
            before = FakeGitHub(self.root/'fake').snapshot()
            self.assertTrue(before['releases']['plugin.video.example-1.0.0']['immutable'])
            reconciled = self.cli('reconcile', frozen)
            self.assertEqual(reconciled['recovery']['completed'][-1], 'publish_release')
            self.assertEqual(FakeGitHub(self.root/'fake').snapshot(), before)
            self.cli('execute', frozen, success=False)
            self.assertIsNotNone(self.cli('status')['active'])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
