"""Complete private candidate feeds using the existing builder and independent auditor."""
from pathlib import Path
import copy
import json
import os
import subprocess

SCRIPTS = ('repository.py','audit_candidate.py','approval_contract.py','qualify.py','check_publication.py')


def inventory(root):
    from lifecycle import path_at, require, sha
    files = {}
    for file in root.rglob('*'):
        require(not file.is_symlink(), 'Linked candidate staging entry')
        if file.is_file():
            relative = file.relative_to(root).as_posix()
            files[relative] = sha(path_at(root, relative).read_bytes())
        else:
            require(file.is_dir(), 'Special candidate staging entry')
    return files


def run(stage, python, script, arguments):
    from lifecycle import require
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
    process = subprocess.run([python,'-I','-B','-c',bootstrap,str(stage/'scripts'),str(stage/'scripts'/script),*arguments], cwd=stage,
                             env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},
                             capture_output=True,text=True,timeout=180)
    require(len(process.stdout)+len(process.stderr) <= 2_000_000, 'Candidate verifier output exceeds limit')
    require(process.returncode == 0, 'Candidate feed blocked: '+(process.stderr or process.stdout)[-1600:])
    return json.loads(process.stdout)


def members(store, binding, state, out):
    """Inputs come only from exact already-enrolled task bindings under their locks."""
    from lifecycle import path_at, read_json, require, sha
    sources = []
    def capture(b, s, o):
        require(s['stage']=='prepared', 'Feed member is not prepared')
        require(b['baseline']==binding['baseline'], 'Feed member production baseline differs')
        receipt = read_json(path_at(o,'preparation.json'))
        require(sha(path_at(o,'preparation.json').read_bytes())==s['preparation_sha256'], 'Feed member receipt changed')
        record_raw = path_at(o,receipt['review_record']).read_bytes()
        blob = path_at(o,receipt['package']).read_bytes()
        require(sha(record_raw)==receipt['review_record_sha256'] and sha(blob)==receipt['package_sha256'], 'Feed member artifact changed')
        record = json.loads(record_raw)
        require(record.get('schema_version')==2 and record.get('approval_policy')=='strict-v1'
                and record.get('rights_approved') is False and record.get('release_approved') is False,
                'Candidate feed imports pending strict-v2 records only')
        sources.append({'task_id':b['task_id'],'binding_sha256':sha(__import__('repository').json_bytes(b)),
                        'source':b['source'],
                        'preparation_sha256':s['preparation_sha256'],'package_sha256':sha(blob),
                        'review_record_sha256':sha(record_raw),'validations':s['validations'],
                        'blob':blob,'record':record,'lanes':list(b['targets'])})
    capture(binding,state,out)
    for member in binding['candidate_feed']['members']:
        with store.bound(member['task_id'],member['expected_digest']) as (b,s,o):
            # Original source mapping and tester receipts are verified before copying.
            store.review(b,s,o)
            capture(b,s,o)
    return sources


def build(store,binding,state,out):
    from lifecycle import require, read_json, path_at, write_new, sha, replace_json, installation
    import repository as repo
    require(state['stage']=='prepared', 'Prepare the candidate package before constructing a feed')
    store.review(binding,state,out)
    if 'feed_sha256' in state:
        return verify(store,binding,state,out)
    sources = members(store,binding,state,out)
    stage = out/'feed-staging'
    path_at(out,'feed-staging',exists=False)
    require(not stage.exists(), 'Partial staging already exists; preserve evidence and enroll a new task')
    stage.mkdir(mode=0o700)
    for name in SCRIPTS:
        write_new(stage/'scripts'/name,path_at(store.root,'scripts/'+name).read_bytes())
    for relative in ('LICENSE','docs/REVIEW-RECORD-SCHEMA.json',*binding['baseline']):
        write_new(stage/relative,path_at(store.root,relative).read_bytes())
    # Preserve original installer source privately; it never enters the candidate site.
    for file in (store.root/'packages/repository.ai.kodi').rglob('*'):
        if file.is_file():
            relative=file.relative_to(store.root).as_posix()
            write_new(stage/relative,path_at(store.root,relative).read_bytes())
    config = read_json(stage/'config/repository.json')
    config = {**config,'addon_id':'repository.ai.kodi.candidate.'+binding['task_id'],
              'base_url':binding['candidate_feed']['base_url'],'provider':'AI Kodi LOCAL CANDIDATE',
              'candidate_context':{'task_id':binding['task_id'],
                  'production_config_sha256':binding['baseline']['config/repository.json'],
                  'production_ledger_sha256':binding['baseline']['releases/manifest.json']}}
    write_new(stage/'config/candidate-repository.json',repo.json_bytes(config))
    ledger={'schema':1,'repository_id':config['addon_id'],'packages':[]}
    write_new(stage/'releases/candidate-manifest.json',repo.json_bytes(ledger))
    for name,data in repo.installer(config,'candidate').items():
        write_new(stage/'packages'/config['addon_id']/name,data)
    identities = {}; owners = {}
    for source in sources:
        manifest,_=repo.inspect_zip(source['blob'])
        key=(manifest.get('id'),manifest.get('version'))
        owner=(source['source']['repository_id'],source['source']['repository'])
        require(key[0] not in owners or owners[key[0]]==owner,'Candidate update source identity changed')
        owners[key[0]]=owner
        require(key not in identities and key[0] != 'repository.ai.kodi' and not key[0].startswith('repository.ai.kodi.candidate.'),
                'Duplicate/reserved candidate package identity')
        source['identity']=key;identities[key]=source
    selected={}
    for key,source in identities.items():
        for lane in source['lanes']:
            previous=selected.get((key[0],lane))
            if previous is None or repo.version(key[1]) > repo.version(previous[1]):
                selected[(key[0],lane)]=key
            elif repo.version(key[1]) == repo.version(previous[1]):
                require(key==previous,'Numerically equivalent candidate versions')
    intake={'schema':1,'external_dependencies':{},'packages':[]}
    for key,source in identities.items():
        aid,version=key
        lanes=[lane for lane in source['lanes'] if selected[(aid,lane)]==key]
        # These are derived pending drafts, never rewritten live approval records.
        record=copy.deepcopy(source['record']);record['approval_lanes']=lanes
        filename=f'{aid}-{version}.zip';review_name=f'{aid}-{version}-candidate-review.json'
        write_new(stage/'incoming'/filename,source['blob'])
        write_new(stage/'incoming'/review_name,repo.json_bytes(record))
        intake['packages'].append({'zip':filename,'sha256':source['package_sha256'],'review_record':review_name,
                                  'review_record_sha256':sha(repo.json_bytes(record)),'lanes':lanes})
    write_new(stage/'config/candidate.json',repo.json_bytes(intake))
    python=installation(store.root)['python']
    run(stage,python,'repository.py',['build','--profile','candidate'])
    plan=read_json(stage/'dist/candidate/release-plan.json')
    ledger['packages']=[{k:package[k] for k in ('id','version','sha256')} for package in plan['packages']]
    replace_json(stage/'releases/candidate-manifest.json',ledger)
    # Existing qualifier rebuilds twice and audits every package, dependency and URL.
    run(stage,python,'qualify.py',['--profile','candidate'])
    audit=run(stage,python,'audit_candidate.py',['--profile','candidate'])
    plan=read_json(stage/'dist/candidate/release-plan.json')
    qualification=read_json(stage/'reports/candidate-qualification.json')
    public_sources=[{k:v for k,v in source.items() if k not in ('blob','record','identity')} for source in sources]
    receipt={'status':'PASS','scope':'complete isolated candidate feed mechanics; release approval absent',
             'task_id':binding['task_id'],'repository_id':config['addon_id'],'base_url':config['base_url'],
             'sources':public_sources,'inventory':inventory(stage),'site_manifest_sha256':plan['site_manifest_sha256'],
             'release_plan_sha256':sha(path_at(stage,'dist/candidate/release-plan.json').read_bytes()),
             'production_baseline':binding['baseline'],'release_blockers':plan['release_blockers'],
             'whole_site_reproducible':qualification['whole_site_reproducible'],
             'url_paths':qualification['url_validation']['url_paths'], 'independent_audit_status':audit['status'],
             'native_tested':False,'publication_authorized':False,
             'native_readiness':'Requires separately authorized target, reachable HTTPS feed and exact artifact binding'}
    write_new(out/'feed.json',repo.json_bytes(receipt))
    store.transition(binding,state,'prepared',feed_sha256=sha(repo.json_bytes(receipt)))
    return receipt


def verify(store,binding,state,out):
    from lifecycle import path_at, require, read_json, sha, installation
    raw=path_at(out,'feed.json').read_bytes()
    require(sha(raw)==state['feed_sha256'],'Frozen candidate feed receipt changed')
    receipt=json.loads(raw);stage=out/'feed-staging'
    require(receipt['repository_id']=='repository.ai.kodi.candidate.'+binding['task_id']
            and receipt['base_url']==binding['candidate_feed']['base_url']
            and receipt['production_baseline']==binding['baseline'],'Frozen candidate context mismatch')
    require(inventory(stage)==receipt['inventory'],'Candidate input/output inventory changed')
    # Pin copied verifiers to reviewed project code before any subprocess execution.
    for name in SCRIPTS:
        require(path_at(stage,'scripts/'+name).read_bytes()==path_at(store.root,'scripts/'+name).read_bytes(),
                'Untrusted candidate verifier')
    for name,digest in binding['baseline'].items():
        require(sha(path_at(stage,name).read_bytes())==digest,'Production baseline changed in candidate staging')
    current_sources=members(store,binding,state,out)
    public_sources=[{k:v for k,v in source.items() if k not in ('blob','record','identity')} for source in current_sources]
    require(public_sources==receipt['sources'],'Frozen candidate source/review/validation scope changed')
    result=run(stage,installation(store.root)['python'],'audit_candidate.py',['--profile','candidate'])
    require(result['status']=='PASS' and inventory(stage)==receipt['inventory'],'Independent frozen feed audit failed')
    return {k:v for k,v in receipt.items() if k!='inventory'}
