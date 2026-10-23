"""Real-package qualification uses synthetic packages, never release approvals."""
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import repository as r
import audit_candidate as audit
import check_publication as publication
import qualify as q


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['config', 'packages', 'releases']:
            shutil.copytree(r.ROOT / name, self.root / name)
        shutil.copy(r.ROOT / 'LICENSE', self.root / 'LICENSE')
        (self.root / 'incoming').mkdir()
        # Synthetic admission tests must not inherit the live release ledger or
        # private production intake when a real add-on has been published.
        (self.root / 'config/production.json').write_bytes(r.json_bytes({'packages': [], 'external_dependencies': {}}))
        (self.root / 'releases/manifest.json').write_bytes(r.json_bytes({'schema': 1, 'packages': []}))
        for module in [r, audit, publication, q]:
            p = patch.object(module, 'ROOT', self.root)
            p.start()
            self.addCleanup(p.stop)

    def files(self, aid='plugin.video.example', floor='3.0.1'):
        manifest = ET.fromstring(f'''<addon id="{aid}" version="1.0.0"
            name="Example" provider-name="Synthetic tests">
          <requires><import addon="xbmc.python" version="{floor}"/></requires>
          <extension point="xbmc.python.pluginsource" library="default.py"><provides>video</provides></extension>
          <extension point="xbmc.addon.metadata"><summary>Example</summary>
            <description>Synthetic package</description><platform>all</platform>
            <license>MIT</license><assets><icon>resources/icon.png</icon></assets>
          </extension></addon>''')
        return {'addon.xml': r.xml_bytes(manifest), 'default.py': b'# Synthetic runtime\n',
                'LICENSE.txt': b'MIT\n', 'resources/icon.png': b'synthetic artwork'}

    def admit(self, files=None, lanes=None, profile='production', approved=True, ver=None):
        files = self.files() if files is None else files
        if ver:
            manifest = r.parse_xml(files['addon.xml']); manifest.set('version', ver)
            files['addon.xml'] = r.xml_bytes(manifest)
        lanes = ['nexus', 'omega'] if lanes is None else lanes
        blob = r.zip_bytes(files)
        stem = str(len(list((self.root / 'incoming').glob('*.zip'))))
        record = {'package_sha256': r.sha(blob), 'runtime_files': {n:r.sha(b) for n,b in files.items()},
                  'source_repository': 'https://github.com/example/synthetic', 'source_commit': 'a'*40,
                  'fixture_only': False, 'release_approved': approved, 'rights_approved': approved,
                  'compatibility': {lane: {'static_accepted': approved, 'runtime_accepted': approved,
                                         'evidence': ['synthetic-test-only']} for lane in lanes}}
        raw = r.json_bytes(record)
        (self.root / f'incoming/{stem}.zip').write_bytes(blob)
        (self.root / f'incoming/{stem}.json').write_bytes(raw)
        path = self.root / f'config/{profile}.json'
        inputs = json.loads(path.read_text()) if path.exists() else {'packages': [], 'external_dependencies': {}}
        inputs['packages'].append({'zip': f'{stem}.zip', 'sha256': r.sha(blob),
                                  'review_record': f'{stem}.json', 'review_record_sha256': r.sha(raw), 'lanes': lanes})
        path.write_bytes(r.json_bytes(inputs))
        return inputs, record

    def test_valid_video_publication_and_lane_catalogs(self):
        self.admit()
        r.build('production')
        self.assertEqual(audit.audit('production')['status'], 'PASS')
        plan = json.loads((self.root / 'dist/production/release-plan.json').read_text())
        self.assertEqual(publication.site_audit(plan)['status'], 'PASS')
        for lane in ['matrix', 'nexus', 'omega', 'piers']:
            self.assertEqual('plugin.video.example' in plan['catalogs'][lane]['ids'], lane in ['nexus', 'omega'])
        self.assertNotIn('Only the repository installer', (self.root / 'dist/production/site/index.html').read_text())

    def test_numeric_api_floor_all_four_catalogs(self):
        self.admit(self.files(floor='3.0.0'), lanes=['matrix', 'nexus', 'omega', 'piers'])
        r.build('production')
        self.assertEqual(audit.audit('production')['status'], 'PASS')

    def test_matrix_cannot_satisfy_nexus_python_floor(self):
        self.admit(lanes=['matrix'])
        with self.assertRaisesRegex(ValueError, 'Required dependency'): r.build('production')

    def test_size_entry_and_expanded_resource_limits(self):
        blob = r.zip_bytes(self.files())
        for constant in ['MAX_ZIP_BYTES', 'MAX_ENTRIES', 'MAX_RUNTIME_BYTES']:
            with self.subTest(limit=constant), patch.object(r, constant, 1), self.assertRaisesRegex(ValueError, 'limit'):
                r.inspect_zip(blob)

    def test_noncanonical_archive_is_still_rejected_by_independent_audit(self):
        self.admit(); r.build('production')
        original = r.zip_bytes(self.files())
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, 'w') as z:
            for name in reversed(source.namelist()): z.writestr(name, source.read(name))
        with self.assertRaises(AssertionError): audit.archive_files(output.getvalue())

    def test_stale_review_hash_and_external_snapshot_stay_blocked(self):
        self.admit(); r.build('production')
        path = self.root / 'incoming/0.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'Review record hash'): r.build('production')
        with self.assertRaises(AssertionError): audit.audit('production')
        path = self.root / 'config/production.json'
        inputs = json.loads(path.read_text()); inputs['external_dependencies'] = {'inputstream.adaptive':'99.0.0'}
        path.write_bytes(r.json_bytes(inputs))
        with self.assertRaisesRegex(ValueError, 'separately reviewed adapter'): r.build('production')

    def test_general_production_qualification_and_loopback(self):
        self.admit()
        result = q.qualify('production')
        self.assertTrue(result['whole_site_reproducible'])
        self.assertEqual(len(result['url_validation']['selection_cases']), 17)
        self.assertTrue(result['url_validation']['loopback_http'])

    def test_skin_structure_supported_but_gui_dependency_is_not_assumed(self):
        files = self.files('skin.example')
        root = r.parse_xml(files['addon.xml'])
        ext = root.find("extension[@point='xbmc.python.pluginsource']")
        ext.attrib = {'point': 'xbmc.gui.skin'}
        ET.SubElement(ext, 'res', {'default': 'true', 'folder': '1080i', 'width': '1920', 'height': '1080'})
        root.find('requires/import').attrib = {'addon': 'xbmc.gui', 'version': '5.15.0'}
        files['addon.xml'] = r.xml_bytes(root)
        files['1080i/Home.xml'] = b'<window/>'
        self.assertEqual(r.inspect_zip(r.zip_bytes(files))[0].get('id'), 'skin.example')
        self.admit(files)
        with self.assertRaisesRegex(ValueError, 'Required dependency'): r.build('production')

    def test_candidate_reports_blockers_and_cannot_pass_publication(self):
        self.admit(profile='candidate', approved=False)
        r.build('candidate')
        self.assertEqual(audit.audit('candidate')['status'], 'PASS')
        plan = json.loads((self.root / 'dist/candidate/release-plan.json').read_text())
        self.assertTrue(plan['release_blockers'])
        with self.assertRaises(ValueError): publication.site_audit(plan)
        # The same unapproved input remains inadmissible to production.
        shutil.copy(self.root / 'config/candidate.json', self.root / 'config/production.json')
        with self.assertRaisesRegex(ValueError, 'approval'): r.build('production')

    def test_invalid_manifest_identity_version_and_dependencies(self):
        for change in ['xml', 'id', 'version', 'dependency', 'optional', 'duplicate', 'requires-child']:
            files = self.files(); root = r.parse_xml(files['addon.xml'])
            if change == 'id': root.set('id', '../escape')
            if change == 'version': root.set('version', '1.0.bad')
            if change == 'dependency': root.find('requires/import').set('version', 'invalid')
            if change == 'optional': root.find('requires/import').set('optional', 'yes')
            if change == 'duplicate': root.find('requires').append(copy.deepcopy(root.find('requires/import')))
            if change == 'requires-child': ET.SubElement(root.find('requires'), 'improt')
            files['addon.xml'] = b'<broken' if change == 'xml' else r.xml_bytes(root)
            with self.subTest(change=change), self.assertRaises((ValueError, ET.ParseError)):
                r.zip_bytes(files)

    def test_development_filenames_and_portable_collisions(self):
        for name in ['CONTRIBUTING.md', 'agents.MD', 'credentials.json', 'profile/session.json',
                     'resources/a.pyc', 'resources/icon.png/child', 'resources/ICON.png', 'resources/file.',
                     'resources/CON', 'resources/a\x01b']:
            files = self.files(); files[name] = b'bad'
            # Handcraft ZIP to exercise admission independently of builder validation.
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as z:
                for n,b in files.items(): z.writestr('plugin.video.example/' + n, b)
            with self.subTest(name=name), self.assertRaises(ValueError): r.inspect_zip(out.getvalue())

    def test_approval_and_hash_failures_are_independently_rejected(self):
        self.admit(); r.build('production')
        review = self.root / 'incoming/0.json'
        original = json.loads(review.read_text())
        rejected_runtime = copy.deepcopy(original['compatibility'])
        rejected_runtime['nexus']['runtime_accepted'] = False
        for field, value in [('rights_approved', False), ('release_approved', False),
                             ('source_commit', 'bad'), ('package_sha256', '0'*64),
                             ('runtime_files', {'addon.xml':'0'*64}),
                             ('compatibility', rejected_runtime)]:
            changed = copy.deepcopy(original); changed[field] = value
            review.write_bytes(r.json_bytes(changed))
            inputs = json.loads((self.root / 'config/production.json').read_text())
            inputs['packages'][0]['review_record_sha256'] = r.sha(review.read_bytes())
            (self.root / 'config/production.json').write_bytes(r.json_bytes(inputs))
            # Keep the generated plan's input binding coherent so the auditor
            # reaches the actual admission predicates, not an earlier stale hash.
            plan_path = self.root / 'dist/production/release-plan.json'
            plan = json.loads(plan_path.read_text())
            plan['input_config_sha256'] = r.sha((self.root / 'config/production.json').read_bytes())
            plan_path.write_bytes(r.json_bytes(plan))
            with self.subTest(field=field):
                with patch.object(audit, 'reviewed_inputs', wraps=audit.reviewed_inputs) as admission:
                    with self.assertRaises((AssertionError, ValueError)): audit.audit('production')
                    admission.assert_called_once()
                with self.assertRaises((ValueError, KeyError)): r.build('production')

    def test_independent_auditor_rejects_unlisted_package_and_lane(self):
        self.admit(); r.build('production')
        path = self.root / 'dist/production/release-plan.json'
        original = json.loads(path.read_text())
        for mutation in ['extra', 'lane']:
            plan = copy.deepcopy(original)
            if mutation == 'extra': plan['packages'].append(copy.deepcopy(plan['packages'][0]))
            else: plan['packages'][0]['lanes'].append('piers')
            path.write_bytes(r.json_bytes(plan))
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, ValueError)):
                audit.audit('production')

    def test_historical_package_retained_without_current_lane(self):
        self.admit(lanes=[], ver='1.0.0')
        self.admit(ver='1.1.0')
        inputs = json.loads((self.root / 'config/production.json').read_text())
        (self.root / 'releases/manifest.json').write_bytes(r.json_bytes({'packages': [
            {'id': 'plugin.video.example', 'version': '1.0.0', 'sha256': inputs['packages'][0]['sha256']}]}))
        r.build('production')
        self.assertEqual(audit.audit('production')['status'], 'PASS')
        plan = json.loads((self.root / 'dist/production/release-plan.json').read_text())
        self.assertEqual(publication.site_audit(plan)['status'], 'PASS')
        self.assertEqual(len(plan['packages']), 3)

    def test_current_installer_in_ledger_is_preserved_and_hash_checked(self):
        self.admit()
        blob = r.zip_bytes(r.installer(r.load_config(), 'production'))
        ledger = {'packages': [{'id': 'repository.ai.kodi', 'version': '0.1.0', 'sha256': r.sha(blob)}]}
        path = self.root / 'releases/manifest.json'; path.write_bytes(r.json_bytes(ledger))
        r.build('production')
        self.assertEqual(audit.audit('production')['status'], 'PASS')
        ledger['packages'][0]['sha256'] = '0'*64; path.write_bytes(r.json_bytes(ledger))
        with self.assertRaisesRegex(ValueError, 'including installer'): r.build('production')
        with self.assertRaises(AssertionError): audit.audit('production')

    def test_previous_installer_can_be_reviewed_and_retained(self):
        files = r.installer(r.load_config(), 'production')
        manifest = r.parse_xml(files['addon.xml'])
        manifest.find("extension[@point='xbmc.addon.repository']/dir/info").text = 'https://example.org/retired.xml'
        files['addon.xml'] = r.xml_bytes(manifest)
        self.admit(files, lanes=[], ver='0.0.9')
        inputs = json.loads((self.root / 'config/production.json').read_text())
        (self.root / 'releases/manifest.json').write_bytes(r.json_bytes({'packages': [
            {'id':'repository.ai.kodi','version':'0.0.9','sha256':inputs['packages'][0]['sha256']}]}))
        r.build('production')
        self.assertEqual(audit.audit('production')['status'], 'PASS')
        self.assertEqual(q.qualify('production')['status'], 'PASS')

    def test_unreviewed_artifact_with_matching_plan_is_rejected(self):
        self.admit(); r.build('production')
        path = self.root / 'dist/production/release-plan.json'
        plan = json.loads(path.read_text())
        name = 'packages/extra/extra-1.0.0.zip'
        p = self.root / 'dist/production/site' / name
        p.parent.mkdir(); p.write_bytes(b'extra')
        plan['site_files'][name] = r.sha(b'extra')
        plan['site_manifest_sha256'] = r.sha(r.json_bytes(plan['site_files']))
        path.write_bytes(r.json_bytes(plan))
        with self.assertRaises((AssertionError, ValueError)): audit.audit('production')


if __name__ == '__main__': unittest.main()
