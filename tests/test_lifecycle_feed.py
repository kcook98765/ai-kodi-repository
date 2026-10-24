"""Complete isolated candidate feeds; no real release approvals or hosting."""
from pathlib import Path
import copy
import json
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_lifecycle as fixtures
from test_lifecycle import runtime, source_archive


class CandidateFeedTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LifecycleTests('test_prepare_deterministic_candidate_reuses_independent_audit')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        shutil.copyfile(fixtures.ROOT/'LICENSE',self.fixture.root/'LICENSE')
        shutil.copytree(fixtures.ROOT/'packages',self.fixture.root/'packages')

    def feed(self):
        self.fixture.prepare()
        return self.fixture.call('build', action='feed')

    @property
    def stage(self):
        return self.fixture.out/'feed-staging'

    def test_complete_feed_reproducible_isolated_and_independently_reviewed(self):
        import repository as repo
        before=self.fixture.store.baseline()
        result=self.feed()
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['whole_site_reproducible'])
        self.assertGreater(result['url_paths'],15)
        self.assertEqual(result['repository_id'],'repository.ai.kodi.candidate.'+self.fixture.task['task_id'])
        self.assertFalse(result['publication_authorized'])
        self.assertTrue(result['release_blockers'])
        self.assertEqual(self.fixture.store.baseline(),before)
        self.assertFalse((self.fixture.root/'dist/production').exists())
        plan=json.loads((self.stage/'dist/candidate/release-plan.json').read_text())
        self.assertEqual(set(plan['catalogs']),{'matrix','nexus','omega','piers'})
        self.assertNotIn('repository.ai.kodi',[p['id'] for p in plan['packages']])
        installer=next(p for p in plan['packages'] if p['id']==result['repository_id'])
        manifest,_=repo.inspect_zip((self.stage/'dist/candidate/site'/installer['path']).read_bytes())
        self.assertIn('LOCAL CANDIDATE',manifest.get('name'))
        for node in manifest.findall("extension[@point='xbmc.addon.repository']/dir/*"):
            if node.tag in ('info','checksum','datadir','artdir'):
                self.assertTrue(node.text.startswith(result['base_url']+'candidate/'))
        review=self.fixture.call('review','kodi-release-reviewer')
        self.assertEqual(review['feed']['site_manifest_sha256'],result['site_manifest_sha256'])
        self.assertEqual(self.fixture.call('build',action='feed')['site_manifest_sha256'],result['site_manifest_sha256'])

    def test_extra_or_changed_site_files_fail_frozen_review(self):
        self.feed()
        site=self.stage/'dist/candidate/site'
        (site/'unreviewed.xml').write_text('unapproved')
        with self.assertRaisesRegex(ValueError,'inventory changed'):
            self.fixture.call('review','kodi-release-reviewer')

    def test_forged_plan_site_hash_cannot_defeat_independent_auditor(self):
        import lifecycle_feed as feed
        self.feed()
        config=json.loads((self.stage/'config/candidate-repository.json').read_text())
        catalog=self.stage/'dist/candidate/site/candidate/catalogs/nexus/addons.xml'
        catalog.write_bytes(catalog.read_bytes().replace(config['addon_id'].encode(),b'repository.ai.kodi'))
        import repository as repo
        site=self.stage/'dist/candidate/site'
        catalog.with_name('addons.xml.sha256').write_text(repo.sha(catalog.read_bytes())+'\n')
        plan_path=self.stage/'dist/candidate/release-plan.json';plan=json.loads(plan_path.read_text())
        plan['catalogs']['nexus']['sha256']=repo.sha(catalog.read_bytes())
        plan['catalogs']['nexus']['ids']['repository.ai.kodi']=plan['catalogs']['nexus']['ids'].pop(config['addon_id'])
        plan['site_files']={p.relative_to(site).as_posix():repo.sha(p.read_bytes()) for p in site.rglob('*') if p.is_file()}
        plan['site_manifest_sha256']=repo.sha(repo.json_bytes(plan['site_files']))
        plan_path.write_bytes(repo.json_bytes(plan))
        with self.assertRaises(ValueError):
            feed.run(self.stage,sys.executable,'audit_candidate.py',['--profile','candidate'])

    def test_production_snapshot_and_candidate_ledger_namespace_are_preserved(self):
        import lifecycle_feed as feed
        self.feed()
        for name,digest in self.fixture.task['binding']['baseline'].items():
            self.assertEqual(__import__('lifecycle').sha((self.stage/name).read_bytes()),digest)
        ledger=self.stage/'releases/candidate-manifest.json'
        value=json.loads(ledger.read_text());value['repository_id']='repository.ai.kodi';ledger.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            feed.run(self.stage,sys.executable,'audit_candidate.py',['--profile','candidate'])

    def test_ledger_retention_guard_rejects_missing_candidate_input(self):
        import lifecycle_feed as feed
        self.feed()
        path=self.stage/'config/candidate.json';value=json.loads(path.read_text());value['packages']=[];path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'Historical release removed|blocked'):
            feed.run(self.stage,sys.executable,'repository.py',['build','--profile','candidate'])

    def test_production_publication_preflight_rejects_candidate_plan(self):
        self.feed()
        import check_publication
        plan=json.loads((self.stage/'dist/candidate/release-plan.json').read_text())
        with self.assertRaisesRegex(ValueError,'Only an approved production plan'):
            check_publication.site_audit(plan)

    def test_missing_required_dependency_is_a_feed_blocker(self):
        files=runtime()
        files['addon.xml']=files['addon.xml'].replace(b'</requires>',b'<import addon="script.module.absent" version="1.0.0"/></requires>')
        self.fixture.gh.files=files;self.fixture.gh.archive=source_archive(files)
        self.fixture.prepare()
        with self.assertRaisesRegex(ValueError,'dependency unavailable'):
            self.fixture.call('build',action='feed')

    def test_owner_bound_dependency_member_satisfies_closure(self):
        files=runtime('script.module.helper','1.0.0')
        self.fixture.gh.files=files;self.fixture.gh.archive=source_archive(files)
        self.fixture.prepare()
        member={k:self.fixture.task[k] for k in ('task_id','expected_digest')}
        files=runtime()
        files['addon.xml']=files['addon.xml'].replace(b'</requires>',b'<import addon="script.module.helper" version="1.0.0"/></requires>')
        self.fixture.gh.files=files;self.fixture.gh.archive=source_archive(files)
        self.fixture.request={**self.fixture.request,'feed_members':[member]}
        self.fixture.prepare()
        result=self.fixture.call('build',action='feed')
        self.assertEqual(result['status'],'PASS')
        plan=json.loads((self.stage/'dist/candidate/release-plan.json').read_text())
        self.assertIn('script.module.helper',plan['catalogs']['nexus']['ids'])
        self.assertNotIn('script.module.helper',plan['catalogs']['matrix']['ids'])

    def test_distinct_identity_rejects_production_origin_and_malformed_members(self):
        for change in ({'candidate_base_url':'https://kcook98765.github.io/private/'},
                       {'candidate_base_url':'https://kcook98765.github.io:443/private/'},
                       {'candidate_base_url':'https://kcook98765.github.io./private/'},
                       {'candidate_base_url':'http://candidate.invalid/'},
                       {'candidate_base_url':'https://candidate.invalid/../escape/'},
                       {'feed_members':[{'task_id':'../escape','expected_digest':'0'*64}]}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.fixture.enroll({**self.fixture.request,**change})

    def test_pending_strict_v2_only_prevents_history_exception_reset(self):
        import lifecycle_feed as feed
        self.feed()
        config=json.loads((self.stage/'config/candidate.json').read_text())
        path=self.stage/'incoming'/config['packages'][0]['review_record'];record=json.loads(path.read_text())
        record['schema_version']=3;path.write_text(json.dumps(record))
        config['packages'][0]['review_record_sha256']=__import__('lifecycle').sha(path.read_bytes())
        (self.stage/'config/candidate.json').write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError,'pending strict-v2'):
            feed.run(self.stage,sys.executable,'repository.py',['build','--profile','candidate'])

    def test_changed_candidate_destination_cannot_reuse_installer_bytes(self):
        import lifecycle_feed as feed
        self.feed()
        path=self.stage/'config/candidate-repository.json';config=json.loads(path.read_text())
        config['base_url']='https://different.invalid/new/';path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError,'Historical release removed|Immutable|blocked'):
            feed.run(self.stage,sys.executable,'repository.py',['build','--profile','candidate'])

    def test_builder_and_auditor_independently_reject_production_origin_alias(self):
        import lifecycle_feed as feed
        self.feed()
        path=self.stage/'config/candidate-repository.json';config=json.loads(path.read_text())
        config['base_url']='https://kcook98765.github.io:443/private/';path.write_text(json.dumps(config))
        for script,args in (('repository.py',['verify','--profile','candidate']),('audit_candidate.py',['--profile','candidate'])):
            with self.subTest(script=script),self.assertRaises(ValueError):
                feed.run(self.stage,sys.executable,script,args)

    def test_successor_selected_and_previous_candidate_bytes_retained(self):
        import repository as repo
        old=runtime(version='1.0.0')
        self.fixture.gh.files=old;self.fixture.gh.archive=source_archive(old)
        self.fixture.prepare()
        member={k:self.fixture.task[k] for k in ('task_id','expected_digest')}
        old_hash=self.fixture.call('review','kodi-release-reviewer')['package_sha256']
        newer=runtime(version='1.1.0')
        self.fixture.gh.files=newer;self.fixture.gh.archive=source_archive(newer)
        self.fixture.request={**self.fixture.request,'feed_members':[member]}
        self.fixture.prepare();self.fixture.call('build',action='feed')
        plan=json.loads((self.stage/'dist/candidate/release-plan.json').read_text())
        self.assertEqual(plan['catalogs']['nexus']['ids']['plugin.video.independent'],'1.1.0')
        previous=next(p for p in plan['packages'] if p['id']=='plugin.video.independent' and p['version']=='1.0.0')
        self.assertEqual(previous['lanes'],[])
        self.assertEqual(repo.sha((self.stage/'dist/candidate/site'/previous['path']).read_bytes()),old_hash)

    def test_original_production_installer_bytes_unchanged(self):
        import repository as repo
        config=repo.load_config()
        blob=repo.zip_bytes(repo.installer(config,'production'))
        ledger=json.loads((fixtures.ROOT/'releases/manifest.json').read_text())
        expected=next(v['sha256'] for v in ledger['packages'] if v['id']=='repository.ai.kodi' and v['version']==config['version'])
        self.assertEqual(repo.sha(blob),expected)

    def test_cached_lane_receipt_rechecks_index_bytes(self):
        import lifecycle as lc
        root=self.fixture.root;cache=root/'cache'
        indexes={}
        for lane in lc.LANES:
            data=('synthetic index '+lane).encode();(cache/(lane+'.xml.gz')).write_bytes(data)
            indexes[lane]={'filename':lane+'.xml.gz','url':f'https://mirrors.kodi.tv/addons/{lane}/addons.xml.gz','sha256':lc.sha(data)}
        (cache/'manifest.json').write_text(json.dumps({'schema_version':1,'indexes':indexes}))
        identity={'environment':{'packages':{'Kodistubs':{'version':'20.0.1'}}}}
        installed=self.fixture.installed
        installed['toolkit_identity']=identity
        installed['lane_environments']={lane:{'status':'unverified','reason':'synthetic missing environment'} for lane in lc.LANES}
        installed['lane_environments']['nexus']={'status':'available','python':sys.executable,'toolkit':str(root),
            'cache':str(cache),'identity':identity,'stub_version':'20.0.1','coverage_limits':['Synthetic static-only control']}
        (root/'.opencode/lifecycle-installation.json').write_text(json.dumps(installed))
        with patch.object(lc,'toolkit_identity',return_value=identity):
            self.fixture.prepare()
            data={'branch':'nexus','passed':True,'source_snapshot':{n:lc.sha(b) for n,b in runtime().items()},
                  'checks':{'types':{'status':'passed','passed':True}}}
            with patch.object(lc.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(data),'')):
                result=self.fixture.call('validate','kodi-addon-tester',lane='nexus')
                self.assertEqual(result['status'],'PASS')
            (cache/'nexus.xml.gz').write_bytes(b'changed without updating manifest')
            for operation,role,args in (('validate','kodi-addon-tester',{'lane':'nexus'}),('review','kodi-release-reviewer',{})):
                with self.subTest(operation=operation),self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    self.fixture.call(operation,role,**args)

    def test_same_addon_successor_from_different_repository_is_rejected(self):
        self.fixture.prepare()
        member={k:self.fixture.task[k] for k in ('task_id','expected_digest')}
        self.fixture.gh.name='new-owner/takeover';self.fixture.gh.repo_id+=1
        self.fixture.request={**self.fixture.request,'repository':self.fixture.gh.name,
                              'repository_id':self.fixture.gh.repo_id,'feed_members':[member]}
        self.fixture.gh.files=runtime(version='2.0.0');self.fixture.gh.archive=source_archive(self.fixture.gh.files)
        self.fixture.prepare()
        with self.assertRaisesRegex(ValueError,'source identity changed'):
            self.fixture.call('build',action='feed')
