"""Versioned approval evidence. No exceptions, publication or evidence invention.

The builder and auditor use this contract against independently loaded, hashed
inputs. Package, catalog, retention and production gates remain in each consumer.
"""
from datetime import datetime
import re

POLICY = 'strict-v1'
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


def assess(record, lanes):
    """Validate additive v2 assertions and return an honest, JSON-safe report.

    Unversioned and explicit v1 records keep the old boolean contract. New
    fields cannot be smuggled into v1 where an older consumer would ignore them.
    This does not authenticate actors or establish the substance of evidence.
    """
    version = record.get('schema_version', 1)
    require(type(version) is int and version in (1, 2), 'unsupported schema_version')
    scope = {key: record[key] for key in ('package_sha256', 'source_repository', 'source_commit',
                                        'rights_approved', 'release_approved')}
    scope['lanes'] = list(lanes)
    blockers = [key for key in ('rights_approved', 'release_approved') if not record[key]]
    runtime = {}
    for lane in lanes:
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
    require(record['approval_policy'] == POLICY, 'unsupported approval_policy')
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
                and risk['category'] in ('rights', 'runtime', 'technical', 'other')
                and references(risk['evidence']), 'risk evidence missing')
        ids.append(risk['id'])
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
        if lane in lanes:
            runtime[lane] = test
            if not passed:
                blockers.append('Runtime testing ' + test['status'] + ': ' + lane)
    require(not (risks and any(r['category'] == 'runtime' for r in risks) and
                 runtime and all(t['status'] == 'passed' for t in runtime.values())),
            'completed runtime contradicts unresolved runtime risks')
    require(not record['release_approved'] or not blockers,
            'final release approval contradicts outstanding gates')
    return {**scope, 'schema_version': 2, 'approval_policy': POLICY, 'approval_lanes': record['approval_lanes'],
            'release_status': record['release_decision']['status'],
            'rights_status': record['rights_review']['status'], 'rights_review': record['rights_review'],
            'technical_release_status': record['technical_release']['status'],
            'technical_release': record['technical_release'], 'release_decision': record['release_decision'],
            'owner_acknowledgment': ack, 'runtime': runtime, 'unresolved_risks': risks,
            'recorded_limitations': record.get('limitations', []),
            'recorded_native_scope': record.get('native_scope', {}),
            'limitations': [], 'release_blockers': sorted(set(blockers))}
