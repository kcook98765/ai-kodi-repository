#!/usr/bin/env python3
"""Deterministic feed/HTTP/retention qualification. Only ephemeral loopback HTTP."""
import copy
import argparse
import functools
from html import unescape
import http.server
import json
from pathlib import Path
import threading
import re
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
import repository as repo

ROOT = repo.ROOT

def http_directory_entries(page, major):
    """Source-matched replay for our ASCII listing, not a native Kodi test.

    HTTPDirectory.cpp uses a case-insensitive DOTALL regex, then compares
    normalized label and link. Matrix requires an attribute-free anchor.
    See docs/NATIVE-ACCEPTANCE.md for pinned upstream sources and limitations.
    """
    repo.require(major in (19, 20, 21, 22), 'Unsupported parser replay version')
    pattern = (r'<a href="(.*?)">\s*(.*?)\s*</a>(.+?)(?=<a|</tr|$)' if major == 19 else
               r'<a href="([^"]*)"[^>]*>\s*(.*?)\s*</a>(.+?)(?=<a|</tr|$)')
    entries = []
    for href, label, _ in re.findall(pattern, page, re.I | re.S | re.ASCII):
        link = href.removeprefix('/').split('?', 1)[0]
        if major != 19:
            link = link.split('#', 1)[0]
        link = unescape(link)
        name = unescape(label.strip()).removesuffix('/')
        compare = unquote(link.removesuffix('/'))
        if compare not in ('', '..') and (name == compare or (':' in name and './'+name == compare)):
            entries.append(link)
    return entries

def bootstrap_listing(page, profile):
    config = repo.load_config(profile)
    version = config['fixture_version'] if profile == 'fixture' else config['version']
    filename = f'{config["addon_id"]}-{version}.zip'
    results = {}
    for major in (19, 20, 21, 22):
        entries = http_directory_entries(page, major)
        repo.require(entries == [filename], 'Kodi bootstrap listing must expose only the current installer')
        results[str(major)] = entries
    return results

def selection(manifest, api):
    return [d for d in manifest.findall("extension[@point='xbmc.addon.repository']/dir")
            if repo.version(d.get('minversion')) <= repo.version(api) <= repo.version(d.get('maxversion'))]

def urls(profile, network=True):
    config = repo.load_config(profile)
    site = ROOT/'dist'/profile/'site'
    output = ROOT/'dist'/profile
    plan = json.loads((output/'release-plan.json').read_text())
    current_version = config['fixture_version'] if profile == 'fixture' else config['version']
    installer_record = next(r for r in plan['packages']
                            if r['id'] == config['addon_id'] and r['version'] == current_version)
    manifest, _ = repo.inspect_zip((site/installer_record['path']).read_bytes())
    cases = {'18.9.0':None, '19.0.0':'matrix', '19.1.0':'matrix', '19.9.999':'matrix',
             '19.90.0':None, '20.0.0':'nexus', '20.5.0':'nexus', '20.9.999':'nexus',
             '20.90.0':None, '21.0.0':'omega', '21.3.0':'omega', '21.9.999':'omega',
             '21.90.0':'piers', '21.90.901':'piers', '22.0.0':'piers', '22.9.999':'piers', '23.0.0':None}
    for api, expected in cases.items():
        dirs = selection(manifest,api)
        repo.require(len(dirs) == (0 if expected is None else 1), 'Wrong number of selected directories')
        if expected:
            repo.require('/catalogs/'+expected+'/' in dirs[0].findtext('info'), 'Wrong lane selected')
    listing = bootstrap_listing((site/'index.html').read_text(), profile)
    paths = {'', 'index.html'}
    for record in plan['packages']:
        if record['id'] == config['addon_id']:
            filename = f'{record["id"]}-{record["version"]}.zip'
            paths.update([filename, filename+'.sha256'])
            blob = repo.safe_path(site, record['path']).read_bytes()
            repo.require(repo.safe_path(site, filename).read_bytes() == blob, 'Bootstrap installer copy mismatch')
            repo.require(repo.safe_path(site, filename+'.sha256').read_bytes() == (repo.sha(blob)+'\n').encode(),
                         'Bootstrap installer sidecar mismatch')
    for directory in manifest.findall("extension[@point='xbmc.addon.repository']/dir"):
        repo.require(directory.findtext('hashes') == 'sha256' and directory.find('checksum').get('verify') == 'sha256', 'Hash policy mismatch')
        for tag in ('info','checksum','datadir','artdir'):
            url = directory.findtext(tag)
            repo.require(url.startswith(config['base_url']) and urlsplit(url).scheme == 'https', 'Unexpected URL origin/path')
        info_path = directory.findtext('info')[len(config['base_url']):]
        paths.update([info_path, directory.findtext('checksum')[len(config['base_url']):]])
        catalog = repo.parse_xml((site/info_path).read_bytes())
        for addon in catalog:
            name = addon.get('id')+'/'+addon.get('id')+'-'+addon.get('version')+'.zip'
            package_path = directory.findtext('datadir')[len(config['base_url']):]+name
            paths.update([package_path,package_path+'.sha256'])
            for asset in addon.findall("extension[@point='xbmc.addon.metadata']/assets/*"):
                paths.add(directory.findtext('artdir')[len(config['base_url']):]+addon.get('id')+'/'+asset.text)
    results = []
    if network:
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_):
                pass
        handler = functools.partial(Handler, directory=str(site))
        with http.server.ThreadingHTTPServer(('127.0.0.1',0),handler) as server:
            thread = threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                for path in sorted(paths):
                    expected = repo.safe_path(site,path or 'index.html').read_bytes()
                    url = 'http://127.0.0.1:'+str(server.server_port)+'/'+path
                    with urlopen(Request(url,method='HEAD'),timeout=5) as response:
                        repo.require(response.status == 200 and int(response.headers['Content-Length']) == len(expected), 'HEAD failed')
                    with urlopen(url,timeout=5) as response:
                        content_type = response.headers.get('Content-Type','').lower()
                        repo.require(response.status == 200 and response.read() == expected and
                                     (content_type.startswith('text/html') if path in ('', 'index.html') else 'text/html' not in content_type),
                                     'GET/content type failed')
                    results.append({'path':path,'head':200,'get':200,'sha256':repo.sha(expected)})
            finally:
                server.shutdown()
                thread.join(timeout=5)
    return {'status':'PASS','selection_cases':cases,'bootstrap_parser_replay':listing,'url_paths':len(paths),
            'loopback_http':results,'public_https':'UNVERIFIED: no deployment authorized',
            'kodi_runtime_tested':False}

def qualify(profile='fixture'):
    before = repo.build(profile)
    site = ROOT/'dist'/profile/'site'
    hashes = {p.relative_to(site).as_posix():repo.sha(p.read_bytes()) for p in site.rglob('*') if p.is_file()}
    repo.build(profile)
    after = {p.relative_to(site).as_posix():repo.sha(p.read_bytes()) for p in site.rglob('*') if p.is_file()}
    repo.require(hashes == after, 'Whole-site reproducibility failed')
    retained = []
    if profile == 'fixture':
        for ver in ['1.0.0','1.1.0']:
            repo.require((site/f'qualification/packages/script.toolkit.sample/script.toolkit.sample-{ver}.zip').is_file(),
                         'Previous version not retained')
            retained.append(ver)
    else:
        ledger = json.loads(repo.ledger_path(profile).read_text())
        prefix = 'candidate/' if profile == 'candidate' else ''
        for old in ledger['packages']:
            path = site/prefix/f'packages/{old["id"]}/{old["id"]}-{old["version"]}.zip'
            repo.require(path.is_file() and repo.sha(path.read_bytes()) == old['sha256'], 'Previous version not retained')
            retained.append(old['id']+'-'+old['version'])
    import audit_candidate
    # Fresh audited inputs retain exact runtime limitations; site mechanics do
    # not exercise or upgrade any of the add-on's unobserved runtime scenarios.
    result = {'status':'PASS','profile':profile,'artifact_validation':repo.verify(profile),
            'independent_audit':audit_candidate.audit(profile),
            'whole_site_reproducible':True,'historical_versions_retained':retained,
            'url_validation':urls(profile), 'build':before}
    if profile == 'fixture':
        # Existing fixed role adapters consume this field.
        result['historical_fixture_versions_retained'] = retained
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['fixture','production','candidate'], default='fixture')
    args = parser.parse_args()
    result = qualify(args.profile)
    (ROOT/'reports').mkdir(exist_ok=True)
    target = 'deterministic-qualification.json' if args.profile=='fixture' else args.profile+'-qualification.json'
    (ROOT/'reports'/target).write_bytes(repo.json_bytes(result))
    print(json.dumps(result,indent=2))
