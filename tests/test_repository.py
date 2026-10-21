"""Failure controls for package admission and repository trust boundaries."""
import copy
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import repository as r
import qualify as q
import check_publication as publication

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (r.ROOT/'reports').mkdir(exist_ok=True)
    def setUp(self):
        self.files = r.installer(r.load_config(),'fixture')
    def malicious_zip(self, name, mode=0o100644):
        out = io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for n,b in self.files.items():
                z.writestr('repository.ai.kodi/'+n,b)
            info = zipfile.ZipInfo(name);info.external_attr=mode<<16
            z.writestr(info,b'forbidden')
        return out.getvalue()
    def test_traversal_and_absolute(self):
        for name in ['../escape','/absolute','C:/escape','repository.ai.kodi/../escape','repository.ai.kodi/..\\escape','repository.ai.kodi//escape','repository.ai.kodi/./escape']:
            with self.subTest(name=name),self.assertRaises(ValueError):r.inspect_zip(self.malicious_zip(name))
    def test_symlink_and_device(self):
        for mode in [stat.S_IFLNK|0o777,stat.S_IFCHR|0o600]:
            with self.assertRaises(ValueError):r.inspect_zip(self.malicious_zip('repository.ai.kodi/link',mode))
    def test_development_contamination(self):
        for name in ['.git/config','.opencode/agents/a.md','tests/test.py','docs/PLAN.md','AGENTS.md','opencode.json','__pycache__/a.pyc','.env','requirements.txt']:
            with self.subTest(name=name),self.assertRaises(ValueError):r.inspect_zip(self.malicious_zip('repository.ai.kodi/'+name))
    def test_duplicate_and_wrong_root(self):
        for name in ['repository.ai.kodi/addon.xml','repository.ai.kodi/ADDON.XML','wrong/root.txt']:
            with self.assertRaises((ValueError,ET.ParseError)):r.inspect_zip(self.malicious_zip(name))
    def test_allowlist_mismatch(self):
        with self.assertRaises(ValueError):r.inspect_zip(r.zip_bytes(self.files),{'addon.xml':'0'*64})
    def test_xml_entities(self):
        text='<!DOCTYPE addon [<!ENTITY x "y">]><addon/>'
        for encoding in ['utf-8','utf-16','utf-16le','utf-16be']:
            with self.subTest(encoding=encoding),self.assertRaises(ValueError):r.parse_xml(text.encode(encoding))
    def test_catalog_indentation_is_not_a_manifest_change(self):
        manifest=r.parse_xml(self.files['addon.xml'])
        catalog=ET.Element('addons');catalog.append(copy.deepcopy(manifest))
        entry=r.parse_xml(r.xml_bytes(catalog))[0]
        self.assertEqual(r.xml_bytes(entry),r.xml_bytes(manifest))
        entry.set('version','9.0.0')
        self.assertNotEqual(r.xml_bytes(entry),r.xml_bytes(manifest))
    def test_missing_entry_and_asset(self):
        files = dict(self.files);del files['resources/icon.png']
        with self.assertRaises(ValueError):r.zip_bytes(files)
    def test_missing_and_too_old_dependency(self):
        manifest = r.parse_xml(self.files['addon.xml'])
        for available in [{},{'xbmc.addon':'12.0.0'}]:
            with self.assertRaises(ValueError):r.dependencies([manifest],available)
    def test_dependency_cycles(self):
        a=ET.fromstring('<addon id="script.a" version="1.0.0"><requires><import addon="script.b" version="1.0.0"/></requires></addon>')
        b=ET.fromstring('<addon id="script.b" version="1.0.0"><requires><import addon="script.a" version="1.0.0"/></requires></addon>')
        with self.assertRaises(ValueError):r.dependencies([a,b],{})
    def test_optional_dependency_is_reported(self):
        a=ET.fromstring('<addon id="script.a" version="1.0.0"><requires><import addon="script.b" version="1.0.0" optional="true"/></requires></addon>')
        self.assertEqual(len(r.dependencies([a],{})),1)
    def test_version_reuse_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=r.ROOT/'reports') as temp:
            p=Path(temp)/'same-1.0.0.zip';r.write_output(p,b'first',immutable=True)
            with self.assertRaises(ValueError):r.write_output(p,b'changed',immutable=True)
            self.assertEqual(p.read_bytes(),b'first')
    def test_piers_rc_and_future_exclusion(self):
        manifest=r.parse_xml(self.files['addon.xml'])
        self.assertEqual(len(q.selection(manifest,'21.90.901')),1)
        self.assertEqual(q.selection(manifest,'23.0.0'),[])
    def test_stale_production_approval_rejected(self):
        with tempfile.TemporaryDirectory(dir=r.ROOT/'reports') as temp:
            root=Path(temp);(root/'config').mkdir();(root/'incoming').mkdir();(root/'releases').mkdir()
            blob=r.zip_bytes(self.files);(root/'incoming/package.zip').write_bytes(blob)
            record={'package_sha256':'0'*64,'release_approved':True,'rights_approved':True,'fixture_only':False}
            raw=r.json_bytes(record);(root/'incoming/review.json').write_bytes(raw)
            (root/'config/production.json').write_bytes(r.json_bytes({'external_dependencies':{},'packages':[{'zip':'package.zip','sha256':r.sha(blob),'review_record':'review.json','review_record_sha256':r.sha(raw),'lanes':['nexus']}]}))
            (root/'releases/manifest.json').write_bytes(r.json_bytes({'packages':[]}))
            with patch.object(r,'ROOT',root),self.assertRaisesRegex(ValueError,'approval'):r.production_packages({})
    def test_historical_release_removal_rejected(self):
        with tempfile.TemporaryDirectory(dir=r.ROOT/'reports') as temp:
            root=Path(temp);(root/'config').mkdir();(root/'releases').mkdir()
            (root/'config/production.json').write_bytes(r.json_bytes({'external_dependencies':{},'packages':[]}))
            (root/'releases/manifest.json').write_bytes(r.json_bytes({'packages':[{'id':'script.previous','version':'1.0.0','sha256':'0'*64}]}))
            with patch.object(r,'ROOT',root),self.assertRaisesRegex(ValueError,'Historical'):r.production_packages({})

class PublicationTests(unittest.TestCase):
    def test_installer_source_matches_generated_runtime(self):
        files=r.installer(r.load_config(),'production')
        self.assertEqual({p.relative_to(r.ROOT/'packages/repository.ai.kodi').as_posix():p.read_bytes()
                          for p in (r.ROOT/'packages/repository.ai.kodi').rglob('*') if p.is_file()},files)

    def test_secret_and_private_path_controls(self):
        for value in [b'gh' + b'p_' + b'A'*36,b'sk-' + b'proj-' + b'A'*40,
                      b'OPENAI_' + b'API_KEY=' + b'A'*40,b'/' + b'home/user/private']:
            with self.subTest(value=value[:8]),self.assertRaises(ValueError):
                publication.scan_bytes('synthetic-control',value)
        publication.scan_bytes('documentation',b'Use environment variables without committing credentials.')

    def test_extra_fixture_site_path_is_rejected_even_with_matching_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ['config','packages','releases']:
                shutil.copytree(r.ROOT/name,root/name)
            shutil.copy(r.ROOT/'LICENSE',root/'LICENSE')
            with patch.object(r,'ROOT',root),patch.object(publication,'ROOT',root):
                r.build('production')
                path=root/'dist/production/release-plan.json'
                plan=json.loads(path.read_text())
                publication.site_audit(plan)
                name='qualification/catalogs/nexus/addons.xml'
                file=root/'dist/production/site'/name;file.parent.mkdir(parents=True);file.write_bytes(b'unreleased')
                plan['site_files'][name]=r.sha(file.read_bytes())
                plan['site_manifest_sha256']=r.sha(r.json_bytes(plan['site_files']))
                path.write_bytes(r.json_bytes(plan))
                with self.assertRaisesRegex(ValueError,'public site files'):
                    publication.site_audit(plan)

if __name__=='__main__':unittest.main()
