import pytest
from app.digests import digest, encode
from app.material import example
from app.modules.delivery.service import signing
from app.problems import Rejection


def cue(cue_id, text, start, end, track='简中', mode='FRAME'):
    return f'{cue_id},{track},{mode},{start},{end},{text}\n'


def table(*lines):
    return 'cue_id,track,format,in,out,text\n' + ''.join(lines)


def cuts(*rows):
    return 'cut,start,end,target,kind\n' + ''.join(f'{name},{start},{end},{target},{kind}\n'
                                                   for name, start, end, target, kind in rows)


def base_of(client, sample='clean'):
    return client.post('/api/runs', json={'sample': sample}).json


def revise(client, base, cues, cut_table):
    response = client.post(f"/api/runs/{base['id']}/revise", json={'cues': cues, 'cuts': cut_table})
    assert response.status_code == 200, response.json
    return response.json


def ledger(client, result):
    return {row['cue_id']: row for row in client.application.extensions['cut_archive']
            .read(result['id'])['stages']['revision']['rows']}


def clean_cues(first='今天的风很轻', second='他收起地图', third='巷口有人等着', fourth=True):
    cues = [cue('C01', first, 100, 140), cue('C02', second, 200, 250), cue('C03', third, 1000, 1100)]
    if fourth:
        cues.append(cue('C04', 'Someone is waiting', 1000, 1100, track='英语'))
    return table(*cues)


CLEAN_CUTS = example('clean')['cuts']


def test_unchanged_text_and_frames_carries(client):
    base = base_of(client)
    rows = ledger(client, revise(client, base, clean_cues(), CLEAN_CUTS))
    assert {row['state'] for row in rows.values()} == {'carried'}
    assert all(not row['reasons'] and all(row['checks'].values()) for row in rows.values())


def test_new_cut_moves_frames_even_when_text_unchanged(client):
    base = base_of(client)
    moved = cuts(('A', 0, 1000, 0, 'KEEP'), ('B', 1000, 1500, 802, 'KEEP'))
    rows = ledger(client, revise(client, base, clean_cues(), moved))
    assert rows['C03']['state'] == 'pending' and rows['C03']['reasons'] == ['MOVED']
    assert rows['C03']['base_ranges'] == ['801-882'] and rows['C03']['ranges'] == ['802-883']
    assert rows['C01']['state'] == 'carried'


def test_retimed_boundary_keeps_line_identity(client):
    base = base_of(client)
    moved = cuts(('A', 0, 1000, 0, 'KEEP'), ('B', 1000, 1500, 803, 'KEEP'))
    rows = ledger(client, revise(client, base, clean_cues(), moved))
    assert rows['C03']['base_ranges'] == ['801-882'] and rows['C03']['ranges'] == ['803-884']
    assert rows['C03']['line'] == 4 and rows['C03']['base_line'] == 4
    assert rows['C03']['state'] == 'pending' and rows['C03']['reasons'] == ['MOVED']


def test_text_change_needs_review(client):
    base = base_of(client)
    rows = ledger(client, revise(client, base, clean_cues(second='他折起地图'), CLEAN_CUTS))
    assert rows['C02']['state'] == 'pending' and rows['C02']['reasons'] == ['TEXT']
    assert rows['C02']['base_text'] == '他收起地图' and rows['C02']['text'] == '他折起地图'


def test_new_cue_never_carries_old_approval(client):
    base = base_of(client)
    extra = clean_cues() + cue('C99', '新补一句', 300, 330)
    rows = ledger(client, revise(client, base, extra, CLEAN_CUTS))
    assert rows['C99']['state'] == 'pending' and rows['C99']['reasons'] == ['NEW']


def test_same_track_conflict_marks_both_sides(client):
    base = base_of(client)
    clashing = clean_cues() + cue('C99', '抢先一句', 1050, 1080)
    rows = ledger(client, revise(client, base, clashing, CLEAN_CUTS))
    assert rows['C03']['reasons'] == ['CONFLICT'] and rows['C99']['reasons'] == ['NEW', 'CONFLICT']


def test_same_track_new_collision_of_old_rows_needs_review(client):
    base = base_of(client)
    shifted = clean_cues() + cue('C11', '另一个供应稿', 1060, 1090)
    rows = ledger(client, revise(client, base, shifted, CLEAN_CUTS))
    assert rows['C03']['reasons'] == ['CONFLICT']


def test_conflict_already_signed_does_not_reopen(client):
    base = base_of(client)
    existing = clean_cues()
    rows = ledger(client, revise(client, base, existing, CLEAN_CUTS))
    assert all(row['state'] == 'carried' for row in rows.values())


def test_other_track_conflict_does_not_pollute(client):
    base = base_of(client)
    same = clean_cues() + cue('C09', 'Someone else', 1000, 1100, track='英语')
    rows = ledger(client, revise(client, base, same, CLEAN_CUTS))
    assert rows['C03']['state'] == 'carried' and rows['C09']['state'] == 'pending'


def test_isolated_row_is_pending(client):
    base = base_of(client)
    broken = clean_cues(second='')
    rows = ledger(client, revise(client, base, broken, CLEAN_CUTS))
    assert rows['C02']['state'] == 'pending' and 'ISOLATED' in rows['C02']['reasons']


def test_gap_is_pending(client):
    base = base_of(client)
    holes = cuts(('A', 0, 1000, 0, 'KEEP'), ('B', 1000, 1050, 801, 'KEEP'))
    rows = ledger(client, revise(client, base, clean_cues(), holes))
    assert rows['C03']['state'] == 'pending' and 'GAP' in rows['C03']['reasons']


def test_retired_cue_records_old_approval_no_longer_usable(client):
    base = base_of(client)
    rows = ledger(client, revise(client, base, table(cue('C01', '今天的风很轻', 100, 140),
                                                     cue('C02', '他收起地图', 200, 250)), CLEAN_CUTS))
    assert rows['C03']['state'] == 'retired' and rows['C03']['reasons'] == ['RETIRED']
    assert rows['C03']['frame_in'] is None and rows['C03']['base_frame_in'] == 801


def test_revision_chain_only_carries_its_own_approvals(client):
    base = base_of(client)
    first = revise(client, base, clean_cues(second='他折起地图'), CLEAN_CUTS)
    second = revise(client, first, clean_cues(second='他折起地图'), CLEAN_CUTS)
    rows = ledger(client, second)
    assert rows['C02']['state'] == 'pending' and rows['C02']['reasons'] == ['NO_APPROVAL']
    assert rows['C01']['state'] == 'carried' and rows['C03']['state'] == 'carried'


def test_delivery_package_explains_carry_and_review(client):
    base = base_of(client)
    result = revise(client, base, clean_cues(second='他折起地图'), CLEAN_CUTS)
    package = client.get(f"/api/delivery/{result['id']}/export").json['review']
    assert package['base_id'] == base['id'] and package['rules'] == 'carry-identical-delivery/1'
    assert package['counts'] == dict(carried=3, pending=1, retired=0, total=4)
    assert [row['cue_id'] for row in package['carried']] == ['C01', 'C03', 'C04']
    assert [(row['cue_id'], row['reasons']) for row in package['pending']] == [('C02', ['TEXT'])]
    assert package['base_manifest']['id'] == base['id']
    assert package['carried'][0]['checks'] == dict(old_approved=True, text_same=True, frames_same=True)


def test_original_run_has_no_review_package(client):
    assert 'review' not in client.get(f"/api/delivery/{base_of(client)['id']}/export").json


def test_failed_revision_keeps_old_evidence(client):
    base = base_of(client)
    before = client.get(f"/api/runs/{base['id']}").json
    bad = client.post(f"/api/runs/{base['id']}/revise", json={'cues': example('clean')['cues'], 'cuts': ''})
    assert (bad.status_code, bad.json['code']) == (422, 'EMPTY')
    assert client.get('/api/runs').json['count'] == 1
    assert client.get(f"/api/runs/{base['id']}").json['manifest'] == before['manifest']
    assert client.get(f"/api/delivery/{base['id']}/export").status_code == 200


def test_failed_revision_on_broken_cut_table_keeps_old_evidence(client):
    base = base_of(client)
    broken = cuts(('A', 0, 1000, 0, 'KEEP'), ('B', 900, 1100, 900, 'KEEP'))
    bad = client.post(f"/api/runs/{base['id']}/revise", json={'cues': example('clean')['cues'], 'cuts': broken})
    assert (bad.status_code, bad.json['code']) == (422, 'CUT_OVERLAP')
    assert client.get('/api/runs').json['count'] == 1
    assert client.get(f"/api/runs/{base['id']}").status_code == 200


def test_retried_revision_does_not_duplicate_archive(client):
    base = base_of(client)
    first = revise(client, base, clean_cues(), CLEAN_CUTS)
    second = client.post(f"/api/runs/{base['id']}/revise", json={'cues': clean_cues(), 'cuts': CLEAN_CUTS})
    assert second.json['reused'] and second.json['id'] == first['id']
    assert client.get('/api/runs').json['count'] == 2


def test_same_cues_under_new_base_is_a_new_revision(client):
    first = base_of(client)
    second = base_of(client, 'dirty')
    a = revise(client, first, clean_cues(), CLEAN_CUTS)
    b = revise(client, second, clean_cues(), CLEAN_CUTS)
    assert a['id'] != b['id'] and client.get('/api/runs').json['count'] == 4


def test_revise_needs_an_archived_base(client):
    missing = '0' * 64
    outcome = client.post(f'/api/runs/{missing}/revise', json=example('clean'))
    assert (outcome.status_code, outcome.json['code']) == (404, 'NO_RUN')


def test_revision_repeat_stays_a_revision(client):
    base = base_of(client)
    result = revise(client, base, example('clean')['cues'], CLEAN_CUTS)
    repeat = client.post(f"/api/runs/{result['id']}/repeat").json
    assert repeat['reused'] and repeat['id'] == result['id']
    assert repeat['manifest']['kind'] == 'revision' and repeat['manifest']['base_id'] == base['id']


def test_revision_detail_reports_review_counts(client):
    base = base_of(client)
    result = revise(client, base, clean_cues(second='他折起地图'), CLEAN_CUTS)
    detail = client.get(f"/api/runs/{result['id']}").json
    assert detail['review'] == dict(counts=dict(carried=3, pending=1, retired=0, total=4),
                                    rules='carry-identical-delivery/1', base_id=base['id'])


def test_tampered_carry_ledger_is_rejected(client):
    base = base_of(client)
    result = revise(client, base, example('clean')['cues'], CLEAN_CUTS)
    entry = client.application.extensions['cut_archive'].read(result['id'])
    entry['stages']['revision']['rows'][0]['state'] = 'pending'
    with pytest.raises(Rejection, match='证据散列'):
        signing(entry)


def test_carried_row_contradicting_its_checks_is_rejected(client):
    base = base_of(client)
    result = revise(client, base, example('clean')['cues'], CLEAN_CUTS)
    entry = client.application.extensions['cut_archive'].read(result['id'])
    row = next(row for row in entry['stages']['revision']['rows'] if row['state'] == 'carried')
    row['checks']['text_same'] = False
    entry['manifest']['result_sha256'] = digest(encode(entry['stages']))
    with pytest.raises(Rejection, match='换版复核'):
        signing(entry)


def test_revision_sheet_lists_basis(client):
    base = base_of(client)
    result = revise(client, base, clean_cues(second='他折起地图'), CLEAN_CUTS)
    page = client.get(f"/sheet/revision?run={result['id']}").get_data(as_text=True)
    assert '沿用旧审签' in page and '字幕文字改动' in page and '他折起地图' in page


def test_delivery_refuses_when_base_archive_is_gone(client):
    base = base_of(client)
    result = revise(client, base, clean_cues(), CLEAN_CUTS)
    store = client.application.extensions['cut_archive']
    (store.root / f"{base['id']}.json").unlink()
    response = client.get(f"/api/delivery/{result['id']}/export")
    assert (response.status_code, response.json['code']) == (409, 'INVALID_EVIDENCE')


def test_revise_refuses_a_tampered_base(client):
    base = base_of(client)
    store = client.application.extensions['cut_archive']
    entry = store.read(base['id'])
    entry['stages']['balance']['rows'][0]['original'] = '999'
    (store.root / f"{base['id']}.json").write_bytes(encode(entry))
    response = client.post(f"/api/runs/{base['id']}/revise", json={'cues': clean_cues(), 'cuts': CLEAN_CUTS})
    assert (response.status_code, response.json['code']) == (409, 'INVALID_EVIDENCE')
    assert client.get('/api/runs').json['count'] == 1
