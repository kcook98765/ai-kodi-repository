"""Synthetic owner-risk publication decisions; never actual owner approvals."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_unofficial_integration as helpers
import approval_contract as contract
import repository as r
import audit_candidate as audit
import check_publication as publication
import qualify


class OwnerRiskTests(unittest.TestCase):
    setUp = helpers.UnofficialTests.setUp
    files = helpers.UnofficialTests.files
    admit = helpers.UnofficialTests.admit
    save = helpers.UnofficialTests.save
    reject = helpers.UnofficialTests.reject
    hold_release = helpers.UnofficialTests.hold_release
    retained_evidence = helpers.UnofficialTests.retained_evidence
    action = helpers.UnofficialTests.action
    eligible = helpers.UnofficialTests.eligible

    def owner_risk(self, profile='production'):
        record = self.eligible(profile)
        integration = record['unofficial_integration']
        integration['service_use_review'].update(status='authorization_unverified',
            upstream_provider='Synthetic provider',
            rationale='Provider terms restrict third-party integrations; provider authorization has not been verified.')
        record['unresolved_risks'][0]['description'] = 'Known provider terms restrict third-party clients; authorization unverified.'
        integration['owner_distribution_decision']['provider_authorization_exception'] = {
            'scope': 'repository_provider_authorization_gate_only',
            'upstream_provider': 'Synthetic provider', 'addon_id': 'plugin.video.example',
            'addon_version': '1.0.0', 'package_sha256': record['package_sha256'],
            'provider_authorization_verified': False,
            'provider_terms_concern': 'Known terms restrict third-party clients; owner accepts publication risk without provider permission or legal clearance.',
            'owner_accepts_risk': True, 'expires_at': '2099-01-01T00:00:00Z'}
        integration['disclosure']['release_text'] += ' Owner accepts the known provider-terms publication risk; provider authorization remains unverified.'
        self.save(record, profile)
        return record

    def exception(self, record):
        return record['unofficial_integration']['owner_distribution_decision']['provider_authorization_exception']

    def test_owner_risk_release_qualifies_with_planner_auditor_and_preflight_agreement(self):
        record = self.owner_risk()
        result = qualify.qualify('production')
        plan = json.loads((self.root/'dist/production/release-plan.json').read_text())
        approval = plan['packages'][0]['approval']
        self.assertEqual(result['independent_audit']['approvals'][0], approval)
        self.assertEqual(publication.site_audit(plan)['approvals'][0], approval)
        self.assertTrue(result['whole_site_reproducible'])
        self.assertTrue(approval['provider_authorization_exception_active'])
        self.assertTrue(approval['package_distribution_eligible'])
        self.assertEqual(approval['unofficial_integration'], record['unofficial_integration'])
        self.assertEqual(approval['unresolved_risks'], record['unresolved_risks'])
        self.assertEqual(approval['release_blockers'], [])
        self.assertFalse(approval['rights_approved'])
        self.assertFalse(approval['provider_permission_obtained'])
        self.assertEqual(approval['provider_content_authorization'], 'not_established')
        self.assertFalse(plan['publication_authorized'])

    def test_missing_malformed_or_mismatched_owner_exception(self):
        original = self.owner_risk()
        for field in self.exception(original):
            record = copy.deepcopy(original); self.exception(record).pop(field)
            with self.subTest(missing=field): self.reject(record)
        changes = [('upstream_provider','Other provider'), ('addon_id','plugin.video.other'),
            ('addon_version','1.0.1'), ('package_sha256','0'*64),
            ('provider_authorization_verified',True), ('owner_accepts_risk',False),
            ('owner_accepts_risk',1), ('scope','all_rights'), ('provider_terms_concern',' '),
            ('expires_at','2026-02-30T00:00:00Z'), ('expires_at','2099-01-01'),
            ('expires_at','2020-01-01T00:00:00Z'), ('unknown',True)]
        for field, value in changes:
            record = copy.deepcopy(original); self.exception(record)[field] = value
            with self.subTest(field=field,value=value): self.reject(record)
        for field in ('actor','role','recorded_at','rationale','evidence'):
            record=copy.deepcopy(original); record['unofficial_integration']['owner_distribution_decision'].pop(field)
            with self.subTest(attribution=field): self.reject(record)
        for status in ('declined','revoked'):
            record=copy.deepcopy(original); record['unofficial_integration']['owner_distribution_decision']['status']=status
            with self.subTest(status=status): self.reject(record)
        for value in (None, {}, [], 'accepted'):
            record=copy.deepcopy(original)
            record['unofficial_integration']['owner_distribution_decision']['provider_authorization_exception']=value
            with self.subTest(malformed=value): self.reject(record)
        record=copy.deepcopy(original)
        record['unofficial_integration']['owner_distribution_decision'].pop('provider_authorization_exception')
        self.reject(record)

    def test_truthful_missing_exception_candidate_is_blocked_in_both_reports(self):
        record=self.owner_risk('candidate'); self.hold_release(record)
        record['unofficial_integration']['owner_distribution_decision'].pop('provider_authorization_exception')
        self.save(record,'candidate'); r.build('candidate')
        plan=json.loads((self.root/'dist/candidate/release-plan.json').read_text())
        approval=audit.audit('candidate')['approvals'][0]
        self.assertEqual(plan['packages'][0]['approval'],approval)
        self.assertFalse(approval['provider_authorization_exception_active'])
        self.assertIn('Provider authorization unverified; active owner-risk decision required',approval['release_blockers'])

    def test_expiry_is_checked_again_at_preflight_and_exact_boundary(self):
        record=self.owner_risk(); r.build('production')
        plan=json.loads((self.root/'dist/production/release-plan.json').read_text())
        expiry=datetime(2099,1,1,tzinfo=timezone.utc)
        with patch.object(contract,'utc_now',return_value=expiry):
            self.reject(record)
            with self.assertRaises(ValueError): publication.site_audit(plan)
        self.hold_release(record); self.save(record)
        with patch.object(contract,'utc_now',return_value=expiry):
            report=contract.assess(record,['nexus','omega'],('plugin.video.example','1.0.0'))
            self.assertFalse(report['provider_authorization_exception_active'])
            self.assertIn('Owner provider-authorization exception inactive, future-dated or expired',report['release_blockers'])
        record['unofficial_integration']['owner_distribution_decision']['recorded_at']='2098-01-01T00:00:00Z'
        self.reject(record)

    def test_exception_cannot_replace_package_rights_attribution_or_other_gates(self):
        original=self.owner_risk('candidate'); self.hold_release(original)
        (self.root/'config/production.json').write_bytes((self.root/'config/candidate.json').read_bytes())
        for category,name in [('rights','missing-attribution'),('rights','unauthorized-video.mp4'),
            ('rights','copied-proprietary-code.py'),('rights','unlicensed-image.png'),
            ('rights','unlicensed-font.ttf'),('other','security-finding')]:
            record=copy.deepcopy(original)
            record['unresolved_risks'].append({'id':name,'category':category,
                'description':'Synthetic mandatory package-rights or security finding',
                'evidence':[self.retained_evidence('hard-risk.txt','Synthetic nonwaivable bundled asset/attribution/security finding.')]})
            record['owner_acknowledgment']['risk_ids'].append(name)
            self.save(record,'candidate')
            report=r.production_packages(r.load_config(),'candidate')[0]['approval']
            self.assertIn('Unresolved risk: '+name,report['release_blockers'])
            self.assertFalse(report['package_distribution_eligible'])
            with self.subTest(finding=name): self.reject(record)
        for status in ('pending','rejected','revoked'):
            record=copy.deepcopy(original)
            review=record['unofficial_integration']['package_distribution_review']
            if status=='pending': record['unofficial_integration']['package_distribution_review']={'status':status}
            else: review['status']=status
            with self.subTest(package_review=status): self.reject(record)

    def test_runtime_deferral_and_user_reported_results_keep_exact_scope(self):
        record=self.owner_risk('candidate'); self.hold_release(record)
        test=record['compatibility']['omega']['runtime_test']
        test.update(status='deferred',scope='User-reported login/playback; audio and recovery unverified',
            outstanding_tests=['Audible audio','Session expiry recovery'])
        record['compatibility']['omega']['runtime_accepted']=False
        self.save(record,'candidate'); r.build('candidate')
        plan=json.loads((self.root/'dist/candidate/release-plan.json').read_text())
        report=audit.audit('candidate')['approvals'][0]
        self.assertEqual(plan['packages'][0]['approval'],report)
        self.assertEqual(report['runtime']['omega'],test)
        self.assertIn('Runtime testing deferred: omega',report['release_blockers'])
        self.assertFalse(report['package_distribution_eligible'])
        (self.root/'config/production.json').write_bytes((self.root/'config/candidate.json').read_bytes())
        self.reject(record)

    def test_exception_bound_zip_with_unauthorized_assets_still_fails_rights_audit(self):
        record=self.owner_risk('candidate'); self.hold_release(record)
        names=('unlicensed-video.mp4','copied-proprietary-code.py')
        files=r.inspect_zip((self.root/'incoming/0.zip').read_bytes())[1]
        for name in names:
            files[name]=b'Synthetic bytes marked unauthorized by the retained package audit.'
            record['unresolved_risks'].append({'id':name,'category':'rights',
                'description':'Bundled member has no redistribution rights; owner risk cannot license it.',
                'evidence':[self.retained_evidence('asset-review.txt','Synthetic bundled video/code redistribution audit: unauthorized.')]})
            record['owner_acknowledgment']['risk_ids'].append(name)
        blob=r.zip_bytes(files); (self.root/'incoming/0.zip').write_bytes(blob)
        record['package_sha256']=r.sha(blob)
        record['runtime_files']={n:r.sha(data) for n,data in files.items()}
        self.exception(record)['package_sha256']=r.sha(blob)
        config_path=self.root/'config/candidate.json'; inputs=json.loads(config_path.read_text())
        inputs['packages'][0]['sha256']=r.sha(blob); config_path.write_bytes(r.json_bytes(inputs))
        self.save(record,'candidate'); r.build('candidate')
        plan=json.loads((self.root/'dist/candidate/release-plan.json').read_text())
        report=audit.audit('candidate')['approvals'][0]
        self.assertEqual(plan['packages'][0]['approval'],report)
        self.assertTrue(report['provider_authorization_exception_active'])
        self.assertFalse(report['package_distribution_eligible'])
        for name in names:
            self.assertIn('Unresolved risk: '+name,report['release_blockers'])
        (self.root/'config/production.json').write_bytes(config_path.read_bytes())
        self.reject(record)

    def test_user_reported_completed_runtime_evidence_is_preserved(self):
        record=self.owner_risk()
        test=record['compatibility']['omega']['runtime_test']
        test.update(actor='synthetic-user',role='user tester',
            rationale='Synthetic user-reported completed required testing of this candidate; no laboratory observation claimed.',
            evidence=[self.retained_evidence('user-report.txt','Synthetic user report of required features on the scoped Kodi/platform candidate.')])
        self.save(record); r.build('production')
        report=audit.audit('production')['approvals'][0]
        self.assertEqual(report['runtime']['omega'],test)
        self.assertEqual(report['release_blockers'],[])

    def test_final_approval_is_still_required(self):
        record=self.owner_risk('candidate'); self.hold_release(record)
        self.save(record,'candidate'); r.build('candidate')
        report=audit.audit('candidate')['approvals'][0]
        self.assertTrue(report['package_distribution_eligible'])
        self.assertEqual(report['release_blockers'],['release_approved'])
        (self.root/'config/production.json').write_bytes((self.root/'config/candidate.json').read_bytes())
        self.reject(record)

    def test_contradictory_owner_service_or_broad_rights_assertions_reject(self):
        original=self.owner_risk()
        mutations=[lambda x:x['unofficial_integration']['service_use_review'].update(status='terms_unresolved'),
            lambda x:x['unofficial_integration']['service_use_review'].update(provider_permission_obtained=True),
            lambda x:x['unofficial_integration']['owner_distribution_decision'].update(authorization_claimed=True),
            lambda x:x['owner_acknowledgment'].update(actor='Other owner'),
            lambda x:x.update(rights_approved=True),lambda x:x.update(release_approved=False)]
        for i,mutate in enumerate(mutations):
            record=copy.deepcopy(original); mutate(record)
            with self.subTest(mutation=i): self.reject(record)

    def test_independent_auditor_checks_exception_even_with_permissive_contract(self):
        original=self.owner_risk()
        good=contract.assess(original,['nexus','omega'],('plugin.video.example','1.0.0'))
        for field,value in [('addon_version','1.0.1'),('package_sha256','0'*64),
            ('scope','all_rights'),('upstream_provider','Other'),('owner_accepts_risk',False),
            ('expires_at','2020-01-01T00:00:00Z')]:
            record=copy.deepcopy(original); self.exception(record)[field]=value; self.save(record)
            with self.subTest(field=field),patch.object(contract,'assess',return_value=good):
                with self.assertRaises(AssertionError): audit.reviewed_inputs(r.load_config(),'production')
        record=copy.deepcopy(original); record['owner_acknowledgment']['actor']='Different owner'; self.save(record)
        with patch.object(contract,'assess',return_value=good),self.assertRaises(AssertionError):
            audit.reviewed_inputs(r.load_config(),'production')
        self.save(original); r.build('production')
        path=self.root/'dist/production/release-plan.json'; plan=json.loads(path.read_text())
        plan['packages'][0]['approval']['unofficial_integration']['owner_distribution_decision'].pop('provider_authorization_exception')
        path.write_bytes(r.json_bytes(plan))
        with self.assertRaises(AssertionError): audit.audit('production')

    @unittest.skipIf(helpers.Draft202012Validator is None,'Optional jsonschema interchange qualification unavailable')
    def test_schema_and_legacy_category_barriers(self):
        schema=json.loads((Path(__file__).parents[1]/'docs/REVIEW-RECORD-SCHEMA.json').read_text())
        validator=helpers.Draft202012Validator(schema); validator.check_schema(schema)
        original=self.owner_risk(); validator.validate(original)
        for version in (None,1,2):
            record=copy.deepcopy(original)
            if version is None: record.pop('schema_version')
            else: record['schema_version']=version
            self.assertTrue(list(validator.iter_errors(record))); self.reject(record)
        for field in self.exception(original):
            record=copy.deepcopy(original); self.exception(record).pop(field)
            with self.subTest(missing=field): self.assertTrue(list(validator.iter_errors(record)))


if __name__ == '__main__': unittest.main()
