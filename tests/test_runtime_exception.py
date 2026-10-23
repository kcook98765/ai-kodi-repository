"""Synthetic initial-release decisions, never real owner or native-test evidence."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_owner_risk as helpers
import test_unofficial_integration as schema_helpers
import approval_contract as contract
import repository as r
import audit_candidate as audit
import check_publication as publication
import qualify


class RuntimeExceptionTests(unittest.TestCase):
    setUp = helpers.OwnerRiskTests.setUp
    files = helpers.OwnerRiskTests.files
    admit = helpers.OwnerRiskTests.admit
    save = helpers.OwnerRiskTests.save
    reject = helpers.OwnerRiskTests.reject
    hold_release = helpers.OwnerRiskTests.hold_release
    retained_evidence = helpers.OwnerRiskTests.retained_evidence
    action = helpers.OwnerRiskTests.action
    eligible = helpers.OwnerRiskTests.eligible
    owner_risk = helpers.OwnerRiskTests.owner_risk

    def supporting(self, method, status='passed'):
        return {'method': method, 'status': status, 'scope': 'Synthetic scoped '+method+' observation only',
                'evidence': [self.retained_evidence(method+'.txt', 'Synthetic supplemental evidence, not real native/provider acceptance.')]}

    def finalize(self, record):
        record['release_decision'] = dict(self.action('approved'), role='owner', actor='synthetic-owner',
            runtime_exception_sha256=contract.exception_digest(record['runtime_acceptance_exception']))
        record['release_approved'] = True

    def initial(self, profile='production'):
        record = self.owner_risk(profile)
        record['approval_policy'] = contract.INITIAL_POLICY
        record['unresolved_risks'].append({'id':'runtime-coverage','category':'runtime',
            'description':'Four synthetic initial-release coverage limitations; no failed tests or security defect.',
            'evidence':[self.retained_evidence('runtime-review.txt','Synthetic independent coverage review.')]})
        record['owner_acknowledgment']['risk_ids'].append('runtime-coverage')
        scenarios = []
        for sid in ('R4','R5','R6','R2-audio'):
            audio = sid == 'R2-audio'
            scenarios.append({'id':sid,'lane':'omega','risk_id':'runtime-coverage',
                'kind':'environment_limitation' if audio else 'unobserved_functionality',
                'observation':'unavailable' if audio else 'not_observed',
                'description':'No managed audio device' if audio else 'Synthetic native scenario '+sid+' not observed',
                'supporting_evidence':[self.supporting('environment','unavailable') if audio else self.supporting('offline')]})
        ids = [s['id'] for s in scenarios]
        record['compatibility']['omega'].update(runtime_accepted=False,
            runtime_test=dict(self.action('deferred'), platform='Linux synthetic fixture', kodi_version='21.3',
                scope='Retain all required scope; only named coverage limitations accepted', outstanding_tests=ids))
        record['runtime_acceptance_exception'] = {
            'scope':'initial_release_runtime_coverage_only','addon_id':'plugin.video.example','addon_version':'1.0.0',
            'package_sha256':record['package_sha256'],'source_commit':record['source_commit'],
            'lanes':['nexus','omega'],'expires_at':'2099-01-01T00:00:00Z','scenarios':scenarios,
            'owner_decision':dict(self.action('accepted'), actor='synthetic-owner', role='owner', scenario_ids=ids, risk_ids=['runtime-coverage']),
            'independent_verification':dict(self.action('verified'), scenario_ids=ids, risk_ids=['runtime-coverage'],
                no_known_security_defects=True, core_evidence=[self.supporting('native'),self.supporting('offline')]),
        }
        self.finalize(record); self.save(record, profile)
        return record

    def test_eligible_initial_release_qualifies_and_preserves_all_results(self):
        record = self.initial()
        result = qualify.qualify('production')
        plan = json.loads((self.root/'dist/production/release-plan.json').read_text())
        approval = plan['packages'][0]['approval']
        self.assertEqual(approval,result['independent_audit']['approvals'][0])
        self.assertEqual(approval,publication.site_audit(plan)['approvals'][0])
        self.assertEqual(approval['runtime_admission'],'owner_accepted_runtime_limitations')
        self.assertTrue(approval['runtime_exception_active'])
        self.assertTrue(approval['provider_authorization_exception_active'])
        self.assertTrue(approval['package_distribution_eligible'])
        self.assertFalse(approval['rights_approved'])
        self.assertEqual(approval['runtime']['omega']['status'],'deferred')
        self.assertEqual(approval['runtime']['omega']['outstanding_tests'],['R4','R5','R6','R2-audio'])
        self.assertEqual(approval['runtime_acceptance_exception'],record['runtime_acceptance_exception'])
        self.assertEqual(approval['unresolved_risks'],record['unresolved_risks'])
        self.assertEqual(approval['release_blockers'],[])
        self.assertFalse(plan['publication_authorized'])
        self.assertEqual(plan['remote_actions_executed'],[])
        page=(self.root/'dist/production/site/index.html').read_text()
        self.assertIn('not_observed',page); self.assertIn('environment_limitation',page)
        self.assertNotIn('synthetic/offline.txt sha256:',page)

    def test_missing_fields_and_malformed_identity_fail_closed(self):
        original=self.initial()
        for field in original['runtime_acceptance_exception']:
            record=copy.deepcopy(original);record['runtime_acceptance_exception'].pop(field)
            with self.subTest(missing=field):self.reject(record)
        for field,value in [('package_sha256','0'*64),('addon_id','plugin.video.other'),('addon_version','1.0.1'),
                            ('source_commit','b'*40),('scope','waive_anything'),('lanes',['omega']),('unknown',True),
                            ('expires_at','2026-02-30T00:00:00Z'),('expires_at','2099-01-01'),('expires_at','2020-01-01T00:00:00Z')]:
            record=copy.deepcopy(original);record['runtime_acceptance_exception'][field]=value
            self.finalize(record)
            with self.subTest(field=field):self.reject(record)
        for action in ('owner_decision','independent_verification'):
            for field in original['runtime_acceptance_exception'][action]:
                record=copy.deepcopy(original);record['runtime_acceptance_exception'][action].pop(field)
                with self.subTest(action=action,field=field):self.reject(record)

    def test_missing_acknowledgment_and_owner_or_reviewer_actions(self):
        original=self.initial()
        mutations=[lambda x:x.update(owner_acknowledgment={'status':'not_recorded'}),
            lambda x:x['owner_acknowledgment'].update(actor='different-owner'),
            lambda x:x['runtime_acceptance_exception'].update(owner_decision={'status':'pending'}),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(role='tester'),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(actor='different-owner'),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(status='declined'),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(status='revoked'),
            lambda x:x['runtime_acceptance_exception'].update(independent_verification={'status':'pending'}),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(actor=' SYNTHETIC-OWNER '),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(no_known_security_defects=False),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(core_evidence=[self.supporting('offline')]),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(core_evidence=[self.supporting('native','failed')]),
        ]
        for i,mutate in enumerate(mutations):
            record=copy.deepcopy(original);mutate(record);self.finalize(record)
            with self.subTest(mutation=i):self.reject(record)

    def test_unlisted_duplicate_or_mismatched_scenarios_are_ineligible(self):
        original=self.initial()
        mutations=[lambda x:x['compatibility']['omega']['runtime_test']['outstanding_tests'].append('unlisted'),
            lambda x:x['runtime_acceptance_exception']['scenarios'].pop(),
            lambda x:x['runtime_acceptance_exception']['scenarios'].append(copy.deepcopy(x['runtime_acceptance_exception']['scenarios'][0])),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(scenario_ids=['R4']),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(risk_ids=['other']),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0].update(risk_id='unlisted-risk'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0].update(lane='piers'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][-1].update(supporting_evidence=[self.supporting('offline')]),
        ]
        for i,mutate in enumerate(mutations):
            record=copy.deepcopy(original);mutate(record);self.finalize(record)
            with self.subTest(mutation=i):self.reject(record)

    def test_failed_tests_cannot_be_represented_as_unobserved(self):
        original=self.initial()
        for mutate in [
            lambda x:x['compatibility']['omega']['runtime_test'].update(status='failed'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0].update(observation='failed'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0].update(observation='passed'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0]['supporting_evidence'][0].update(status='failed'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0]['supporting_evidence'][0].update(method='native',status='failed'),
            lambda x:x['compatibility']['omega'].update(runtime_accepted=True),
            lambda x:x['compatibility']['nexus'].update(runtime_accepted=False,runtime_test={'status':'pending'}),
        ]:
            record=copy.deepcopy(original);mutate(record);self.finalize(record);self.reject(record)

    def test_final_owner_approval_is_separate_and_binds_exact_exception(self):
        record=self.initial('candidate');self.hold_release(record);self.save(record,'candidate')
        r.build('candidate');approval=audit.audit('candidate')['approvals'][0]
        self.assertTrue(approval['runtime_exception_active'])
        self.assertTrue(approval['package_distribution_eligible'])
        self.assertEqual(approval['release_blockers'],['release_approved'])
        (self.root/'config/production.json').write_bytes((self.root/'config/candidate.json').read_bytes())
        self.reject(record)
        original=copy.deepcopy(record);self.finalize(original)
        for values in ({'role':'reviewer'},{'actor':'other-owner'},{'runtime_exception_sha256':'0'*64},
                       {'recorded_at':'2020-01-01T00:00:00Z'},{'recorded_at':'2098-01-01T00:00:00Z'},
                       {'evidence':['not-pinned']}):
            record=copy.deepcopy(original);record['release_decision'].update(values);self.reject(record)

    def test_expiry_and_future_decisions_rechecked_at_publication_preflight(self):
        record=self.initial();r.build('production')
        plan=json.loads((self.root/'dist/production/release-plan.json').read_text())
        with patch.object(contract,'utc_now',return_value=datetime(2099,1,1,tzinfo=timezone.utc)):
            with self.assertRaises(ValueError):publication.site_audit(plan)
        for action in ('owner_decision','independent_verification'):
            changed=copy.deepcopy(record);changed['runtime_acceptance_exception'][action]['recorded_at']='2098-01-01T00:00:00Z'
            self.finalize(changed);self.reject(changed)

    def test_initial_history_is_independent_and_preserves_retained_first_artifact(self):
        record=self.initial()
        identity=('plugin.video.example','1.0.0')
        first={'id':identity[0],'version':'1.0.0','sha256':record['package_sha256']}
        later=dict(first,version='1.1.0',sha256='c'*64)
        manifest=r.inspect_zip((self.root/'incoming/0.zip').read_bytes())[0]
        report=contract.assess(record,['nexus','omega'],identity,[first,later])
        self.assertTrue(report['runtime_exception_active'])
        audit.initial_runtime_gate(record,['nexus','omega'],manifest,[first,later])
        for history in ([later],[dict(first,sha256='0'*64)]):
            with self.assertRaises(ValueError):contract.assess(record,['nexus','omega'],identity,history)
            with self.assertRaises(AssertionError):audit.initial_runtime_gate(record,['nexus','omega'],manifest,history)
        with self.assertRaises(ValueError):contract.assess(record,['nexus','omega'],identity)

    def test_rights_security_static_archive_and_provider_protections_remain(self):
        original=self.initial()
        for category in ('rights','other','technical'):
            record=copy.deepcopy(original)
            record['unresolved_risks'].append({'id':'hard-finding','category':category,'description':'Nonwaivable adverse finding',
                'evidence':[self.retained_evidence('hard.txt','Synthetic known security or substantive rights defect.')]})
            record['owner_acknowledgment']['risk_ids'].append('hard-finding');self.reject(record)
        record=copy.deepcopy(original);record['compatibility']['omega']['static_accepted']=False;self.reject(record)
        record=copy.deepcopy(original);record['unofficial_integration']['package_distribution_review']={'status':'pending'};self.reject(record)
        record=copy.deepcopy(original)
        record['unofficial_integration']['owner_distribution_decision']['provider_authorization_exception']['expires_at']='2020-01-01T00:00:00Z'
        self.reject(record)
        record=copy.deepcopy(original);record['runtime_files']['default.py']='0'*64;self.reject(record)

    def test_independent_auditor_rejects_permissive_shared_contract(self):
        original=self.initial();good=contract.assess(original,['nexus','omega'],('plugin.video.example','1.0.0'),[])
        mutations=[lambda x:x['runtime_acceptance_exception'].update(package_sha256='0'*64),
            lambda x:x['runtime_acceptance_exception'].update(expires_at='2020-01-01T00:00:00Z'),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(status='declined'),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(actor='synthetic-owner'),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(no_known_security_defects=False),
            lambda x:x['runtime_acceptance_exception']['independent_verification'].update(core_evidence=[self.supporting('offline')]),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0]['supporting_evidence'][0].update(status='failed'),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0]['supporting_evidence'][0].update(evidence=['. sha256:'+'a'*64]),
            lambda x:x['compatibility']['omega']['runtime_test']['outstanding_tests'].append('extra'),
            lambda x:x['compatibility']['omega']['runtime_test'].update(status='failed'),
            lambda x:x['release_decision'].update(actor='different-owner')]
        for i,mutate in enumerate(mutations):
            record=copy.deepcopy(original);mutate(record)
            if i != len(mutations)-1:self.finalize(record)
            self.save(record)
            with self.subTest(mutation=i),patch.object(contract,'assess',return_value=good),self.assertRaises((AssertionError,KeyError)):
                audit.reviewed_inputs(r.load_config(),'production')

    def test_public_scenario_notice_and_plan_cannot_hide_limitations(self):
        self.initial();r.build('production')
        site=self.root/'dist/production/site';page=(site/'index.html').read_text()
        path=self.root/'dist/production/release-plan.json';original=json.loads(path.read_text())
        for text in (page.replace('not_observed','passed'),page.replace('No managed audio device','Audio passed')):
            (site/'index.html').write_text(text);plan=copy.deepcopy(original)
            plan['site_files']['index.html']=r.sha(text.encode());plan['site_manifest_sha256']=r.sha(r.json_bytes(plan['site_files']))
            path.write_bytes(r.json_bytes(plan))
            with self.assertRaisesRegex(AssertionError,'Public disclosure'):audit.audit('production')
        (site/'index.html').write_text(page)
        plan=copy.deepcopy(original);plan['packages'][0]['approval']['runtime_acceptance_exception']['scenarios']=[]
        path.write_bytes(r.json_bytes(plan))
        with self.assertRaises(AssertionError):audit.audit('production')

    def test_old_policy_provider_exception_cannot_waive_runtime(self):
        record=self.initial();record['approval_policy']=contract.UNOFFICIAL_POLICY;self.reject(record)
        record.pop('runtime_acceptance_exception');record['release_decision'].pop('runtime_exception_sha256');self.reject(record)
        self.hold_release(record);self.save(record)
        report=contract.assess(record,['nexus','omega'],('plugin.video.example','1.0.0'))
        self.assertTrue(report['provider_authorization_exception_active'])
        self.assertFalse(report['package_distribution_eligible'])
        self.assertIn('Runtime testing deferred: omega',report['release_blockers'])

    @unittest.skipIf(schema_helpers.Draft202012Validator is None,'Optional jsonschema unavailable')
    def test_schema_closed_objects_and_policy_downgrade(self):
        schema=json.loads((Path(__file__).parents[1]/'docs/REVIEW-RECORD-SCHEMA.json').read_text())
        validator=schema_helpers.Draft202012Validator(schema);validator.check_schema(schema)
        original=self.initial();validator.validate(original)
        mutations=[lambda x:x.update(schema_version=1),lambda x:x.update(schema_version=2),lambda x:x.pop('schema_version'),
            lambda x:x.update(approval_policy=contract.UNOFFICIAL_POLICY),lambda x:x.pop('runtime_acceptance_exception'),
            lambda x:x['runtime_acceptance_exception'].update(override=True),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0].update(observation='passed'),
            lambda x:x['runtime_acceptance_exception']['owner_decision'].update(override=True),
            lambda x:x['runtime_acceptance_exception']['scenarios'][0]['supporting_evidence'][0].update(status='failed'),
            lambda x:x['release_decision'].pop('runtime_exception_sha256')]
        for i,mutate in enumerate(mutations):
            record=copy.deepcopy(original);mutate(record)
            with self.subTest(mutation=i):self.assertTrue(list(validator.iter_errors(record)))


if __name__ == '__main__':unittest.main()
