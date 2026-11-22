from collections import defaultdict
from itertools import combinations

REVIEW_RULES = 'carry-identical-delivery/1'
STATES = {'carried': '沿用旧审签', 'pending': '待复核', 'retired': '旧审签退出'}
REASONS = {
    'NEW': '新版新增字幕',
    'NO_APPROVAL': '旧版无可用审签',
    'TEXT': '字幕文字改动',
    'MOVED': '交付目标帧移动',
    'NOT_DELIVERED': '没有交付帧',
    'GAP': '缺少切版记录',
    'CONFLICT': '同轨冲突变化',
    'ISOLATED': '新版该行被隔离',
    'RETIRED': '旧版字幕已退出',
}
REASON_ORDER = ('NEW', 'NO_APPROVAL', 'TEXT', 'MOVED', 'NOT_DELIVERED', 'GAP', 'CONFLICT', 'ISOLATED', 'RETIRED')


def identity(row):
    return (row['track'], row['cue_id'])


def split(stages):
    sources = {identity(row): row for row in stages['source']['rows']}
    isolated = defaultdict(list)
    for area in ('source', 'clock'):
        for row in stages[area].get('isolated', []):
            if row.get('cue_id') and row.get('track'):
                isolated[identity(row)].append(row)
    delivered, gaps = defaultdict(list), defaultdict(list)
    for fragment in stages['edits']['rows']:
        if fragment['kind'] == 'KEEP':
            delivered[identity(fragment)].append(fragment)
        elif fragment['kind'] == 'GAP':
            gaps[identity(fragment)].append(fragment)
    return sources, isolated, delivered, gaps


def approved(base, base_delivered):
    """旧版真正签过字的字幕：首版即全部交付行；换版档案只取沿用行。"""
    if base['manifest'].get('kind') != 'revision':
        return set(base_delivered)
    carried = {identity(row) for row in base['stages'].get('revision', {}).get('rows', [])
               if row.get('state') == 'carried'}
    return set(base_delivered) & carried


def merge(intervals):
    result = []
    for left, right in sorted(intervals):
        if left >= right:
            continue
        if result and left <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], right))
        else:
            result.append((left, right))
    return result


def ranges(fragments):
    return merge((int(row['frame_in']), int(row['frame_out'])) for row in fragments)


def extent(intervals):
    return (intervals[0][0], intervals[-1][1]) if intervals else (None, None)


def labels(fragments):
    return sorted({row['cut'] for row in fragments if row.get('cut')})


def conflict_signatures(delivered):
    hits = defaultdict(list)
    per_track = defaultdict(list)
    for (track, cue), fragments in delivered.items():
        per_track[track].extend((cue, int(row['frame_in']), int(row['frame_out'])) for row in fragments)
    for track, items in per_track.items():
        for (left_cue, left_in, left_out), (right_cue, right_in, right_out) in combinations(sorted(items), 2):
            if left_cue == right_cue:
                continue
            left, right = max(left_in, right_in), min(left_out, right_out)
            if left < right:
                first, second = sorted((left_cue, right_cue))
                hits[(track, first, second)].append((left, right))
    return {(track, first, second, left, right)
            for (track, first, second), intervals in hits.items()
            for left, right in merge(intervals)}


def show(intervals):
    return [f'{left}-{right}' for left, right in intervals]


def decide(base, stages):
    base_sources, base_isolated, base_delivered, _ = split(base['stages'])
    new_sources, new_isolated, new_delivered, new_gaps = split(stages)
    signed = approved(base, base_delivered)
    added = conflict_signatures(new_delivered) - conflict_signatures(base_delivered)
    clashes = set()
    for track, first, second, _, _ in added:
        clashes.update({(track, first), (track, second)})

    rows = []
    for key in sorted(set(new_sources) | set(new_isolated) | set(base_sources)):
        source = new_sources.get(key) or (new_isolated[key][0] if key in new_isolated else None)
        old = base_sources.get(key)
        if source is None and key not in signed:
            continue  # 旧版本就没有可用审签、新版也已退出，不产生复核行
        old_fragments, new_fragments = base_delivered.get(key, []), new_delivered.get(key, [])
        reasons = []
        if source is None:
            reasons.append('RETIRED')
        elif old is None:
            reasons.append('NO_APPROVAL' if key in base_isolated else 'NEW')
        elif key not in signed:
            reasons.append('NO_APPROVAL')
        else:
            if old['text'] != source['text']:
                reasons.append('TEXT')
            if ranges(old_fragments) != ranges(new_fragments):
                reasons.append('MOVED')
        if source is not None:
            if key in new_isolated:
                reasons.append('ISOLATED')
            else:
                if not new_fragments:
                    reasons.append('NOT_DELIVERED')
                if new_gaps.get(key):
                    reasons.append('GAP')
            if key in clashes:
                reasons.append('CONFLICT')
        rows.append(line(key, source, old, old_fragments, new_fragments, reasons, key in signed))

    for row in rows:
        row['reasons'] = sorted(set(row['reasons']), key=REASON_ORDER.index)
        if row['source_gone']:
            row['state'] = 'retired'
        else:
            row['state'] = 'carried' if not row['reasons'] else 'pending'
    rows.sort(key=lambda row: (row['track'], row['cue_id'], row['state']))
    counts = {name: sum(row['state'] == name for row in rows) for name in STATES}
    counts['total'] = len(rows)
    return dict(rules=REVIEW_RULES, base_id=base['manifest']['id'],
                base_manifest={name: base['manifest'].get(name) for name in
                               ('id', 'version', 'kind', 'created_at', 'result_sha256')},
                counts=counts, rows=rows)


def line(key, source, old, old_fragments, new_fragments, reasons, signed):
    track, cue_id = key
    old_ranges, new_ranges = ranges(old_fragments), ranges(new_fragments)
    old_in, old_out = extent(old_ranges)
    new_in, new_out = extent(new_ranges)
    checks = dict(old_approved=signed, text_same=bool(old) and bool(source) and old['text'] == source['text'],
                  frames_same=bool(old) and old_ranges == new_ranges)
    return dict(state=None, source_gone=source is None, reasons=reasons, checks=checks,
                cue_id=cue_id, track=track,
                line=source['line'] if source else None, base_line=old['line'] if old else None,
                text=source['text'] if source else (old['text'] if old else None),
                base_text=old['text'] if old else None,
                base_frame_in=old_in, base_frame_out=old_out, frame_in=new_in, frame_out=new_out,
                base_ranges=show(old_ranges), ranges=show(new_ranges),
                base_cuts=labels(old_fragments), cuts=labels(new_fragments))
