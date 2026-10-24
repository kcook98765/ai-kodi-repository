"""Bound local publication preparation through existing roles; no owner/remote authority."""
from pathlib import Path


def operate(store, binding, state, out, operation, role):
    import lifecycle as lc
    import lifecycle_feed
    import publication_proposal as proposal

    lc.require(operation in ('build', 'qualify', 'review'), 'Publication operation denied')
    if operation == 'build':
        lc.require(role == 'kodi-repo-manager', 'Only manager prepares publication payloads')
    else:
        lc.require(role in lc.ROLES[operation], 'Publication evaluation role denied')
    # Check the original frozen feed and bound source before inspecting a copy.
    # The role cannot choose a path, destination, owner identity or fake approval.
    lc.require('feed_sha256' in state, 'Freeze a complete candidate feed first')
    lifecycle_feed.verify(store, binding, state, out)
    target = out / 'publication'
    lc.path_at(out, 'publication', exists=False)
    if operation == 'build' and not target.exists():
        source = binding['source']
        metadata = store.github.json('repos/' + source['repository'])
        lc.require(metadata.get('id') == source['repository_id'] and
                   metadata.get('full_name') == source['repository'], 'Source repository identity changed')
        owner = metadata.get('owner', {})
        lc.require(type(owner) is dict and type(owner.get('id')) is int and owner['id'] > 0,
                   'Verified source owner numeric identity unavailable')
        stage = out / 'feed-staging'
        # These synthetic heads describe a file-only simulation, never GitHub heads.
        expected = {'main_sha': '1' * 40, 'pages_sha': '2' * 40,
                    'pages_tree': proposal.git_tree({}), 'site_files': {},
                    'ledger_sha256': lc.sha(lc.path_at(stage, 'releases/candidate-manifest.json').read_bytes())}
        manifest = lc.read_json(out / 'preparation.json')
        proposal.prepare(stage, target,
                         source={k: source[k] for k in ('repository', 'repository_id', 'commit')} |
                                {'owner_id': owner['id']},
                         lanes=list(binding['targets']), expected=expected,
                         release_tag=manifest['addon_id'] + '-' + manifest['version'],
                         profile='candidate', synthetic=False)
    lc.require(target.is_dir(), 'Manager must freeze the local publication payload first')
    result = proposal.verify_payload(target)
    payload = result['payload']
    digest = proposal.sha(proposal.canonical(payload))
    blockers = list(result['production_blockers'])
    return {'status': 'BLOCKED' if blockers else 'PASS',
            'scope': 'Frozen local publication proposal evaluation; no publication authorization',
            'mode': 'local-simulation', 'task_id': binding['task_id'],
            'payload_sha256': digest, 'role': role,
            'eligibility_blockers': result['eligibility_blockers'],
            'production_blockers': blockers, 'simulation_eligible': result['simulation_eligible'],
            'independent_review_recorded': False,
            'review_status': 'Independent report and owner decisions remain separate',
            'publication_authorized': False, 'remote_actions_executed': [],
            'native_tested': False}
