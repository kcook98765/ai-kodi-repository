#!/usr/bin/env python3
"""Read-only source, infrastructure-site and optional public HTTPS qualification."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import audit_candidate
import qualify
import repository as repo

ROOT = repo.ROOT
SOURCE_ROOTS = {'.gitignore', 'AGENTS.md', 'README.md', 'LICENSE', 'CONTRIBUTING.md',
                'config', 'docs', 'fixtures', 'incoming', 'packages', 'plans',
                'releases', 'scripts', 'tests'}
SECRET_PATTERNS = [
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    rb'gh[pousr]_[A-Za-z0-9]{30,}',
    rb'github_pat_[A-Za-z0-9_]{40,}',
    rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
    rb'(?i)(?:OPENAI_API_KEY|GITHUB_TOKEN|GH_TOKEN)\s*[=:]\s*["\']?[A-Za-z0-9_-]{20,}',
]

def scan_bytes(name, data):
    for pattern in SECRET_PATTERNS:
        repo.require(re.search(pattern, data) is None, 'Credential pattern in '+name)
    repo.require((b'/' + b'home/') not in data and (b'/' + b'Users/') not in data,
                 'Private workstation path in '+name)

def source_audit():
    result = subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],
                            cwd=ROOT,capture_output=True,check=True)
    names = sorted(set(result.stdout.decode().split('\0'))-{''})
    repo.require(bool(names), 'No source files selected')
    hashes = {}
    for name in names:
        parts = Path(name).parts
        repo.require(parts[0] in SOURCE_ROOTS, 'Unreviewed source root: '+name)
        repo.require(not any(p.startswith('.') for p in parts if p != '.gitignore'),
                     'Private source path: '+name)
        repo.require(Path(name).suffix.lower() not in {'.zip','.log','.key','.pem','.db','.sqlite','.pyc'},
                     'Artifact/credential file in source: '+name)
        if parts[0] == 'incoming':
            repo.require(name == 'incoming/README.md', 'Private intake evidence in source')
        p = repo.safe_path(ROOT,name)
        data = p.read_bytes()
        scan_bytes(name,data)
        hashes[name] = repo.sha(data)
    return {'status':'PASS','files':hashes,'file_count':len(hashes),
            'credential_patterns_detected':False,
            'scope':'Selected Git source files; pattern scan is not a proof of secret absence'}

def site_audit(plan):
    repo.verify('production')
    config = repo.load_config()
    repo.require(json.loads((ROOT/'config/production.json').read_text())['packages']==[],
                 'This initial-publication gate accepts infrastructure only')
    repo.require(len(plan['packages'])==1 and
                 plan['packages'][0]['id']==config['addon_id'] and
                 plan['packages'][0]['version']==config['version'] and
                 plan['packages'][0]['fixture_only'] is False,
                 'Unexpected initial-publication package')
    paths = {'.nojekyll','index.html'}
    aid = config['addon_id']
    package = f'packages/{aid}/{aid}-{config["version"]}.zip'
    paths.update([package,package+'.sha256'])
    for lane in config['lanes']:
        catalog = 'catalogs/'+lane+'/addons.xml'
        paths.update([catalog,catalog+'.sha256',f'artwork/{lane}/{aid}/resources/icon.png'])
        repo.require(plan['catalogs'][lane]['ids']=={aid:config['version']},
                     'Unexpected catalog entry')
    repo.require(set(plan['site_files'])==paths, 'Unreviewed or missing public site files')
    for path in sorted(paths):
        scan_bytes(path,repo.safe_path(ROOT/'dist/production/site',path).read_bytes())
    return {'status':'PASS','site_files':len(paths),'only_repository_installer':True}

def public_https(plan):
    base = repo.load_config()['base_url']
    receipts = []
    for path,digest in sorted(plan['site_files'].items()):
        # .nojekyll is a Pages build control and is not served by GitHub Pages.
        if path == '.nojekyll':
            continue
        url = base+path
        with urlopen(Request(url,method='HEAD'),timeout=20) as head:
            repo.require(head.status==200 and head.geturl()==url, 'Unexpected HEAD redirect/status')
            head_type = head.headers.get('Content-Type','')
        with urlopen(url,timeout=20) as response:
            data = response.read(2_000_001)
            repo.require(response.status==200 and response.geturl()==url and len(data)<=2_000_000,
                         'Unexpected GET redirect/status/size')
            content_type = response.headers.get('Content-Type','')
        repo.require(repo.sha(data)==digest, 'Public bytes mismatch: '+path)
        if path!='index.html':
            repo.require('text/html' not in content_type and 'text/html' not in head_type,
                         'HTML instead of repository artifact')
        receipts.append({'url':url,'head':200,'get':200,'content_type':content_type,'sha256':digest})
    negatives = ['qualification/catalogs/nexus/addons.xml',
                 'qualification/packages/script.toolkit.sample/script.toolkit.sample-1.0.0.zip',
                 'packages/plugin.video.tastemade/plugin.video.tastemade-1.0.0.zip',
                 'packages/skin.aura/skin.aura-1.0.0.zip']
    for path in negatives:
        try:
            with urlopen(base+path,timeout=20):
                raise ValueError('Excluded artifact unexpectedly reachable: '+path)
        except HTTPError as error:
            repo.require(error.code==404, 'Expected excluded-artifact HTTP 404')
    return {'status':'PASS','public_https_verified':True,'tls':'System certificate verification enabled',
            'responses':receipts,'excluded_artifact_404s':negatives,
            'note':'.nojekyll is verified in the hosting Git tree, not as a served URL'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--https',action='store_true',help='Verify configured public HTTPS URLs')
    args=parser.parse_args()
    plan=json.loads((ROOT/'dist/production/release-plan.json').read_text())
    result={'status':'PASS','source':source_audit(),'site':site_audit(plan),
            'independent_audit':audit_candidate.audit('production'),
            'selection_and_loopback':qualify.urls('production'),
            'site_manifest_sha256':plan['site_manifest_sha256'],
            'runtime_tested':False,'publication_performed':False}
    if args.https:result['https']=public_https(plan)
    (ROOT/'reports').mkdir(exist_ok=True)
    target=ROOT/'reports'/('public-https.json' if args.https else 'publication-preflight.json')
    target.write_bytes(repo.json_bytes(result))
    print(json.dumps({'status':'PASS','report':str(target),'source_files':result['source']['file_count'],
                      'site_files':result['site']['site_files'],'public_https_verified':args.https,
                      'selection_cases':len(result['selection_and_loopback']['selection_cases'])}))

if __name__=='__main__':
    if not __debug__:raise RuntimeError('Run without -O; audit assertions are required')
    main()
