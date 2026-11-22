from app.modules.revision.ledger import REASONS, STATES

HEADERS = {
    'source': ('line', 'cue_id', 'format', 'in', 'out', 'code', 'text'),
    'clock': ('line', 'cue_id', 'in', 'out', 'start', 'end', 'nominal_start', 'code'),
    'edits': ('line', 'cue_id', 'start', 'end', 'cut', 'kind', 'frame_in', 'frame_out'),
    'overlaps': ('frame_in', 'frame_out', 'frames', 'track', 'cues', 'lines', 'code'),
    'balance': ('track', 'original', 'delivered', 'removed', 'pending'),
    'runs': ('id', 'kind', 'base_id', 'version', 'created_at', 'elapsed_us'),
    'revision': ('state', 'cue_id', 'track', 'line', 'base_line', 'text', 'base_frame_in', 'base_frame_out',
                 'frame_in', 'frame_out', 'reasons', 'cuts'),
    'delivery': ('field', 'hash'),
}
LABELS = {'line': '原行', 'cue_id': '字幕号', 'format': '格式', 'in': '原入点', 'out': '原出点', 'code': '原因',
          'text': '字幕文本', 'start': '源入帧', 'end': '源出帧', 'nominal_start': '折算入帧', 'cut': '切段',
          'kind': '分段判定', 'frame_in': '目标入帧', 'frame_out': '目标出帧', 'frames': '重叠帧',
          'track': '轨道', 'cues': '字幕号', 'lines': '原行组', 'original': '原覆盖', 'delivered': '交付覆盖',
          'removed': '剪辑移除', 'pending': '缺段待证', 'id': '归档档号', 'version': '规则版本',
          'created_at': '生成 UTC', 'elapsed_us': '耗时 μs', 'field': '原件', 'hash': 'SHA-256',
          'state': '复核判定', 'base_line': '旧版原行', 'base_frame_in': '旧目标入帧', 'base_frame_out': '旧目标出帧',
          'reasons': '待复核依据', 'cuts': '新版切段', 'base_id': '换版来源'}


def cells(stages, sheet, archive, stamp):
    if sheet == 'runs':
        return archive.inventory()
    if sheet == 'revision':
        return stages.get('revision', {}).get('rows', [])
    if sheet == 'delivery':
        return [dict(field=key, hash=value) for key, value in stamp['input_sha256'].items()] if stamp else []
    view = stages[sheet]
    return view.get('isolated', []) + view.get('copies', []) + view['rows']
