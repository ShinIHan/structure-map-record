# structure-map forward record (pre-registered, append-only, hash-chained)

*English first, 한국어는 아래.*

This repository is the public, tamper-evident copy of a **pre-registered forward record**: the predictions of a
structure-map model (Elliott-style wave counts and chart structures: support/resistance zones, fair-value gaps, wedges,
CME weekend gaps) for **BTC/ETH/SOL USDT perpetuals on Gate.io** (CME rows use Binance as the population). A prediction
row is appended **once per closed bar, when the bar closes**, and is never edited or deleted afterwards. The model code
stays private; what is public is the record of what it said, when, and the frozen rules by which it will be judged.

It is **not trading advice**. Nothing here is a recommendation to buy or sell anything.

## What is in the repository

| path | content |
|---|---|
| `docs/structure_wave_forward_prereg.md`, `docs/structure_chart_forward_prereg.md` | the frozen pre-registration documents (hypotheses, definitions, scoring rules, kill conditions). Byte-exact copies of the private originals. |
| `docs/*.sha256` | sidecars: line 1 = exactly `<sha256 in lowercase hex>  docs/<same name>.md` (two spaces) of the frozen document; later lines = **append-only** operational notes (deploy markers, cell T0 values, decisions). |
| `data/forward/wave_log_YYYY-MM.jsonl` | one JSON object per wave prediction row, one file per UTC month of `logged_at`, ordered by `id` inside a file, keys in `manifest.columns.wave_log` order |
| `data/forward/chart_log_YYYY-MM.jsonl` | one JSON object per chart-structure event row (zone / fvg / wedge / cme), same layout |
| `data/forward/wave_log_quarantine.jsonl` | rows of `wave_log` excluded from scoring by the 2026-10-24 integrity decision (see below); append-only |
| `data/forward/meta.json` | write-once keys: `wave_T0`, `chart_T0_<cell>`, deploy markers, loader/job live timestamps |
| `data/forward/schema.sql` | the `CREATE TABLE` text of the four tables as found in the source database |
| `data/forward/manifest.json` | the file list of the snapshot with sha256 / byte length / row count of every data file, row counts, `max_id`, column lists, `prev_manifest_sha256` (hash chain), late-row counters, schema-change notes, `generated_at_utc` |
| `data/forward/anchors/<generated_at>.manifest.json` + `.ots` | byte copies of published manifests with their OpenTimestamps proofs (Bitcoin anchors). `.ots` files are the only files that legitimately change (proof upgrades). |
| `verify_record.py` | stdlib-only verifier (no network): working tree, full history, row lookup |
| `allowed_signers` | the SSH public keys that sign the commits of this repository |
| `.gitattributes` | `* -text` so no clone ever rewrites line endings (hashes stay byte-stable on every OS) |
| `.gitignore` | keeps temp files out of the repository |
| `LICENSE` | the CC BY 4.0 legal code, see **Licence** below |

Snapshots are published by an automated job (daily at 23:50 KST = 14:50 UTC, plus a catch-up run after a reboot). Each
snapshot exports **every** row of the source database, so a missed day loses nothing; it only widens the gap between two
anchors. Only `manifest.json` lists the files of a snapshot; a file of an earlier month changes only when a late row
lands in it.

## How the record protects itself

1. **Hash chain.** Every `manifest.json` carries `prev_manifest_sha256` = sha256 of the previous published manifest
   (`null` for the first snapshot). Rewriting any old snapshot breaks every later link.
2. **Append-only check (verifiable by anyone).** Between any two consecutive snapshots: every earlier row must still exist
   with identical cells (compared cell by cell on the earlier snapshot's column list), `wave_log`/`chart_log` ids are
   `AUTOINCREMENT` so every new id must exceed the previous `max_id`, `meta` keys are write-once, quarantine rows are only
   appended. Appending a column is allowed and reported; removing or renaming a column or a table is a failure.
   One row per key: `id` / `wave_id` is the PRIMARY KEY of every row table, `wave_log_quarantine` included and across
   monthly files, so a snapshot that lists a key twice fails verification, and so does a row filed under a month other than
   the one of its `logged_at`. Every row line, `meta.json` and `manifest.json` has exactly one byte form (the exporter's
   `json.dumps` output, sorted keys), so a duplicated JSON key can never show one value to one reader and another value to another.
3. **External time anchors.** `anchors/*.manifest.json.ots` are OpenTimestamps proofs that the manifest bytes existed no
   later than a Bitcoin block time. Because each manifest chains to its predecessor, the **latest complete anchor
   transitively covers every earlier snapshot**; a missing or still-pending anchor on some day is not fatal.
4. **Frozen rules.** The scoring rules were frozen in the two `docs/*.md` files; their sha256 are the first tokens of the
   sidecars. The sync job refuses to publish if a frozen document's bytes no longer match its sidecar, or if a sidecar's
   earlier lines changed.
5. **Signed commits.** Every commit is SSH-signed with a key listed in `allowed_signers`, from the first commit on.

## Verify it yourself

Clone **without line-ending conversion** (the repository also carries `.gitattributes` for this, but be explicit):

```
git -c core.autocrlf=false clone https://github.com/ShinIHan/structure-map-record.git
cd structure-map-record
python verify_record.py              # working tree: every file hash vs manifest, frozen docs vs sidecars
python verify_record.py --history    # every commit: chain, append-only, meta write-once, columns, anchors, sidecars (not on a shallow clone)
python verify_record.py --find-row wave_log 1234   # first commit (and anchor) that contains a row
git -c gpg.ssh.allowedSignersFile=allowed_signers verify-commit HEAD   # the commit signature (git 2.34 or later)
```

Manual checks, if you prefer not to run Python:

```
sha256sum data/forward/wave_log_2026-11.jsonl   # compare with manifest.json -> files.wave_log_2026-11.jsonl.sha256
git log -2 --format=%H -- data/forward/manifest.json      # the last two snapshots, newest first
git show <second hash>:data/forward/manifest.json | sha256sum   # must equal the newest manifest's prev_manifest_sha256
git show HEAD:docs/structure_wave_forward_prereg.md | sha256sum   # must equal line 1 of docs/structure_wave_forward_prereg.sha256
git log --format='%H %cI %s' -- data/forward/manifest.json       # one commit per snapshot
```

OpenTimestamps (needs the `ots` client, https://opentimestamps.org, and a Bitcoin node or a public block explorer):

```
ots verify data/forward/anchors/20261104T145003Z.manifest.json.ots      # verifies the sibling .manifest.json
git show <commit>:data/forward/anchors/<x>.manifest.json | sha256sum    # same bytes as a published manifest
```

If the `.ots` file is still "pending" the calendar has not yet aggregated it into Bitcoin; run `ots upgrade` later or
rely on a later anchor (the chain covers earlier snapshots).

### Reading the data

* Each line of a `.jsonl` file is one row; keys follow `manifest.columns[<table>]` (the source table's column order).
  Lines are split on LF only (`\n`); strings may contain any Unicode. `grid_json`, `alternates_json` and `payload_json`
  are stored as **strings** exactly as the server wrote them (parse them yourself if you need the internals).
* A table is the union of its monthly files. A row belongs to the UTC month of its `logged_at`.
* Timestamps (`bar_ts`, `t0_bar_ts`, `logged_at`, `quarantined_at`, meta values) are Unix seconds, UTC.
* **Id gaps are normal, not deletions.** The source tables are `INTEGER PRIMARY KEY AUTOINCREMENT` and the recorder issues
  `INSERT OR IGNORE` for every candidate on every pass; ignored duplicates still advance the sequence, so ids jump and
  `max_id` is larger than the row count. The verifier never assumes contiguity; it checks that no earlier row disappears
  and that new ids are above the previous maximum.
* **Quarantine.** `wave_log_quarantine` lists wave rows written before the fixed data loader went live
  (2026-10-24, incident I-2026-10-24-01). Those rows stay in `wave_log` untouched (first-log-only); the quarantine table
  only appends; un-quarantining a row would be a rewrite and is therefore impossible without breaking the record. The
  scoring excludes quarantined rows (sidecar decision of 2026-10-24). Any future correction is likewise an **appended**
  erratum/quarantine row referencing the original id, never an edit.
* `meta` is write-once: `wave_T0`, `chart_T0_<cell>` and the deploy markers are set once and never change.
* `manifest.late_rows[<table>]` counts rows that are new in a snapshot but carry a `logged_at` older than the previous
  snapshot's `generated_at_utc` minus 300 s (also flagged in the commit subject as `late N`). `late_rows` > 0 means a
  row reached the record late or carries an unusual time; it is a flag for you to judge, not a verdict.
* `manifest.schema_change` reports columns present in the source database but not published (`unexported_columns`),
  tables not published, or columns appended since the previous snapshot.

## Honest limits — what a third party can and cannot verify

**Can be verified by anyone from this repository alone**

* every file's bytes against its manifest hash, and the manifest chain across the whole history;
* that no published row was ever changed or removed after it first appeared (append-only across all commits);
* that the frozen documents' bytes match the hashes in their sidecars, and that sidecars were only appended to;
* that manifests existed no later than the Bitcoin block times proven by the `.ots` anchors.

**Cannot be verified from this repository**

* **Rows before the first anchored snapshot are owner-attested only.** The first snapshot (first commit of this record,
  2026-11) contains every row logged since the record started (2026-10-21T08:21:44Z for `wave_log`, 2026-10-24T12:00:10Z
  for `chart_log`). For those rows the only evidence that they were written at the times they claim is the owner's word
  plus their internal consistency; the first manifest's `max_id` marks the boundary (`id <= first max_id` = pre-anchor) and
  its `row_counts` gives the numbers. You can cross-check their `close` values against the exchanges' public candle
  history, which the owner does not control.
* The freeze date of the pre-registration documents ("frozen 2026-10-21 before T0, committed in 3abe68a") refers to a
  commit of the **private** repository and is owner-asserted until the first OTS anchor of this repository.
* `logged_at` and `bar_ts` are **self-reported** by the recorder. An anchor proves only that a row existed **no later
  than** the anchor time, never that it existed before an outcome was knowable.
* **What the timing proves.** An OpenTimestamps anchor is only as precise as Bitcoin block time (about 2 h either way), so
  no cadence can make it prove anything about a single hour. With today's daily snapshot, measured on the rows up to
  2026-11-06:

  | cell timeframe | published before the end of the scoring window | published before the first possible outcome |
  |---|---|---|
  | 1d | 100% | 100% |
  | 4h | 100% | 16% of wave rows, 5% of zone rows |
  | 1h | 100% | 0-5% |

  So the anchors show that the judged 4h cells existed before their scoring window closed, not before the first bar that
  could have decided them. The owner plans to raise the cadence to every 4 hours at minute 10 UTC within six weeks of the
  first snapshot, which moves the 4h row to about 98% of wave rows and 100% of zone rows when the anchor lands within
  3 hours. The cadence is only ever raised, and the spacing of `generated_at_utc` shows what actually happened.
* **Git dates are author-set** and GitHub's push times are weak, short-lived evidence (the Events API keeps 30 days; a
  force-push would erase them). The OTS anchors are the durable evidence; commit dates are a convenience.
* **Signatures and branch rules guard against accidents, not against the owner.** A repository ruleset blocks force pushes,
  branch deletion, non-linear history and unsigned commits, with nobody on the bypass list, but the owner holds the
  signing key and can edit the ruleset. A signature shows who published a commit. A later rewrite of history stays visible
  to anyone holding a clone, and the chain + anchors are what you should trust, not the Git metadata.
* The owner controls the database, the exporter and this repository. The model code is private. The record shows what
  was predicted and when it was published, nothing more.
* The daily cadence is **best-effort**: the job runs on a home PC as an interactive scheduled task; after an unattended
  reboot nothing runs until the next logon, so gaps between commits follow reboots. Every snapshot is complete, so gaps
  never lose rows, they only widen the interval between anchors.
* If the source database is ever restored from an older backup, the verifier will (correctly) report deleted rows and the
  publishing job stops; the published JSONL files are then the authority and the missing rows must be re-imported from
  them — the baseline must never be regenerated.
* Data come from public exchange APIs (Gate.io, Binance) and may contain exchange-side errors.
* `wave_log` grows by about 93 rows x 4.0 KB a day and `chart_log` by about 111 rows x 2.0 KB a day (27 to 233 rows, it
  depends on the market), 0.59 MB a day together as measured on 2026-11-06, so one month adds about 18 MB. GitHub refuses
  blobs over 100 MB; the publishing job withholds a public commit above 95 MiB per file and warns from half of that.

## Licence

Copyright (c) 2026 ShinIHan.

| path | licence |
|---|---|
| `data/forward/**`, `docs/**`, `README.md` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (SPDX `CC-BY-4.0`), full text in `LICENSE` |
| `verify_record.py` | MIT (SPDX `MIT`), notice in the file header |

Attribution when you reuse the data: *structure-map forward record by ShinIHan,
https://github.com/ShinIHan/structure-map-record, CC BY 4.0*. Say so if you changed it, and do not imply that the owner
endorses your use. Prices and other values taken from exchange APIs are facts reproduced for verification: no rights in
them are claimed, and the licence covers only the rights the owner holds.

---

# 구조 지도 전방 기록 (사전등록 · 추가만 가능 · 해시 체인)

이 저장소는 **사전등록된 전방 기록**의 공개 사본입니다. 구조 지도 모델(엘리엇식 파동 카운트와 차트 구조: 지지·저항 층, FVG,
쐐기, CME 주말 갭)이 **Gate.io 의 BTC/ETH/SOL USDT 무기한**에 대해 낸 예측을, 봉이 닫힐 때 한 행씩 덧붙이고 그 뒤로는
절대 고치거나 지우지 않습니다(CME 행은 바이낸스 모집단). 모델 코드는 비공개이고, 공개되는 것은 "무엇을 언제 말했는가"의
기록과 그것을 판정할 동결 규칙입니다. **투자 조언이 아닙니다.**

## 파일

* `docs/*.md` — 동결 사전등록 문서(가설·정의·판정 규칙·중단 조건), 비공개 원본과 바이트 동일. `docs/*.sha256` 첫 줄은 정확히
  `<소문자 sha256>  docs/<같은 이름>.md`(공백 두 칸), 그 아래 줄은 **덧붙이기만 하는** 운영 메모(배포 마커, 셀 T0, 결정 기록).
  행 한 줄·`meta.json`·`manifest.json` 은 바이트 모양이 하나뿐입니다(내보내기의 `json.dumps` 출력, 키 정렬). 같은 키를 두 번 써서
  읽는 프로그램마다 다른 값을 보게 만들 수 없습니다.
* `data/forward/wave_log_YYYY-MM.jsonl`, `chart_log_YYYY-MM.jsonl` — `logged_at` 의 UTC 달마다 한 파일, 한 줄 = 한 행(JSON),
  파일 안에서 id 순, 키 순서는 `manifest.columns`. `wave_log_quarantine.jsonl` 은 한 파일. `meta.json` 은 write-once 키.
  `schema.sql` 은 원본 표의 CREATE 문. `manifest.json` 은 스냅샷의 파일 목록과 각 파일의 sha256·바이트·행 수, `max_id`·열 목록·
  `prev_manifest_sha256`(체인)·지연 행·스키마 변화·`generated_at_utc`.
* `data/forward/anchors/<시각>.manifest.json(.ots)` — 공개된 manifest 의 바이트 복사본과 OpenTimestamps(비트코인) 증명.
  `.ots` 만이 정당하게 바뀌는 파일입니다(증명 업그레이드).
* `verify_record.py` — 표준 라이브러리만 쓰는 검증기(네트워크 없음). `allowed_signers` — 커밋 서명에 쓰는 SSH 공개키.

## 검증

```
git -c core.autocrlf=false clone https://github.com/ShinIHan/structure-map-record.git
cd structure-map-record
python verify_record.py              # 작업 트리: 파일 해시 vs manifest, 동결 문서 vs 사이드카
python verify_record.py --history    # 모든 커밋: 체인·append-only·meta write-once·열 변화·앵커·사이드카
python verify_record.py --find-row wave_log 1234
git -c gpg.ssh.allowedSignersFile=allowed_signers verify-commit HEAD   # 커밋 서명(git 2.34 이상)
```

## 정직한 한계

* 첫 앵커 이전 행(첫 manifest 의 `max_id` 이하, 각각 2026-10-21T08:21:44Z·2026-10-24T12:00:10Z 부터, 행 수는 첫 manifest 의
  `row_counts`)은 **소유자 증언(owner-attested)** 입니다. 거래소 공개 캔들로 종가를 대조할 수는 있습니다.
* 동결일 "2026-10-21, 커밋 3abe68a" 는 비공개 저장소의 커밋이며 이 저장소의 첫 OTS 앵커 전까지는 소유자 주장입니다.
* `logged_at`·`bar_ts` 는 기록기가 스스로 적은 값입니다. 앵커는 "그 시각 **이전에** 존재했다" 만 증명합니다.
* OpenTimestamps 앵커의 정밀도는 비트코인 블록 시각(앞뒤 약 2시간)까지라, 주기를 아무리 올려도 한 시간 단위는 증명하지 못합니다.
  지금의 하루 1회 기준으로, 2026-11-06 까지의 행을 측정한 결과입니다.

  | 시간대 | 판정 구간이 끝나기 전 공개 | 가장 이른 결과가 가능해지기 전 공개 |
  |---|---|---|
  | 1d | 100% | 100% |
  | 4h | 100% | wave 행 16%, zone 행 5% |
  | 1h | 100% | 0~5% |

  즉 앵커는 판정 대상 4h 칸이 판정 구간이 닫히기 전에 있었음을 보여 주지만, 결과를 결정할 수 있는 첫 봉 이전에 있었음을 보여
  주지는 못합니다. 소유자는 첫 스냅샷 뒤 6주 안에 4시간마다 10분(UTC)으로 주기를 올릴 계획이며, 앵커가 3시간 안에 찍히면 위 4h
  줄은 wave 약 98%·zone 100% 가 됩니다. 주기는 올리기만 하고, 실제 간격은 `generated_at_utc` 에 그대로 드러납니다.
* git 커밋 시각은 작성자가 정하는 값이고 GitHub push 시각은 30일만 남는 약한 증거입니다. 내구성 있는 증거는 OTS 앵커입니다.
  최신 완료 앵커가 체인을 통해 이전 스냅샷 전부를 덮으므로 중간 앵커가 빠져도 치명적이지 않습니다.
* 서명과 브랜치 규칙은 사고를 막는 장치이지 소유자를 막는 장치가 아닙니다. 규칙셋이 강제 푸시·브랜치 삭제·비선형 이력·서명 없는
  커밋을 막고 우회 목록은 비어 있지만, 서명 키와 규칙셋은 소유자가 쥐고 있습니다. 이력을 나중에 바꾸면 클론을 가진 누구에게나
  드러나며, 믿을 것은 git 메타데이터가 아니라 체인과 앵커입니다.
* id 공백은 삭제가 아닙니다(AUTOINCREMENT + INSERT OR IGNORE). 격리 행은 wave_log 에 그대로 남고 격리표는 덧붙이기만 하며,
  격리 해제는 재작성이라 불가능합니다. 정정은 언제나 원본 id 를 가리키는 **추가 행**입니다. 키(id·wave_id)는 표마다, 달 파일을
  통틀어 한 행뿐이라 같은 키가 두 번 든 스냅샷이나 `logged_at` 과 다른 달 파일에 든 행은 검증에 실패합니다.
* 일일 주기는 **최선 노력(best-effort)** 입니다: 가정용 PC 의 대화형 예약 작업이라 무인 재부팅 뒤에는 로그온까지 쉬고, 그 공백은
  커밋 간격으로 드러납니다. 스냅샷은 전체 내보내기라 행이 사라지지는 않습니다.
* 원본 DB 를 옛 백업으로 복원하면 검증기가 삭제를 보고하고 공개가 멈춥니다. 그때는 공개된 JSONL 이 정본이며 거기서 빠진 행을
  다시 넣어야 하고, 기준선을 다시 만드는 일은 금지입니다.
* 소유자가 DB·내보내기·저장소를 모두 통제합니다. 모델 코드는 비공개입니다. 데이터는 거래소 공개 API 에서 왔습니다.

## 라이선스

Copyright (c) 2026 ShinIHan.

| 경로 | 라이선스 |
|---|---|
| `data/forward/**`, `docs/**`, `README.md` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode.ko) (SPDX `CC-BY-4.0`), 전문은 `LICENSE`(영문이 정본) |
| `verify_record.py` | MIT (SPDX `MIT`), 파일 머리말의 고지 |

데이터를 재사용할 때 표기: *structure-map forward record by ShinIHan, https://github.com/ShinIHan/structure-map-record, CC BY 4.0*.
변경했다면 그 사실을 밝히고, 소유자가 그 사용을 보증하는 것처럼 표시하지 마세요. 거래소 API 에서 온 가격 등의 값은 검증을 위해
옮긴 사실이며 그에 대한 권리를 주장하지 않습니다. 라이선스는 소유자가 가진 권리에만 적용됩니다.
