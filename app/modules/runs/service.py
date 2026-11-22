from datetime import datetime, timezone
from time import perf_counter_ns
from app.digests import digest, encode, fingerprints
from app.modules.revision.ledger import REVIEW_RULES, decide
from app.pipeline import inspect
from app.problems import Rejection
from app.settings import VERSION

KIND_ORIGINAL = 'original'
KIND_REVISION = 'revision'


def key_for(kind, base_id, material):
    hashes = fingerprints(material)
    if kind == KIND_REVISION:
        identity = [VERSION, KIND_REVISION, REVIEW_RULES, base_id, hashes]
    else:
        identity = [VERSION, hashes]
    return digest(encode(identity)), hashes


def record(store, material, base=None, kind=None):
    kind = kind or (KIND_REVISION if base else KIND_ORIGINAL)
    if kind == KIND_REVISION and base is None:
        raise Rejection('NO_BASE', '换版归档缺少旧版档案', 404)
    if kind == KIND_ORIGINAL and base is not None:
        raise Rejection('BASE_KIND', '旧版档案不能作为首版归档', 422)
    return build(store, material, kind=kind, base=base)


def build(store, material, kind=KIND_ORIGINAL, base=None):
    start = perf_counter_ns()
    base_id = base['manifest']['id'] if base else None
    key, hashes = key_for(kind, base_id, material)
    stages = inspect(material)
    if kind == KIND_REVISION:
        stages['revision'] = decide(base, stages)
    result_hash = digest(encode(stages))
    manifest = dict(id=key, version=VERSION, kind=kind, input_sha256=hashes, result_sha256=result_hash,
                    created_at=datetime.now(timezone.utc).isoformat(), elapsed_us=(perf_counter_ns() - start) // 1000)
    if base:
        manifest.update(base_id=base_id, base_result_sha256=base['manifest']['result_sha256'],
                        review_rules=REVIEW_RULES)
    actual, reused = store.publish(key, dict(manifest=manifest, original=material, stages=stages))
    if actual['manifest']['result_sha256'] != result_hash or digest(encode(actual['stages'])) != result_hash:
        raise Rejection('DRIFT', '复算与已归档结果不一致', 409)
    if actual['manifest'].get('base_id') != base_id:
        raise Rejection('DRIFT', '换版关系与已归档结果不一致', 409)
    return dict(summary(actual), reused=reused)


def summary(record):
    stages = record['stages']
    result = dict(id=record['manifest']['id'], manifest=record['manifest'],
                  counts=stages['balance']['counts'])
    if 'revision' in stages:
        result['review'] = dict(counts=stages['revision']['counts'],
                                rules=stages['revision']['rules'],
                                base_id=stages['revision']['base_id'])
    return result
