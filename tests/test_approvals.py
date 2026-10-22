"""Approval decisions are synthetic evidence, never authorization to publish."""
import copy
import json
import unittest

import test_intake as fixtures
import repository as r
import audit_candidate as audit
import check_publication as publication


class ApprovalTests(unittest.TestCase):
    setUp = fixtures.IntakeTests.setUp
    files = fixtures.IntakeTests.files
    admit = fixtures.IntakeTests.admit

    def action(self, status):
        return {'status': status, 'actor': 'synthetic-reviewer', 'role': 'test-reviewer',
                'recorded_at': '2026-10-22T23:00:00Z', 'rationale': 'Synthetic decision only',
                'evidence': ['synthetic-evidence-sha256-reference']}

    def approved(self, profile='production'):
        _, record = self.admit(profile=profile)
        record.update(schema_version=2, approval_policy='strict-v1', approval_lanes=['nexus', 'omega'],
                      rights_review=self.action('verified'), technical_release=self.action('approved'),
                      release_decision=self.action('approved'),
                      owner_acknowledgment={'status': 'not_recorded'}, unresolved_risks=[])
        for lane in record['compatibility']:
            record['compatibility'][lane]['runtime_test'] = dict(self.action('passed'),
                platform='Linux test fixture', kodi_version='20.5' if lane == 'nexus' else '21.3',
                scope='Synthetic full required feature scope', outstanding_tests=[])
        self.save(record, profile)
        return record

    def save(self, record, profile='production'):
        raw = r.json_bytes(record)
        (self.root / 'incoming/0.json').write_bytes(raw)
        path = self.root / f'config/{profile}.json'
        inputs = json.loads(path.read_text())
        inputs['packages'][0]['review_record_sha256'] = r.sha(raw)
        path.write_bytes(r.json_bytes(inputs))

    def reject(self, record, profile='production'):
        self.save(record, profile)
        with self.assertRaises((ValueError, AssertionError, KeyError)):
            r.production_packages(r.load_config(), profile)
        with self.assertRaises((ValueError, AssertionError, KeyError)):
            audit.reviewed_inputs(r.load_config(), profile)

    def hold_release(self, record):
        record['release_approved'] = False
        record['release_decision'] = {'status': 'pending'}

    def test_valid_v2_release_and_completed_runtime_report(self):
        self.approved()
        r.build('production')
        plan = json.loads((self.root / 'dist/production/release-plan.json').read_text())
        result = publication.site_audit(plan)
        self.assertEqual(result['release_blockers'], [])
        approval = result['approvals'][0]
        self.assertEqual(approval, plan['packages'][0]['approval'])
        self.assertEqual(approval['rights_status'], 'verified')
        self.assertEqual(approval['runtime']['omega']['status'], 'passed')
        self.assertEqual(approval['technical_release']['actor'], 'synthetic-reviewer')
        self.assertFalse(plan['publication_authorized'])

    def test_missing_rights_approval(self):
        record = self.approved()
        self.hold_release(record)
        record['rights_approved'] = False
        record['rights_review'] = {'status': 'pending'}
        self.reject(record)

    def test_acknowledgment_does_not_supply_rights(self):
        record = self.approved('candidate')
        self.hold_release(record)
        record['rights_approved'] = False
        record['rights_review'] = {'status': 'pending'}
        record['unresolved_risks'] = [{'id': 'service-rights', 'category': 'rights',
            'description': 'Unresolved service rights', 'evidence': ['synthetic-finding']}]
        record['owner_acknowledgment'] = dict(self.action('acknowledged'), role='owner', risk_ids=['service-rights'])
        self.save(record, 'candidate')
        r.build('candidate')
        result = audit.audit('candidate')
        self.assertIn('rights_approved', result['release_blockers'])
        self.assertIn('Unresolved risk: service-rights', result['release_blockers'])
        self.assertEqual(result['approvals'][0]['owner_acknowledgment']['status'], 'acknowledged')
        self.assertEqual(result['approvals'][0]['rights_status'], 'pending')
        self.assertFalse(record['rights_approved'])
        # Admission remains blocked with the identical evidence on production.
        (self.root / 'config/production.json').write_bytes((self.root / 'config/candidate.json').read_bytes())
        self.reject(record)

    def test_runtime_deferred_report_is_not_a_pass(self):
        record = self.approved('candidate')
        self.hold_release(record)
        lane = record['compatibility']['omega']
        lane['runtime_accepted'] = False
        lane['runtime_test'] = dict(self.action('deferred'), platform='Linux', kodi_version='21.3',
            scope='Authentication and playback', outstanding_tests=['Login', 'Audible VOD playback'])
        self.save(record, 'candidate')
        r.build('candidate')
        result = audit.audit('candidate')
        self.assertIn('Runtime testing deferred: omega', result['release_blockers'])
        self.assertEqual(result['approvals'][0]['runtime']['omega']['outstanding_tests'],
                         ['Login', 'Audible VOD playback'])
        self.assertFalse(result['runtime_tested'])
        plan = json.loads((self.root / 'dist/candidate/release-plan.json').read_text())
        with self.assertRaises(ValueError): publication.site_audit(plan)
        (self.root / 'config/production.json').write_bytes((self.root / 'config/candidate.json').read_bytes())
        self.reject(record)

    def test_explicit_technical_release_approval_missing(self):
        record = self.approved()
        self.hold_release(record)
        record['technical_release'] = {'status': 'pending'}
        self.reject(record)

    def test_completed_runtime_requires_attribution_evidence_and_scope(self):
        original = self.approved()
        for field in ['actor', 'role', 'recorded_at', 'rationale', 'evidence',
                      'platform', 'kodi_version', 'scope', 'outstanding_tests']:
            record = copy.deepcopy(original)
            del record['compatibility']['omega']['runtime_test'][field]
            with self.subTest(field=field): self.reject(record)
        record = copy.deepcopy(original)
        record['compatibility']['omega']['runtime_test']['evidence'] = []
        self.reject(record)

    def test_v2_retained_release_with_no_current_lanes(self):
        record = self.approved()
        record['approval_lanes'] = []
        self.save(record)
        path = self.root / 'config/production.json'
        inputs = json.loads(path.read_text()); inputs['packages'][0]['lanes'] = []
        path.write_bytes(r.json_bytes(inputs))
        r.build('production')
        self.assertEqual(audit.audit('production')['status'], 'PASS')

    def test_required_attribution_and_evidence(self):
        original = self.approved()
        for decision in ['rights_review', 'technical_release', 'release_decision']:
            for field in ['actor', 'role', 'recorded_at', 'rationale', 'evidence']:
                record = copy.deepcopy(original)
                del record[decision][field]
                with self.subTest(decision=decision, field=field): self.reject(record)
        for field, value in [('actor', ' '), ('recorded_at', '2026-02-30T00:00:00Z'),
                             ('recorded_at', '2026-10-22'), ('evidence', []), ('evidence', [' '])]:
            record = copy.deepcopy(original); record['rights_review'][field] = value
            with self.subTest(field=field, value=value): self.reject(record)

    def test_contradictory_approvals(self):
        original = self.approved()
        mutations = [lambda r: r.update(rights_approved=False),
                     lambda r: r.update(release_approved=False),
                     lambda r: r['rights_review'].update(status='rejected'),
                     lambda r: r['technical_release'].update(status='revoked'),
                     lambda r: r['compatibility']['omega']['runtime_test'].update(status='deferred'),
                     lambda r: r['compatibility']['omega']['runtime_test'].update(outstanding_tests=['Playback']),
                     lambda r: r['compatibility']['omega'].update(runtime_accepted=False),
                     lambda r: r['compatibility']['omega'].update(evidence=[])]
        for i, mutate in enumerate(mutations):
            record = copy.deepcopy(original); mutate(record)
            with self.subTest(mutation=i): self.reject(record)

    def test_unknown_policy_version_and_wrong_scope(self):
        original = self.approved()
        for field, value in [('schema_version', 3), ('schema_version', True),
                             ('approval_policy', 'owner-risk-exception'), ('approval_lanes', ['piers']),
                             ('approval_lanes', ['nexus', 'nexus', 'omega'])]:
            record = copy.deepcopy(original); record[field] = value
            with self.subTest(field=field, value=value): self.reject(record)

    def test_v2_cannot_downgrade_to_legacy(self):
        original = self.approved()
        for version in [None, 1]:
            record = copy.deepcopy(original)
            if version is None: del record['schema_version']
            else: record['schema_version'] = version
            with self.subTest(version=version): self.reject(record)

    def test_legacy_approvals_preserve_contract_and_report_limits(self):
        self.admit()
        r.build('production')
        result = audit.audit('production')
        approval = result['approvals'][0]
        self.assertEqual(approval['schema_version'], 1)
        self.assertEqual(approval['rights_status'], 'legacy_approved')
        self.assertEqual(approval['technical_release_status'], 'legacy_unspecified')
        self.assertIsNone(approval['unresolved_risks'])
        self.assertEqual(approval['runtime']['omega']['status'], 'legacy_accepted')
        self.assertTrue(approval['limitations'])
        self.assertEqual(result['release_blockers'], [])
        record = json.loads((self.root / 'incoming/0.json').read_text())
        record['schema_version'] = 1; self.save(record)
        self.assertEqual(len(r.production_packages(r.load_config())), 1)
        record['rights_approved'] = False; self.reject(record)

    def test_legacy_risk_narrative_is_preserved(self):
        _, record = self.admit(profile='candidate', approved=False)
        record['limitations'] = ['Service rights unresolved', 'Manual playback pending']
        record['native_scope'] = {'authentication': 'PENDING'}
        self.save(record, 'candidate'); r.build('candidate')
        approval = audit.audit('candidate')['approvals'][0]
        self.assertEqual(approval['recorded_limitations'], record['limitations'])
        self.assertEqual(approval['recorded_native_scope'], record['native_scope'])
        self.assertIsNone(approval['unresolved_risks'])
        self.assertEqual(approval['package_sha256'], record['package_sha256'])

    def test_pending_failed_and_deferred_results_remain_blocked(self):
        original = self.approved('candidate'); self.hold_release(original)
        for status in ['pending', 'failed', 'deferred']:
            record = copy.deepcopy(original); item = record['compatibility']['omega']
            item['runtime_accepted'] = False
            item['runtime_test'] = {'status': 'pending'} if status == 'pending' else dict(
                self.action(status), platform='Linux', kodi_version='21.3', scope='VOD',
                outstanding_tests=['Playback'])
            self.save(record, 'candidate')
            result = r.production_packages(r.load_config(), 'candidate')[0]['approval']
            self.assertIn('Runtime testing ' + status + ': omega', result['release_blockers'])
            (self.root / 'config/production.json').write_bytes((self.root / 'config/candidate.json').read_bytes())
            with self.subTest(status=status): self.reject(record)

    def test_legacy_booleans_must_be_booleans(self):
        _, original = self.admit()
        for field in ['rights_approved', 'release_approved']:
            record = copy.deepcopy(original); record[field] = 1
            with self.subTest(field=field): self.reject(record)

    def test_risk_scope_and_decision_status_controls(self):
        original = self.approved('candidate')
        self.hold_release(original)
        original['rights_approved'] = False; original['rights_review'] = {'status': 'pending'}
        original['unresolved_risks'] = [{'id': 'rights', 'category': 'rights',
            'description': 'Pending review', 'evidence': ['synthetic-finding']}]
        original['owner_acknowledgment'] = dict(self.action('acknowledged'), role='owner', risk_ids=['rights'])
        for change in ['wrong-risk', 'wrong-role', 'no-evidence', 'duplicate-risk', 'verified-rights', 'accept-risk', 'unknown-runtime']:
            record = copy.deepcopy(original)
            if change == 'wrong-risk': record['owner_acknowledgment']['risk_ids'] = ['other']
            if change == 'wrong-role': record['owner_acknowledgment']['role'] = 'tester'
            if change == 'no-evidence': record['owner_acknowledgment']['evidence'] = []
            if change == 'duplicate-risk': record['unresolved_risks'] *= 2
            if change == 'verified-rights':
                record['rights_approved'] = True; record['rights_review'] = self.action('verified')
            if change == 'accept-risk': record['owner_acknowledgment']['status'] = 'approved'
            if change == 'unknown-runtime': record['compatibility']['omega']['runtime_test']['status'] = 'waived'
            with self.subTest(change=change): self.reject(record, 'candidate')

    def test_plan_cannot_hide_risks_or_invent_decisions(self):
        self.approved('candidate'); r.build('candidate')
        path = self.root / 'dist/candidate/release-plan.json'
        original = json.loads(path.read_text())
        for change in ['blockers', 'approval']:
            plan = copy.deepcopy(original)
            if change == 'blockers': plan['release_blockers'] = []
            else: plan['packages'][0]['approval']['rights_status'] = 'pending'
            path.write_bytes(r.json_bytes(plan))
            with self.subTest(change=change), self.assertRaises(AssertionError): audit.audit('candidate')

    def test_fresh_preflight_rechecks_current_approvals(self):
        record = self.approved(); r.build('production')
        record['technical_release'] = self.action('revoked'); self.hold_release(record)
        self.save(record)
        # No builder regeneration: a former passing plan cannot approve changed inputs.
        with self.assertRaises((ValueError, AssertionError)):
            publication.site_audit(json.loads((self.root / 'dist/production/release-plan.json').read_text()))
        self.reject(record)


if __name__ == '__main__':
    unittest.main()
