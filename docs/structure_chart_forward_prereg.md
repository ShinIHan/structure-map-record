# 사전등록: 차트 구조물 전방(forward) 검증 — structure_chart_fwd_v1 (지지·저항층 · FVG · 'CME 주말창' · 쐐기/삼각형)

**동결 2026-10-21 (T0 전 동결).** 동결 뒤 무수정. sha256 은 커밋 메시지와 사이드카 `docs/structure_chart_forward_prereg.sha256` 에 기록한다
(문서 안에 자기 해시를 넣지 않는다). 변경이 필요하면 '중단(abandoned)' 기록 + 새 family 로 새 사전등록.

- family: `structure_chart_fwd_v1` (API `forward_test.chart.family`) · 상수 버전 **`structure_chart_v1`**(FVG·CME·패턴) + `structure_v1`(피벗·층·B1 도달 엔진).
  사양: `docs/structure_map_spec_v2.md` §2 Z1·G1·G2·W1, §5 마지막 문단.
- T0: 미기입 — 배포 시 `structure.db` `meta` 에 기록. 층(P0)과 FVG·CME·패턴(P1)은 배포 시점이 다를 수 있으므로 **셀별 T0** 를 따로 둔다
  (`chart_T0_zone`, `chart_T0_fvg`, `chart_T0_cme`, `chart_T0_wedge`; 각각 그 셀의 동결 코드가 라이브 메모리에 실린 뒤 첫 등록 행의 t0). 문서는 수정하지 않는다.
- 성격: 전방 OOS 빈도 기록. 사전 기대 **넷 다 '차이 없음'**. 결과는 꼬리표만 바꾸고 그림·매매는 불변. 자본 0, 매매 입력 0.

## 0. 비전문가용 한 줄
"지지선이라서 더 버티나, 갭이라서 더 메워지나, 주말 갭이라서 더 되돌아오나, 쐐기라서 교과서 방향으로 깨지나" 를 앞으로의 폐봉으로 센다.
비교 대상은 '아무 가격·같은 거리·같은 계산' 의 우연 기준이다. 파일럿(2026-10-21, 인샘플·탐색)에서는 넷 다 우연과 구별되지 않았고, 이 실험의 기대도 같다.
'차이 없음' 은 실패가 아니라 기본 결과다.

## 1. 공통 규약 (동결)
- **기록**: `structure.db` 테이블 `chart_log` — 열 (event_family ∈ {zone, fvg, cme, wedge}, exchange, symbol, tf, event_key, t0_bar_ts, payload_json,
  logged_at, logged_by, chart_version, structure_version). **멱등 UNIQUE(event_family, exchange, symbol, tf, event_key)** — 첫 등록만(first-log-only):
  가장자리·거리·기준율 등 사건의 모든 수치는 첫 행에 고정되고, 이후 재계산이 달라져도 갱신하지 않는다. 기록 실패는 카운터 + `errors[]`, API 200 유지.
- **기준율은 등록 시점의 as-of 값**(그때까지의 폐봉만으로 계산)을 첫 행에 고정한다 — 사후 재계산 금지(룩어헤드 차단). RW 통제(층·쐐기)는 예외적으로
  판정 시 전방 기간 데이터로 1회 생성한다(§2.1·§2.4 — 전방 기간의 실현 수익률을 부호 플립해야 '같은 파이프라인·같은 변동성' 이 되기 때문).
- **모집단**: 셀별 T0 이후 첫 등록 사건. **성숙**: 판정 시점에 사건 창(H)이 이미 지난 것만. 창 안에 결과 없음(unresolved/expired)은 제외·건수 보고.
- **통계**: 사건 i 의 결과 y_i ∈ {0, 1}, 기준 p_ref,i → x_i = y_i − p_ref,i, Δ̄ = 평균,
  CI = `src/shadow._cluster_bootstrap_ci(values=x, clusters=ISO주, n_boot=10000, seed=20261021)` (서명 `_cluster_bootstrap_ci(values: list, clusters: list,
  n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple`, `src/shadow.py:283`; 클러스터 = t0 의 UTC ISO 연-주, 3심볼 공유; 클러스터 < 2 → 판정불가).
  병기: p̂ 의 Wilson 95% CI(n_eff = 사건 수 — 층은 (symbol, tf, 방향)별 **서로 겹치지 않는 사건 창의 최대 개수**(§2.1 n_eff 규칙), FVG 는 합집합 사건,
  CME 는 심볼당 주 1건, 패턴은 키당 1건)와 기준율의 밴드/CI.
- **'차이 있음' 선언 조건(양방향)**: 클러스터 CI 가 0 을 포함하지 않고 \|Δ̄\| ≥ 0.05, **그리고** 기준율이 밴드를 가진 셀(RW 20경로)은 p̂ 의 Wilson CI 가
  RW 2.5–97.5% 밴드와 겹치지 않을 것. 그 외는 '차이 없음(전방 확인)'.
- 심볼·TF·방향 분할, 거울 대칭(상승/하락, 위/아래 접근), 미해소 비율, logged_by 비율은 보고 의무(판정 무관).
- 1h·1d 의 층·FVG 통계는 서술만(판정 없음). CME 는 1h 프레임 단일(4h/1d 화면도 1h 로 계산). 쐐기는 §2.4 에 규정.
- 판정 전 패널 칩은 '사전 기대: 차이 없음 · 전방 n = …' 만 표시하고 Δ̄·CI 는 계산·표시하지 않는다(중간 열람 금지).

## 2. 판정 셀 4개 (이 넷만 판정 칩이 붙는다 — 나머지 셀·버킷·H 는 전부 서술)

### 2.1 피벗층 버팀(held) vs RW 통제 — 4h, H = 12, 3심볼 풀
- 층: 확정 S/M/L 피벗을 확정 시점 순으로 군집 중심 ±0.25×atr_t 안이면 병합(가중 S1/M2/L4), touches ≥ 2 만 층, 밴드 = 중심 ±0.25×atr_now, **kind = 'pivot'**.
- 접근 사건: 직전 종가가 가까운 가장자리 밖 ≥ 0.25 ATR 이고 당 봉 극값이 밴드에 진입. 결과(12 폐봉, 종가 기준, 먼저 온 것): broke = 먼 가장자리 + 0.25 ATR 너머 종가,
  held = 가까운 가장자리에서 반대쪽 ≥ 1.0 ATR 종가, 그 외 unresolved(제외). 층당 창 비중첩(재무장은 창 종료 뒤).
- **n_eff 규칙(2026-10-21 리뷰 P04 반영 — 보고 규칙이지 동결 그림 상수가 아니다, structure_v1 불변)**: 군집은 서로 병합되지 않으므로 중심 간격 < 0.5 ATR 인
  이웃 층이 같은 봉을 각자 사건으로 등록한다(4000봉 GBM 에서 풀 사건의 45~49% 가 다른 층과 같은 (봉, 방향)). 점추정 p̂ 는 등록 사건 전체(n)로 내되,
  **Wilson CI 의 n_eff 와 §3 성숙 기준(n_eff ≥ 100)은 (symbol, tf, 방향)별로 서로 겹치지 않는 사건 창 [접근 봉, 해소 봉](unresolved 는 +H)의 최대 개수**
  (끝이 빠른 창부터 고르는 interval scheduling, `src/structure_layers._pool` 과 동일 규칙)를 3심볼에 걸쳐 합한 값이다. 층별 사건 수를 그냥 더하면 CI 가
  ≈1.5배 좁고 성숙이 ≈2배 일찍 선언된다. 화면 `zones_stats.by_kind_side` 도 같은 규칙(n = 사건 수, n_eff = 비중첩 창 수, ci = wilson(p̂·n_eff, n_eff)).
- 키: (symbol, tf, 'zone', first_touch_time, 접근 bar_ts). 군집 병합으로 first_touch_time 이 바뀌면 새 키(건수 보고).
- 방향: from_below · from_above **풀**(각각은 보고). 층별 k/n 은 표시만.
- p_ref,i = 같은 (symbol, tf) 의 RW 통제 held 비율: 로그수익률 부호 플립(\|r\| 순서 보존, 봉 수직 반전) **20경로, seed 20261021 + k**, 같은 층·접근·결과 파이프라인,
  **판정 시 전방 기간 데이터로 1회 생성**(디스크 캐시 `.structure_ref_cache.json` 은 화면용 — 판정에 쓰지 않음), 풀 평균 + 2.5/97.5 분위 밴드.
- 사전 기대: 차이 없음(파일럿 held 0.42–0.46 vs RW 0.50–0.54 — 인샘플 참고만). 기하 참고치 d/(d+d′) 는 접근 정의상 틀린 기준이라 쓰지 않는다.

### 2.2 FVG far 채움 vs 거리매칭 — 크기 [0.5, 1.0) ATR, 4h, H2 = 42, 3심볼 풀
- 사건: 폐봉 i 에서 low_i > high_{i−2}(상승 갭) / high_i < low_{i−2}(하락 갭), 박스 top/bottom/mid, size_atr = 높이 / atr_i; 같은 방향·3봉 이내·겹침 → 1 사건
  (합집합, 먼 가장자리 = 첫 갭). 집계 최소 0.10 ATR; **셀은 [0.5, 1.0) ATR 버킷만**. 상승·하락 풀(거울). 봉간 갭은 24/7 시장이라 계산하지 않는다.
- 결과: far 채움 = i+1 .. i+42 폐봉 고저가 먼 가장자리에 도달(정확 터치 포함). 창 안 미도달 = 0(채움 실패 — '미해소' 가 아니라 결과 0; 창이 고정이므로 성숙만 요구).
- 키: (symbol, tf, 'fvg', dir, 첫 갭 봉 bar_ts).
- p_ref,i = 사건 거리 d_e = (먼 가장자리 − close_i) / atr_i (부호 = 방향)의 **무조건 도달률**: 등록 시점 as-of 과거 모집단(폐봉 i 까지)에서 같은 방향·같은 거리·H2 = 42 의
  도달 ECDF 평균(B1 엔진 `possibility.level_query` 의 거리 규약과 동일: 시작점 t 의 수준은 atr_t 기준, 창 t+1 .. t+H).
- 사전 기대: 차이 없음(파일럿 FVG 채움률 ≈ 거리매칭 ±0.05 — "거리 때문").

### 2.3 'CME 주말창' \|gap\| ≥ 0.5% 되돌림 vs 요일매칭·플라시보 — 1h, 118h, 3심볼 풀
> **구조 변화 공지(동결 전 확인, 2026-10-21)**: CME 는 **2026-05-29 16:00 CT 부터 암호화폐 선물·옵션을 24/7 거래**한다(주중 16:00–16:02 CT 2분 정지,
> 토 02:00–04:00 CT 유지보수; 금 저녁~일 저녁 거래는 다음 영업일 거래일로 귀속 — `docs/cme_holidays.json` `_crypto_24_7`, `_verify` 포함).
> 따라서 **전방 기간 전체에서 'CME 가 주말에 닫혀 생기는 갭' 이라는 기제는 존재하지 않는다.** 이 셀은 **동일 달력 창(금 15:00 CT 봉 종가 → 일 17:00 CT 봉 시가)의
> 가격 변화가, 주중 같은 시각·같은 거리의 움직임보다 더 되돌아오는가** 를 검증하는 것으로 정의한다('CME 갭' 은 역사적 명칭). 차이가 나오더라도 CME 기제가 아니라
> 주말 유동성·달력 효과로만 서술할 수 있다. 셀 유지/삭제는 소유자 결정 사항이며, 삭제 시 이 셀은 '등록 철회(판정 없음)' 로 사이드카에 기록한다.
> 과거 모집단(바이낸스 1h 18000봉 캐시)은 2026-05-29 전후 두 체제를 섞고 있으므로 as-of 기준율은 체제 구분 없이 쓰되, 리포트는 전후 분할을 서술한다.
- 사건: 바이낸스 1h('바이낸스 모집단' 표기; Gate 1h 는 현재 갭 표시만). fri_close = 금 15:00 CT 시작 봉 종가, sun_open = 일 17:00 CT 시작 봉 시가
  (zoneinfo 'America/Chicago', 폴백 `_us_dst`, `clock_source` 노출), gap_pct = (sun_open − fri_close) / fri_close, gap_atr_1h. **\|gap_pct\| ≥ 0.5% 만 셀**
  (미만은 '베이시스 근사 오차 우세' 서술). 경계 봉 결측 → skip + reason. `docs/cme_holidays.json` 의 `excluded_weekends` 에 든 주말(휴일 인접 주) 제외 —
  JSON 의 사후 변경은 CME 공식 공지 반영만 허용하고 결과를 보고 고치지 않으며 `_changelog` 에 남긴다. `_coverage` 밖 주말은 '휴일 정보 없음' 으로 표시만.
- 결과: 완전 되돌림 = 일 17:00 CT 봉부터 118봉(= 다음 금 15:00 CT 직전) 안에 폐봉 고저가 fri_close 에 도달. 절반 되돌림(중간값)·24/72/168h 는 서술.
- 키: (symbol, '1h', 'cme', 금요일 ISO 날짜(CT)).
- 기준 둘(둘 다 as-of): **p_ref_weekday,i** = 같은 심볼 과거 모집단에서 월~목 17:00 CT 시작 봉을 시작점으로, 같은 거리 \|gap_pct\| 를 되돌림 방향으로 118h 안에
  도달한 비율의 ECDF 평균(요일매칭·거리매칭); **p_placebo,i** = 과거 주말 시작점에서 같은 거리를 갭 **진행 방향**으로 118h 안에 도달한 비율.
  판정 통계는 x_i = y_i − p_ref_weekday,i; '차이 있음' 은 추가로 p̂ 의 Wilson CI 하한 > p_placebo 풀 평균을 요구한다.
- 사전 기대: 차이 없음.

### 2.4 쐐기 돌파 방향 vs 같은 kind RW — 1h(S) · 4h(M) · 1d(M) 풀, 3심볼
- 패턴: 피벗 마지막 k ∈ {4, 5, 6} 교대 창, 상단 = 고점 OLS, 하단 = 저점 OLS(잔차 ≤ 0.25 ATR), w_start ≥ 1.5 ATR, conv ≤ 0.75, x_apex ∈ (마지막 피벗, +3L];
  발산 = unsupported. 분류(flat = \|s\| ≤ 0.15 상대): rising/falling wedge, asc/desc/sym triangle.
- **키: (symbol, tf, kind, 첫 피벗 ts ISO basic)** — 사양 문구 '첫 피벗 idx' 대신 ts 를 쓴다: idx 는 캐시가 1봉 밀릴 때마다 바뀌어 '첫 등록만' 을 무력화한다
  (`src/structure.py _start_key` 와 같은 교훈). ts 없는 입력은 등록하지 않는다.
- 돌파: 종가 > 상단 + 0.25 ATR_t0 → up, 종가 < 하단 − 0.25 ATR_t0 → down(t0 = 등록 봉, ATR_t0 는 그 봉의 atr_14); min(apex, t0 + 3L) 까지 없음 → expired(제외·보고).
  후속(서술만): 돌파 종가 ± w_start 를 L봉 안에 도달 = reached / 선 안쪽 복귀 = failed, 같은 kind RW 의 p_follow_rw 병기.
- **판정 셀 = 쐐기(rising + falling)의 '교과서 방향 돌파' 비율**: y_i = 1[돌파 방향 = textbook](rising → down, falling → up). 거울 풀로 n 을 확보한다.
  이것이 사양 문구 '쐐기 P(up) vs RW' 의 운영 정의이며, rising 만의 P(up)·falling 만의 P(up) 은 각각 보고한다. 삼각형 3종은 서술.
- p_ref,i = 같은 (symbol, tf, kind) 의 RW 경로(부호 플립 20경로, seed 20261021 + k, 판정 시 전방 기간 데이터로 1회)에서 같은 검출·돌파 규칙으로 얻은 교과서 방향 비율
  (풀 평균 + 밴드). 패턴이 RW 에서 0건이면 그 (symbol, tf, kind) 는 기준 없음 → 사건 제외·보고.
- 사전 기대: 차이 없음(파일럿 상승 쐐기 하향 돌파 71–93% vs RW 84–90% — 수렴하는 두 선의 기하가 방향을 만든다).

## 3. 판정 (동결, 셀별 1회 열람)
- 시점: 셀별 **n_eff ≥ 100**(해소·성숙 사건; 층 셀은 §2.1 의 비중첩 창 수) 또는 **셀 T0 + 12개월** 중 먼저. 셀은 서로 독립으로 판정한다(한 셀의 열람이 다른 셀을 열지 않는다).
  리포트 `docs/structure_chart_forward_result_<cell>_<date>.md`(입력은 structure.db 원본).
- 결과 → **꼬리표만**: '차이 있음(전방 ±x pp, n, CI)' / '차이 없음(전방 확인, n, CI)' / '판정불가(전방 n < 100)'. 그림(박스·선·층)·거래 경로 불변.
- **킬 규칙**: 이 family 에서 '킬' 은 **서술 문구의 영구 제거**다 — 판정이 '차이 없음' 또는 '판정불가' 인 셀은 '채워진다/버틴다/교과서 방향' 류 기대 문구,
  `textbook` 방향 문자열, '교과서 측정치' 라벨에 영구 꼬리표 **'예측력 없음(전방 검증: 차이 없음)'** / **'(전방 판정불가)'** 를 붙이고, 이후 어떤 재파라미터화
  (버킷·H·임계·심볼·TF 변경)도 금지한다(새 family 만). '차이 있음' 이어도 매매 입력 금지는 영구이며 '전방 차이 +x pp (n, CI)' 문구만 허용된다.
- **장치 무결성 킬(실험 무효)**: 배포 전 GBM/RW 반증(같은 파이프라인에서 실측 − 기준의 CI 가 0 을 포함해야 함)에 실패한 셀은 배포 금지(사양 §5 '수학 반증').
  전방 중 기준율 장치의 결함이 재현되면 그 셀은 '무효(장치 결함)' 로 기록하고 결과를 해석하지 않는다(재실험 = 새 family).
- 검정력 공지: n = 100 에서 검출 가능 차 ≈ ±0.10(80% 검정력 ≈ 0.14). 쐐기·CME 는 12개월에 n < 100 가능성이 크다(쐐기: 4h 월 1–2건/심볼 수준 예상;
  CME: 주당 심볼 3 × \|gap\| ≥ 0.5% 비율) → '판정불가' 가 최빈 경로일 수 있음을 알고 등록한다.

## 4. 시도장부 (research.db)
- 배포 시 `src/trial_ledger.log_trial` 로 1행(`structure_chart_fwd_v1`; 4셀은 선택 없이 전부 보고되는 사전등록 하위 분석이므로 1시도) —
  `docs/structure_wave_forward_prereg.md`(`structure_wave_fwd_v1`)와 합쳐 **N 58→60**. 현재 N = 58(2026-10-21 `research.db` 읽기 전용 `COUNT(*)` 확인).
- 서명(`src/trial_ledger.py:33`, 2026-10-21 확인):
  ```python
  def log_trial(family: str, spec: dict | str, dataset: str,
                n_obs: int | None = None, mean_r: float | None = None,
                sharpe: float | None = None, note: str = "") -> None:
      """변형 1건 기록. spec 은 dict(정렬 직렬화) 또는 str. 재평가는 last_ts/지표만 갱신."""
  ```
  UNIQUE(family, spec, dataset) — 재실행은 갱신(멱등). 배포 로그에 기산 전후 `trial_count()` 를 남긴다(58 → 60).
- 기산 호출(동결):
  `log_trial("structure_chart_fwd_v1", {"prereg": "docs/structure_chart_forward_prereg.md", "sha256": "<사이드카 해시>", "chart_version": "structure_chart_v1", "structure_version": "structure_v1", "cells": ["zone_pivot_held_4h_h12", "fvg_0.5-1.0atr_4h_h42_far", "cme_window_abs0.5pct_1h_118h", "wedge_textbook_dir_pooled"], "n_judge": 100, "min_effect": 0.05, "seed": 20261021}, dataset="gate_binance_structure_fwd_<T0 날짜 YYYY-MM-DD>", note="사전등록(결과 전 기산); 셀별 T0 는 structure.db meta")`.
  판정 시 `n_obs` = 셀 n 합, `mean_r` = None(셀별 Δ̄ 는 note 에), note = 셀별 판정 문구로 갱신.

## 5. 보고 의무
셀별 n_logged·n_eff·미해소/expired·skip 사유(결측·휴일), p̂·Wilson CI·p_ref·밴드·Δ̄·클러스터 CI·n_cluster, 분할(심볼·TF·방향·버킷·CME 체제 전후), 거울 대칭,
as-of 기준율의 모집단 크기, RW 경로 생성 로그(seed·n), chart_version·structure_version·sha256·셀 T0, `cme_holidays.json` 변경 이력. 나쁜 소식 먼저, 포장 금지.
