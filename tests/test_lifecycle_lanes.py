"""Independent Phase C lane-registry controls; synthetic tooling only."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import lifecycle_lanes as lanes


def identity(version, marker='a'):
    return {
        'source_files': {'validate.py': marker * 64},
        'environment': {'python': '3.12 test interpreter', 'packages': {
            'Kodistubs': {'version': version, 'record_sha256': marker * 64},
            'mypy': {'version': '2.4.0', 'record_sha256': marker * 64}}},
        'interpreter_sha256': marker * 64,
        'cache_manifest_sha256': marker * 64,
    }


def entry(version, name):
    return {'status': 'available', 'python': f'/trusted/{name}/bin/python',
            'toolkit': '/trusted/toolkit', 'cache': f'/trusted/cache/{name}',
            'identity': identity(version), 'stub_version': version,
            'coverage_limits': list(lanes.LIMITS)}


def installed():
    return {'schema': 1, 'python': '/trusted/base/bin/python',
            'toolkit': '/trusted/base/toolkit', 'cache': '/trusted/base/cache',
            'lane_environments': {
                'matrix': entry('19.0.3', 'matrix'),
                'nexus': entry('20.0.1', 'nexus'),
                'omega': entry('21.0.0', 'omega'),
                'piers': {'status': 'unverified', 'reason': 'No independently qualified 22 environment'},
            }}


class LifecycleLaneRegistryTests(unittest.TestCase):
    def test_existing_ab_installation_needs_no_new_registry(self):
        self.assertEqual(lanes.registry({'schema': 1}), {})
        self.assertIsNone(lanes.select({'schema': 1}, 'nexus'))

    def test_target_labels_are_distinct_and_do_not_supply_runtime_acceptance(self):
        self.assertEqual(lanes.TARGETS, {'matrix': ('19.5', '19.0.3'),
                                      'nexus': ('20.5', '20.0.1'),
                                      'omega': ('21.3', '21.0.0'),
                                      'piers': ('22 preview', None)})
        text = ' '.join(lanes.LIMITS)
        self.assertIn('Python 3.10', text)
        self.assertIn('not target-runtime', text)
        self.assertIn('not complete runtime or native', text)
        self.assertIn('do not establish compatibility', text)

    def test_matching_lane_selects_its_own_tooling_and_cache(self):
        value = installed()
        for lane in ('matrix', 'nexus', 'omega'):
            with self.subTest(lane=lane):
                selected = lanes.select(value, lane)
                self.assertEqual(selected['python'], f'/trusted/{lane}/bin/python')
                self.assertEqual(selected['cache'], f'/trusted/cache/{lane}')
                self.assertEqual(selected['stub_version'], lanes.TARGETS[lane][1])

    def test_selected_registry_is_a_copy_not_mutable_installation_authority(self):
        value = installed()
        selected = lanes.registry(value)
        selected['matrix']['identity']['environment']['packages']['Kodistubs']['version'] = '20.0.1'
        self.assertEqual(value['lane_environments']['matrix']['identity']['environment']['packages']['Kodistubs']['version'], '19.0.3')

    def test_unknown_target_strings_and_versions_reject(self):
        for lane in ('leia', 'matrix19.5', '19.5', 'omega/../../production', '', 21):
            with self.subTest(lane=lane), self.assertRaises(ValueError):
                lanes.select(installed(), lane)

    def test_registry_requires_exact_supported_lane_set(self):
        for mutate in ('missing', 'extra'):
            value = installed()
            if mutate == 'missing':
                del value['lane_environments']['omega']
            else:
                value['lane_environments']['leia'] = entry('18.0.0', 'leia')
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                lanes.registry(value)
        for bad in ([], 'all', True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                lanes.registry({'lane_environments': bad})

    def test_stub_major_or_exact_pinned_version_mismatch_rejects(self):
        for lane, version in (('matrix', '20.0.1'), ('nexus', '21.0.0'),
                              ('omega', '20.0.1'), ('omega', '21.0.0rc1')):
            value = installed()
            value['lane_environments'][lane]['stub_version'] = version
            with self.subTest(lane=lane, version=version), self.assertRaises(ValueError):
                lanes.registry(value)

    def test_declared_stub_identity_must_match_recorded_distribution(self):
        value = installed()
        value['lane_environments']['matrix']['identity']['environment']['packages']['Kodistubs']['version'] = '20.0.1'
        with self.assertRaisesRegex(ValueError, 'identity/stub'):
            lanes.registry(value)

    def test_unqualified_piers_remains_unverified_and_does_not_run_an_environment(self):
        called = []
        result = lanes.verify(installed(), 'piers', lambda value: called.append(value))
        self.assertEqual(result['status'], 'unverified')
        self.assertTrue(result['reason'])
        self.assertEqual(called, [])
        value = installed()
        value['lane_environments']['piers'] = entry('21.0.0', 'piers')
        with self.assertRaises(ValueError):
            lanes.registry(value)

    def test_unverified_lane_requires_reason_and_cannot_hide_extra_authority(self):
        for bad in ({'status': 'unverified', 'reason': ''},
                    {'status': 'unverified', 'reason': ' '},
                    {'status': 'unverified', 'reason': 'pending', 'publication_authorized': True}):
            value = installed()
            value['lane_environments']['piers'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                lanes.registry(value)

    def test_available_lane_fields_are_closed_and_paths_are_bound(self):
        for change in ({'native_accepted': True}, {'publication_authorized': True},
                       {'python': 'relative/python'}, {'cache': '../shared/cache'},
                       {'toolkit': ''}):
            value = installed()
            value['lane_environments']['omega'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                lanes.registry(value)

    def test_missing_coverage_limits_reject(self):
        value = installed()
        value['lane_environments']['omega']['coverage_limits'] = []
        with self.assertRaises(ValueError):
            lanes.registry(value)

    def test_verify_passes_only_selected_lane_overrides_to_trusted_reader(self):
        value = installed()
        calls = []
        def reader(current):
            calls.append(current)
            return value['lane_environments']['omega']['identity']
        selected = lanes.verify(value, 'omega', reader)
        self.assertEqual(selected['stub_version'], '21.0.0')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['python'], '/trusted/omega/bin/python')
        self.assertEqual(calls[0]['cache'], '/trusted/cache/omega')
        self.assertEqual(value['python'], '/trusted/base/bin/python')

    def test_toolkit_source_interpreter_package_and_cache_drift_reject(self):
        for field in ('source_files', 'interpreter_sha256', 'cache_manifest_sha256', 'environment'):
            changed = copy.deepcopy(installed()['lane_environments']['omega']['identity'])
            if field == 'source_files': changed[field]['validate.py'] = 'b' * 64
            elif field == 'environment': changed[field]['packages']['mypy']['version'] = 'changed'
            else: changed[field] = 'b' * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'drift'):
                lanes.verify(installed(), 'omega', lambda value: changed)


class LifecycleLaneIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.indexes = {}
        for lane in lanes.TARGETS:
            blob = ('independent-' + lane).encode()
            filename = lane + '.xml.gz'
            (self.root / filename).write_bytes(blob)
            self.indexes[lane] = {'url': f'https://mirrors.kodi.tv/addons/{lane}/addons.xml.gz',
                                  'filename': filename, 'sha256': hashlib.sha256(blob).hexdigest(),
                                  'fetched_at': '2026-10-20T23:27:37Z'}
        self.manifest = {'schema_version': 1, 'fetched_at': '2026-10-20T23:27:37Z', 'indexes': self.indexes}
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_each_lane_selects_independent_origin_hash_and_file(self):
        results = [lanes.index_identity(self.root, lane) for lane in lanes.TARGETS]
        self.assertEqual(len({r['sha256'] for r in results}), 4)
        for record in results:
            self.assertEqual(record['file'], record['lane'] + '.xml.gz')
            self.assertEqual(record['url'], self.indexes[record['lane']]['url'])
            self.assertEqual(record['sha256'], self.indexes[record['lane']]['sha256'])

    def test_wrong_index_origin_missing_or_ambiguous_lane_reject(self):
        self.indexes['omega']['url'] = 'https://other.example/omega.xml.gz'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            lanes.index_identity(self.root, 'omega')
        self.indexes['omega']['url'] = self.indexes['nexus']['url']
        self.save()
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            lanes.index_identity(self.root, 'nexus')

    def test_index_content_mutation_rejects(self):
        (self.root / 'matrix.xml.gz').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            lanes.index_identity(self.root, 'matrix')

    def test_index_path_override_cannot_escape_cache(self):
        self.indexes['omega']['filename'] = '../outside.xml.gz'
        self.save()
        with self.assertRaises(ValueError):
            lanes.index_identity(self.root, 'omega')

    def test_linked_index_rejects(self):
        (self.root / 'omega.xml.gz').unlink()
        (self.root / 'omega.xml.gz').symlink_to(self.root / 'nexus.xml.gz')
        with self.assertRaises(ValueError):
            lanes.index_identity(self.root, 'omega')

    def test_unknown_index_lane_rejects(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            lanes.index_identity(self.root, 'leia')

    def test_index_manifest_schema_version_is_not_silently_reinterpreted(self):
        self.manifest['schema_version'] = 2
        self.save()
        with self.assertRaises(ValueError):
            lanes.index_identity(self.root, 'omega')

    def test_declared_filename_cannot_differ_from_qualified_cache_filename(self):
        self.indexes['omega']['filename'] = 'nexus.xml.gz'
        self.indexes['omega']['sha256'] = self.indexes['nexus']['sha256']
        self.save()
        with self.assertRaises(ValueError):
            lanes.index_identity(self.root, 'omega')


if __name__ == '__main__':
    unittest.main()
