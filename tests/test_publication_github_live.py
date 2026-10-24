"""Live interface serialization against mock HTTP only; sockets are denied."""
from __future__ import annotations
import base64
import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import publication_github_live as github
import publication_pilot_contract as contract
import publication_d3_contract as d3
import publication_proposal as core

NOW=datetime(2026,10,24,4,0,tzinfo=timezone.utc)
MAIN='1'*40; PAGES='2'*40; HEADS={'main_sha':MAIN,'pages_sha':PAGES}
TAG='script.ai.kodi.d3.fixture-1.0.0'; PREFIX='/repos/'+github.QUAL_REPOSITORY
POLICY=github.expected_policy({'app_id':100003,'ci_app_id':100006,'pages_environment_id':100008})
POLICY_SHA=core.sha(core.canonical(POLICY))


def enrolled():
    old=d3.mock_enrollment(now=NOW)
    value={k:copy.deepcopy(v) for k,v in old.items() if k in contract.ENROLL_FIELDS}
    value.update(profile=github.PROFILE,repository_id=100001,owner_id=100002,app_id=100003,
                 app_installation_id=100004,bot_user_id=100005,ci_app_id=100006,
                 pages_workflow_id=100009,validation_workflow_id=100010,
                 validation_workflow_path='.github/workflows/qualification-validation.yml',
                 validation_workflow_commit='c'*40,validation_workflow_sha256=core.sha(b'# trusted pinned validation workflow\n'),
                 validation_job_name='qualification-validation',policy_sha256=POLICY_SHA)
    if 'pages_environment_id' in contract.ENROLL_FIELDS: value['pages_environment_id']=100008
    value['fixture_source']['commits']={'1.0.0':'a'*40,'1.1.0':'b'*40}
    value['identity_evidence']={'kind':'local-test-fixture','observed_at':core.utc(NOW),
      'repository_sha256':'1'*64,'installation_sha256':'2'*64,
      'source_sha256':core.sha(core.canonical(value['fixture_source'])),'policy_sha256':POLICY_SHA}
    return contract.validate_enrollment(value)


class Signer:
    def __init__(self): self.inputs=[]
    def sign_rs256(self,raw): self.inputs.append(raw); return b'MOCK-SIGNATURE-NOT-A-REAL-KEY'


def exchange(method,path,value=None,*,status=200,body=None,binary=False,headers=None,absolute=False,upload=False):
    url=path if absolute else (github.UPLOADS if upload else github.API)+PREFIX+path
    response=github.HTTPResponse(status,value if binary else core.canonical(value),headers or {})
    return github.HTTPExchange(method,url,response,body)


def repo(): return {'id':100001,'full_name':github.QUAL_REPOSITORY,'private':False,
                     'owner':{'id':100002,'login':'kcook98765-kodi-qualification','type':'Organization'},**POLICY['repository']}
def ref(branch,sha): return {'ref':'refs/'+branch,'object':{'type':'commit','sha':sha,'url':'metadata'}}
def preflight(): return [exchange('GET','',repo()),exchange('GET','/git/ref/heads/main',ref('heads/main',MAIN)),
                        exchange('GET','/git/ref/heads/gh-pages',ref('heads/gh-pages',PAGES))]
def policy():
    queue=[exchange('GET','',repo()),exchange('GET','/rulesets?includes_parents=true&per_page=100&page=1',[{'id':r['id']} for r in POLICY['rulesets']])]
    queue += [exchange('GET','/rulesets/'+str(r['id']),r) for r in POLICY['rulesets']]
    queue += [exchange('GET','/environments/github-pages',POLICY['environments']['github-pages']),
              exchange('GET','/environments/github-pages/deployment-branch-policies?per_page=100&page=1',{'total_count':1,'branch_policies':POLICY['pages_branch_policies']}),
              exchange('GET','/actions/permissions/workflow',POLICY['default_actions']),
              exchange('GET','/immutable-releases',POLICY['immutable_releases'])]
    return queue



def auth(effect,args,*,kind='publication',expiry=None,mock_only=True):
    return {'schema':1,'profile':github.PROFILE,'kind':kind,'proposal_sha256':'e'*64,
      'execution_sha256':'f'*64 if kind=='publication' else None,'repository_id':100001,
      'expires_at':expiry or core.utc(NOW+timedelta(minutes=30)), 'heads':HEADS,'policy_sha256':POLICY_SHA,
      'mock_only':mock_only,'effects':{effect:[core.sha(core.canonical(github.effect_arguments(effect,args)))]}}


class LiveTransportTests(unittest.TestCase):
    def setUp(self):
        self.sockets=patch('socket.socket',side_effect=AssertionError('REAL NETWORK DENIED'))
        self.sockets.start(); self.addCleanup(self.sockets.stop)
        self.addCleanup(patch.stopall)

    def client(self,queue,enrollment=None,backend=None):
        e=enrollment or enrolled(); sender=backend or github.ScriptedHTTPS(queue); signer=Signer()
        provider=github.AppTokenProvider(e,signer,sender,clock=lambda:NOW)
        for caps in ({'contents':'read'},{'contents':'write'},{'pull_requests':'read'},{'pull_requests':'write'},
                     {'administration':'read'},{'actions':'read'},{'pages':'read'}):
            caps=dict(caps,metadata='read')
            provider._tokens[tuple(sorted(caps.items()))]=github._Token('MOCK_TEST_TOKEN',core.utc(NOW+timedelta(minutes=30)),caps)
        return github.PilotGitHub(e,provider,sender,clock=lambda:NOW),sender,provider

    def scoped(self,effect,args,**changes):
        value=auth(effect,args,**changes)
        return github.BoundScope(Path('/sealed-test-only'),value['kind'],claimed_review_id=17 if value['kind']=='publication' else None),patch.object(contract,'transport_authority',return_value=value)

    def test_selected_destination_ids_and_canonical_origin_only(self):
        e=enrolled()
        for updates in ({'repository_id':True},{'repository_id':github.PRODUCTION_ID},
                        {'base_url':'https://attacker.example/'},{'base_url':github.QUAL_ORIGIN.replace('.io/','.io:443/')},
                        {'repository':'kcook98765/ai-kodi-repository'},{'owner_id':900002}):
            with self.subTest(updates=updates),self.assertRaises(ValueError):
                self.client([],dict(e,**updates))

    def test_old_mock_credential_and_sender_cannot_be_live_inputs(self):
        import publication_github as old
        with self.assertRaises(ValueError): github.AppTokenProvider(enrolled(),Signer(),old.ScriptedMockSender([]))
        with self.assertRaises(ValueError): github.PilotGitHub(enrolled(),lambda:None,github.ScriptedHTTPS([]))
        self.assertNotIn('MOCK_TEST_TOKEN',repr(github._Token('MOCK_TEST_TOKEN',core.utc(NOW),{'metadata':'read'})))

    def test_permission_ceiling_excludes_write_actions_admin_and_checks(self):
        for caps in ({'actions':'write'},{'administration':'write'},{'pages':'write'},{'checks':'read'},
                     {'statuses':'read'},{'workflows':'write'},{'issues':'write'}):
            with self.subTest(caps=caps),self.assertRaises(ValueError): github.permissions(caps)

    def test_preparation_grant_cannot_create_tag_and_zero_requests(self):
        client,sender,_=self.client([])
        args={'heads':HEADS,'tag':TAG,'target':MAIN}
        value=auth('create_blob',{'heads':HEADS,'data':b'x','expected_sha':None},kind='preparation')
        with patch.object(contract,'transport_authority',return_value=value),self.assertRaisesRegex(ValueError,'outside exact'):
            client.create_tag(github.BoundScope(Path('/sealed'),'preparation'),**args)
        self.assertEqual(sender.requests,[])

    def test_create_tag_is_single_create_only_effect_exact_head_policy_and_receipt(self):
        args={'heads':HEADS,'tag':TAG,'target':MAIN}
        queue=preflight()+[exchange('GET','/git/ref/tags/'+TAG,{},status=404)]+policy()+preflight()+[
          exchange('POST','/git/refs',ref('tags/'+TAG,MAIN),status=201,body={'ref':'refs/tags/'+TAG,'sha':MAIN})]
        client,sender,_=self.client(queue); scope,patched=self.scoped('create_tag',args)
        with patched,patch.object(contract,'load_material',return_value={}),patch('publication_pr_owner.OwnerPRVerifier.verify',return_value={'real_owner_authenticated':False,'review_id':17}): receipt=client.create_tag(scope,**args)
        self.assertEqual(receipt['transport_origin'],'scripted-mock-https')
        self.assertTrue(receipt['mock_only']);self.assertFalse(receipt['production_authorized'])
        self.assertEqual(sender.remaining,0)
        self.assertEqual(sum(r['method']=='POST' for r in sender.requests),1)
        self.assertNotIn('MOCK_TEST_TOKEN',repr(sender.requests))

    def test_changed_scope_expiry_and_policy_fail_before_effect(self):
        args={'heads':HEADS,'tag':TAG,'target':MAIN}
        client,sender,_=self.client([])
        scope,patched=self.scoped('create_tag',args,expiry=core.utc(NOW))
        with patched,self.assertRaises(ValueError):client.create_tag(scope,**args)
        self.assertEqual(sender.requests,[])
        scope,patched=self.scoped('create_tag',args)
        value=auth('create_tag',args)
        with patch.object(contract,'transport_authority',side_effect=[value,dict(value,proposal_sha256='0'*64)]):
            scope.verify('create_tag',args,enrolled(),NOW)
            with self.assertRaisesRegex(ValueError,'changed'):scope.verify('create_tag',args,enrolled(),NOW)
        queue=preflight()+[exchange('GET','/git/ref/tags/'+TAG,{},status=404)]+policy()
        queue[-1]=exchange('GET','/immutable-releases',{'enabled':False,'enforced_by_owner':False})
        client,sender,_=self.client(queue);scope,patched=self.scoped('create_tag',args)
        with patched,self.assertRaises(ValueError):client.create_tag(scope,**args)
        self.assertFalse(any(r['method'] in ('POST','PATCH','PUT') for r in sender.requests))

    def test_mock_authority_rejected_by_TLS_before_any_key_or_network(self):
        client,_,provider=self.client([],backend=github.HTTPSBackend())
        args={'heads':HEADS,'tag':TAG,'target':MAIN};scope,patched=self.scoped('create_tag',args)
        with patched,self.assertRaisesRegex(ValueError,'Local test authority'):client.create_tag(scope,**args)
        self.assertEqual(provider.key_provider.inputs,[])

    def test_scoped_mutation_expiring_during_token_mint_stops_before_effect(self):
        args={'heads':HEADS,'tag':TAG,'target':MAIN};scope,patched=self.scoped('create_tag',args)
        queue=preflight()+[exchange('GET','/git/ref/tags/'+TAG,{},status=404)]
        client,sender,provider=self.client(queue); clock=[NOW];client.clock=lambda:clock[0]
        real=provider.token
        def slow(caps):
            token=real(caps)
            if caps=={'contents':'write'}:clock[0]=NOW+timedelta(hours=1)
            return token
        with patched,patch.object(provider,'token',side_effect=slow),self.assertRaises(ValueError):client.create_tag(scope,**args)
        self.assertFalse(any(r['method']=='POST' for r in sender.requests))

    def test_create_blob_default_hash_and_publish_asset_ID_projection(self):
        self.assertEqual(github.effect_arguments('create_blob',{'heads':HEADS,'data':b'x','expected_sha':None})['expected_sha'],core.git_object('blob',b'x'))
        args={'release_id':5,'assets':{'a':{'id':7,'size':1,'sha256':'f'*64}}}
        projection=github.effect_arguments('publish_release',args)
        self.assertNotIn('release_id',projection);self.assertNotIn('id',projection['assets']['a'])

    def test_404_absence_only_and_response_errors_redacted(self):
        for code in (404,403,500):
            client,sender,_=self.client([exchange('GET','/git/commits/'+MAIN,{'secret':'SENTINEL'},status=code)])
            if code==404:self.assertIsNone(client.read_commit(MAIN,absent=True))
            else:
                with self.assertRaises(ValueError) as error:client.read_commit(MAIN,absent=True)
                self.assertNotIn('SENTINEL',str(error.exception))
            self.assertEqual(sender.remaining,0)

    def test_arbitrary_endpoint_method_and_force_have_no_escape(self):
        client,sender,_=self.client([])
        access=github._Access({'contents':'write'})
        for method,path,body in [('DELETE','/releases/5',None),('PATCH','/git/refs/heads/main',{'sha':MAIN,'force':True}),
                                 ('POST','/environments/github-pages',{}),('PUT','/pulls/1',{})]:
            with self.subTest(method=method,path=path),self.assertRaises(ValueError):client._request(method,path,access,body=body)
        self.assertEqual(sender.requests,[])

    def test_asset_redirect_strips_authorization_and_rejects_host_alias(self):
        data=b'zip';name=TAG+'.zip';a={'id':7,'name':name,'state':'uploaded','size':3,'digest':'sha256:'+core.sha(data)}
        location='https://release-assets.githubusercontent.com/object?signed=SECRET'
        queue=[exchange('GET','/releases/assets/7',a),exchange('GET','/releases/assets/7',b'',binary=True,status=302,headers={'Location':location}),
               exchange('GET',location,data,binary=True,absolute=True)]
        client,sender,_=self.client(queue);receipt=client.download_asset(5,7,name,core.sha(data),3)
        self.assertTrue(receipt['mock_only']);self.assertFalse(sender.requests[-1]['authenticated'])
        self.assertNotIn('SECRET',repr(sender.requests))
        for url in ('https://attacker.invalid/a','https://api.github.com:443/a','http://api.github.com/a','https://API.GITHUB.COM/a'):
            with self.subTest(url=url),self.assertRaises(ValueError):github._url(url,allow_storage=True)

    def test_public_get_head_no_auth_and_actual_sha_mime(self):
        data=b'<addons/>';path='nexus/addons.xml';url=github.QUAL_ORIGIN+path
        queue=[exchange('HEAD',url,b'',binary=True,absolute=True,headers={'Content-Type':'application/xml'}),
               exchange('GET',url,data,binary=True,absolute=True,headers={'Content-Type':'application/xml'})]
        client,sender,_=self.client(queue);value=client.read_public(path,core.sha(data),mime='application/xml')
        self.assertTrue(value['mock_only']);self.assertTrue(all(not r['authenticated'] for r in sender.requests))

    def token_queue(self, *, overrides=None):
        e=enrolled();caps={'contents':'write','metadata':'read'}
        owner={'id':e['owner_id'],'type':'Organization'}
        value={'token':'TEST_PRIVATE_TOKEN_NEVER_VALID','expires_at':core.utc(NOW+timedelta(hours=1)),
          'permissions':caps,'repository_selection':'selected','repositories':[{'id':e['repository_id'],'full_name':e['repository']}]}
        value.update(overrides or {})
        return [exchange('GET',github.API+'/app',{'id':e['app_id'],'owner':owner,'permissions':github.PERMISSIONS},absolute=True),
          exchange('GET',github.API+'/app/installations/'+str(e['app_installation_id']),{'id':e['app_installation_id'],
            'app_id':e['app_id'],'account':owner,'repository_selection':'selected','suspended_at':None,'permissions':github.PERMISSIONS},absolute=True),
          exchange('POST',github.API+'/app/installations/'+str(e['app_installation_id'])+'/access_tokens',value,status=201,absolute=True,
            body={'repository_ids':[e['repository_id']],'permissions':caps})]

    def test_explicit_App_JWT_claims_and_exact_single_repository_token_serialization(self):
        backend=github.ScriptedHTTPS(self.token_queue());signer=Signer()
        provider=github.AppTokenProvider(enrolled(),signer,backend,clock=lambda:NOW)
        token=provider.token({'contents':'write'})
        self.assertEqual(token.permissions,{'contents':'write','metadata':'read'})
        header,claims=signer.inputs[0].decode().split('.')
        decoded=lambda value:core.strict_load(base64.urlsafe_b64decode(value+'='*(-len(value)%4)))
        self.assertEqual(decoded(header),{'alg':'RS256','typ':'JWT'})
        payload=decoded(claims);self.assertEqual(payload['iss'],'100003')
        self.assertEqual(payload['iat'],int(NOW.timestamp())-60)
        self.assertLessEqual(payload['exp'],int(NOW.timestamp())+600)
        self.assertIs(provider.token({'contents':'write'}),token)
        self.assertEqual(backend.remaining,0)
        self.assertNotIn(token.value,repr(backend.requests));self.assertNotIn(token.value,repr(token))
        self.assertEqual(sum(r['method']=='POST' for r in backend.requests),1)

    def test_malformed_expanded_or_overlong_installation_token_never_accepted(self):
        changes=[{'permissions':{'contents':'write','actions':'write','metadata':'read'}},
                 {'permissions':{'contents':'read','metadata':'read'}},{'repository_selection':'all'},
                 {'repositories':[{'id':github.PRODUCTION_ID,'full_name':'kcook98765/ai-kodi-repository'}]},
                 {'expires_at':core.utc(NOW)},{'expires_at':core.utc(NOW+timedelta(hours=2))},
                 {'token':'PRIVATE SENTINEL\nINJECT'},{'expires_at':'PRIVATE_SENTINEL'}]
        for changeset in changes:
            backend=github.ScriptedHTTPS(self.token_queue(overrides=changeset))
            provider=github.AppTokenProvider(enrolled(),Signer(),backend,clock=lambda:NOW)
            with self.subTest(fields=list(changeset)),self.assertRaises(ValueError) as error:provider.token({'contents':'write'})
            self.assertNotIn('PRIVATE',str(error.exception));self.assertEqual(provider._tokens,{})

    def test_HTTPS_uses_default_verified_TLS_and_serializes_once_without_redirect_or_retry(self):
        backend=github.HTTPSBackend(timeout=3);conn=MagicMock();response=MagicMock()
        response.status=302;response.headers.get_all.return_value=[]
        response.read.return_value=b'';response.getheaders.return_value=[('Location','https://attacker.invalid/SECRET')]
        conn.getresponse.return_value=response
        with patch.object(github.http.client,'HTTPSConnection',return_value=conn) as factory:
            result=backend.send('POST',github.API+PREFIX+'/git/refs',{'Authorization':'Bearer TEST-ONLY'},b'{}',max_size=100)
        self.assertEqual(result.status,302);factory.assert_called_once()
        context=factory.call_args.kwargs['context']
        self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,github.ssl.CERT_REQUIRED)
        conn.request.assert_called_once_with('POST',PREFIX+'/git/refs',body=b'{}',headers={'Authorization':'Bearer TEST-ONLY'})
        self.assertTrue(conn.close.called)
        conn=MagicMock();conn.request.side_effect=TimeoutError('PRIVATE SENTINEL')
        with patch.object(github.http.client,'HTTPSConnection',return_value=conn),self.assertRaises(ValueError) as error:
            backend.send('POST',github.API+PREFIX+'/git/refs',{},b'{}',max_size=100)
        self.assertNotIn('PRIVATE',str(error.exception));self.assertEqual(conn.request.call_count,1)

    def test_HTTPS_size_deadline_and_authorization_forwarding_fail_closed(self):
        backend=github.HTTPSBackend(timeout=3)
        with self.assertRaises(ValueError):backend.send('GET',github.QUAL_ORIGIN,{'Authorization':'SECRET'},b'',max_size=100)
        for size,raw,clock in [('101',b'x',None),('4',b'x',None),(None,b'xxxx',None),(None,b'x',[0,4])]:
            conn=MagicMock();response=MagicMock();response.status=200
            response.headers.get_all.return_value=[] if size is None else [size]
            response.read.return_value=raw;response.getheaders.return_value=[];conn.getresponse.return_value=response
            with patch.object(github.http.client,'HTTPSConnection',return_value=conn):
                timer=patch.object(github.time,'monotonic',side_effect=clock) if clock else patch.object(github.time,'monotonic',return_value=0)
                with timer,self.assertRaises(ValueError):backend.send('GET',github.API+PREFIX,{},b'',max_size=3 if size is None else 100)

    def test_semantic_policy_rejects_opaque_hash_of_unsafe_controls(self):
        self.assertEqual(github.validate_policy(enrolled(),copy.deepcopy(POLICY))['rulesets'][0]['enforcement'],'active')
        mutations=[lambda p:p['rulesets'].pop(),lambda p:p['rulesets'][1].update(bypass_actors=[{'actor_id':100003,'actor_type':'Integration','bypass_mode':'always'}]),
          lambda p:p['rulesets'][2]['rules'][0]['parameters']['required_status_checks'][0].update(integration_id=1),
          lambda p:p['rulesets'][1]['rules'][0]['parameters'].update(require_last_push_approval=False),
          lambda p:p['rulesets'][7].update(rules=[{'type':'update'}]),
          lambda p:p['repository'].update(allow_auto_merge=True),lambda p:p['repository'].update(delete_branch_on_merge=True),
          lambda p:p['default_actions'].update(can_approve_pull_request_reviews=True),lambda p:p['default_actions'].update(default_workflow_permissions='write'),
          lambda p:p['environments']['github-pages'].update(can_admins_bypass=True),lambda p:p['environments']['github-pages'].update(protection_rules=[{'type':'required_reviewers'}]),
          lambda p:p['pages_branch_policies'][0].update(name='*'),lambda p:p['immutable_releases'].update(enabled=False),
          lambda p:p['rulesets'][0]['bypass_actors'][0].update(actor_id=True),lambda p:p['repository'].update(allow_merge_commit=1)]
        for mutate in mutations:
            value=copy.deepcopy(POLICY);mutate(value)
            with self.subTest(mutation=mutations.index(mutate)),self.assertRaises(ValueError):github.validate_policy(enrolled(),value)

    def test_fresh_owner_proof_is_rechecked_after_slow_preflights(self):
        args={'heads':HEADS,'tag':TAG,'target':MAIN}
        queue=preflight()+[exchange('GET','/git/ref/tags/'+TAG,{},status=404)]+policy()+preflight()
        client,sender,_=self.client(queue);scope,patched=self.scoped('create_tag',args)
        with patched,patch.object(contract,'load_material',return_value={}),patch('publication_pr_owner.OwnerPRVerifier.verify',side_effect=ValueError('Owner revoked')),self.assertRaisesRegex(ValueError,'revoked'):
            client.create_tag(scope,**args)
        self.assertFalse(any(r['method']=='POST' for r in sender.requests));self.assertEqual(sender.remaining,0)

    def merge_queue(self, *, wrong_parent=False):
        target='a'*40;tree='b'*40;merged='c'*40;branch='publication-ledger/'+'e'*64
        pr={'number':1,'state':'open','draft':False,'merged':False,'mergeable':True,'mergeable_state':'clean',
            'head':{'ref':branch,'sha':target,'repo':{'id':100001}},'base':{'ref':'main','sha':MAIN,'repo':{'id':100001}}}
        head={'sha':target,'tree':{'sha':tree},'parents':[{'sha':MAIN}]}
        actual={'sha':merged,'tree':{'sha':tree},'parents':[{'sha':'f'*40 if wrong_parent else MAIN},{'sha':target}]}
        queue=preflight()+[exchange('GET','/pulls/1',pr),exchange('GET','/git/commits/'+target,head)]+policy()+preflight()+[
            exchange('PUT','/pulls/1/merge',{'merged':True,'sha':merged},body={'sha':target,'merge_method':'merge'}),
            exchange('GET','/git/commits/'+merged,actual)]
        if not wrong_parent:queue.append(exchange('GET','/git/ref/heads/main',ref('heads/main',merged)))
        return queue,{'heads':HEADS,'number':1,'target':target,'expected_tree':tree}

    def test_normal_merge_exact_head_and_postmerge_bothparents_fulltree(self):
        queue,args=self.merge_queue();client,sender,_=self.client(queue);scope,patched=self.scoped('merge_ledger_pr',args)
        with patched,patch.object(contract,'load_material',return_value={}),patch('publication_pr_owner.OwnerPRVerifier.verify',return_value={'real_owner_authenticated':False,'review_id':17}):
            receipt=client.merge_ledger_pr(scope,**args)
        self.assertTrue(receipt['merged']);self.assertTrue(receipt['mock_only']);self.assertFalse(receipt['production_authorized'])
        self.assertEqual(receipt['parents'],[MAIN,args['target']]);self.assertEqual(sender.remaining,0)
        self.assertEqual(sum(r['method']=='PUT' for r in sender.requests),1)

    def test_accepted_merge_wrongbase_is_incomplete_incident_never_blind_retry(self):
        queue,args=self.merge_queue(wrong_parent=True);client,sender,_=self.client(queue);scope,patched=self.scoped('merge_ledger_pr',args)
        with patched,patch.object(contract,'load_material',return_value={}),patch('publication_pr_owner.OwnerPRVerifier.verify',return_value={'real_owner_authenticated':False,'review_id':17}),self.assertRaisesRegex(ValueError,'incomplete incident'):
            client.merge_ledger_pr(scope,**args)
        self.assertEqual(sum(r['method']=='PUT' for r in sender.requests),1);self.assertEqual(sender.remaining,0)

    def test_pagination_missing_history_and_foreign_next_link_are_rejected(self):
        for response in [exchange('GET','/pulls/1/reviews?per_page=100&page=1',[],headers={'Link':'<https://attacker.example/>; rel="next"'}),
                         exchange('GET','/actions/workflows/100010/runs?head_sha='+MAIN+'&status=completed&per_page=100&page=1',{'total_count':1,'workflow_runs':[]})]:
            client,sender,_=self.client([response])
            with self.assertRaises(ValueError):
                if '/reviews' in response.url:client.read_ledger_reviews(1)
                else:client._collection('/actions/workflows/100010/runs?head_sha='+MAIN+'&status=completed','workflow_runs')
            self.assertEqual(sender.remaining,0)

    def validation_queue(self, *, wrong_head=False, failed=False, changed_source=False):
        e=enrolled();identity=e['validation_workflow_id'];raw=b'# trusted pinned validation workflow\n'
        run={'id':77,'workflow_id':identity,'head_sha':MAIN,'path':e['validation_workflow_path'],'status':'completed',
             'conclusion':'success','repository':{'id':e['repository_id'],'full_name':e['repository']}}
        job={'id':78,'run_id':77,'head_sha':'f'*40 if wrong_head else MAIN,'name':e['validation_job_name'],
             'status':'completed','conclusion':'failure' if failed else 'success'}
        return [exchange('GET','/actions/workflows/'+str(identity),{'id':identity,'path':e['validation_workflow_path'],'state':'active'}),
          exchange('GET','/contents/'+e['validation_workflow_path']+'?ref='+e['validation_workflow_commit'],
            {'type':'file','path':e['validation_workflow_path'],'encoding':'base64','sha':core.git_object('blob',raw),
             'content':base64.b64encode(b'changed' if changed_source else raw).decode()}),
          exchange('GET','/actions/workflows/'+str(identity)+'/runs?head_sha='+MAIN+'&status=completed&per_page=100&page=1',{'total_count':1,'workflow_runs':[run]}),
          exchange('GET','/actions/runs/77/jobs?per_page=100&page=1',{'total_count':1,'jobs':[job]})]

    def test_Actions_read_validation_binds_trusted_workflow_actualbytes_run_and_job_head(self):
        client,sender,_=self.client(self.validation_queue());receipt=client.observe_validation(MAIN)
        self.assertEqual(receipt['commit'],MAIN);self.assertEqual(receipt['conclusion'],'success')
        self.assertTrue(receipt['mock_only']);self.assertFalse(receipt['production_authorized'])
        self.assertEqual(sender.remaining,0);self.assertTrue(all(r['method']=='GET' for r in sender.requests))
        for changes in ({'wrong_head':True},{'failed':True},{'changed_source':True}):
            client,sender,_=self.client(self.validation_queue(**changes))
            with self.subTest(changes=changes),self.assertRaises(ValueError):client.observe_validation(MAIN)

    def test_Pages_build_without_exact_successful_native_GitHub_deployment_run_is_unverified(self):
        # This observation concerns publication transport, not native Kodi tests.
        identity=enrolled()['pages_workflow_id']
        queue=[exchange('GET','/actions/workflows/'+str(identity),{'id':identity,'path':'dynamic/pages/pages-build-deployment','state':'active'}),
          exchange('GET','/actions/workflows/'+str(identity)+'/runs?head_sha='+PAGES+'&per_page=100&page=1',{'total_count':0,'workflow_runs':[]})]
        client,sender,_=self.client(queue)
        with self.assertRaisesRegex(ValueError,'missing'):client.observe_pages_deployment(PAGES)
        self.assertEqual(sender.remaining,0)

    def test_safe_API_branch_policy_marker_is_allowed_without_human_review(self):
        value=copy.deepcopy(POLICY)
        value['environments']['github-pages']['protection_rules']=[{'id':123,'type':'branch_policy','node_id':'metadata'}]
        self.assertIs(github.validate_policy(enrolled(),value),value)
        value['environments']['github-pages']['protection_rules'][0]['id']=True
        with self.assertRaises(ValueError):github.validate_policy(enrolled(),value)


    def pages_jobs_queue(self, *, deploy='success', build='skipped'):
        e=enrolled();identity=e['pages_workflow_id']
        run={'id':77,'workflow_id':identity,'head_sha':PAGES,'head_branch':'gh-pages','status':'completed','conclusion':'success',
             'repository':{'id':e['repository_id'],'full_name':e['repository']}}
        jobs=[{'id':78,'run_id':77,'head_sha':PAGES,'name':'build','status':'completed','conclusion':build},
              {'id':79,'run_id':77,'head_sha':PAGES,'name':'deploy','status':'completed','conclusion':deploy}]
        return [exchange('GET','/actions/workflows/'+str(identity),{'id':identity,'path':'dynamic/pages/pages-build-deployment','state':'active'}),
          exchange('GET','/actions/workflows/'+str(identity)+'/runs?head_sha='+PAGES+'&per_page=100&page=1',{'total_count':1,'workflow_runs':[run]}),
          exchange('GET','/actions/runs/77/jobs?per_page=100&page=1',{'total_count':2,'jobs':jobs}),
          exchange('GET','/pages',{'html_url':github.QUAL_ORIGIN,'https_enforced':True,'build_type':'legacy','source':{'branch':'gh-pages','path':'/'}}),
          exchange('GET','/pages/builds/latest',{'commit':PAGES,'status':'built'}),
          exchange('GET','/environments/github-pages',{'id':e['pages_environment_id'],'name':'github-pages'})]

    def test_Pages_nojekyll_skipped_build_successful_deploy_is_verified(self):
        client,sender,_=self.client(self.pages_jobs_queue())
        receipt=client.observe_pages_deployment(PAGES)
        self.assertEqual(receipt['conclusion'],'success');self.assertEqual(receipt['commit'],PAGES)
        self.assertTrue(receipt['mock_only']);self.assertFalse(receipt['production_authorized'])
        self.assertEqual(sender.remaining,0)

    def test_Pages_skipped_deploy_successful_build_is_unverified(self):
        client,sender,_=self.client(self.pages_jobs_queue(deploy='skipped',build='success')[:3])
        with self.assertRaisesRegex(ValueError,'successful completed Pages deploy'):
            client.observe_pages_deployment(PAGES)
        self.assertEqual(sender.remaining,0)

    def test_final_new_review_after_durable_claim_rejects_every_effect(self):
        args={'heads':HEADS,'tag':TAG,'target':MAIN}
        queue=preflight()+[exchange('GET','/git/ref/tags/'+TAG,{},status=404)]+policy()+preflight()
        client,sender,_=self.client(queue);scope,patched=self.scoped('create_tag',args)
        self.assertEqual(scope.claimed_review_id,17)
        with patched,patch.object(contract,'load_material',return_value={}),patch('publication_pr_owner.OwnerPRVerifier.verify',return_value={'real_owner_authenticated':False,'review_id':18}),self.assertRaisesRegex(ValueError,'review changed after durable consumption'):
            client.create_tag(scope,**args)
        self.assertEqual(sender.remaining,0)
        self.assertFalse(any(r['method'] in ('POST','PATCH','PUT') for r in sender.requests))

    def test_publication_review_context_must_be_claimed_typed_integer(self):
        args={'heads':HEADS,'tag':TAG,'target':MAIN}
        for identity in (None,True,17.0,'17',0,-1):
            client,sender,_=self.client([]);scope,patched=self.scoped('create_tag',args)
            scope.claimed_review_id=identity
            with self.subTest(identity=identity),patched,self.assertRaisesRegex(ValueError,'durably claimed'):
                client.create_tag(scope,**args)
            self.assertEqual(sender.requests,[])

    def test_serialized_Pages_missing_queued_and_inprogress_reads_then_success(self):
        for state in ('missing','queued','in_progress'):
            pending=self.pages_jobs_queue()[:2]
            value=core.strict_load(pending[1].response.body)
            if state=='missing':value={'total_count':0,'workflow_runs':[]}
            else:value['workflow_runs'][0].update(status=state,conclusion=None)
            pending[1]=github.HTTPExchange('GET',pending[1].url,github.HTTPResponse.json(200,value))
            client,sender,_=self.client(pending+self.pages_jobs_queue())
            with self.subTest(state=state),self.assertRaises(github.PendingPagesReadiness):client.observe_pages_deployment(PAGES)
            self.assertEqual(sender.remaining,6)
            receipt=client.observe_pages_deployment(PAGES)
            self.assertEqual(receipt['conclusion'],'success');self.assertEqual(sender.remaining,0)
            self.assertTrue(all(r['method']=='GET' for r in sender.requests))

    def test_Pages_completed_failures_and_unsafe_pending_identity_are_hard_failures(self):
        for scenario in ('run_failure','deploy_failure','foreign_pending'):
            queue=self.pages_jobs_queue(deploy='failure' if scenario=='deploy_failure' else 'success')
            if scenario!='deploy_failure':
                value=core.strict_load(queue[1].response.body)
                if scenario=='run_failure':value['workflow_runs'][0].update(conclusion='failure')
                else:
                    value['workflow_runs'][0].update(status='queued',conclusion=None)
                    value['workflow_runs'][0]['repository']['id']=github.PRODUCTION_ID
                queue[1]=github.HTTPExchange('GET',queue[1].url,github.HTTPResponse.json(200,value))
            queue=queue[:3 if scenario=='deploy_failure' else 2]
            client,sender,_=self.client(queue)
            with self.subTest(scenario=scenario),self.assertRaises(ValueError) as error:client.observe_pages_deployment(PAGES)
            self.assertNotIsInstance(error.exception,github.PendingPagesReadiness)
            self.assertEqual(sender.remaining,0)

    def test_Pages_build_pending_or_stale_then_success_and_failed_current_hard(self):
        values=[{'commit':PAGES,'status':'queued'},{'commit':PAGES,'status':'building'},
                {'commit':MAIN,'status':'built'},{'commit':PAGES,'status':'built'},{'commit':PAGES,'status':'errored'}]
        client,sender,_=self.client([exchange('GET','/pages/builds/latest',v) for v in values])
        for _ in range(3):
            with self.assertRaises(github.PendingPagesReadiness):client.read_pages_build(PAGES)
        self.assertEqual(client.read_pages_build(PAGES)['status'],'built')
        with self.assertRaises(ValueError) as error:client.read_pages_build(PAGES)
        self.assertNotIsInstance(error.exception,github.PendingPagesReadiness)
        self.assertEqual(sender.remaining,0)

    def test_serialized_public_404_expected_MIME_stale_digest_then_success(self):
        expected=b'<addons new="true"/>';old=b'<addons/>';url=github.QUAL_ORIGIN+'nexus/addons.xml'
        response=lambda method,data:exchange(method,url,data,binary=True,absolute=True,headers={'Content-Type':'application/xml'})
        queue=[exchange('HEAD',url,b'',binary=True,absolute=True,status=404),response('HEAD',b''),response('GET',old),
               response('HEAD',b''),response('GET',expected)]
        client,sender,_=self.client(queue)
        for remaining in (4,2):
            with self.assertRaises(github.PendingPublicBytes):client.read_public('nexus/addons.xml',core.sha(expected),mime='application/xml',previous_sha256=core.sha(old))
            self.assertEqual(sender.remaining,remaining)
        result=client.read_public('nexus/addons.xml',core.sha(expected),mime='application/xml',previous_sha256=core.sha(old))
        self.assertEqual(result['sha256'],core.sha(expected));self.assertEqual(sender.remaining,0)
        self.assertTrue(all(r['method'] in ('HEAD','GET') and not r['authenticated'] for r in sender.requests))

    def test_public_redirect_or_unsafe_MIME_is_not_pending_readiness(self):
        url=github.QUAL_ORIGIN+'nexus/addons.xml'
        for response in (exchange('HEAD',url,b'',binary=True,absolute=True,status=302,headers={'Location':'https://attacker.invalid/'}),
                         exchange('HEAD',url,b'',binary=True,absolute=True,headers={'Content-Type':'text/html'})):
            client,sender,_=self.client([response])
            with self.assertRaises(ValueError) as error:client.read_public('nexus/addons.xml','f'*64,mime='application/xml')
            self.assertNotIsInstance(error.exception,github.PendingPublicBytes)
            self.assertEqual(sender.remaining,0)

    def test_public_exact_previous_mutable_catalog_index_checksum_is_pending(self):
        for path,mime in [('nexus/addons.xml','application/xml'),('nexus/addons.xml.md5','text/plain'),
                          ('nexus/addons.xml.sha256','application/octet-stream'),('index.html','text/html'),
                          ('candidate/catalogs/nexus/addons.xml','application/xml'),
                          ('candidate/catalogs/nexus/addons.xml.sha256','text/plain')]:
            url=github.QUAL_ORIGIN+path;old=b'known previous frozen bytes'
            queue=[exchange('HEAD',url,b'',binary=True,absolute=True,headers={'Content-Type':mime}),
                   exchange('GET',url,old,binary=True,absolute=True,headers={'Content-Type':mime})]
            client,sender,_=self.client(queue)
            with self.subTest(path=path),self.assertRaises(github.PendingPublicBytes):
                client.read_public(path,core.sha(b'new'),previous_sha256=core.sha(old))
            self.assertEqual(sender.remaining,0)

    def test_wrong_immutable_ZIP_sidecar_and_unknown_catalog_are_hard_failures(self):
        old=b'wrong unexpected bytes'
        cases=[('nexus/'+TAG+'.zip','application/zip',core.sha(old)),
               ('nexus/'+TAG+'.zip.sha256','text/plain',core.sha(old)),
               ('candidate/packages/'+TAG+'.zip','application/zip',core.sha(old)),
               ('candidate/packages/'+TAG+'.zip.sha256','text/plain',core.sha(old)),
               ('candidate/catalogs/nexus/addons.xml','application/xml',core.sha(b'known different before')),
               ('nexus/addons.xml','application/xml',None),('nexus/addons.xml','application/xml',core.sha(b'known different before')),
               ('arbitrary/index.html','text/html',core.sha(old))]
        for path,mime,prior in cases:
            url=github.QUAL_ORIGIN+path
            queue=[exchange('HEAD',url,b'',binary=True,absolute=True,headers={'Content-Type':mime}),
                   exchange('GET',url,old,binary=True,absolute=True,headers={'Content-Type':mime})]
            client,sender,_=self.client(queue)
            with self.subTest(path=path,known=prior is not None),self.assertRaises(ValueError) as error:
                client.read_public(path,core.sha(b'expected'),mime=mime,previous_sha256=prior)
            self.assertNotIsInstance(error.exception,github.PendingPublicBytes)
            self.assertEqual(sender.remaining,0)


if __name__=='__main__':unittest.main()
