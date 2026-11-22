# 深度登记 字幕交付校对册

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 字幕文件采信 | 核对逐行隔离与重复字幕 | `/sheet/source` `/api/check/source` | `app/modules/source/service.py` | `tests/test_source.py` |
| M2 帧率与丢帧约束 | 复查非法标签与精确换算 | `/sheet/clock` `/api/check/clock` | `app/modules/clock/timecode.py` | `tests/test_clock.py` |
| M3 切版段映射 | 按切版重建目标帧 | `/` `/api/check/edits` | `app/modules/edits/contract.py` `app/modules/edits/mapping.py` | `tests/test_edits.py` |
| M4 字幕冲突定位 | 定位同轨重叠帧与原行组 | `/sheet/overlaps` `/api/check/overlaps` | `app/modules/overlaps/service.py` | `tests/test_overlaps.py` |
| M5 时长与丢段对账 | 查看并集覆盖守恒 | `/sheet/balance` `/api/check/balance` | `app/modules/balance/service.py` | `tests/test_balance.py` |
| M6 批次留档复跑 | 保存原件并逐值复算 | `/sheet/runs` `POST /api/runs` | `app/modules/runs/files.py` `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 换版复核台账 | 按切版映射与同轨冲突判定旧审签沿用范围 | `/sheet/revision` `POST /api/runs/<id>/revise` | `app/modules/revision/ledger.py` `app/modules/revision/service.py` | `tests/test_revision.py` |
| M8 交付证据签发 | 下载经散列核验的交付证据 | `/sheet/delivery` `/api/delivery/<key>/export` | `app/modules/delivery/checks.py` | `tests/test_delivery.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-02 | 脏字幕首列 BOM | 首列无效 | 去首 BOM | `app/modules/source/reader.py` | `tests/test_source.py::test_bom_and_alias` |
| TRAP-04 | 脏字幕重复表头 | 当成字幕计算 | 单列分段 | `app/modules/source/reader.py` | `tests/test_source.py::test_repeated_header` |
| TRAP-05 | C112 多余列 | 文本错位 | 保留整行隔离 | `app/modules/source/reader.py` | `tests/test_source.py::test_width_and_missing` |
| TRAP-07 | C110 时码 N/A | 当成零帧 | 隔离必填空值 | `app/modules/source/service.py` | `tests/test_source.py::test_width_and_missing` |
| TRAP-09 | 9007199254740993 | 浏览器数值吞位 | 字符串保形 | `app/modules/source/service.py` | `tests/test_source.py::test_string_identity` |
| TRAP-10 | C104 使用分数帧率 | 假设 30 或先舍入 | 保留端点有理数至最后 | `app/modules/clock/timecode.py` | `tests/test_clock.py::test_exact_rate` |
| TRAP-14 | C111 内容相撞 | 后稿静默覆盖 | 同号矛盾整组隔离 | `app/modules/source/service.py` | `tests/test_source.py::test_conflicting_revision` |
| TRAP-17 | `legacy_id` 旧表头 | 硬读当前字段失败 | 按列别名迁移 | `app/modules/source/service.py` | `tests/test_source.py::test_bom_and_alias` |
| TRAP-23 | C115 与 C116 首尾相接 | 共同边界算重叠 | 半开区间扫线 | `app/modules/overlaps/sweep.py` | `tests/test_overlaps.py::test_touch_is_not_overlap` |
| TRAP-27 | 切段改号但字幕文字不变 | 按字幕文字一律沿用旧审签 | 比对交付目标帧区间，移动即待复核 | `app/modules/revision/ledger.py` | `tests/test_revision.py::test_new_cut_moves_frames_even_when_text_unchanged` |
| TRAP-28 | 移帧后与同轨旧字幕相交 | 只看单行是否移动 | 新旧冲突集合取差，卷进变化的双方都待复核 | `app/modules/revision/ledger.py` | `tests/test_revision.py::test_same_track_conflict_marks_both_sides` |
| TRAP-29 | 换版重试或并发提交同一版 | 每次新增归档、旧证据被覆盖 | 档号含旧版散列与复核规则，写入原子判重 | `app/modules/runs/service.py` `app/modules/runs/files.py` | `tests/test_revision.py::test_retried_revision_does_not_duplicate_archive` |
| TRAP-30 | 换版中途切版失败 | 先删旧档再算新版 | 先算后写，失败不触碰旧版 | `app/modules/runs/service.py` | `tests/test_revision.py::test_failed_revision_keeps_old_evidence` |

## 守恒与范围

脏样例 1140 源帧 = 740 交付 + 200 移除 + 200 待证。65 个重叠目标帧独立记录，5 条隔离记录无法量化。原件为带格式列的供应商抽取 CSV，DF 参数固定为 29.97，目标固定 24 fps。

换版复核对每版字幕（轨道 + 字幕号）给出 `carried` / `pending` / `retired`：只有旧版已签发、文字一致、交付目标帧区间未动、且未卷进新版新增同轨冲突的行沿用旧审签；新字幕、任一项变化、缺段、隔离和退出的行都进待复核并附依据码。复核台账随归档落盘，交付证据包同时给出 `carried` 与 `pending` 明细；签发时按归档旧版复算整本台账，旧版被改动即拒绝。
