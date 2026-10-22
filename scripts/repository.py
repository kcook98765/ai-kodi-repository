#!/usr/bin/env python3
"""Offline deterministic repository builder. No publication or source execution."""
from __future__ import annotations
import argparse
import approval_contract
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zlib
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)+\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
DENIED = {'.git', '.opencode', '.agents', 'tests', 'test', 'docs', 'tools',
          'node_modules', '.venv', 'venv', '__pycache__', 'reports', 'profile', 'profiles'}
MAX_ZIP_BYTES = 64_000_000
MAX_ENTRIES = 10000
MAX_RUNTIME_BYTES = 256_000_000

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def version(value):
    require(isinstance(value, str) and bool(VERSION.fullmatch(value)), 'Only reviewed numeric x.y.z versions are supported')
    return tuple(map(int, value.split('.')))

def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()

def xml_bytes(element):
    element = copy.deepcopy(element)
    element.tail = None
    ET.indent(element, space='  ')
    return ET.tostring(element, encoding='utf-8', xml_declaration=True) + b'\n'

def parse_xml(data):
    require(len(data) <= 2_000_000, 'XML size limit exceeded')
    text = data.decode('utf-8-sig')
    require('\0' not in text, 'Only UTF-8 XML is accepted')
    require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(), 'XML entities forbidden')
    return ET.fromstring(data)

def safe_path(base, name, exists=True):
    p = PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and '..' not in p.parts and
            '\\' not in name and ':' not in name and '\0' not in name,
            'Unsafe relative path')
    require(p.as_posix() == name, 'Noncanonical relative path')
    require(p.parts and all(not any(ord(c) < 32 or c in '<>"|?*' for c in part) and
            not part.endswith((' ', '.')) and
            part.split('.')[0].upper() not in {'CON', 'PRN', 'AUX', 'NUL',
                *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}
            for part in p.parts), 'Unsafe portable path')
    result = base.joinpath(*p.parts)
    require(result.resolve().is_relative_to(base.resolve()), 'Path escapes scope')
    for item in [result, *result.parents]:
        require(not item.is_symlink(), 'Linked path forbidden')
        if item == base:
            break
    if exists:
        require(result.is_file(), 'Missing file: ' + name)
    return result

def runtime_name(name):
    parts = PurePosixPath(name).parts
    require(not any(x.lower() in DENIED or x.startswith('.') for x in parts), 'Development/hidden payload forbidden')
    require(not name.lower().endswith(('.pyc', '.pyo', '.log', '.toml', '.lock')) and
            PurePosixPath(name).name.lower() not in {'opencode.json', 'agents.md', 'development.md',
                'contributing.md', 'requirements.txt', 'pyproject.toml', 'credentials.json', 'auth.json'},
            'Development payload forbidden')

def inventory_paths(names):
    folded = {name.casefold() for name in names}
    require(len(folded) == len(names), 'Duplicate/case-colliding paths')
    for name in names:
        safe_path(ROOT, name, exists=False)
        require(not any(p.as_posix().casefold() in folded for p in PurePosixPath(name).parents
                        if p.as_posix() != '.'), 'File/directory path collision')

def manifest_files(files):
    require('addon.xml' in files, 'Manifest missing')
    root = parse_xml(files['addon.xml'])
    require(root.tag == 'addon' and bool(ID.fullmatch(root.get('id', ''))), 'Invalid add-on ID')
    version(root.get('version', ''))
    require(root.get('name') and root.get('provider-name'), 'Required identity metadata missing')
    metadata = root.find("extension[@point='xbmc.addon.metadata']")
    require(metadata is not None and len(root.findall("extension[@point='xbmc.addon.metadata']")) == 1,
            'Exactly one metadata extension required')
    require(any(e.get('point') and e.get('point') != 'xbmc.addon.metadata' for e in root.findall('extension')),
            'Runtime extension missing')
    for tag in ('summary', 'description', 'platform', 'license'):
        require(bool(metadata.findtext(tag)), 'Required metadata missing: ' + tag)
    require(any(PurePosixPath(x).name.lower().startswith(('license', 'copying')) for x in files), 'License missing')
    for extension in root.findall('extension'):
        library = extension.get('library')
        if library:
            require(library in files, 'Declared entry point missing')
    for asset in metadata.findall('assets/*'):
        require(asset.text in files, 'Declared artwork missing')
    requires = root.findall('requires')
    require(len(requires) <= 1 and all(d.tag == 'import' for group in requires for d in group),
            'Malformed dependency declarations')
    dependency_ids = set()
    for dep in root.findall('requires/import'):
        require(bool(ID.fullmatch(dep.get('addon', ''))), 'Invalid dependency ID')
        require(dep.get('addon') not in dependency_ids, 'Duplicate dependency ID')
        dependency_ids.add(dep.get('addon'))
        version(dep.get('version', ''))
        require(dep.get('optional', 'false') in ('true', 'false'), 'Invalid optional dependency flag')
    return root

def zip_bytes(files):
    inventory_paths(files)
    root = manifest_files(files)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            safe_path(ROOT, name, exists=False)
            runtime_name(name)
            info = zipfile.ZipInfo(root.get('id') + '/' + name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buffer.getvalue()

def inspect_zip(blob, expected=None):
    require(len(blob) <= MAX_ZIP_BYTES, 'ZIP size limit exceeded')
    files = {}
    roots = set()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_ENTRIES, 'ZIP entry limit exceeded')
        require(len({i.filename for i in infos}) == len(infos), 'Duplicate ZIP paths')
        require(len({i.filename.casefold() for i in infos}) == len(infos), 'Case-colliding ZIP paths')
        inventory_paths([i.filename for i in infos])
        require(sum(i.file_size for i in infos) <= MAX_RUNTIME_BYTES, 'Uncompressed ZIP size limit exceeded')
        for info in infos:
            require(not info.is_dir() and not info.flag_bits & 1, 'Directories/encryption not accepted')
            mode = info.external_attr >> 16
            require(not stat.S_ISLNK(mode) and (stat.S_IFMT(mode) in (0, stat.S_IFREG)), 'Non-regular ZIP entry')
            safe_path(ROOT, info.filename, exists=False)
            parts = PurePosixPath(info.filename).parts
            require(len(parts) >= 2, 'Single add-on root required')
            roots.add(parts[0])
            name = '/'.join(parts[1:])
            runtime_name(name)
            files[name] = archive.read(info)
        require(archive.testzip() is None, 'CRC failure')
    manifest = manifest_files(files)
    require(roots == {manifest.get('id')}, 'ZIP root differs from manifest ID')
    if expected is not None:
        require({n: sha(v) for n, v in files.items()} == expected, 'ZIP differs from reviewed runtime allowlist')
    return manifest, files

def load_config():
    config = json.loads((ROOT/'config/repository.json').read_text())
    require(config['addon_id'] == 'repository.ai.kodi', 'Repository identity mismatch')
    require(config['publication_authorized'] is False, 'This builder has no publication authority')
    url = urlsplit(config['base_url'])
    require(url.scheme == 'https' and url.hostname and not url.username and not url.password and
            not url.query and not url.fragment and url.path.endswith('/'), 'Invalid HTTPS base URL')
    previous = None
    for lane in config['lanes'].values():
        low, high = version(lane['minversion']), version(lane['maxversion'])
        require(low <= high and (previous is None or low > previous), 'Overlapping/invalid lane ranges')
        previous = high
    return config

def installer(config, profile):
    root = ET.Element('addon', {'id': config['addon_id'], 'version': config['fixture_version'] if profile == 'fixture' else config['version'],
        'name': 'AI Kodi Repository' + (' LOCAL FIXTURE' if profile == 'fixture' else ''),
        'provider-name': config['provider']})
    requires = ET.SubElement(root, 'requires')
    ET.SubElement(requires, 'import', {'addon': 'xbmc.addon', 'version': '19.0.0'})
    ext = ET.SubElement(root, 'extension', {'point': 'xbmc.addon.repository'})
    base = config['base_url'] + ('qualification/' if profile == 'fixture' else '')
    for name, lane in config['lanes'].items():
        directory = ET.SubElement(ext, 'dir', {k: lane[k] for k in ('minversion', 'maxversion')})
        ET.SubElement(directory, 'info').text = base + 'catalogs/' + name + '/addons.xml'
        ET.SubElement(directory, 'checksum', {'verify': 'sha256'}).text = base + 'catalogs/' + name + '/addons.xml.sha256'
        ET.SubElement(directory, 'datadir').text = base + 'packages/'
        ET.SubElement(directory, 'artdir').text = base + 'artwork/' + name + '/'
        ET.SubElement(directory, 'hashes').text = 'sha256'
    meta = ET.SubElement(root, 'extension', {'point': 'xbmc.addon.metadata'})
    for tag, text in [('summary', 'Independent Kodi add-on distribution'),
                      ('description', 'Local qualification only. Not published.' if profile == 'fixture' else
                       'Reviewed independent add-ons, selected by Kodi version.'),
                      ('platform', 'all'), ('license', 'MIT'),
                      ('source', 'https://github.com/' + config['github_repository'])]:
        ET.SubElement(meta, tag, {'lang': 'en_GB'} if tag in ('summary', 'description') else {}).text = text
    ET.SubElement(ET.SubElement(meta, 'assets'), 'icon').text = 'resources/icon.png'
    return {'addon.xml': xml_bytes(root),
            'LICENSE.txt': (ROOT/'LICENSE').read_bytes(),
            'resources/ICON-LICENSE.txt': (ROOT/'packages/repository.ai.kodi/resources/ICON-LICENSE.txt').read_bytes(),
            'resources/icon.png': (ROOT/'packages/repository.ai.kodi/resources/icon.png').read_bytes()}

def fixture_packages():
    result = []
    for release, lanes in [('1.0.0', ['matrix', 'nexus']), ('1.1.0', ['omega', 'piers'])]:
        source = ROOT/'fixtures'/release/'script.toolkit.sample'
        names = ['LICENSE.txt', 'addon.xml', 'default.py', 'resources/icon.png']
        files = {name: safe_path(source, name).read_bytes() for name in names}
        blob = zip_bytes(files)
        require(blob == zip_bytes(files), 'Non-reproducible fixture package')
        validation_path = ROOT/'reports'/('toolkit-'+release+'.json')
        validation = json.loads(validation_path.read_text())
        from kodi_agent_toolkit.evidence import source_snapshot
        require(validation['passed'] and validation['branch'] == 'nexus' and
                validation['source_snapshot'] == source_snapshot(source), 'Missing/stale fixture Nexus validation')
        result.append({'blob': blob, 'lanes': lanes, 'fixture_only': True,
            'provenance': {'source': 'Kodi Agent Toolkit MIT disposable fixture',
                'toolkit_revision': '552b0b949220f2d545ab42a7f27d1826a535c686',
                'runtime_files': {n: sha(v) for n,v in files.items()},
                'static_lane': 'nexus', 'runtime_tested': False,
                'validation_sha256': sha(validation_path.read_bytes())}})
    return result

def production_packages(config, profile='production'):
    require(profile in ('production', 'candidate'), 'Invalid intake profile')
    inputs = json.loads((ROOT/f'config/{profile}.json').read_text())
    require(inputs['external_dependencies'] == {}, 'External dependency snapshots need a separately reviewed adapter')
    ledger = json.loads((ROOT/'releases/manifest.json').read_text())
    packages = []
    for item in inputs['packages']:
        blob = safe_path(ROOT/'incoming', item['zip']).read_bytes()
        require(sha(blob) == item['sha256'], 'Reviewed input checksum mismatch')
        record_path = safe_path(ROOT/'incoming', item['review_record'])
        require(sha(record_path.read_bytes()) == item['review_record_sha256'], 'Review record hash mismatch')
        record = json.loads(record_path.read_text())
        require(record['package_sha256'] == sha(blob) and record['fixture_only'] is False,
                'Independent package approval/hash evidence missing')
        require(all(type(record[k]) is bool for k in ('release_approved','rights_approved')),
                'Malformed approval evidence')
        require(re.fullmatch('[0-9a-f]{40}', record['source_commit']) and record['source_repository'].startswith('https://github.com/'), 'Source provenance missing')
        require(len(set(item['lanes'])) == len(item['lanes']), 'Duplicate lane')
        for lane in item['lanes']:
            require(lane in config['lanes'], 'Unknown lane')
            acceptance = record['compatibility'][lane]
            require(all(type(acceptance[k]) is bool for k in ('static_accepted','runtime_accepted')) and
                    isinstance(acceptance['evidence'], list) and
                    all(isinstance(e, str) and e.strip() for e in acceptance['evidence']), 'Malformed lane evidence')
        approval = approval_contract.assess(record, item['lanes'])
        approval['review_record_sha256'] = item['review_record_sha256']
        approval['package_sha256'] = sha(blob)
        blockers = approval['release_blockers']
        require(profile == 'candidate' or not blockers, 'Independent package approval evidence missing: ' + '; '.join(blockers))
        inspect_zip(blob, record['runtime_files'])
        packages.append({'blob': blob, 'lanes': item['lanes'], 'fixture_only': False,
                         'provenance': record, 'approval': approval, 'release_blockers': blockers})
    current = {}
    for item in packages:
        manifest, _ = inspect_zip(item['blob'])
        current[(manifest.get('id'), manifest.get('version'))] = sha(item['blob'])
    for old in ledger['packages']:
        if (old['id'], old['version']) == (config.get('addon_id'), config.get('version')):
            # The generated installer is appended in build(); check its bytes there.
            continue
        require(current.get((old['id'], old['version'])) == old['sha256'], 'Historical release removed or changed')
    return packages

def dependencies(selected, builtins):
    available = {**builtins, **{m.get('id'): m.get('version') for m in selected}}
    edges = {}
    warnings = []
    for manifest in selected:
        edges[manifest.get('id')] = []
        for dep in manifest.findall('requires/import'):
            name = dep.get('addon')
            satisfied = name in available and version(available[name]) >= version(dep.get('version'))
            if dep.get('optional') == 'true':
                if not satisfied:
                    warnings.append('Optional dependency unresolved: ' + name)
                continue
            require(satisfied, 'Required dependency unavailable/too old: ' + name)
            if name not in builtins:
                edges[manifest.get('id')].append(name)
    def visit(node, active, done):
        require(node not in active, 'Dependency cycle')
        if node in done:
            return
        for child in edges.get(node, []):
            visit(child, active | {node}, done)
        done.add(node)
    done = set()
    for node in edges:
        visit(node, set(), done)
    return warnings

def write_output(path, data, immutable=False):
    safe_path(ROOT, path.relative_to(ROOT).as_posix(), exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        require(path.read_bytes() == data, 'Immutable version/path would change: ' + str(path))
    path.write_bytes(data)

def build(profile):
    require(profile in ('fixture', 'production', 'candidate'), 'Invalid profile')
    config = load_config()
    output = ROOT/'dist'/profile
    site = output/'site'
    prefix = 'qualification/' if profile == 'fixture' else ('candidate/' if profile == 'candidate' else '')
    feedroot = site/prefix
    inputs = fixture_packages() if profile == 'fixture' else production_packages(config, profile)
    installer_files = installer(config, profile)
    if profile == 'candidate':
        # Private preview only: never point its installer at the production feed.
        root = parse_xml(installer_files['addon.xml'])
        for directory in root.findall("extension[@point='xbmc.addon.repository']/dir"):
            for tag in ('info','checksum','datadir','artdir'):
                node = directory.find(tag)
                node.text = node.text.replace(config['base_url'], config['base_url']+'candidate/', 1)
        installer_files['addon.xml'] = xml_bytes(root)
    installer_blob = zip_bytes(installer_files)
    inputs.append({'blob': installer_blob, 'lanes': list(config['lanes']),
                   'fixture_only': profile == 'fixture',
                   'provenance': {'runtime_files': {n:sha(v) for n,v in installer_files.items()},
                                  'source': 'local repository installer', 'runtime_tested': False}})
    if profile != 'fixture':
        retained = {}
        for item in inputs:
            manifest, _ = inspect_zip(item['blob'])
            retained[(manifest.get('id'), manifest.get('version'))] = sha(item['blob'])
        for old in json.loads((ROOT/'releases/manifest.json').read_text())['packages']:
            require(retained.get((old['id'], old['version'])) == old['sha256'],
                    'Historical release removed or changed (including installer)')
    records = []
    parsed = []
    identities = set()
    for item in inputs:
        manifest, files = inspect_zip(item['blob'], item['provenance']['runtime_files'])
        aid, ver = manifest.get('id'), manifest.get('version')
        require((aid,ver) not in identities, 'Duplicate release identity')
        identities.add((aid,ver))
        relative = f'packages/{aid}/{aid}-{ver}.zip'
        checksum = (sha(item['blob'])+'\n').encode()
        for target in [feedroot/relative, output/'release-assets'/f'{aid}-{ver}.zip']:
            write_output(target, item['blob'], immutable=True)
            write_output(Path(str(target)+'.sha256'), checksum, immutable=True)
        record = {'id': aid, 'version': ver, 'sha256': sha(item['blob']), 'bytes': len(item['blob']),
                  'path': prefix+relative, 'lanes': item['lanes'], 'fixture_only': item['fixture_only'],
                  'provenance': item['provenance']}
        if 'approval' in item:
            record['approval'] = item['approval']
        records.append(record)
        parsed.append((item,manifest,files))
    catalogs = {}
    for lane, settings in config['lanes'].items():
        selected = [(item,m,f) for item,m,f in parsed if lane in item['lanes']]
        require(len({m.get('id') for _,m,_ in selected}) == len(selected), 'Multiple current versions in one lane')
        warnings = dependencies([m for _,m,_ in selected], settings['builtins'])
        catalog = ET.Element('addons')
        for item,m,files in sorted(selected,key=lambda v:v[1].get('id')):
            catalog.append(copy.deepcopy(m))
            for asset in m.findall("extension[@point='xbmc.addon.metadata']/assets/*"):
                target = feedroot/'artwork'/lane/m.get('id')/asset.text
                write_output(target, files[asset.text])
        data = xml_bytes(catalog)
        path = feedroot/'catalogs'/lane/'addons.xml'
        write_output(path, data)
        write_output(Path(str(path)+'.sha256'), (sha(data)+'\n').encode())
        catalogs[lane] = {'path': path.relative_to(site).as_posix(), 'sha256': sha(data),
                          'ids': {m.get('id'):m.get('version') for _,m,_ in selected}, 'warnings': warnings}
    write_output(site/'.nojekyll', b'')
    links = ''.join(f'<li><a href="{r["path"]}">{r["id"]} {r["version"]}</a></li>' for r in records)
    if profile == 'fixture':
        page = ('<!doctype html><title>AI Kodi repository: local draft</title>'
                '<p>Not published. Fixture artifacts must never be deployed.</p><ul>'+links+'</ul>\n')
    elif profile == 'candidate':
        page = ('<!doctype html><title>Private Kodi candidate</title>'
                '<p>Not approved for release. Native acceptance and rights must be resolved.</p><ul>'+links+'</ul>\n')
    else:
        availability = ('Native Kodi acceptance is pending. Only the repository installer is currently available.</p>'
                        '<p>Tastemade and Aura are not published.' if len(records) == 1 else
                        'Available packages are listed below. Compatibility and acceptance are package-specific.')
        page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>AI Kodi Repository</title><h1>AI Kodi Repository</h1>'
                '<p>Version-aware Kodi repository infrastructure. '
                +availability+'</p><ul>'+links+'</ul>'
                '<p>Each ZIP has a SHA-256 sidecar at the same URL plus .sha256.</p>'
                '<p><a href="https://github.com/'+config['github_repository']+'">'
                'Source, architecture and release procedures</a></p></html>\n')
    write_output(site/'index.html', page.encode())
    site_files = {p.relative_to(site).as_posix():sha(p.read_bytes()) for p in sorted(site.rglob('*')) if p.is_file()}
    release_assets = {p.name:sha(p.read_bytes()) for p in sorted((output/'release-assets').iterdir()) if p.is_file()}
    plan = {'schema':1, 'profile':profile, 'fixture_only':profile=='fixture',
            'publication_authorized':False, 'github_repository':config['github_repository'],
            'proposed_tag':('qualification-'+config['fixture_version'] if profile=='fixture' else 'repository-'+config['version']),
            'config_sha256':sha((ROOT/'config/repository.json').read_bytes()),
            'input_config_sha256':sha((ROOT/('config/candidate.json' if profile=='candidate' else 'config/production.json')).read_bytes()),
            'retention_ledger_sha256':sha((ROOT/'releases/manifest.json').read_bytes()),
            'toolchain': {'python':sys.version.split()[0], 'zlib':zlib.ZLIB_RUNTIME_VERSION,
                          'builder_sha256':sha(Path(__file__).read_bytes()),
                          'approval_contract_sha256':sha(Path(approval_contract.__file__).read_bytes())},
            'release_assets':release_assets, 'site_files':site_files,
            'site_manifest_sha256':sha(json_bytes(site_files)),
            'proposed_actions':['create approved GitHub repository (not authorized)',
                                'push approved source snapshot (not authorized)',
                                'upload pinned reviewed Release assets (not authorized)',
                                'deploy approved production Pages artifact (not authorized)'],
            'packages':records, 'catalogs':catalogs,
            'required_approvals':['source package review','compatibility and runtime evidence','rights','exact release hashes','GitHub creation','release and Pages deployment'],
            'remote_actions_executed':[], 'live_https_verified':False}
    plan['release_blockers'] = sorted({blocker for item in inputs for blocker in item.get('release_blockers', [])}
        | ({'Private candidate profile cannot authorize publication'} if profile == 'candidate' else set()))
    write_output(output/'release-plan.json', json_bytes(plan))
    sums = ''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in sorted((output/'release-assets').iterdir()) if p.is_file())
    write_output(output/'SHA256SUMS', sums.encode())
    return {'status':'PASS', 'profile':profile, 'output':str(output), 'plan_sha256':sha(json_bytes(plan)),
            'packages':[{k:r[k] for k in ('id','version','bytes','sha256')} for r in records],
            'catalogs':catalogs, 'publication_authorized':False}

def verify(profile):
    config = load_config()
    output = ROOT/'dist'/profile
    site = output/'site'
    plan = json.loads((output/'release-plan.json').read_text())
    require(plan['publication_authorized'] is False and plan['profile'] == profile, 'Plan profile mismatch')
    require(plan['config_sha256'] == sha((ROOT/'config/repository.json').read_bytes()), 'Stale configuration')
    require(plan['input_config_sha256'] == sha((ROOT/('config/candidate.json' if profile=='candidate' else 'config/production.json')).read_bytes()), 'Stale intake configuration')
    require(plan['retention_ledger_sha256'] == sha((ROOT/'releases/manifest.json').read_bytes()), 'Stale retention ledger')
    require(plan['toolchain']['builder_sha256'] == sha(Path(__file__).read_bytes()), 'Stale builder evidence')
    require(plan['toolchain']['approval_contract_sha256'] == sha(Path(approval_contract.__file__).read_bytes()), 'Stale approval contract')
    actual_site = {p.relative_to(site).as_posix():sha(p.read_bytes()) for p in sorted(site.rglob('*')) if p.is_file()}
    require(actual_site == plan['site_files'] and sha(json_bytes(actual_site)) == plan['site_manifest_sha256'], 'Site contains missing/changed/unreviewed files')
    require({p.name:sha(p.read_bytes()) for p in sorted((output/'release-assets').iterdir()) if p.is_file()} == plan['release_assets'], 'Release asset set differs')
    for line in (output/'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        require(sha(safe_path(output/'release-assets', name).read_bytes()) == digest, 'Release checksum list mismatch')
    for record in plan['packages']:
        blob = safe_path(site,record['path']).read_bytes()
        require(sha(blob) == record['sha256'], 'Package hash mismatch')
        require(Path(str(site/record['path'])+'.sha256').read_text().strip() == sha(blob), 'Package sidecar mismatch')
        manifest, _ = inspect_zip(blob, record['provenance']['runtime_files'])
        require(manifest.get('id') == record['id'] and manifest.get('version') == record['version'], 'Package identity mismatch')
        require((output/'release-assets'/Path(record['path']).name).read_bytes() == blob, 'Release mirror mismatch')
    for lane, record in plan['catalogs'].items():
        data = safe_path(site, record['path']).read_bytes()
        require(sha(data) == record['sha256'] == Path(str(site/record['path'])+'.sha256').read_text().strip(), 'Catalog checksum mismatch')
        root = parse_xml(data)
        require(root.tag == 'addons', 'Invalid catalog root')
        actual = {m.get('id'):m.get('version') for m in root}
        require(actual == record['ids'], 'Catalog identity mismatch')
        dependencies(list(root), config['lanes'][lane]['builtins'])
        for entry in root:
            package = next(r for r in plan['packages'] if r['id']==entry.get('id') and r['version']==entry.get('version'))
            manifest, files = inspect_zip((site/package['path']).read_bytes())
            require(xml_bytes(entry) == xml_bytes(manifest), 'Catalog/package manifest mismatch')
            for asset in entry.findall("extension[@point='xbmc.addon.metadata']/assets/*"):
                prefix = 'qualification/' if profile=='fixture' else ('candidate/' if profile=='candidate' else '')
                require(safe_path(site, prefix+f'artwork/{lane}/{entry.get("id")}/{asset.text}').read_bytes() == files[asset.text], 'Artwork mismatch')
    return {'status':'PASS','profile':profile,'catalogs':len(plan['catalogs']),'packages':len(plan['packages']),
            'live_https_verified':False,'runtime_tested':False,'publication_authorized':False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['build','verify'])
    parser.add_argument('--profile', choices=['fixture','production','candidate'], default='fixture')
    args = parser.parse_args()
    print(json.dumps((build if args.operation=='build' else verify)(args.profile), indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status':'FAIL','error':type(error).__name__,'detail':str(error)}))
        sys.exit(1)
