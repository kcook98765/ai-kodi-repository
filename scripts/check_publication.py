#!/usr/bin/env python3
"""Read-only source, reviewed production-site and optional HTTPS qualification."""
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
    # Reassess real inputs and both exception expiries now; cached plan flags
    # never replace the shared contract or independent production conjunction.
    repo.require(plan.get('profile') == 'production' and not plan.get('release_blockers'),
                 'Only an approved production plan can pass publication preflight')
    repo.verify('production')
    repo.require(plan == json.loads((ROOT/'dist/production/release-plan.json').read_text()),
                 'Plan differs from verified on-disk production plan')
    independent = audit_candidate.audit('production')
    config = repo.load_config()
    paths = {'.nojekyll','index.html'}
    for record in plan['packages']:
        repo.require(record['fixture_only'] is False, 'Fixture in production')
        paths.update([record['path'],record['path']+'.sha256'])
        if record['id'] == config['addon_id']:
            bootstrap = f'{record["id"]}-{record["version"]}.zip'
            paths.update([bootstrap, bootstrap+'.sha256'])
        manifest, files = repo.inspect_zip((ROOT/'dist/production/site'/record['path']).read_bytes())
        for name,data in files.items():
            scan_bytes(record['id']+'/'+name,data)
    for lane,record in plan['catalogs'].items():
        catalog = record['path']
        paths.update([catalog,catalog+'.sha256'])
        for manifest in repo.parse_xml((ROOT/'dist/production/site'/catalog).read_bytes()):
            for asset in manifest.findall("extension[@point='xbmc.addon.metadata']/assets/*"):
                paths.add(f'artwork/{lane}/{manifest.get("id")}/{asset.text}')
    repo.require(set(plan['site_files'])==paths, 'Unreviewed or missing public site files')
    for path in sorted(paths):
        scan_bytes(path,repo.safe_path(ROOT/'dist/production/site',path).read_bytes())
    return {'status':'PASS','site_files':len(paths),'only_repository_installer':len(plan['packages'])==1,
            'reviewed_packages':len(independent['packages']),
            'approvals':independent['approvals'], 'release_blockers':independent['release_blockers']}

def public_https(plan):
    base = repo.load_config()['base_url']
    receipts = []
    # Kodi opens the documented directory URL, not just index.html directly.
    checks = list(plan['site_files'].items()) + [('', plan['site_files']['index.html'])]
    for path,digest in sorted(checks):
        url = base+path
        with urlopen(Request(url,method='HEAD'),timeout=20) as head:
            repo.require(head.status==200 and head.geturl()==url, 'Unexpected HEAD redirect/status')
            head_type = head.headers.get('Content-Type','')
        with urlopen(url,timeout=20) as response:
            limit = repo.MAX_ZIP_BYTES if path.endswith('.zip') else 2_000_000
            data = response.read(limit+1)
            repo.require(response.status==200 and response.geturl()==url and len(data)<=limit,
                         'Unexpected GET redirect/status/size')
            content_type = response.headers.get('Content-Type','')
        repo.require(repo.sha(data)==digest, 'Public bytes mismatch: '+path)
        if path in ('', 'index.html'):
            repo.require(content_type.lower().startswith('text/html') and head_type.lower().startswith('text/html'),
                         'Bootstrap index must be text/html')
            qualify.bootstrap_listing(data.decode('utf-8'), 'production')
        else:
            repo.require('text/html' not in content_type and 'text/html' not in head_type,
                         'HTML instead of repository artifact')
        receipts.append({'url':url,'head':200,'get':200,'content_type':content_type,'sha256':digest})
    negatives = ['qualification/catalogs/nexus/addons.xml', 'candidate/catalogs/nexus/addons.xml']
    # Check only unadmitted runtime directories; admitted add-ons must be reachable.
    for source in sorted((ROOT/'fixtures').glob('*/*/addon.xml')):
        manifest = repo.parse_xml(source.read_bytes())
        negatives.append(f'packages/{manifest.get("id")}/{manifest.get("id")}-{manifest.get("version")}.zip')
    negatives = sorted(set(negatives)-set(plan['site_files']))
    for path in negatives:
        try:
            with urlopen(base+path,timeout=20):
                raise ValueError('Excluded artifact unexpectedly reachable: '+path)
        except HTTPError as error:
            repo.require(error.code==404, 'Expected excluded-artifact HTTP 404')
    return {'status':'PASS','public_https_verified':True,'tls':'System certificate verification enabled',
            'responses':receipts,'excluded_artifact_404s':negatives,
            'note':'Includes .nojekyll; excluded paths are derived from private profiles and fixtures'}

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
