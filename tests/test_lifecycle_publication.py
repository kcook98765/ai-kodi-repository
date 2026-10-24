"""Actual bound-role publication preparation, always local and production-blocked."""
import unittest

import test_lifecycle_feed as feeds


class LifecyclePublicationTests(unittest.TestCase):
    def setUp(self):
        self.feed = feeds.CandidateFeedTests()
        self.feed.setUp()
        self.addCleanup(self.feed.doCleanups)
        self.fixture = self.feed.fixture
        self.fixture.gh.overrides['repos/' + self.fixture.gh.name] = {
            'id': self.fixture.gh.repo_id, 'full_name': self.fixture.gh.name,
            'private': False, 'owner': {'id': 987654}}

    def test_manager_prepares_and_distinct_roles_evaluate_blocked_payload(self):
        self.feed.feed()
        result = self.fixture.call('build', action='publication')
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(result['simulation_eligible'])
        self.assertFalse(result['publication_authorized'])
        self.assertTrue(result['production_blockers'])
        self.assertEqual(result['remote_actions_executed'], [])
        for operation, role in [('review', 'kodi-release-reviewer'), ('qualify', 'kodi-addon-tester'),
                                ('qualify', 'kodi-repo-manager')]:
            with self.subTest(role=role):
                checked = self.fixture.call(operation, role, action='publication')
                self.assertEqual(checked['payload_sha256'], result['payload_sha256'])
                self.assertFalse(checked['independent_review_recorded'])
                self.assertEqual(checked['status'], 'BLOCKED')
        self.assertEqual(self.fixture.call('build', action='publication')['payload_sha256'],
                         result['payload_sha256'])
        self.assertFalse((self.fixture.root/'dist/production').exists())

    def test_publication_requires_complete_frozen_feed(self):
        self.fixture.prepare()
        with self.assertRaisesRegex(ValueError, 'complete candidate feed'):
            self.fixture.call('build', action='publication')

    def test_reviewer_cannot_prepare_and_developer_cannot_evaluate(self):
        self.feed.feed()
        for op, role in [('build', 'kodi-release-reviewer'), ('build', 'kodi-addon-tester'),
                         ('review', 'kodi-addon-developer'), ('qualify', 'kodi-addon-developer')]:
            with self.subTest(op=op, role=role), self.assertRaisesRegex(ValueError, 'Role denied'):
                self.fixture.call(op, role, action='publication')

    def test_roles_cannot_inject_approval_execution_or_destination(self):
        self.feed.feed()
        for action in ['approve', 'execute', 'publish', 'recover', 'request']:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.fixture.call('build', action=action)
        for name in ['destination', 'owner_id', 'output', 'source', 'synthetic', 'approval']:
            with self.subTest(field=name), self.assertRaises(ValueError):
                self.fixture.call('build', action='publication', **{name: 'injected'})
        self.assertFalse((self.fixture.out/'publication').exists())

    def test_missing_source_owner_identity_is_blocked(self):
        self.feed.feed()
        self.fixture.gh.overrides['repos/' + self.fixture.gh.name].pop('owner')
        with self.assertRaisesRegex(ValueError, 'owner numeric identity'):
            self.fixture.call('build', action='publication')

    def test_frozen_feed_change_is_rejected_before_preparation(self):
        self.feed.feed()
        site = self.feed.stage/'dist/candidate/site/index.html'
        site.write_text('changed')
        with self.assertRaises(ValueError):
            self.fixture.call('build', action='publication')
        self.assertFalse((self.fixture.out/'publication').exists())


if __name__ == '__main__':
    unittest.main()
