"""Explicit static lane registry. No native/runtime compatibility is inferred."""
from pathlib import Path
import copy
import hashlib
import json

TARGETS = {'matrix': ('19.5', '19.0.3'), 'nexus': ('20.5', '20.0.1'),
           'omega': ('21.3', '21.0.0'), 'piers': ('22 preview', None)}
LIMITS = [
    'Toolkit syntax and mypy use Python 3.10; this is not target-runtime interpreter qualification.',
    'Matching Kodistubs checks selected API signatures, not complete runtime or native compatibility.',
    'Declared Python dependencies/platforms do not establish compatibility.',
]


def registry(installed):
    """Validate an operator-pinned registry without downloading or executing code."""
    from lifecycle import closed, require
    values = installed.get('lane_environments')
    if values is None:
        return {}
    require(isinstance(values, dict) and set(values) == set(TARGETS), 'Lane registry must name exactly four supported lanes')
    for lane, value in values.items():
        require(isinstance(value, dict) and value.get('status') in ('available', 'unverified'), 'Invalid lane registry status')
        if value['status'] == 'unverified':
            closed(value, {'status', 'reason'})
            require(isinstance(value['reason'], str) and bool(value['reason'].strip()), 'Unverified lane needs a reason')
            continue
        closed(value, {'status', 'python', 'toolkit', 'cache', 'identity', 'stub_version', 'coverage_limits'})
        require(isinstance(value['stub_version'], str) and value['stub_version'] == TARGETS[lane][1], 'Stub version/lane mismatch')
        for name in ('python', 'toolkit', 'cache'):
            require(isinstance(value[name], str) and Path(value[name]).is_absolute(), 'Lane paths must be operator-bound absolute paths')
        require(isinstance(value['identity'], dict) and value['identity'].get('environment', {}).get('packages', {}).get('Kodistubs', {}).get('version') == value['stub_version'],
                'Lane identity/stub mismatch')
        require(isinstance(value['coverage_limits'], list) and bool(value['coverage_limits']) and all(isinstance(v, str) and v.strip() for v in value['coverage_limits']),
                'Lane coverage limits missing')
    return copy.deepcopy(values)


def select(installed, lane):
    from lifecycle import require
    require(lane in TARGETS, 'Unsupported compatibility lane/version')
    return registry(installed).get(lane)


def verify(installed, lane, identity_reader):
    """Return selected current identity, failing closed on source/env/cache drift."""
    from lifecycle import require
    value = select(installed, lane)
    if value is None or value['status'] == 'unverified':
        return value
    current = identity_reader({**installed, **{k: value[k] for k in ('python', 'toolkit', 'cache')}})
    require(current == value['identity'], 'Lane source/environment/cache drift')
    return value


def index_identity(cache, lane):
    """Select exactly the branch's already-acquired, digest-verified offline index."""
    from lifecycle import read_json, path_at, require
    require(lane in TARGETS, 'Unsupported index lane')
    manifest = read_json(path_at(Path(cache), 'manifest.json'))
    require(manifest.get('schema_version') == 1, 'Unknown Toolkit cache manifest schema')
    entries = manifest.get('entries', manifest.get('indexes'))
    # The pinned Toolkit cache uses a list of source records.
    if isinstance(entries, dict):
        entries = list(entries.values())
    require(isinstance(entries, list), 'Unknown Toolkit cache manifest schema')
    matches = [e for e in entries if e.get('url') == f'https://mirrors.kodi.tv/addons/{lane}/addons.xml.gz']
    require(len(matches) == 1, 'Missing/ambiguous lane index')
    entry = matches[0]
    name = entry.get('filename', entry.get('file', entry.get('path', lane+'.xml.gz')))
    require(name == lane+'.xml.gz', 'Lane index filename mismatch')
    data = path_at(Path(cache), name).read_bytes()
    require(hashlib.sha256(data).hexdigest() == entry['sha256'], 'Lane index checksum mismatch')
    return {'lane': lane, 'url': entry['url'], 'sha256': entry['sha256'],
            'fetched_at': entry.get('fetched_at', manifest.get('fetched_at')), 'file': name}


def configure(root):
    """Operator-only local environments; preserve the shared Nexus installation."""
    import shutil
    import subprocess
    from urllib.request import build_opener, ProxyHandler, Request
    from urllib.parse import urlsplit
    from lifecycle import installation, toolkit_identity, read_json, path_at, require, replace_json, sha
    installed = installation(root)
    require('lane_environments' not in installed, 'Lane registry already installed; explicit reviewed migration required')
    require(toolkit_identity(installed) == installed['toolkit_identity'], 'Trusted baseline environment drift')
    pins = read_json(path_at(root, 'config/LIFECYCLE-LANES.json'))
    output = root/'.opencode/lane-environments'
    path_at(output.parent, output.name, exists=False)
    output.mkdir(mode=0o700, exist_ok=False)
    results = {}
    opener = build_opener(ProxyHandler({}))
    for lane, (_, version) in TARGETS.items():
        if version is None:
            results[lane] = {'status':'unverified', 'reason':'No published or independently qualified Piers 22 stub environment; no other-major substitution'}
            continue
        if lane == 'nexus':
            python = Path(installed['python'])
        else:
            pin = pins['stubs'][lane]
            require(pin['version'] == version, 'Stub acquisition pin mismatch')
            with opener.open(Request(f'https://pypi.org/pypi/Kodistubs/{version}/json'), timeout=25) as response:
                raw = response.read(2_000_001)
                require(len(raw) <= 2_000_000, 'Oversized package index')
                metadata = json.loads(raw)
            wheels = [v for v in metadata['urls'] if v['filename'].endswith('.whl') and v['digests']['sha256'] == pin['sha256']]
            require(len(wheels) == 1, 'Pinned stub wheel unavailable')
            wheel = wheels[0]; url = urlsplit(wheel['url'])
            require(url.scheme == 'https' and url.netloc == 'files.pythonhosted.org' and not url.query, 'Unexpected wheel origin')
            with opener.open(Request(wheel['url']), timeout=25) as response:
                data = response.read(4_000_001)
            require(len(data) <= 4_000_000 and sha(data) == pin['sha256'], 'Stub wheel digest mismatch')
            wheel_path = output/wheel['filename']
            require(wheel_path.parent == output, 'Unsafe wheel filename')
            wheel_path.write_bytes(data)
            environment = output/lane
            shutil.copytree(Path(installed['python']).parent.parent, environment, symlinks=True)
            python = environment/'bin/python'
            process = subprocess.run([str(python), '-I', '-B', '-m', 'pip', '--isolated', 'install', '--no-index',
                                      '--no-deps', '--disable-pip-version-check', str(wheel_path)],
                                     cwd=output, env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},
                                     capture_output=True, text=True, timeout=120)
            require(process.returncode == 0, 'Local stub environment install failed: '+process.stderr[-500:])
        selected = {**installed, 'python':str(python)}
        identity = toolkit_identity(selected)
        require(identity['environment']['packages']['Kodistubs']['version'] == version, 'Installed stub version differs')
        index_identity(installed['cache'], lane)
        results[lane] = {'status':'available', 'python':str(python), 'toolkit':installed['toolkit'], 'cache':installed['cache'],
                         'identity':identity, 'stub_version':version, 'coverage_limits':list(LIMITS)}
    candidate = {**installed, 'lane_environments':results}
    registry(candidate)
    replace_json(root/'.opencode/lifecycle-installation.json', candidate)
    return {'status':'PASS', 'lanes':{k:{'status':v['status'],'stub_version':v.get('stub_version'), 'reason':v.get('reason')}
                                    for k,v in results.items()}, 'native_tested':False}
