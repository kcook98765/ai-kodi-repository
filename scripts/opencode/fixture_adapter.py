"""Fixed role-scoped local adapters. Never publishes or executes add-on code."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
INSTALL=json.loads((ROOT/'.opencode/lifecycle-installation.json').read_text())
BASE=Path(INSTALL['toolkit']).parent
PYTHON=Path(INSTALL['python'])
sys.path.insert(0,str(ROOT/'scripts'))
import repository as repo
ROLES={'inspect':{'kodi-repo-manager','kodi-addon-tester','kodi-release-reviewer','kodi-addon-developer'},
       'validate':{'kodi-addon-tester'},'build':{'kodi-repo-manager'},
       'qualify':{'kodi-repo-manager','kodi-addon-tester'},
       'review':{'kodi-repo-manager','kodi-release-reviewer'},'github':{'kodi-repo-manager'}}
ALLOWLIST=['kcook98765/kodi-agent-toolkit','kcook98765/kodi-lab','kcook98765/plugin.video.tastemade','kcook98765/skin.aura']

def run(argv,cwd=ROOT,github=False):
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
    if github:raise ValueError('Legacy credentialed GitHub subprocess is unavailable; use the anonymous fixed GET reader')
    p=subprocess.run(argv,cwd=cwd,env=env,capture_output=True,text=True,timeout=180)
    return {'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=ROLES);parser.add_argument('--role',required=True)
    parser.add_argument('--repository',choices=ALLOWLIST);parser.add_argument('--resource',choices=['issues','pulls','releases'],default='issues');parser.add_argument('--page',type=int,choices=range(1,6),default=1)
    a=parser.parse_args();repo.require(a.role in ROLES[a.operation],'Role denied for operation')
    repo.require(str(ROOT)==INSTALL['project_root'],'Workspace binding mismatch')
    if a.operation=='inspect':
        result={'root':str(ROOT),'config':repo.load_config(),'production_intake':json.loads((ROOT/'config/production.json').read_text()),
                'readable_files':['README.md','AGENTS.md','docs/ARCHITECTURE.md','docs/RELEASE-WORKFLOW.md','docs/MONITORING.md','docs/SOURCES.md','scripts/repository.py','scripts/qualify.py','scripts/check_publication.py','scripts/audit_candidate.py','tests/test_repository.py'],
                'reports':[p.relative_to(ROOT).as_posix() for p in (ROOT/'reports').glob('*.json')],
                'has_git_remote':bool(run(['/usr/bin/git','remote'])['stdout'].strip()),
                'runtime_authorized':False,'publication_authorized':False}
    elif a.operation=='validate':
        validations={}
        for release in ['1.0.0','1.1.0']:
            source=ROOT/'fixtures'/release/'script.toolkit.sample'
            r=run([str(PYTHON),'-B','-m','kodi_agent_toolkit.cli','validate',str(source),'--branch','nexus','--cache',str(Path(INSTALL['cache']))],Path(INSTALL['toolkit']))
            repo.require(bool(r['stdout']),'Toolkit emitted no validation record')
            data=json.loads(r['stdout']);repo.write_output(ROOT/'reports'/('toolkit-'+release+'.json'),repo.json_bytes(data))
            repo.require(r['exit_code']==0 and data['passed'],'Toolkit fixture validation failed')
            validations[release]={'passed':data['passed'],'branch':data['branch'],
                'validation_file':str(ROOT/'reports'/('toolkit-'+release+'.json')),
                'validation_sha256':repo.sha((ROOT/'reports'/('toolkit-'+release+'.json')).read_bytes()),
                'checks':{k:{field:v[field] for field in ['status','passed','errors','warnings'] if field in v} for k,v in data['checks'].items()},
                'coverage_limits':data['coverage_limits']}
        tests=run([str(PYTHON),'-B','-m','unittest','discover','-s','tests','-v'])
        repo.write_output(ROOT/'reports/unit-tests.json',repo.json_bytes(tests))
        repo.require(tests['exit_code']==0,'Failure-control suite failed: '+tests['stderr'][-2500:])
        result={'status':'PASS','validations':validations,'unit_tests':tests,'runtime_tested':False}
        repo.write_output(ROOT/'reports/tester-execution.json',repo.json_bytes(result))
    elif a.operation=='build':
        result=repo.build('fixture')
        repo.write_output(ROOT/'reports/manager-build.json',repo.json_bytes(result))
    elif a.operation=='qualify':
        import qualify
        result=qualify.qualify()
        repo.write_output(ROOT/'reports/deterministic-qualification.json',repo.json_bytes(result))
    elif a.operation=='review':
        import qualify
        verified=repo.verify('fixture')
        plan=json.loads((ROOT/'dist/fixture/release-plan.json').read_text())
        summary={k:v for k,v in plan.items() if k!='site_files'}
        summary['site_file_count']=len(plan['site_files'])
        machine=json.loads((ROOT/'reports/deterministic-qualification.json').read_text())
        result={'status':'PASS','verified':verified,'urls':qualify.urls('fixture',network=False),
                'plan_file':str(ROOT/'dist/fixture/release-plan.json'),
                'plan_sha256':repo.sha((ROOT/'dist/fixture/release-plan.json').read_bytes()),'plan':summary,
                'deterministic_qualification':{k:machine[k] for k in ['status','whole_site_reproducible','historical_fixture_versions_retained']},
                'unit_test_execution':json.loads((ROOT/'reports/unit-tests.json').read_text())['stderr'][-100:],
                'toolkit_warnings':{release:json.loads((ROOT/'reports'/('toolkit-'+release+'.json')).read_text())['checks']['official_checker'].get('warnings',[]) for release in ['1.0.0','1.1.0']}}
        # Full machine records remain readable; avoid repeating the entire site manifest.
    else:
        repo.require(a.repository in ALLOWLIST,'Repository is not allowlisted')
        import lifecycle
        result=lifecycle.GitHub().listing(a.repository,a.resource,a.page)
    print(json.dumps(result))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'FAIL','error':type(error).__name__,'detail':str(error)}));sys.exit(1)
