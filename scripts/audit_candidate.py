#!/usr/bin/env python3
"""Independent stdlib artifact audit; does not import the builder or run add-ons."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def digest(data):return hashlib.sha256(data).hexdigest()
def structure(element):
    return (element.tag,sorted(element.attrib.items()),(element.text or '').strip(),[structure(c) for c in element])

def audit(profile='fixture'):
    assert profile in ('fixture','production')
    prefix='qualification/' if profile=='fixture' else ''
    out=ROOT/'dist'/profile;site=out/'site';config=json.loads((ROOT/'config/repository.json').read_text())
    plan=json.loads((out/'release-plan.json').read_text());packages={};receipts=[]
    for record in plan['packages']:
        blob=(site/record['path']).read_bytes()
        assert digest(blob)==record['sha256']==Path(str(site/record['path'])+'.sha256').read_text().strip()
        assert (out/'release-assets'/Path(record['path']).name).read_bytes()==blob
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names=z.namelist();assert names==sorted(names) and len(names)==len(set(names)) and z.testzip() is None
            expected_root=record['id']+'/'
            for info in z.infolist():
                assert info.filename.startswith(expected_root) and info.date_time==(1980,1,1,0,0,0)
                assert stat.S_ISREG(info.external_attr>>16) and (info.external_attr>>16)&0o777==0o644
            files={n[len(expected_root):]:z.read(n) for n in names}
            assert {n:digest(data) for n,data in files.items()}==record['provenance']['runtime_files']
            manifest=ET.fromstring(files['addon.xml']);assert manifest.get('id')==record['id'] and manifest.get('version')==record['version']
            if record['id']=='script.toolkit.sample':
                source=ROOT/'fixtures'/record['version']/record['id']
                assert set(files)=={'addon.xml','default.py','LICENSE.txt','resources/icon.png'}
                assert all(data==(source/name).read_bytes() for name,data in files.items())
            else:
                assert record['id']=='repository.ai.kodi' and set(files)=={'addon.xml','LICENSE.txt','resources/icon.png','resources/ICON-LICENSE.txt'}
                dirs=manifest.findall("extension[@point='xbmc.addon.repository']/dir")
                assert len(dirs)==4
                for d,(name,lane) in zip(dirs,config['lanes'].items()):
                    assert d.attrib=={k:lane[k] for k in ['minversion','maxversion']}
                    assert d.findtext('info')==config['base_url']+prefix+'catalogs/'+name+'/addons.xml'
                    assert d.findtext('datadir')==config['base_url']+prefix+'packages/'
                if profile=='production':
                    assert all(data==(ROOT/'packages/repository.ai.kodi'/name).read_bytes() for name,data in files.items())
            packages[(record['id'],record['version'])]=manifest
            receipts.append({'id':record['id'],'version':record['version'],'entries':names,'sha256':digest(blob),'bytes':len(blob)})
    expected={'matrix':'1.0.0','nexus':'1.0.0','omega':'1.1.0','piers':'1.1.0'}
    for lane,record in plan['catalogs'].items():
        data=(site/record['path']).read_bytes();assert digest(data)==record['sha256']==Path(str(site/record['path'])+'.sha256').read_text().strip()
        root=ET.fromstring(data);assert root.tag=='addons'
        identities={'repository.ai.kodi':'0.0.0','script.toolkit.sample':expected[lane]} if profile=='fixture' else {'repository.ai.kodi':config['version']}
        assert {m.get('id'):m.get('version') for m in root}==identities and len(root)==len(identities)
        for m in root:assert structure(m)==structure(packages[(m.get('id'),m.get('version'))])
    assert json.loads((ROOT/'config/production.json').read_text())['packages']==[]
    assert all(p.get('id') not in ['plugin.video.tastemade','skin.aura'] for p in plan['packages'])
    if profile=='production':
        assert len(plan['packages'])==1 and plan['packages'][0]['id']=='repository.ai.kodi'
        actual={p.relative_to(site).as_posix():digest(p.read_bytes()) for p in site.rglob('*') if p.is_file()}
        assert actual==plan['site_files'] and not any('qualification' in p or 'script.toolkit.sample' in p for p in actual)
    return {'status':'PASS','profile':profile,'audit':'independent standard-library ZIP/XML/source/checksum inspection',
            'packages':receipts,'catalogs':4,'production_addon_intake_empty':True,
            'tastemade_or_aura_present':False,'runtime_tested':False,'public_https_verified':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',choices=['fixture','production'],default='fixture');args=parser.parse_args()
    if not __debug__:raise RuntimeError('Run without -O; independent audit assertions are required')
    result=audit(args.profile);(ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports'/('operator-independent-audit.json' if args.profile=='fixture' else 'production-audit.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
