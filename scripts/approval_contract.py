"""Versioned approval evidence. No publication or evidence invention.

The builder and auditor use this contract against independently loaded, hashed
inputs. Package, catalog, retention and production gates remain in each consumer.
"""
from datetime import datetime
from pathlib import PurePosixPath
import re

POLICY = 'strict-v1'
UNOFFICIAL_POLICY = 'unofficial-integration-v1'
DECISION_FIELDS = {'status', 'actor', 'role', 'recorded_at', 'rationale', 'evidence'}
V2_FIELDS = {'approval_policy', 'approval_lanes', 'rights_review',
             'owner_acknowledgment', 'technical_release', 'release_decision',
             'unresolved_risks'}


def require(condition, message):
    if not condition:
        raise ValueError('Approval contract: ' + message)


def references(value):
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value)


def decision(value, statuses, inactive='pending', extra=()):
    require(isinstance(value, dict) and value.get('status') in statuses,
            'invalid decision status')
    require(set(value) <= DECISION_FIELDS | set(extra), 'unknown decision field')
    if value['status'] == inactive:
        require(set(value) == {'status'}, 'pending decision must not imply an action')
        return
    require(DECISION_FIELDS <= set(value), 'decision attribution/evidence missing')
    for key in ('actor', 'role', 'rationale'):
        require(isinstance(value[key], str) and bool(value[key].strip()), 'empty ' + key)
    stamp = value['recorded_at']
    require(isinstance(stamp, str) and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', stamp) is not None,
        'recorded_at must be UTC RFC3339 seconds')
    try:
        datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise ValueError('Approval contract: invalid recorded_at date') from None
    require(references(value['evidence']), 'decision evidence missing')


def canonical_path(value):
    return (isinstance(value, str) and bool(PurePosixPath(value).parts) and
            not PurePosixPath(value).is_absolute() and PurePosixPath(value).as_posix() == value and
            '..' not in PurePosixPath(value).parts and
            not any(c in value for c in ('\\', ':')) and
            all(ord(c) >= 32 for c in value))


def pinned_references(value):
    if not references(value):
        return False
    for item in value:
        match = re.fullmatch(r'(.+) sha256:([0-9a-f]{64})', item)
        if not match or not canonical_path(match[1]):
            return False
    return True


def exact_risks(value, ids):
    return (isinstance(value, list) and bool(value) and
            all(isinstance(item, str) for item in value) and
            len(value) == len(set(value)) and set(value) == set(ids))


def unofficial(record, risks, ack, blockers):
    """Validate the closed v3 assertions; retain accepted findings as unresolved."""
    require(record['rights_approved'] is False and record['rights_review'] == {'status': 'pending'},
            'v3 broad rights must remain false/pending')
    value = record.get('unofficial_integration')
    require(isinstance(value, dict) and set(value) == {'package_distribution_review',
            'service_use_review', 'owner_distribution_decision', 'disclosure'},
            'malformed unofficial_integration')
    package = value['package_distribution_review']
    service = value['service_use_review']
    owner = value['owner_distribution_decision']
    ids = [r['id'] for r in risks if r['category'] == 'provider_terms']
    for action, statuses, extras in [
        (package, ('pending', 'verified', 'rejected', 'revoked'), ('scope',)),
        (service, ('pending', 'terms_unresolved', 'blocked', 'revoked'),
         ('scope', 'risk_ids', 'provider_permission_obtained', 'provider_content_authorization')),
        (owner, ('pending', 'accepted', 'declined', 'revoked'), ('risk_ids', 'authorization_claimed'))]:
        decision(action, statuses, extra=extras)
        if action['status'] != 'pending':
            require(set(action) == DECISION_FIELDS | set(extras), 'v3 action fields missing')
            require(pinned_references(action['evidence']), 'v3 evidence must be hash-pinned')
    if package['status'] != 'pending':
        require(package['scope'] == 'all_distributed_materials', 'package distribution scope missing')
    if service['status'] != 'pending':
        require(service['scope'] == 'runtime_service_content_and_marks' and
                service['provider_permission_obtained'] is False and
                service['provider_content_authorization'] == 'not_established',
                'v3 must not claim provider/content authorization')
        require(exact_risks(service['risk_ids'], ids), 'service review risk scope mismatch')
    if owner['status'] != 'pending':
        require(owner['role'] == 'owner' and owner['authorization_claimed'] is False,
                'owner distribution decision must not claim authorization')
        require(exact_risks(owner['risk_ids'], ids), 'owner distribution risk scope mismatch')
    notice = value['disclosure']
    require(isinstance(notice, dict) and set(notice) == {'package_path', 'package_sha256', 'release_text'},
            'malformed unofficial disclosure')
    require(canonical_path(notice['package_path']) and
            isinstance(notice['package_sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', notice['package_sha256']) is not None and
            record['runtime_files'].get(notice['package_path']) == notice['package_sha256'],
            'disclosure must bind a reviewed runtime member')
    require(isinstance(notice['release_text'], str) and bool(notice['release_text'].strip()) and
            all(ord(c) >= 32 or c in '\n\r\t' for c in notice['release_text']),
            'release disclosure text missing or unsafe')
    gates = [
        (bool(ids) and len(ids) == len(risks), 'Only nonempty provider-terms findings are eligible'),
        (package['status'] == 'verified', 'Package distribution review missing'),
        (service['status'] == 'terms_unresolved', 'Service-use assessment missing or blocked'),
        (ack['status'] == 'acknowledged', 'Owner acknowledgment missing'),
        (owner['status'] == 'accepted', 'Owner distribution acceptance missing'),
    ]
    if owner['status'] == 'accepted':
        for review in (package, service):
            gates.append((review.get('actor', '').strip().casefold() != owner['actor'].strip().casefold(),
                          'Distribution and service reviewers must be independent of accepting owner'))
    blockers.extend(message for passed, message in gates if not passed)
    accepted = all(passed for passed, _ in gates)
    if not accepted:
        blockers.extend('Unresolved risk: ' + item for item in ids)
    return {'unofficial_integration': value,
            'provider_permission_obtained': False, 'provider_content_authorization': 'not_established',
            'accepted_terms_risks': [r for r in risks if r['category'] == 'provider_terms'] if accepted else [],
            'publication_authorized': False}


def assess(record, lanes):
    """Validate versioned assertions and return an honest, JSON-safe report.

    Unversioned and explicit v1 records keep the old boolean contract. New
    fields cannot be smuggled into v1 where an older consumer would ignore them.
    This does not authenticate actors or establish the substance of evidence.
    """
    version = record.get('schema_version', 1)
    require(type(version) is int and version in (1, 2, 3), 'unsupported schema_version')
    require(version == 3 or 'unofficial_integration' not in record, 'v3 fields require schema_version=3')
    scope = {key: record[key] for key in ('package_sha256', 'source_repository', 'source_commit',
                                        'rights_approved', 'release_approved')}
    scope['lanes'] = list(lanes)
    blockers = [key for key in ('rights_approved', 'release_approved')
                if not record[key] and not (version == 3 and key == 'rights_approved')]
    runtime = {}
    # No active lanes is retained history only. Preserve acceptance over the
    # recorded compatibility scope; both consumers separately require the ledger.
    acceptance_lanes = lanes or (list(record['compatibility']) if version == 3 else [])
    if version == 3 and not acceptance_lanes:
        blockers.append('Original runtime acceptance scope missing')
    for lane in acceptance_lanes:
        item = record['compatibility'][lane]
        if not (item['static_accepted'] and item['runtime_accepted'] and item['evidence']):
            blockers.append('Per-lane acceptance missing: ' + lane)
        runtime[lane] = {'status': 'legacy_accepted' if item['runtime_accepted'] else 'legacy_not_accepted',
                         'evidence': item['evidence']}
    if version == 1:
        require(not (V2_FIELDS & set(record)) and all('runtime_test' not in item
                for item in record['compatibility'].values()), 'v2 fields require schema_version=2')
        return {**scope, 'schema_version': 1, 'rights_status': 'legacy_approved' if record['rights_approved'] else 'pending',
                'release_status': 'legacy_approved' if record['release_approved'] else 'pending',
                'technical_release_status': 'legacy_unspecified', 'owner_acknowledgment': {'status': 'not_recorded'},
                'runtime': runtime, 'unresolved_risks': None,
                'recorded_limitations': record.get('limitations', []),
                'recorded_native_scope': record.get('native_scope', {}),
                'limitations': ['Legacy boolean attestations; separate attribution, rights basis, technical decision and runtime deferrals are unspecified.'],
                'release_blockers': sorted(set(blockers))}

    require(V2_FIELDS <= set(record), 'v2 fields missing')
    policy = UNOFFICIAL_POLICY if version == 3 else POLICY
    require(record['approval_policy'] == policy, 'unsupported approval_policy')
    require(isinstance(record['approval_lanes'], list) and
            all(isinstance(lane, str) for lane in record['approval_lanes']) and
            len(record['approval_lanes']) == len(set(record['approval_lanes'])) and
            set(record['approval_lanes']) == set(lanes), 'approval lane scope mismatch')
    for key, statuses in [('rights_review', ('verified', 'pending', 'rejected', 'revoked')),
                          ('technical_release', ('approved', 'pending', 'rejected', 'revoked')),
                          ('release_decision', ('approved', 'pending', 'rejected', 'revoked'))]:
        decision(record[key], statuses)
    require(record['rights_approved'] is (record['rights_review']['status'] == 'verified'),
            'rights_approved contradicts rights_review')
    require(record['release_approved'] is (record['release_decision']['status'] == 'approved'),
            'release_approved contradicts release_decision')
    if record['technical_release']['status'] != 'approved':
        blockers.append('Explicit technical release approval missing')

    risks = record['unresolved_risks']
    require(isinstance(risks, list), 'unresolved_risks must be a list')
    ids = []
    for risk in risks:
        require(isinstance(risk, dict) and set(risk) == {'id', 'category', 'description', 'evidence'},
                'malformed unresolved risk')
        require(all(isinstance(risk[k], str) and risk[k].strip() for k in ('id', 'description'))
                and risk['category'] in (('rights', 'runtime', 'technical', 'other', 'provider_terms')
                                         if version == 3 else ('rights', 'runtime', 'technical', 'other'))
                and references(risk['evidence']), 'risk evidence missing')
        if version == 3:
            require(pinned_references(risk['evidence']), 'v3 risk evidence must be hash-pinned')
        ids.append(risk['id'])
        if version != 3 or risk['category'] != 'provider_terms':
            blockers.append('Unresolved risk: ' + risk['id'])
    require(len(ids) == len(set(ids)), 'duplicate risk id')
    ack = record['owner_acknowledgment']
    decision(ack, ('acknowledged', 'not_recorded'), inactive='not_recorded', extra=('risk_ids',))
    if ack['status'] == 'acknowledged':
        require(ack['role'] == 'owner', 'acknowledgment must record an owner action')
        require(isinstance(ack.get('risk_ids'), list) and bool(ids) and
                all(isinstance(item, str) for item in ack['risk_ids']) and
                len(ack['risk_ids']) == len(set(ack['risk_ids'])) and set(ack['risk_ids']) == set(ids),
                'acknowledgment must identify the exact unresolved risks')
    require(not (record['rights_approved'] and any(r['category'] == 'rights' for r in risks)),
            'verified rights contradict unresolved rights risks')
    require(not (record['technical_release']['status'] == 'approved' and
                 any(r['category'] == 'technical' for r in risks)),
            'technical approval contradicts unresolved technical risks')

    for lane, item in record['compatibility'].items():
        require(lane in ('matrix', 'nexus', 'omega', 'piers'), 'unknown compatibility lane')
        require(all(type(item[k]) is bool for k in ('static_accepted', 'runtime_accepted')) and
                isinstance(item['evidence'], list) and all(isinstance(e, str) and e.strip()
                for e in item['evidence']), 'malformed compatibility evidence')
        test = item.get('runtime_test')
        decision(test, ('passed', 'deferred', 'pending', 'failed'),
                 extra=('platform', 'kodi_version', 'scope', 'outstanding_tests'))
        passed = test['status'] == 'passed'
        require(type(item['runtime_accepted']) is bool and item['runtime_accepted'] is passed,
                'runtime_accepted contradicts runtime_test')
        if test['status'] != 'pending':
            require(all(isinstance(test.get(k), str) and test[k].strip()
                        for k in ('platform', 'kodi_version', 'scope')), 'runtime scope missing')
            pending = test.get('outstanding_tests')
            require(isinstance(pending, list) and all(isinstance(t, str) and t.strip() for t in pending),
                    'invalid outstanding_tests')
            require(not pending if passed else bool(pending), 'runtime result contradicts outstanding tests')
            if passed:
                require(references(item['evidence']), 'completed runtime evidence missing')
        if lane in acceptance_lanes:
            runtime[lane] = test
            if not passed:
                blockers.append('Runtime testing ' + test['status'] + ': ' + lane)
    require(not (risks and any(r['category'] == 'runtime' for r in risks) and
                 runtime and all(t['status'] == 'passed' for t in runtime.values())),
            'completed runtime contradicts unresolved runtime risks')
    alternative = unofficial(record, risks, ack, blockers) if version == 3 else {}
    if version == 3:
        alternative['package_distribution_eligible'] = not any(b != 'release_approved' for b in blockers)
    require(not record['release_approved'] or not blockers,
            'final release approval contradicts outstanding gates')
    return {**scope, **alternative, 'schema_version': version, 'approval_policy': policy, 'approval_lanes': record['approval_lanes'],
            'release_status': record['release_decision']['status'],
            'rights_status': record['rights_review']['status'], 'rights_review': record['rights_review'],
            'technical_release_status': record['technical_release']['status'],
            'technical_release': record['technical_release'], 'release_decision': record['release_decision'],
            'owner_acknowledgment': ack, 'runtime': runtime, 'unresolved_risks': risks,
            'recorded_limitations': record.get('limitations', []),
            'recorded_native_scope': record.get('native_scope', {}),
            'limitations': [], 'release_blockers': sorted(set(blockers))}
