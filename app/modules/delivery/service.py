from .checks import verify

CODES = {'MISSING': '必填字段缺失', 'WIDTH': '列数不符', 'CUE_CONFLICT': '同轨同号内容冲突',
         'CUE_COPY': '相同字幕副本', 'TIME_LABEL': '时码格式无效', 'DROPPED_LABEL': '该帧号已跳过',
         'TIME_ORDER': '出点不晚于入点', 'OVERLAP': '同轨目标帧相交', 'GAP': '缺少切版记录',
         'NEW': '新版新增字幕', 'NO_APPROVAL': '旧版无可用审签', 'TEXT': '字幕文字改动',
         'MOVED': '交付目标帧移动', 'NOT_DELIVERED': '没有交付帧', 'CONFLICT': '同轨冲突变化',
         'ISOLATED': '新版该行被隔离', 'RETIRED': '旧版字幕已退出', 'BASE_DRIFT': '旧版审签已变动'}


def review_package(record):
    stages = record['stages']
    if 'revision' not in stages:
        return None
    review = stages['revision']
    pick = lambda state: [row for row in review['rows'] if row['state'] == state]
    return dict(rules=review['rules'], base_id=review['base_id'],
                base_manifest={name: review['base_manifest'].get(name) for name in
                               ('id', 'version', 'created_at', 'result_sha256')},
                counts=review['counts'],
                carried=pick('carried'), pending=pick('pending'), retired=pick('retired'))


def signing(record, archive=None):
    package = dict(verified=True, certificate=verify(record, archive), **record, reason_codes=CODES)
    review = review_package(record)
    if review is not None:
        package['review'] = review
    return package
