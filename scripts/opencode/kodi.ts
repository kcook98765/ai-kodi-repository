import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const install = JSON.parse(fs.readFileSync(path.join(ROOT, '.opencode/lifecycle-installation.json'), 'utf8'));
if (install.schema !== 1 || install.adapter_version !== 1 || install.project_root !== ROOT || fs.realpathSync(ROOT) !== ROOT) {
  throw new Error('Unreviewed lifecycle installation binding');
}
const {tool} = await import(pathToFileURL(install.plugin_module).href);
const binding = {
  task_id: tool.schema.string().regex(/^[0-9a-f]{32}$/).optional(),
  expected_digest: tool.schema.string().regex(/^[0-9a-f]{64}$/).optional(),
};
const ROLES: Record<string, string[]> = {
  inspect: ['kodi-repo-manager','kodi-addon-tester','kodi-release-reviewer','kodi-addon-developer'],
  publication: ['kodi-repo-manager'], github: ['kodi-repo-manager'], build: ['kodi-repo-manager'], validate: ['kodi-addon-tester'],
  qualify: ['kodi-repo-manager','kodi-addon-tester'], review: ['kodi-repo-manager','kodi-release-reviewer'],
};

async function run(operation: string, input: any, ctx: any): Promise<string> {
  if (ctx.directory !== ROOT || fs.realpathSync(ctx.directory) !== ROOT || !ROLES[operation]?.includes(ctx.agent)) {
    throw new Error('Workspace or role denied');
  }
  await ctx.ask({permission: 'kodi_' + operation, patterns: ['*'], always: [],
    metadata: {operation, scope: input.task_id ? 'owner-bound local candidate preparation' : 'local fixture only'}});
  const {task_id, expected_digest, ...args} = input;
  if (!!task_id !== !!expected_digest) throw new Error('Task and exact binding digest are both required');
  let script: string, argv: string[], body = '';
  if (operation === 'publication') {
    if (!task_id || !expected_digest) throw new Error('Task binding required');
    script = path.join(ROOT, 'scripts/publication_cli.py'); argv = ['--role',ctx.agent];
    body = JSON.stringify({task_id,expected_digest,...args});
  } else if (task_id) {
    script = path.join(ROOT, 'scripts/lifecycle_adapter.py');
    argv = ['--role', ctx.agent, '--operation', operation];
    body = JSON.stringify({task_id, expected_digest, arguments: args,
      ...(args.action === 'publication_pilot' ? {context:{agent:ctx.agent,session_id:ctx.sessionID,tool:'kodi_'+operation}} : {})});
  } else {
    script = path.join(ROOT, '.opencode/control/agent-tools.py');
    argv = [operation, '--role', ctx.agent];
    if (operation === 'github') {
      for (const name of ['repository','resource','page']) {
        if (args[name] !== undefined) argv.push('--' + name, String(args[name]));
      }
      if (Object.keys(args).some(k => !['repository','resource','page'].includes(k))) throw new Error('Task required');
    } else if (Object.keys(args).length) throw new Error('Task required for preparation arguments');
  }
  return new Promise((resolve, reject) => {
    const p = spawn(install.python, ['-I','-B',script,...argv], {cwd:ROOT, shell:false,
      env:{PATH:'/usr/bin:/bin',LANG:'C.UTF-8',PYTHONDONTWRITEBYTECODE:'1',PYTHONNOUSERSITE:'1'}, signal:ctx.abort});
    let out = '', err = '', exceeded = false;
    const collect = (target: 'out'|'err', data: Buffer) => {
      if (target === 'out') out += data.toString(); else err += data.toString();
      if (out.length + err.length > 2_000_000) { exceeded = true; p.kill('SIGKILL'); }
    };
    p.stdout.on('data', b => collect('out', b)); p.stderr.on('data', b => collect('err', b));
    const timer = setTimeout(() => p.kill('SIGKILL'), 240_000);
    p.on('error', e => {clearTimeout(timer); reject(e);});
    p.on('close', code => {clearTimeout(timer); resolve(JSON.stringify({exit_code:code,
      result:out.slice(0,2_000_000),stderr:err.slice(0,20_000),output_limit_exceeded:exceeded}));});
    p.stdin.end(body);
  });
}

export const inspect = tool({description:'Inspect bound task source identity and state; zero arguments retain fixture inspection.',
  args:{...binding,file:tool.schema.string().max(500).optional()},execute:(a:any,c:any)=>run('inspect',a,c)});
export const github = tool({description:'Anonymous bounded GitHub GET only. Enrolled task can acquire pinned source or read lists. No writes/enrollment.',
  args:{...binding,action:tool.schema.enum(['acquire','list']).optional(),
    resource:tool.schema.enum(['issues','pulls','releases']).optional(),page:tool.schema.number().int().min(1).max(5).optional(),
    repository:tool.schema.enum(['kcook98765/kodi-agent-toolkit','kcook98765/kodi-lab','kcook98765/plugin.video.tastemade','kcook98765/skin.aura']).optional()},
  execute:(a:any,c:any)=>run('github',a,c)});
export const build = tool({description:'Prepare a candidate package, action=feed for its isolated feed, or action=publication for a blocked local frozen proposal. No remote publication. Zero arguments retain fixtures.',
  args:{...binding,action:tool.schema.enum(['feed','publication','publication_pilot']).optional(),addon_subdir:tool.schema.string().max(500).optional(),
    runtime_files:tool.schema.array(tool.schema.string().max(500)).min(1).max(10000).optional()},
  execute:(a:any,c:any)=>run('build',a,c)});
export const validate = tool({description:'Independently registered lane Toolkit static checks; missing matching tooling is UNVERIFIED. No native/runtime compatibility claim. Zero arguments retain fixture checks.',
  args:{...binding,lane:tool.schema.enum(['matrix','nexus','omega','piers']).optional()},execute:(a:any,c:any)=>run('validate',a,c)});
export const qualify = tool({description:'Verify frozen bound candidate package/source only; no compatibility claims. Zero arguments retain fixture qualification.',
  args:{...binding,action:tool.schema.enum(['publication','publication_pilot']).optional()},execute:(a:any,c:any)=>run('qualify',a,c)});
export const review = tool({description:'Independent frozen bound candidate ZIP/source and pending-record audit. Zero arguments retain fixture review.',
  args:{...binding,action:tool.schema.enum(['publication','publication_pilot']).optional()},execute:(a:any,c:any)=>run('review',a,c)});
export const policy_probe = tool({description:'Ask actual permission engine about fixed canaries; execute no operation.',
  args:{probe:tool.schema.enum(['publish','docker','source_edit','scope_edit','mcp','delegate','report_edit'])},
  async execute(a:any,c:any) {
    if(c.directory !== ROOT)throw new Error('Workspace mismatch');
    const cases:Record<string,[string,string]> = {publish:['bash','git push'],docker:['bash','docker info'],
      source_edit:['edit',path.join(ROOT,'forbidden-source.py')],scope_edit:['edit',path.relative(c.worktree,path.join(ROOT,'config/repository.json'))],
      mcp:['kodi_lab_managed_ensure_ready','*'],delegate:['task','kodi-addon-developer'],
      report_edit:['edit',path.relative(c.worktree,path.join(ROOT,'plans/MANAGER-READINESS.md'))]};
    const [permission,pattern]=cases[a.probe];
    try {await c.ask({permission,patterns:[pattern],always:[],metadata:{canary:true,executes_operation:false}});
      return JSON.stringify({probe:a.probe,decision:'ALLOW',operation_executed:false});}
    catch {return JSON.stringify({probe:a.probe,decision:'DENY',operation_executed:false});}
  }});

export const publication = tool({description:'Opt-in disposable pilot only. Fixed task-bound status/request/execute/reconcile; exact owner review required. No key or backend arguments.',
  args:{task_id:tool.schema.string().regex(/^[0-9a-f]{32}$/),expected_digest:tool.schema.string().regex(/^[0-9a-f]{64}$/),
    operation:tool.schema.enum(['status','request','execute','reconcile']),proposal_sha256:tool.schema.string().regex(/^[0-9a-f]{64}$/).optional()},
  execute:(a:any,c:any)=>run('publication',a,c)});
