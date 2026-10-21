#!/usr/bin/env python3
"""Deterministic feed/HTTP/retention qualification. Only ephemeral loopback HTTP."""
import copy
import functools
import http.server
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import repository as repo

ROOT = repo.ROOT

def selection(manifest, api):
    return [d for d in manifest.findall("extension[@point='xbmc.addon.repository']/dir")
            if repo.version(d.get('minversion')) <= repo.version(api) <= repo.version(d.get('maxversion'))]

def urls(profile, network=True):
    config = repo.load_config()
    site = ROOT/'dist'/profile/'site'
    output = ROOT/'dist'/profile
    plan = json.loads((output/'release-plan.json').read_text())
    installer_record = next(r for r in plan['packages'] if r['id'] == config['addon_id'])
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
    paths = set()
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
                    expected = repo.safe_path(site,path).read_bytes()
                    url = 'http://127.0.0.1:'+str(server.server_port)+'/'+path
                    with urlopen(Request(url,method='HEAD'),timeout=5) as response:
                        repo.require(response.status == 200 and int(response.headers['Content-Length']) == len(expected), 'HEAD failed')
                    with urlopen(url,timeout=5) as response:
                        repo.require(response.status == 200 and response.read() == expected and 'text/html' not in response.headers.get('Content-Type',''), 'GET/content type failed')
                    results.append({'path':path,'head':200,'get':200,'sha256':repo.sha(expected)})
            finally:
                server.shutdown()
                thread.join(timeout=5)
    return {'status':'PASS','selection_cases':cases,'url_paths':len(paths),
            'loopback_http':results,'public_https':'UNVERIFIED: no deployment authorized',
            'kodi_runtime_tested':False}

def qualify():
    before = repo.build('fixture')
    site = ROOT/'dist/fixture/site'
    hashes = {p.relative_to(site).as_posix():repo.sha(p.read_bytes()) for p in site.rglob('*') if p.is_file()}
    repo.build('fixture')
    after = {p.relative_to(site).as_posix():repo.sha(p.read_bytes()) for p in site.rglob('*') if p.is_file()}
    repo.require(hashes == after, 'Whole-site reproducibility failed')
    one = site/'qualification/packages/script.toolkit.sample/script.toolkit.sample-1.0.0.zip'
    two = site/'qualification/packages/script.toolkit.sample/script.toolkit.sample-1.1.0.zip'
    repo.require(one.is_file() and two.is_file(), 'Previous version not retained')
    return {'status':'PASS','artifact_validation':repo.verify('fixture'),
            'whole_site_reproducible':True,'historical_fixture_versions_retained':['1.0.0','1.1.0'],
            'url_validation':urls('fixture'), 'build':before}

if __name__ == '__main__':
    result = qualify()
    (ROOT/'reports/deterministic-qualification.json').write_bytes(repo.json_bytes(result))
    print(json.dumps(result,indent=2))
