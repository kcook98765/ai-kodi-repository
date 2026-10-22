#!/usr/bin/env python3
"""Independent stdlib audit against reviewed intake, source and retention inputs.

Never imports the builder, executes add-ons or treats generated plan inventories
as approval. Candidate results describe structural qualification only.
"""
import argparse
import approval_contract
import copy
import hashlib
from html import escape
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r'[a-z0-9]+(?:[._-][a-z0-9]+)+\Z')
VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+\Z')
DENIED = {'.git', '.opencode', '.agents', 'test', 'tests', 'docs', 'tools', 'reports',
          'node_modules', 'venv', '.venv', '__pycache__', 'profile', 'profiles'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True)+'\n').encode()


def structure(element):
    return (element.tag, sorted(element.attrib.items()), (element.text or '').strip(),
            [structure(c) for c in element])


def path(base, name):
    p = PurePosixPath(name)
    assert p.parts and not p.is_absolute() and p.as_posix() == name
    assert not any(c in name for c in ('\\', ':', '\0')) and '..' not in p.parts
    for part in p.parts:
        assert not part.endswith((' ', '.')) and not any(ord(c) < 32 or c in '<>"|?*' for c in part)
        assert part.split('.')[0].upper() not in {'CON', 'PRN', 'AUX', 'NUL',
            *('COM'+str(i) for i in range(1, 10)), *('LPT'+str(i) for i in range(1, 10))}
    result = base.joinpath(*p.parts)
    assert result.resolve().is_relative_to(base.resolve())
    assert not any(item.is_symlink() for item in [result, *result.parents])
    return result


def xml(data):
    assert len(data) <= 2_000_000
    text = data.decode('utf-8-sig')
    assert '\0' not in text and '<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper()
    return ET.fromstring(data)


def numeric(value):
    assert isinstance(value, str) and VERSION.fullmatch(value)
    return tuple(map(int, value.split('.')))


def archive_files(blob):
    assert len(blob) <= 64_000_000
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        infos = z.infolist(); names = z.namelist()
        assert 0 < len(names) <= 10000 and names == sorted(names)
        folded = {n.casefold() for n in names}
        assert len(names) == len(folded) and sum(i.file_size for i in infos) <= 256_000_000
        roots = set(); files = {}
        for info in infos:
            p = PurePosixPath(info.filename); path(ROOT, info.filename)
            assert len(p.parts) >= 2
            assert not any(parent.as_posix().casefold() in folded for parent in p.parents)
            assert not info.is_dir() and not info.flag_bits & 1
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            mode = info.external_attr >> 16
            assert stat.S_ISREG(mode) and mode & 0o777 == 0o644
            roots.add(p.parts[0]); name = '/'.join(p.parts[1:])
            assert not any(x.lower() in DENIED or x.startswith('.') for x in p.parts[1:])
            assert not name.lower().endswith(('.pyc', '.pyo', '.log', '.toml', '.lock'))
            assert p.name.lower() not in {'agents.md', 'development.md', 'contributing.md',
                'opencode.json', 'requirements.txt', 'pyproject.toml', 'credentials.json', 'auth.json'}
            files[name] = z.read(info)
        assert z.testzip() is None
    manifest = xml(files['addon.xml'])
    assert manifest.tag == 'addon' and ID.fullmatch(manifest.get('id', ''))
    numeric(manifest.get('version'))
    assert roots == {manifest.get('id')} and manifest.get('name') and manifest.get('provider-name')
    metas = manifest.findall("extension[@point='xbmc.addon.metadata']")
    assert len(metas) == 1
    assert any(e.get('point') and e.get('point') != 'xbmc.addon.metadata' for e in manifest.findall('extension'))
    for tag in ['summary', 'description', 'platform', 'license']: assert metas[0].findtext(tag)
    assert any(PurePosixPath(n).name.lower().startswith(('license', 'copying')) for n in files)
    for extension in manifest.findall('extension'):
        if extension.get('library'): assert extension.get('library') in files
    for asset in metas[0].findall('assets/*'): assert asset.text in files
    groups = manifest.findall('requires')
    assert len(groups) <= 1 and all(d.tag == 'import' for group in groups for d in group)
    seen = set()
    for dep in manifest.findall('requires/import'):
        name = dep.get('addon', '')
        assert ID.fullmatch(name) and name not in seen
        seen.add(name); numeric(dep.get('version'))
        assert dep.get('optional', 'false') in ('true', 'false')
    return manifest, files


def reviewed_inputs(config, profile):
    expected = {}
    if profile == 'fixture':
        for ver, lanes in [('1.0.0', ['matrix', 'nexus']), ('1.1.0', ['omega', 'piers'])]:
            source = ROOT/'fixtures'/ver/'script.toolkit.sample'
            files = {n:path(source, n).read_bytes() for n in ['addon.xml', 'default.py', 'LICENSE.txt', 'resources/icon.png']}
            expected[('script.toolkit.sample', ver)] = {'files': files, 'lanes': lanes, 'fixture_only': True}
        return expected
    inputs = json.loads((ROOT/f'config/{profile}.json').read_text())
    assert inputs['external_dependencies'] == {}
    for item in inputs['packages']:
        blob = path(ROOT/'incoming', item['zip']).read_bytes()
        assert digest(blob) == item['sha256']
        raw = path(ROOT/'incoming', item['review_record']).read_bytes()
        assert digest(raw) == item['review_record_sha256']
        record = json.loads(raw)
        assert record['package_sha256'] == digest(blob) and record['fixture_only'] is False
        assert re.fullmatch('[0-9a-f]{40}', record['source_commit'])
        assert record['source_repository'].startswith('https://github.com/')
        assert all(type(record[k]) is bool for k in ['rights_approved', 'release_approved'])
        assert len(item['lanes']) == len(set(item['lanes']))
        for lane in item['lanes']:
            assert lane in config['lanes']
            acceptance = record['compatibility'][lane]
            assert all(type(acceptance[k]) is bool for k in ['static_accepted', 'runtime_accepted'])
            assert isinstance(acceptance['evidence'], list)
            assert all(isinstance(e, str) and e.strip() for e in acceptance['evidence'])
        approval = approval_contract.assess(record, item['lanes'])
        approval['review_record_sha256'] = digest(raw)
        approval['package_sha256'] = digest(blob)
        # Independently enforce every strict production gate, even if a plan lies.
        if profile == 'production':
            assert record['release_approved']
            assert not approval['release_blockers'], 'Outstanding approval gates'
            for lane in item['lanes']:
                accepted = record['compatibility'][lane]
                assert accepted['static_accepted'] and accepted['runtime_accepted'] and accepted['evidence']
            if record.get('schema_version', 1) != 3:
                assert record['rights_approved']
            if record.get('schema_version', 1) in (2, 3):
                assert record['technical_release']['status'] == 'approved'
                assert record['release_decision']['status'] == 'approved'
            if record.get('schema_version', 1) == 2:
                assert record['rights_review']['status'] == 'verified'
                assert not record['unresolved_risks']
                assert all(record['compatibility'][lane]['runtime_test']['status'] == 'passed' for lane in item['lanes'])
            if record.get('schema_version') == 3:
                assert record['approval_policy'] == 'unofficial-integration-v1'
                assert set(record['approval_lanes']) == set(item['lanes'])
                assert record['rights_approved'] is False and record['rights_review'] == {'status': 'pending'}
                risks = record['unresolved_risks']
                ids = {r['id'] for r in risks}
                assert risks and all(r['category'] == 'provider_terms' for r in risks)
                value = record['unofficial_integration']
                package = value['package_distribution_review']; service = value['service_use_review']
                owner = value['owner_distribution_decision']; ack = record['owner_acknowledgment']
                assert package['status'] == 'verified' and package['scope'] == 'all_distributed_materials'
                assert service['status'] == 'terms_unresolved' and service['scope'] == 'runtime_service_content_and_marks'
                assert service['provider_permission_obtained'] is False
                assert service['provider_content_authorization'] == 'not_established'
                assert owner['status'] == 'accepted' and owner['role'] == 'owner' and owner['authorization_claimed'] is False
                assert ack['status'] == 'acknowledged' and ack['role'] == 'owner'
                for action in (service, owner, ack):
                    assert len(action['risk_ids']) == len(ids) and set(action['risk_ids']) == ids
                assert all(review['actor'].strip().casefold() != owner['actor'].strip().casefold()
                           for review in (package, service))
                scope = item['lanes'] or list(record['compatibility'])
                assert scope
                for lane in scope:
                    accepted = record['compatibility'][lane]; test = accepted['runtime_test']
                    assert accepted['static_accepted'] and accepted['runtime_accepted'] and accepted['evidence']
                    assert test['status'] == 'passed' and test['outstanding_tests'] == []
                    assert all(test[k].strip() for k in ('actor', 'role', 'platform', 'kodi_version', 'scope', 'recorded_at', 'rationale'))
                    assert test['evidence']
                assert approval['package_distribution_eligible'] is True
                assert approval['accepted_terms_risks'] == risks and approval['rights_status'] == 'pending'
        manifest, files = archive_files(blob)
        assert {n:digest(b) for n,b in files.items()} == record['runtime_files']
        if record.get('schema_version') == 3:
            notice = record['unofficial_integration']['disclosure']
            path(ROOT/'incoming', notice['package_path'])
            assert digest(files[notice['package_path']]) == notice['package_sha256']
            assert files[notice['package_path']].decode('utf-8').strip()
            if not item['lanes']:
                assert any((old['id'], old['version'], old['sha256']) ==
                           (manifest.get('id'), manifest.get('version'), digest(blob))
                           for old in json.loads((ROOT/'releases/manifest.json').read_text())['packages'])
        key = (manifest.get('id'), manifest.get('version'))
        assert key not in expected
        expected[key] = {'blob': blob, 'files': files, 'lanes': item['lanes'],
                         'fixture_only': False, 'provenance': record, 'approval': approval}
    for old in json.loads((ROOT/'releases/manifest.json').read_text())['packages']:
        if (old['id'], old['version']) == (config['addon_id'], config['version']):
            continue  # Generated installer is checked with the complete inventory below.
        assert digest(expected[(old['id'], old['version'])]['blob']) == old['sha256']
    return expected


def check_dependencies(manifests, builtins):
    available = {**builtins, **{m.get('id'):m.get('version') for m in manifests}}
    edges = {}
    for manifest in manifests:
        aid = manifest.get('id'); edges[aid] = []
        for dep in manifest.findall('requires/import'):
            name = dep.get('addon')
            satisfied = name in available and numeric(available[name]) >= numeric(dep.get('version'))
            if dep.get('optional') == 'true': continue
            assert satisfied, 'Required dependency unavailable/too old: '+name
            if name not in builtins: edges[aid].append(name)
    def visit(node, active, done):
        assert node not in active, 'Dependency cycle'
        if node in done: return
        for child in edges.get(node, []): visit(child, active | {node}, done)
        done.add(node)
    done = set()
    for node in edges: visit(node, set(), done)


def audit(profile='fixture'):
    if not __debug__:
        raise RuntimeError('Run without -O; audit assertions are required')
    assert profile in ('fixture', 'production', 'candidate')
    prefix = {'fixture':'qualification/', 'production':'', 'candidate':'candidate/'}[profile]
    out = ROOT/'dist'/profile; site = out/'site'
    config = json.loads((ROOT/'config/repository.json').read_text())
    plan = json.loads((out/'release-plan.json').read_text())
    assert plan['profile'] == profile and plan['publication_authorized'] is False
    assert plan['fixture_only'] is (profile == 'fixture') and plan['remote_actions_executed'] == []
    assert plan['config_sha256'] == digest((ROOT/'config/repository.json').read_bytes())
    intake_path = 'config/candidate.json' if profile == 'candidate' else 'config/production.json'
    assert plan['input_config_sha256'] == digest((ROOT/intake_path).read_bytes())
    assert plan['retention_ledger_sha256'] == digest((ROOT/'releases/manifest.json').read_bytes())
    assert plan['toolchain']['approval_contract_sha256'] == digest(Path(approval_contract.__file__).read_bytes())
    for name,filename in [('builder', 'repository.py'), ('auditor', 'audit_candidate.py'),
                          ('qualifier', 'qualify.py'), ('preflight', 'check_publication.py')]:
        assert plan['toolchain'][name+'_sha256'] == digest((Path(__file__).parent/filename).read_bytes())
    assert plan['toolchain']['review_schema_sha256'] == digest((Path(__file__).parents[1]/'docs/REVIEW-RECORD-SCHEMA.json').read_bytes())
    expected = reviewed_inputs(config, profile)
    installer_version = config['fixture_version'] if profile == 'fixture' else config['version']
    installer_source = ROOT/'packages'/config['addon_id']
    installer_files = {p.relative_to(installer_source).as_posix():p.read_bytes() for p in installer_source.rglob('*') if p.is_file()}
    assert set(installer_files) == {'addon.xml', 'LICENSE.txt', 'resources/icon.png', 'resources/ICON-LICENSE.txt'}
    assert installer_files['LICENSE.txt'] == (ROOT/'LICENSE').read_bytes()
    installer_manifest = xml(installer_files['addon.xml'])
    if profile == 'fixture':
        installer_manifest.set('version', config['fixture_version'])
        installer_manifest.set('name', installer_manifest.get('name')+' LOCAL FIXTURE')
        installer_manifest.find("extension[@point='xbmc.addon.metadata']/description").text = 'Local qualification only. Not published.'
    for directory in installer_manifest.findall("extension[@point='xbmc.addon.repository']/dir"):
        for tag in ('info', 'checksum', 'datadir', 'artdir'):
            node = directory.find(tag); node.text = node.text.replace(config['base_url'], config['base_url']+prefix, 1)
    assert (config['addon_id'], installer_version) not in expected, 'Duplicate generated installer'
    expected[(config['addon_id'], installer_version)] = {'files': installer_files,
        'manifest': installer_manifest, 'lanes': list(config['lanes']), 'fixture_only': profile == 'fixture'}
    keys = [(p['id'], p['version']) for p in plan['packages']]
    assert len(keys) == len(set(keys)) and set(keys) == set(expected), 'Unreviewed or missing package'
    if profile != 'fixture':
        hashes = {(p['id'], p['version']):p['sha256'] for p in plan['packages']}
        for old in json.loads((ROOT/'releases/manifest.json').read_text())['packages']:
            assert hashes.get((old['id'], old['version'])) == old['sha256'], 'Installer/package retention mismatch'
    expected_site = {'.nojekyll', 'index.html'}; assets = {}; packages = {}; receipts = []
    for record in plan['packages']:
        key = (record['id'], record['version']); reviewed = expected[key]
        assert record['lanes'] == reviewed['lanes'] and record['fixture_only'] is reviewed['fixture_only']
        assert record.get('approval') == reviewed.get('approval'), 'Approval report differs from reviewed input'
        relative = prefix+f'packages/{key[0]}/{key[0]}-{key[1]}.zip'
        assert record['path'] == relative
        blob = path(site, relative).read_bytes()
        assert len(blob) == record['bytes'] and digest(blob) == record['sha256']
        assert digest(blob) == path(site, relative+'.sha256').read_text().strip()
        if 'blob' in reviewed: assert blob == reviewed['blob'] and record['provenance'] == reviewed['provenance']
        manifest, files = archive_files(blob)
        assert (manifest.get('id'), manifest.get('version')) == key
        assert {n:digest(b) for n,b in files.items()} == record['provenance']['runtime_files']
        if 'manifest' in reviewed:
            assert set(files) == set(reviewed['files'])
            assert all(data == reviewed['files'][n] for n,data in files.items() if n != 'addon.xml')
            assert structure(manifest) == structure(reviewed['manifest'])
            dirs = manifest.findall("extension[@point='xbmc.addon.repository']/dir")
            assert len(dirs) == len(config['lanes'])
            for d,(lane,settings) in zip(dirs, config['lanes'].items()):
                assert d.attrib == {k:settings[k] for k in ['minversion', 'maxversion']}
                base = config['base_url']+prefix
                for tag, suffix in [('info', f'catalogs/{lane}/addons.xml'),
                    ('checksum', f'catalogs/{lane}/addons.xml.sha256'), ('datadir', 'packages/'), ('artdir', f'artwork/{lane}/')]:
                    assert d.findtext(tag) == base+suffix
                assert d.findtext('hashes') == 'sha256' and d.find('checksum').get('verify') == 'sha256'
        else: assert files == reviewed['files']
        mirror = Path(relative).name
        for name,data in [(mirror,blob), (mirror+'.sha256',(digest(blob)+'\n').encode())]:
            assert path(out/'release-assets', name).read_bytes() == data
            assets[name] = digest(data)
        expected_site.update([relative, relative+'.sha256'])
        packages[key] = (manifest, files)
        receipts.append({'id':key[0], 'version':key[1], 'entries':sorted(files), 'sha256':digest(blob), 'bytes':len(blob)})
    assert set(plan['catalogs']) == set(config['lanes'])
    for lane,settings in config['lanes'].items():
        record = plan['catalogs'][lane]; relative = prefix+f'catalogs/{lane}/addons.xml'
        assert record['path'] == relative
        selected = {key:packages[key] for key,item in expected.items() if lane in item['lanes']}
        assert len({k[0] for k in selected}) == len(selected)
        identities = {k[0]:k[1] for k in selected}
        data = path(site, relative).read_bytes()
        assert digest(data) == record['sha256'] == path(site, relative+'.sha256').read_text().strip()
        root = xml(data); assert root.tag == 'addons'
        assert len(root) == len(identities) and {m.get('id'):m.get('version') for m in root} == identities == record['ids']
        assert [m.get('id') for m in root] == sorted(identities)
        check_dependencies(list(root), settings['builtins'])
        for m in root:
            manifest, files = selected[(m.get('id'), m.get('version'))]
            assert structure(m) == structure(manifest)
            for asset in m.findall("extension[@point='xbmc.addon.metadata']/assets/*"):
                relative_asset = prefix+f'artwork/{lane}/{m.get("id")}/{asset.text}'
                assert path(site, relative_asset).read_bytes() == files[asset.text]
                expected_site.add(relative_asset)
        expected_site.update([relative, relative+'.sha256'])
    # Reconstruct the whole page from reviewed inputs. Substring matching alone
    # would accept notices hidden in comments, styles or hidden ancestors.
    page = path(site, 'index.html').read_bytes().decode('utf-8')
    links = ''.join(f'<li><a href="{prefix}packages/{aid}/{aid}-{ver}.zip">{aid} {ver}</a></li>'
                    for aid,ver in expected)
    notices = []
    for key,item in expected.items():
        record = item.get('provenance', {})
        if record.get('schema_version') == 3:
            notices.append('<section data-unofficial-package="'+key[0]+'-'+key[1]+'"><h2>'
                           +key[0]+' '+key[1]+'</h2><pre>'
                           +escape(record['unofficial_integration']['disclosure']['release_text'])
                           +'</pre></section>')
    if profile == 'fixture':
        expected_page = ('<!doctype html><title>AI Kodi repository: local draft</title>'
                         '<p>Not published. Fixture artifacts must never be deployed.</p><ul>'+links+'</ul>\n')
    elif profile == 'candidate':
        expected_page = ('<!doctype html><title>Private Kodi candidate</title>'
                         '<p>Not approved for release. Native acceptance and rights must be resolved.</p><ul>'+links+'</ul>\n')
    else:
        availability = ('Native Kodi acceptance is pending. Only the repository installer is currently available.</p>'
                        '<p>Tastemade and Aura are not published.' if len(expected) == 1 else
                        'Available packages are listed below. Compatibility and acceptance are package-specific.')
        expected_page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                         '<meta name="viewport" content="width=device-width, initial-scale=1">'
                         '<title>AI Kodi Repository</title><h1>AI Kodi Repository</h1>'
                         '<p>Version-aware Kodi repository infrastructure. '+availability+'</p><ul>'+links+'</ul>'
                         '<p>Each ZIP has a SHA-256 sidecar at the same URL plus .sha256.</p>'
                         '<p><a href="https://github.com/'+config['github_repository']+'">'
                         'Source, architecture and release procedures</a></p></html>\n')
    if notices:
        rendered = ''.join(notices)
        expected_page = (expected_page.replace('</html>', rendered+'</html>')
                         if '</html>' in expected_page else expected_page+rendered)
    assert page == expected_page, 'Public disclosure/index differs from reviewed input'
    actual = {p.relative_to(site).as_posix():digest(path(site, p.relative_to(site).as_posix()).read_bytes())
              for p in site.rglob('*') if p.is_file()}
    assert set(actual) == expected_site, 'Unreviewed or missing public site files'
    assert actual == plan['site_files'] and digest(json_bytes(actual)) == plan['site_manifest_sha256']
    assert {p.name:digest(path(out/'release-assets', p.name).read_bytes())
            for p in (out/'release-assets').iterdir() if p.is_file()} == assets == plan['release_assets']
    assert (out/'SHA256SUMS').read_bytes() == ''.join(f'{value}  {name}\n' for name,value in sorted(assets.items())).encode()
    blockers = ['Private candidate profile cannot authorize publication'] if profile == 'candidate' else []
    approvals = []
    for item in expected.values():
        if 'approval' in item:
            blockers.extend(item['approval']['release_blockers'])
            approvals.append(item['approval'])
    assert plan['release_blockers'] == sorted(set(blockers)), 'Approval blocker report mismatch'
    return {'status':'PASS', 'profile':profile, 'audit':'independent stdlib reviewed-input ZIP/XML/checksum inspection',
            'packages':receipts, 'catalogs':len(config['lanes']), 'site_files':len(actual),
            'production_addon_intake_empty':not json.loads((ROOT/'config/production.json').read_text())['packages'],
            'tastemade_or_aura_present':any(k[0] in ['plugin.video.tastemade', 'skin.aura'] for k in expected),
            'approvals': approvals, 'release_blockers':sorted(set(blockers)), 'runtime_tested':False, 'public_https_verified':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['fixture', 'production', 'candidate'], default='fixture')
    args = parser.parse_args()
    if not __debug__: raise RuntimeError('Run without -O; independent audit assertions are required')
    result = audit(args.profile); (ROOT/'reports').mkdir(exist_ok=True)
    target = 'operator-independent-audit.json' if args.profile == 'fixture' else args.profile+'-audit.json'
    (ROOT/'reports'/target).write_bytes(json_bytes(result))
    print(json.dumps(result, indent=2))
