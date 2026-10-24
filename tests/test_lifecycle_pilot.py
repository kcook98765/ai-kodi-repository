"""Offline real role protocol, fixed local data and credential boundary tests."""
import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures
import publication_cli as cli
import publication_d3_contract as d3
import publication_pilot_contract as contract
import publication_proposal as frozen
import lifecycle_pilot as pilot
from test_publication_pilot_contract import test_enrollment, VALIDATION


class PilotRoleTests(unittest.TestCase):
    def test_bound_manager_and_two_independent_tool_receipts(self):
        fx = fixtures.LifecycleTests('test_prepare_deterministic_candidate_reuses_independent_audit')
        fx.setUp(); self.addCleanup(fx.doCleanups)
        now = datetime.now(timezone.utc).replace(microsecond=0); e = test_enrollment(now)
        fx.gh = fixtures.FakeGitHub(e['repository'], d3.fixture_files('1.0.0'))
        fx.gh.repo_id = e['repository_id']; fx.gh.commit = e['fixture_source']['commits']['1.0.0']; fx.gh.ref_commit = fx.gh.commit
        fx.gh.overrides['repos/' + fx.gh.name] = {'id': fx.gh.repo_id, 'full_name': fx.gh.name, 'private': False, 'owner': {'id': e['owner_id']}}
        fx.store = fixtures.lc.Store(fx.root, fx.gh)
        fx.request.update(repository=fx.gh.name, repository_id=fx.gh.repo_id, lanes=['nexus'], candidate_base_url=e['base_url'])
        shutil.copyfile(fixtures.ROOT/'LICENSE', fx.root/'LICENSE'); shutil.copytree(fixtures.ROOT/'packages', fx.root/'packages')
        fx.acquire(); fx.call('build', addon_subdir='.', runtime_files=list(fx.gh.files)); fx.call('build', action='feed')
        config = {'schema': 1, 'profile': contract.PROFILE, 'project_root': str(fx.root), 'installation_uuid': e['installation_uuid'],
                  'epoch': e['epoch'], 'enrollment': e, 'remote_enabled': False}
        (fx.root/'.opencode/publication-pilot.json').write_bytes(frozen.canonical(config))
        binding = fixtures.lc.read_json(fx.store.control/fx.task['task_id']/'binding.json')
        ledger = {'schema': 1, 'packages': []}; main = {'releases/manifest.json': fixtures.repo.json_bytes(ledger),
            'config/qualification.json': b'{}', e['validation_workflow_path']: VALIDATION, '.github/CODEOWNERS': b'* @kcook98765\n'}
        inputs = {'schema': 1, 'profile': contract.PROFILE, 'task': pilot.task_identity(binding, config),
            'enrollment_sha256': frozen.sha(frozen.canonical(e)), 'observed_at': frozen.utc(now), 'source_commit': fx.gh.commit,
            'expected': {'main_sha': 'c'*40, 'main_tree': d3.tree(main), 'pages_sha': '2'*40, 'pages_tree': frozen.git_tree({}),
                         'ledger_sha256': frozen.sha(fixtures.repo.json_bytes(ledger)), 'site_files': {}},
            'published_ledger': ledger, 'main_files': {n: base64.b64encode(b).decode() for n,b in main.items()}}
        frozen.write_new(fx.out/'publication-pilot/inputs.json', frozen.canonical(inputs))
        def call(op, role, session):
            return fx.store.operate(op, role, fx.task['task_id'], fx.task['expected_digest'], {'action': 'publication_pilot'},
                context={'agent': role, 'session_id': session, 'tool': pilot.TOOLS[op]})
        p = call('build', 'kodi-repo-manager', 'ses_manager')
        self.assertEqual(p['status'], 'AWAITING_INDEPENDENT_REVIEW')
        with self.assertRaisesRegex(ValueError, 'independent role'): call('qualify', 'kodi-repo-manager', 'ses_manager')
        with self.assertRaisesRegex(ValueError, 'report must bind'): call('qualify', 'kodi-addon-tester', 'ses_tester')
        for op,role,session in [('qualify','kodi-addon-tester','ses_tester'), ('review','kodi-release-reviewer','ses_reviewer')]:
            frozen.write_new(fx.root/pilot.REPORTS[role], (f"Task {fx.task['task_id']}\nD3-PILOT-QUALIFIED {p['payload_sha256']}\nInert fixture reviewed; native/interpreter/Piers UNVERIFIED.\n").encode())
            result = call(op,role,session)
            self.assertFalse(result['publication_authorized'])
        final = call('build','kodi-repo-manager','ses_manager')
        self.assertEqual(final['status'], 'REVIEWED')
        self.assertEqual(final['payload_sha256'], p['payload_sha256'])
        self.assertFalse((fx.out/'publication-pilot/material/preparation.json').exists())
        self.assertFalse((fx.root/'dist/production').exists())
        with self.assertRaisesRegex(ValueError, 'activation is disabled'):
            cli.dispatch({'operation':'request', 'task_id':fx.task['task_id'], 'expected_digest':fx.task['expected_digest']},role='kodi-repo-manager',root=fx.root)

    def test_context_is_role_and_tool_specific(self):
        for c in (None, {}, {'agent':'kodi-repo-manager','session_id':'ses_x','tool':'kodi_review'},
                  {'agent':'kodi-release-reviewer','session_id':'','tool':'kodi_review'}):
            with self.subTest(c=c), self.assertRaises(ValueError): pilot.provenance(c,'kodi-release-reviewer','review')


class PilotBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.root = self.base/'project'; self.root.mkdir(); (self.root/'.opencode').mkdir()
        self.now = datetime.now(timezone.utc); self.e = test_enrollment(self.now)
        self.config = {'schema':1,'profile':contract.PROFILE,'project_root':str(self.root),'installation_uuid':self.e['installation_uuid'],
                       'epoch':self.e['epoch'],'enrollment':self.e,'remote_enabled':False}

    def test_actual_main_accepts_tool_wire_order_and_rejects_duplicate_keys(self):
        import contextlib, io, sys
        request = {"task_id": "a"*32, "expected_digest": "b"*64, "operation": "status"}
        wire = json.dumps(request, separators=(",", ":")).encode()
        self.assertNotEqual(wire, frozen.canonical(request))
        captured = []
        def dispatch(value, **kwargs):
            captured.append((cli._request(value, kwargs["role"]), kwargs["role"]))
            return {"status": "OFFLINE_PROTOCOL_OK"}
        def invoke(raw):
            stream = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8")
            with patch.object(sys, "stdin", stream), patch.object(sys, "argv", ["publication_cli.py", "--role", "kodi-repo-manager"]), patch.object(cli, "dispatch", side_effect=dispatch), contextlib.redirect_stdout(io.StringIO()) as output:
                cli.main()
                return json.loads(output.getvalue())
        self.assertEqual(invoke(wire)["status"], "OFFLINE_PROTOCOL_OK")
        self.assertEqual(captured, [(request, "kodi-repo-manager")])
        for raw in (b'{"operation":"status","operation":"execute"}', b'{"operation":NaN}', b'{"task_id":1.1}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): invoke(raw)
        self.assertEqual(len(captured), 1)

    def test_missing_opt_in_never_consults_ambient_credentials(self):
        with patch.dict(os.environ, {'GH_TOKEN':'synthetic-must-not-read','GITHUB_TOKEN':'synthetic-must-not-read'}), patch('socket.socket', side_effect=AssertionError('network forbidden')):
            with self.assertRaisesRegex(ValueError,'not installed'):
                cli.dispatch({'operation':'status','task_id':'a'*32,'expected_digest':'b'*64},role='kodi-repo-manager',root=self.root)
        for role in ('kodi-addon-tester','kodi-release-reviewer','kodi-addon-developer'):
            with self.assertRaises(ValueError): cli._request({'operation':'status','task_id':'a'*32,'expected_digest':'b'*64},role)

    def test_private_locator_traversal_links_and_mode_are_rejected(self):
        value = {'schema':1,'profile':contract.PROFILE,'installation_uuid':self.e['installation_uuid'],'epoch':1,
                 'key_file':str(self.base/'not-installed.pem'),'staging_authorizations':{}}
        file = self.base/'private.json'; raw = frozen.canonical(value); file.write_bytes(raw); file.chmod(0o600)
        config = dict(self.config,private_config_file=str(file),private_config_sha256=frozen.sha(raw))
        self.assertEqual(cli._private_config(self.root,config)[0],value)
        for path in (str(self.root/'..'/'private.json'),str(self.root/'private.json')):
            if Path(path).parent == self.root: (self.root/'private.json').symlink_to(file)
            with self.assertRaises(ValueError): cli._private_config(self.root,dict(config,private_config_file=path))
        file.chmod(0o644)
        with self.assertRaises(ValueError): cli._private_config(self.root,config)
        file.chmod(0o600)
        value['key_file'] = str(self.root/'..'/'project'/'key.pem'); raw=frozen.canonical(value); file.write_bytes(raw)
        with self.assertRaises(ValueError): cli._private_config(self.root,dict(config,private_config_sha256=frozen.sha(raw)))

    def test_pinned_hash_cannot_issue_or_expand_private_task_grant(self):
        task={'id':'a'*32,'sha256':'b'*64,'installation_uuid':self.e['installation_uuid'],'epoch':1}
        data={'enrollment':self.e,'payload':{'task':task,'source':{'commit':self.e['fixture_source']['commits']['1.0.0']}}}
        record={'task_sha256':task['sha256'],'source_commit':data['payload']['source']['commit'],
                'destination_sha256':frozen.sha(frozen.canonical(contract.transport_enrollment(self.e))),
                'installation_uuid':task['installation_uuid'],'epoch':1,'expires_at':frozen.utc(self.now+timedelta(minutes=30)),
                'metadata_only':True,'operations':['create_blob','create_tree','create_commit','create_ledger_branch','create_ledger_pr','update_request_pr']}
        value={'schema':1,'profile':contract.PROFILE,'installation_uuid':task['installation_uuid'],'epoch':1,
               'key_file':str(self.base/'not-installed.pem'),'staging_authorizations':{task['id']:record}}
        raw=frozen.canonical(value); file=self.base/'private.json';file.write_bytes(raw);file.chmod(0o600)
        config=dict(self.config,remote_enabled=True,private_config_file=str(file),private_config_sha256=frozen.sha(raw))
        public=self.root/'.opencode/publication-pilot.json';public.write_bytes(frozen.canonical(config))
        auth={'expires_at':record['expires_at'],'authorization_sha256':frozen.sha(raw)}
        self.assertEqual(cli.validate_staging_authority(data,auth,root=self.root,now=self.now),record)
        with self.assertRaises(ValueError): cli.validate_staging_authority(data,dict(auth,authorization_sha256='0'*64),root=self.root,now=self.now)
        future=self.now+timedelta(hours=1)
        with self.assertRaises(ValueError): cli.validate_staging_authority(data,auth,root=self.root,now=future)
        cli.validate_staging_authority(data,auth,root=self.root,now=future,observation=True)
        value['staging_authorizations']={}; raw=frozen.canonical(value);file.write_bytes(raw)
        with self.assertRaises(ValueError): cli.validate_staging_authority(data,auth,root=self.root,now=self.now)

    def test_bootstrap_is_inventory_only_and_role_overlay_is_inactive(self):
        path=fixtures.ROOT/'scripts/opencode/pilot-bootstrap.py'
        spec=importlib.util.spec_from_file_location('pilot_bootstrap',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.inventory(self.e)
        self.assertEqual(result['remote_actions'],[]);self.assertEqual(len(result['settings']['rulesets']),8)
        self.assertFalse(result['production_authorized'])
        self.assertEqual(result['seeds']['gh-pages']['files'], {})
        profile=json.loads((fixtures.ROOT/'scripts/opencode/pilot-profiles.json').read_text())
        self.assertFalse(profile['activated']);self.assertEqual(profile['overlay']['kodi-repo-manager'],{'kodi_publication':'allow'})
        self.assertNotIn('kodi_publication',json.loads((fixtures.ROOT/'scripts/opencode/profiles.json').read_text())['roles']['kodi-repo-manager']['frontmatter']['permission'])


if __name__ == '__main__': unittest.main()
