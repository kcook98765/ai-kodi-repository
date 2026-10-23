"""Synthetic v3 release evidence; no provider access, approval or runtime execution."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_approvals as helpers
import approval_contract as contract
import repository as r
import audit_candidate as audit
import check_publication as publication
import qualify

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


class UnofficialTests(unittest.TestCase):
    setUp = helpers.ApprovalTests.setUp
    files = helpers.ApprovalTests.files
    admit = helpers.ApprovalTests.admit
    save = helpers.ApprovalTests.save
    reject = helpers.ApprovalTests.reject
    hold_release = helpers.ApprovalTests.hold_release

    def retained_evidence(self, name, text):
        path = self.root/'incoming/synthetic'/name
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        return 'synthetic/'+name+' sha256:'+r.sha(path.read_bytes())

    def action(self, status):
        return dict(helpers.ApprovalTests.action(self, status),
                    evidence=[self.retained_evidence('retained-review.txt',
                        'Synthetic independent review and scoped runtime/owner fixture evidence only. No real provider or runtime claims.')])

    def eligible(self, profile='production'):
        files = self.files()
        files['NOTICE.txt'] = (b'Independent unofficial integration. No provider affiliation, '
                               b'endorsement or support. Support: https://example.invalid/issues')
        _, record = self.admit(files, profile=profile)
        record.update(schema_version=3, approval_policy='unofficial-integration-v1',
            approval_lanes=['nexus', 'omega'], rights_approved=False,
            rights_review={'status': 'pending'}, technical_release=self.action('approved'),
            release_decision=self.action('approved'),
            unresolved_risks=[{'id': 'terms-1', 'category': 'provider_terms',
                'description': 'Unresolved applicability of provider client terms; no authorization established.',
                'evidence': [self.retained_evidence('terms-review.txt',
                    'Synthetic unresolved service-terms applicability; no independent authorization requirement found in this synthetic scenario.')]}],
            owner_acknowledgment=dict(self.action('acknowledged'), actor='synthetic-owner',
                                      role='owner', risk_ids=['terms-1']))
        for lane in record['compatibility']:
            record['compatibility'][lane]['runtime_test'] = dict(self.action('passed'),
                platform='Linux synthetic fixture', kodi_version='20.5' if lane == 'nexus' else '21.3',
                scope='All required synthetic fixture features', outstanding_tests=[])
        record['unofficial_integration'] = {
            'package_distribution_review': dict(self.action('verified'), scope='all_distributed_materials',
                rationale='Original independently developed code and art, compatible MIT notices/attribution; all publication assets reviewed. No independent distribution authorization restriction applies.'),
            'service_use_review': dict(self.action('terms_unresolved'),
                scope='runtime_service_content_and_marks', risk_ids=['terms-1'],
                provider_permission_obtained=False, provider_content_authorization='not_established'),
            'owner_distribution_decision': dict(self.action('accepted'), actor='synthetic-owner',
                role='owner', risk_ids=['terms-1'], authorization_claimed=False),
            'disclosure': {'package_path': 'NOTICE.txt', 'package_sha256': r.sha(files['NOTICE.txt']),
                'release_text': 'Independent unofficial integration; no affiliation, endorsement or provider support. '
                'Support: https://example.invalid/issues. Provider terms https://example.invalid/terms remain unresolved. '
                'Provider permission and content authorization are not established. Accounts and entitlements remain required. '
                'Owner distribution acceptance grants no legal or content rights.'}}
        self.save(record, profile)
        return record

    def test_eligible_release_passes_all_consumers_without_broad_rights(self):
        record = self.eligible()
        result = qualify.qualify('production')
        self.assertTrue(result['whole_site_reproducible'])
        self.assertEqual(len(result['url_validation']['selection_cases']), 17)
        plan = json.loads((self.root/'dist/production/release-plan.json').read_text())
        approval = publication.site_audit(plan)['approvals'][0]
        self.assertEqual(approval, result['independent_audit']['approvals'][0])
        self.assertTrue(approval['package_distribution_eligible'])
        self.assertFalse(approval['rights_approved'])
        self.assertEqual(approval['rights_status'], 'pending')
        self.assertEqual(approval['accepted_terms_risks'], record['unresolved_risks'])
        self.assertEqual(approval['unresolved_risks'], record['unresolved_risks'])
        self.assertEqual(approval['provider_content_authorization'], 'not_established')
        self.assertEqual(approval['release_blockers'], [])
        self.assertFalse(approval['publication_authorized'])
        self.assertFalse(plan['publication_authorized'])

    def test_missing_and_contradictory_actions_fail_closed(self):
        original = self.eligible()
        (self.root/'config/candidate.json').write_bytes((self.root/'config/production.json').read_bytes())
        mutations = []
        for name, statuses in [('package_distribution_review', ['pending','rejected','revoked']),
                               ('service_use_review', ['pending','blocked','revoked']),
                               ('owner_distribution_decision', ['pending','declined','revoked'])]:
            for status in statuses:
                record = copy.deepcopy(original)
                action = record['unofficial_integration'][name]
                if status == 'pending': record['unofficial_integration'][name] = {'status':status}
                else: action['status'] = status
                mutations.append((name+':'+status, record))
        for name,record in mutations:
            with self.subTest(action=name): self.reject(record)
            self.hold_release(record)
            self.save(record, 'candidate')
            for consumer in (r.production_packages, audit.reviewed_inputs):
                items = consumer(r.load_config(), 'candidate')
                item = next(iter(items.values())) if isinstance(items, dict) else items[0]
                approval = item['approval']
                self.assertFalse(approval['package_distribution_eligible'])
                self.assertTrue(approval['release_blockers'])

    def test_owner_acknowledgment_alone_cannot_accept_terms(self):
        record = self.eligible('candidate'); self.hold_release(record)
        record['unofficial_integration']['owner_distribution_decision'] = {'status':'pending'}
        self.save(record, 'candidate'); r.build('candidate')
        approval = audit.audit('candidate')['approvals'][0]
        self.assertEqual(approval['accepted_terms_risks'], [])
        self.assertFalse(approval['package_distribution_eligible'])
        self.assertIn('Unresolved risk: terms-1', approval['release_blockers'])
        with self.assertRaises(ValueError):
            publication.site_audit(json.loads((self.root/'dist/candidate/release-plan.json').read_text()))

    def test_nonwaivable_package_and_operating_restrictions(self):
        original = self.eligible()
        original_blob = (self.root/'incoming/0.zip').read_bytes()
        original_intake = (self.root/'config/production.json').read_bytes()
        findings = [('rights', 'unauthorized-provider-image.jpg'), ('rights', 'unlicensed-video.mp4'),
                    ('rights', 'copied-provider-code.py'), ('rights', 'unlicensed-font.ttf'),
                    ('rights', 'copied-provider-binary.so'), ('rights', 'missing-attribution'),
                    ('rights', 'distribution-authorization-required'), ('other', 'operation-authorization-required')]
        for category,name in findings:
            (self.root/'incoming/0.zip').write_bytes(original_blob)
            (self.root/'config/production.json').write_bytes(original_intake)
            record = copy.deepcopy(original)
            # Add real synthetic bytes for asset findings and bind the new ZIP.
            if '.' in name:
                files = self.files(); files['NOTICE.txt'] = b'Independent unofficial; no affiliation. Project support.'
                files[name] = b'Synthetic unlicensed asset finding, not actual provider content.'
                blob = r.zip_bytes(files); (self.root/'incoming/0.zip').write_bytes(blob)
                record['package_sha256'] = r.sha(blob)
                record['runtime_files'] = {n:r.sha(b) for n,b in files.items()}
                record['unofficial_integration']['disclosure']['package_sha256'] = r.sha(files['NOTICE.txt'])
                path = self.root/'config/production.json'; inputs = json.loads(path.read_text())
                inputs['packages'][0]['sha256'] = r.sha(blob); path.write_bytes(r.json_bytes(inputs))
            record['unresolved_risks'].append({'id':name, 'category':category,
                'description':'Independent authorization/attribution requirement remains unsatisfied.',
                'evidence':['synthetic/adverse-review.txt sha256:'+'c'*64]})
            record['owner_acknowledgment']['risk_ids'].append(name)
            self.hold_release(record)
            assessment = contract.assess(record, ['nexus','omega'])
            self.assertIn('Unresolved risk: '+name, assessment['release_blockers'])
            self.assertFalse(assessment['package_distribution_eligible'])
            with self.subTest(finding=name): self.reject(record)

    def test_version_scope_dates_evidence_and_authorization_claims(self):
        original = self.eligible()
        changes = [lambda x:x.pop('schema_version'),
            lambda x:x.update(schema_version=True), lambda x:x.update(schema_version=4),
            lambda x:x.update(schema_version=2), lambda x:x.update(schema_version=1),
            lambda x:x.update(approval_policy='strict-v1'), lambda x:x.update(approval_lanes=['omega']),
            lambda x:x.update(rights_approved=True, rights_review=self.action('verified')),
            lambda x:x.update(rights_review=self.action('revoked')),
            lambda x:x['unofficial_integration'].update(override=True),
            lambda x:x['unofficial_integration']['package_distribution_review'].update(override=True),
            lambda x:x['unofficial_integration']['service_use_review'].update(provider_permission_obtained=True),
            lambda x:x['unofficial_integration']['service_use_review'].update(provider_content_authorization='authorized'),
            lambda x:x['unofficial_integration']['owner_distribution_decision'].update(authorization_claimed=True)]
        for name in ('package_distribution_review','service_use_review','owner_distribution_decision'):
            for field,value in [('recorded_at','2026-02-30T00:00:00Z'),('actor',''),('rationale',''),
                                ('evidence',[]),('evidence',['https://example.invalid/unpinned']),
                                ('evidence',['../escape sha256:'+'a'*64])]:
                changes.append(lambda x,n=name,f=field,v=value:x['unofficial_integration'][n].update({f:v}))
        for i,change in enumerate(changes):
            record = copy.deepcopy(original); change(record)
            with self.subTest(change=i): self.reject(record)

    def test_owner_scope_and_review_independence(self):
        original = self.eligible()
        for name in ('owner_acknowledgment','service_use_review','owner_distribution_decision'):
            for ids in ([], ['terms-1','terms-1'], ['other'], ['terms-1','extra']):
                record = copy.deepcopy(original)
                action = record[name] if name == 'owner_acknowledgment' else record['unofficial_integration'][name]
                action['risk_ids'] = ids
                with self.subTest(name=name,ids=ids): self.reject(record)
        for name in ('package_distribution_review','service_use_review'):
            record = copy.deepcopy(original)
            record['unofficial_integration'][name]['actor'] = ' SYNTHETIC-OWNER '
            self.reject(record)
        for name in ('owner_acknowledgment','owner_distribution_decision'):
            record = copy.deepcopy(original)
            action = record[name] if name == 'owner_acknowledgment' else record['unofficial_integration'][name]
            action['role'] = 'tester'; self.reject(record)
        record = copy.deepcopy(original); record['owner_acknowledgment'] = {'status':'not_recorded'}
        self.reject(record)

    def test_multiple_terms_findings_remain_unresolved_and_visible(self):
        record = self.eligible()
        risk = copy.deepcopy(record['unresolved_risks'][0]); risk['id']='terms-2'
        record['unresolved_risks'].append(risk)
        for action in (record['owner_acknowledgment'], record['unofficial_integration']['service_use_review'],
                       record['unofficial_integration']['owner_distribution_decision']):
            action['risk_ids'].append('terms-2')
        self.save(record); r.build('production')
        approval = audit.audit('production')['approvals'][0]
        self.assertEqual(len(approval['accepted_terms_risks']), 2)
        self.assertEqual(approval['unresolved_risks'], record['unresolved_risks'])

    def test_deferred_pending_failed_and_static_gates_remain_blockers(self):
        original = self.eligible('candidate')
        for status in ('pending','deferred','failed'):
            record = copy.deepcopy(original); self.hold_release(record)
            entry = record['compatibility']['omega']; entry['runtime_accepted']=False
            if status == 'pending': entry['runtime_test']={'status':'pending'}
            else: entry['runtime_test'].update(status=status, outstanding_tests=['Required playback/audio'])
            self.save(record, 'candidate'); r.build('candidate')
            approval = audit.audit('candidate')['approvals'][0]
            self.assertFalse(approval['package_distribution_eligible'])
            self.assertEqual(approval['runtime']['omega']['status'], status)
            (self.root/'config/production.json').write_bytes((self.root/'config/candidate.json').read_bytes())
            self.reject(record)
        record = copy.deepcopy(original); record['compatibility']['omega']['static_accepted']=False
        self.reject(record, 'candidate')

    def test_missing_empty_unsafe_or_unbound_disclosure(self):
        original = self.eligible()
        for change in ('missing','empty-text','path','hash','unknown','empty-member'):
            record = copy.deepcopy(original); notice = record['unofficial_integration']['disclosure']
            if change == 'missing': record['unofficial_integration'].pop('disclosure')
            if change == 'empty-text': notice['release_text']=' '
            if change == 'path': notice['package_path']='../NOTICE.txt'
            if change == 'hash': notice['package_sha256']='0'*64
            if change == 'unknown': notice['package_path']='absent.txt'
            if change == 'empty-member':
                files=self.files(); files['NOTICE.txt']=b' '
                blob=r.zip_bytes(files); (self.root/'incoming/0.zip').write_bytes(blob)
                record['runtime_files']={n:r.sha(b) for n,b in files.items()}
                record['package_sha256']=r.sha(blob); notice['package_sha256']=r.sha(b' ')
                path=self.root/'config/production.json'; inputs=json.loads(path.read_text())
                inputs['packages'][0]['sha256']=r.sha(blob); path.write_bytes(r.json_bytes(inputs))
            with self.subTest(change=change): self.reject(record)

    def test_public_disclosure_escaped_complete_and_independently_checked(self):
        record = self.eligible()
        record['unofficial_integration']['disclosure']['release_text'] += ' <script>alert("synthetic")</script> & terms'
        self.save(record); r.build('production')
        site=self.root/'dist/production/site'; page=(site/'index.html').read_text()
        self.assertIn('&lt;script&gt;',page); self.assertNotIn('<script>',page)
        audit.audit('production')
        plan_path=self.root/'dist/production/release-plan.json'; plan=json.loads(plan_path.read_text())
        for changed in (page.replace('&lt;script&gt;','<script>'),
                        page.replace('Owner distribution acceptance','Altered notice'),
                        page.replace('<section ', '<!-- <section ').replace('</section>', '</section> -->'),
                        page.replace('<section ', '<div hidden><section ').replace('</section>', '</section></div>'),
                        page.replace('<section ', '<style>section{display:none}</style><section ')):
            (site/'index.html').write_text(changed)
            plan['site_files']['index.html']=r.sha(changed.encode())
            plan['site_manifest_sha256']=r.sha(r.json_bytes(plan['site_files']))
            plan_path.write_bytes(r.json_bytes(plan))
            with self.assertRaisesRegex(AssertionError,'Public disclosure'): audit.audit('production')
            with self.assertRaises(AssertionError): publication.site_audit(plan)

    def test_forged_plan_cannot_hide_pending_rights_or_terms_or_eligibility(self):
        self.eligible(); r.build('production')
        path=self.root/'dist/production/release-plan.json'; original=json.loads(path.read_text())
        for key,value in [('rights_status','verified'),('accepted_terms_risks',[]),
                          ('unresolved_risks',[]),('package_distribution_eligible',False),
                          ('provider_content_authorization','authorized')]:
            plan=copy.deepcopy(original); plan['packages'][0]['approval'][key]=value
            path.write_bytes(r.json_bytes(plan))
            with self.subTest(field=key),self.assertRaises(AssertionError): audit.audit('production')

    def test_independent_production_predicate_survives_shared_contract_error(self):
        record = self.eligible(); good = contract.assess(record, ['nexus','omega'])
        self.hold_release(record); record['unofficial_integration']['owner_distribution_decision']={'status':'pending'}
        record['release_approved']=True; record['release_decision']=self.action('approved')
        self.save(record)
        with patch.object(contract,'assess',return_value=good),self.assertRaises((AssertionError,KeyError)):
            audit.reviewed_inputs(r.load_config(),'production')

    def test_current_input_or_toolchain_mutation_invalidates_preflight(self):
        record = self.eligible(); r.build('production')
        path=self.root/'dist/production/release-plan.json'; original=json.loads(path.read_text())
        for key in ('approval_contract_sha256','review_schema_sha256','auditor_sha256','qualifier_sha256','preflight_sha256'):
            plan=copy.deepcopy(original); plan['toolchain'][key]='0'*64; path.write_bytes(r.json_bytes(plan))
            with self.subTest(pin=key),self.assertRaises((ValueError,AssertionError)): publication.site_audit(plan)
        path.write_bytes(r.json_bytes(original))
        record['unresolved_risks'][0]['evidence']=['synthetic/new-terms.txt sha256:'+'d'*64]
        self.save(record)
        with self.assertRaises((ValueError,AssertionError)): publication.site_audit(original)

    @unittest.skipIf(Draft202012Validator is None, 'Optional jsonschema interchange qualification unavailable')
    def test_interchange_schema_versions_and_closed_v3_decisions(self):
        schema = json.loads((Path(__file__).parents[1]/'docs/REVIEW-RECORD-SCHEMA.json').read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        original = self.eligible()
        validator.validate(original)
        for name in ('package_distribution_review','service_use_review','owner_distribution_decision'):
            record = copy.deepcopy(original); self.hold_release(record)
            record['unofficial_integration'][name] = {'status':'pending'}
            validator.validate(record)
            record['unofficial_integration'][name]['actor']='invented-pending-action'
            self.assertTrue(list(validator.iter_errors(record)))
        for change in (lambda x:x.update(schema_version=2), lambda x:x.update(schema_version=1),
                       lambda x:x.pop('schema_version'), lambda x:x.update(schema_version=True),
                       lambda x:x.update(approval_policy='strict-v1'),
                       lambda x:x['unofficial_integration']['package_distribution_review'].update(override=True),
                       lambda x:x['unofficial_integration']['service_use_review'].update(provider_permission_obtained=True)):
            record=copy.deepcopy(original); change(record)
            self.assertTrue(list(validator.iter_errors(record)))
        # Strip only v3 fields: strict v2 must still reject provider_terms.
        record=copy.deepcopy(original); record.pop('unofficial_integration')
        record.update(schema_version=2,approval_policy='strict-v1'); self.hold_release(record)
        self.assertTrue(list(validator.iter_errors(record)))
        self.reject(record)
        record.update(unresolved_risks=[],owner_acknowledgment={'status':'not_recorded'})
        validator.validate(record)  # Truthful blocked v2 still has its original shape.
        legacy={k:copy.deepcopy(original[k]) for k in ('package_sha256','runtime_files','source_repository',
            'source_commit','fixture_only','rights_approved','release_approved','compatibility')}
        for item in legacy['compatibility'].values(): item.pop('runtime_test')
        legacy.update(rights_approved=True)
        validator.validate(legacy)
        legacy['schema_version']=1; validator.validate(legacy)

    def test_v3_secret_payload_cannot_pass_publication(self):
        record=self.eligible(); files=self.files()
        files['NOTICE.txt']=b'Independent unofficial, no affiliation; project support.'
        files['default.py']=b'# Synthetic credential control: gh'+b'p_'+b'A'*36+b'\n'
        blob=r.zip_bytes(files); (self.root/'incoming/0.zip').write_bytes(blob)
        record['package_sha256']=r.sha(blob); record['runtime_files']={n:r.sha(b) for n,b in files.items()}
        record['unofficial_integration']['disclosure']['package_sha256']=r.sha(files['NOTICE.txt'])
        path=self.root/'config/production.json'; inputs=json.loads(path.read_text())
        inputs['packages'][0]['sha256']=r.sha(blob); path.write_bytes(r.json_bytes(inputs))
        self.save(record); r.build('production')
        plan=json.loads((self.root/'dist/production/release-plan.json').read_text())
        with self.assertRaisesRegex(ValueError,'Credential pattern'): publication.site_audit(plan)

    def test_empty_lanes_require_retained_hash_and_original_runtime_acceptance(self):
        record = self.eligible(); record['approval_lanes']=[]
        path=self.root/'config/production.json'; inputs=json.loads(path.read_text()); inputs['packages'][0]['lanes']=[]
        path.write_bytes(r.json_bytes(inputs)); self.reject(record)
        ledger={'packages':[{'id':'plugin.video.example','version':'1.0.0','sha256':record['package_sha256']}]}
        (self.root/'releases/manifest.json').write_bytes(r.json_bytes(ledger))
        self.save(record); r.build('production'); audit.audit('production')
        record['compatibility']['omega']['runtime_accepted']=False
        record['compatibility']['omega']['runtime_test']={'status':'pending'}
        self.reject(record)


if __name__ == '__main__': unittest.main()
