"""Bootstrap trust boundaries and source-matched Kodi directory discovery."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit

import test_intake as fixtures
import repository as r
import audit_candidate as audit
import check_publication as publication
import qualify as q


class BootstrapTests(unittest.TestCase):
    setUp = fixtures.IntakeTests.setUp
    files = fixtures.IntakeTests.files
    admit = fixtures.IntakeTests.admit

    def build(self):
        r.build('production')
        self.site = self.root/'dist/production/site'
        self.plan_path = self.root/'dist/production/release-plan.json'
        self.plan = json.loads(self.plan_path.read_text())
        self.filename = 'repository.ai.kodi-0.1.0.zip'
        return self.site

    def forge_manifest(self):
        # Matching a forged plan must never make modified public files trusted.
        self.plan['site_files'] = {p.relative_to(self.site).as_posix():r.sha(p.read_bytes())
                                   for p in self.site.rglob('*') if p.is_file()}
        self.plan['site_manifest_sha256'] = r.sha(r.json_bytes(self.plan['site_files']))
        self.plan_path.write_bytes(r.json_bytes(self.plan))

    def test_only_installer_visible_with_multiple_independent_addons(self):
        self.admit()
        self.admit(self.files(aid='plugin.video.second', floor='3.0.0'), lanes=['matrix'])
        self.build()
        page = (self.site/'index.html').read_text()
        self.assertEqual(q.bootstrap_listing(page, 'production'),
                         {str(m):[self.filename] for m in (19, 20, 21, 22)})
        self.assertNotIn('plugin.video.example', page)
        self.assertNotIn('plugin.video.second', page)
        for lane, expected in [('matrix', 'plugin.video.second'), ('nexus', 'plugin.video.example'),
                               ('omega', 'plugin.video.example'), ('piers', None)]:
            catalog = r.parse_xml((self.site/f'catalogs/{lane}/addons.xml').read_bytes())
            ids = {a.get('id') for a in catalog}
            self.assertEqual(ids, {'repository.ai.kodi'} | ({expected} if expected else set()))
            for a in catalog:
                if a.get('id') != 'repository.ai.kodi':
                    self.assertEqual(a.findtext("extension[@point='xbmc.python.pluginsource']/provides"), 'video')
        self.assertEqual(publication.site_audit(self.plan)['status'], 'PASS')

    def test_root_copy_sidecar_and_url_resolution(self):
        self.build()
        canonical = self.site/'packages/repository.ai.kodi'/self.filename
        self.assertEqual((self.site/self.filename).read_bytes(), canonical.read_bytes())
        self.assertEqual((self.site/(self.filename+'.sha256')).read_bytes(),
                         (r.sha(canonical.read_bytes())+'\n').encode())
        for major in (19, 20, 21, 22):
            link, = q.http_directory_entries((self.site/'index.html').read_text(), major)
            self.assertEqual(urljoin(r.load_config()['base_url'], link),
                             r.load_config()['base_url']+self.filename)
        self.assertEqual(audit.audit('production')['status'], 'PASS')

    def test_source_matched_parser_rejects_malformed_links(self):
        name = 'repository.ai.kodi-0.1.0.zip'
        invalid = [f'<a href="{name}">Download installer</a><br>',
                   f"<a href='{name}'>{name}</a><br>",
                   f'<a href={name}>{name}</a><br>',
                   f'<a href="{name}"><b>{name}</b></a><br>',
                   f'<a href="packages/{name}">{name}</a><br>',
                   f'<a href="{name}">{name}</a>']
        for major in (19, 20, 21, 22):
            for page in invalid:
                with self.subTest(major=major, page=page):
                    self.assertEqual(q.http_directory_entries(page, major), [])
            # Source-derived replay is deliberately not a general HTML parser:
            # DOTALL and case-insensitive matching are part of Kodi's contract.
            page = f'<A HREF="{name}">\n{name}\n</A>\n'
            self.assertEqual(q.http_directory_entries(page, major), [name])
        self.assertEqual(q.http_directory_entries(f'<a href="{name}" title="x">{name}</a><br>', 19), [])

    def test_qualification_rejects_wrong_absolute_or_extra_link(self):
        self.build()
        for href in ['https://example.org/'+self.filename, '../'+self.filename, 'other.zip']:
            page = f'<a href="{href}">{href}</a><br>'
            with self.subTest(href=href), self.assertRaisesRegex(ValueError, 'bootstrap listing'):
                q.bootstrap_listing(page, 'production')
        page = (self.site/'index.html').read_text()+'<a href="extra.zip">extra.zip</a><br>'
        with self.assertRaisesRegex(ValueError, 'bootstrap listing'): q.bootstrap_listing(page, 'production')

    def test_forged_index_cannot_pass_independent_audit(self):
        self.build()
        page = self.site/'index.html'
        page.write_text(page.read_text().replace(f'>{self.filename}</a>', '>Download</a>'))
        self.forge_manifest()
        with self.assertRaisesRegex(AssertionError, 'disclosure/index'): audit.audit('production')
        with self.assertRaisesRegex(ValueError, 'bootstrap listing'): q.urls('production', network=False)

    def test_wrong_copy_rejected_even_with_matching_sidecar_and_plan(self):
        self.build()
        wrong = b'not the reviewed installer'
        (self.site/self.filename).write_bytes(wrong)
        (self.site/(self.filename+'.sha256')).write_text(r.sha(wrong)+'\n')
        self.forge_manifest()
        with self.assertRaisesRegex(ValueError, 'Bootstrap installer copy'): r.verify('production')
        with self.assertRaisesRegex(AssertionError, 'Bootstrap installer copy'): audit.audit('production')
        with self.assertRaisesRegex(ValueError, 'Bootstrap installer copy'): q.urls('production', network=False)
        with self.assertRaisesRegex(ValueError, 'Bootstrap installer copy'): publication.site_audit(self.plan)

    def test_wrong_or_missing_sidecar_rejected(self):
        self.build()
        (self.site/(self.filename+'.sha256')).write_text('0'*64+'\n')
        self.forge_manifest()
        with self.assertRaisesRegex(AssertionError, 'Bootstrap installer sidecar'): audit.audit('production')
        with self.assertRaisesRegex(ValueError, 'Bootstrap installer sidecar'): r.verify('production')
        (self.site/(self.filename+'.sha256')).unlink()
        self.forge_manifest()
        with self.assertRaises((AssertionError, FileNotFoundError)): audit.audit('production')

    def test_unexpected_root_package_rejected_even_with_forged_plan(self):
        self.build()
        (self.site/'plugin.video.unreviewed-1.0.0.zip').write_bytes(b'unreviewed')
        self.forge_manifest()
        with self.assertRaisesRegex(AssertionError, 'public site files'): audit.audit('production')
        with self.assertRaisesRegex(AssertionError, 'public site files'): publication.site_audit(self.plan)

    def test_reproducible_and_existing_copy_is_immutable(self):
        self.build()
        before = {p.relative_to(self.site):p.read_bytes() for p in self.site.rglob('*') if p.is_file()}
        r.build('production')
        self.assertEqual(before, {p.relative_to(self.site):p.read_bytes() for p in self.site.rglob('*') if p.is_file()})
        (self.site/self.filename).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Immutable'): r.build('production')

    def test_public_https_bootstrap_checks_mime_hash_and_discovery(self):
        self.build()
        base = r.load_config()['base_url']
        failure = {}

        class Response(io.BytesIO):
            status = 200
            def __init__(self, url, data, mime):
                super().__init__(data)
                self.url, self.headers = url, {'Content-Type':mime}
            def geturl(self):
                return self.url

        def fetch(request, **_):
            url = request if isinstance(request, str) else request.full_url
            relative = url[len(base):] or 'index.html'
            target = self.site/relative
            if not target.is_file():
                raise HTTPError(url, 404, 'Not Found', {}, None)
            data = target.read_bytes()
            mime = 'text/html; charset=utf-8' if relative == 'index.html' else 'application/octet-stream'
            if relative == 'index.html':
                method = 'GET' if isinstance(request, str) else request.get_method()
                mime = failure.get(method+'_mime', mime)
                if failure.get('corrupt_bytes'): data += b'changed'
            return Response(url, data, mime)

        with patch.object(publication, 'urlopen', side_effect=fetch):
            result = publication.public_https(self.plan)
            self.assertEqual(result['status'], 'PASS')
            self.assertIn(base, [receipt['url'] for receipt in result['responses']])
            for method in ('HEAD', 'GET'):
                failure[method+'_mime'] = 'text/plain'
                with self.assertRaisesRegex(ValueError, 'text/html'): publication.public_https(self.plan)
                failure.clear()
            failure['corrupt_bytes'] = True
            with self.assertRaisesRegex(ValueError, 'Public bytes mismatch'): publication.public_https(self.plan)
            failure.clear()
            page = self.site/'index.html'
            page.write_text(page.read_text().replace(f'>{self.filename}</a>', '>Download</a>'))
            self.forge_manifest()
            with self.assertRaisesRegex(ValueError, 'bootstrap listing'): publication.public_https(self.plan)

    def test_future_installer_selected_automatically_and_history_retained(self):
        self.build()
        old_blob = (self.site/self.filename).read_bytes()
        self.admit(r.installer(r.load_config(), 'production'), lanes=[])
        (self.root/'releases/manifest.json').write_bytes(r.json_bytes({'schema':1, 'packages':[
            {'id':'repository.ai.kodi', 'version':'0.1.0', 'sha256':r.sha(old_blob)}]}))
        config = r.load_config(); config['version'] = '0.2.0'
        (self.root/'config/repository.json').write_bytes(r.json_bytes(config))
        source = self.root/'packages/repository.ai.kodi/addon.xml'
        manifest = r.parse_xml(source.read_bytes()); manifest.set('version', '0.2.0')
        source.write_bytes(r.xml_bytes(manifest))
        r.build('production')
        page = (self.site/'index.html').read_text()
        self.assertEqual(q.http_directory_entries(page, 19), ['repository.ai.kodi-0.2.0.zip'])
        self.assertEqual((self.site/self.filename).read_bytes(), old_blob)
        self.assertEqual((self.site/'packages/repository.ai.kodi'/self.filename).read_bytes(), old_blob)
        self.assertEqual((self.site/'repository.ai.kodi-0.2.0.zip').read_bytes(),
                         (self.site/'packages/repository.ai.kodi/repository.ai.kodi-0.2.0.zip').read_bytes())
        self.assertEqual(audit.audit('production')['status'], 'PASS')
        plan = json.loads(self.plan_path.read_text())
        self.assertEqual(publication.site_audit(plan)['status'], 'PASS')
        self.assertEqual(q.urls('production', network=False)['status'], 'PASS')
        for data in (None, b'changed historical bootstrap'):
            with self.subTest(historical_bytes=data):
                old = self.site/self.filename
                if data is None: old.unlink()
                else: old.write_bytes(data)
                self.plan = plan
                self.forge_manifest()
                with self.assertRaises((AssertionError, FileNotFoundError)): audit.audit('production')
                with self.assertRaises(ValueError): publication.site_audit(self.plan)
                old.write_bytes(old_blob)


if __name__ == '__main__':
    unittest.main()
