from app.digests import digest, encode, fingerprints
from app.modules.revision.ledger import decide
from app.problems import Rejection


def verify(record, archive=None, seen=None):
    stamp = record['manifest']
    checks = (fingerprints(record['original']) == stamp['input_sha256'],
              digest(encode(record['stages'])) == stamp['result_sha256'],
              record['stages']['source']['counts']['balanced'],
              record['stages']['balance']['balanced'])
    if not all(checks):
        raise Rejection('INVALID_EVIDENCE', '证据散列或覆盖勾稽不符', 409)
    if 'revision' in record['stages']:
        verify_review(record, archive, seen or frozenset())
    elif stamp.get('kind') not in (None, 'original') or stamp.get('base_id'):
        raise Rejection('INVALID_EVIDENCE', '换版复核台账与归档记录不符', 409)
    return stamp


def verify_review(record, archive, seen):
    stamp, stages = record['manifest'], record['stages']
    review, rows = stages['revision'], stages['revision']['rows']
    counted = {state: sum(row['state'] == state for row in rows) for state in ('carried', 'pending', 'retired')}
    if (stamp.get('kind') != 'revision' or stamp.get('base_id') != review['base_id'] or
            stamp.get('review_rules') != review['rules'] or review['base_id'] == stamp['id'] or
            any(counted[state] != review['counts'][state] for state in counted) or
            review['counts']['total'] != len(rows) or
            any(row['state'] == 'carried' and (row['reasons'] or not all(row['checks'].values())) for row in rows) or
            any(row['state'] != 'carried' and not row['reasons'] for row in rows) or
            any(row['source_gone'] != (row['state'] == 'retired') for row in rows)):
        raise Rejection('INVALID_EVIDENCE', '换版复核台账与归档记录不符', 409)
    if archive is None:
        return
    if review['base_id'] in seen:
        raise Rejection('INVALID_EVIDENCE', '换版档案引用成环', 409)
    try:
        base = archive.read(review['base_id'])
    except Rejection as error:
        raise Rejection('INVALID_EVIDENCE', '换版复核引用的旧版档案不存在', 409) from error
    verify(base, archive, seen | {stamp['id']})
    if (base['manifest']['result_sha256'] != stamp.get('base_result_sha256') or
            digest(encode(base['stages'])) != stamp.get('base_result_sha256') or
            any(review['base_manifest'].get(name) != base['manifest'].get(name)
                for name in ('id', 'version', 'kind', 'created_at', 'result_sha256'))):
        raise Rejection('INVALID_EVIDENCE', '换版复核引用的旧版档案不符', 409)
    if decide(base, stages) != review:
        raise Rejection('INVALID_EVIDENCE', '换版复核台账无法按切版映射复算', 409)
