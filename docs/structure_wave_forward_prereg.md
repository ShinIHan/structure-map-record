# 사전등록: 파동 카운트 전방(forward) 검증 — structure_wave_fwd_v1

**동결 2026-10-21 (T0 전 동결).** 이 문서는 결과를 보기 전에 고정되며, 동결 뒤에는 한 글자도 바꾸지 않는다.
sha256 은 커밋 메시지와 사이드카 `docs/structure_wave_forward_prereg.sha256` 에 기록한다(문서 안에 자기 해시를 넣지 않는다 —
넣는 순간 해시가 바뀐다). 바꿔야 할 일이 생기면 이 실험은 장부에 '중단(abandoned)' 으로 남기고 **새 family 로 새 사전등록**을 한다.

- family: `structure_wave_fwd_v1` · 상수 버전 `structure_v1` (`src/structure.py STRUCTURE_V1`, `src/possibility.py STRUCTURE_V1`,
  MappingProxyType 으로 런타임 변경 차단). 사양: `docs/structure_map_spec_v2.md` §2 D1 · §5 (v1 §5 는 배경).
- T0: **미기입** — 배포 시 `structure.db` 의 `meta` 테이블 키 `wave_T0` 에 최초 1회 기록(INSERT OR IGNORE — 재기동은 T0 를 옮기지 않음)하고
  사이드카에 같은 값을 적는다. 이 문서는 수정하지 않는다. T0 = 동결된 코드가 라이브 데몬 메모리에 실린 뒤 첫 `wave_log` 행의 `bar_ts`.
- 성격: 백테스트가 아니라 **전방 OOS 기록**. 자본 0, 매매 입력 0. 통과해도 매매 입력이 되지 않는다(별도 사전등록 없이는 영구).

## 0. 비전문가용 한 줄
차트의 '파동 카운트' 는 "이 해석이 맞다면 가격이 **비율 목표**에 닿을 것이고, **깨지는 가격**에 먼저 닿으면 해석이 틀린 것" 이라고 말한다.
이 실험은 앞으로 쌓이는 폐봉만으로 **"목표가 깨지는 가격보다 먼저 닿는 일이, 두 가격까지의 거리만으로 설명되는 우연보다 잦은가"** 를 센다.
사전 기대는 **"아니다(차이 없음)"** 다. 결과가 어떻든 그림(피벗·파동 라벨·깨지는 가격)은 그대로 남고, 트레이더·워처·점수·advise 에는 어떤 값도 들어가지 않는다.

## 1. 가설 (동결)
- **H1(주)**: 4h · 3심볼 풀(Gate `BTC/USDT:USDT`·`ETH/USDT:USDT`·`SOL/USDT:USDT` = `watcher.py DEFAULT_SYMBOLS`) 에서 1위 가설 사건의
  **`목표-먼저 적중률 − P_ref` 의 평균 Δ̄ ≥ +0.05 이고 ISO-주 클러스터 부트스트랩 95% CI 하한 > 0**.
  - P_ref = d_inv / (d_inv + d_tgt): 드리프트 0 무작위보행이 두 가격 중 어느 쪽에 먼저 닿는지의 기하 기준(도박꾼 파산, 무한 창·해소 조건부).
    거리 효과를 뺀 나머지만 '카운트가 가진 정보' 로 친다.
- **H2(보조, 킬·통과와 무관)**: 같은 사건 봉에서 1위 가설의 50봉 무효화율 < 대안(2위) 가설의 50봉 무효화율.
- **사전 기대: H1 기각(차이 없음).** 근거: 점수 확률 캘리브 ship=false(2026-09-25 빌드), 파일럿(2026-10-21, 인샘플) 측정 목표 도달 7–35%,
  파동 카운트의 전방 예측력에 대한 통제된 증거 부재. 이 실험은 '없음을 확인' 하려는 것이지 '있음을 보이려는' 것이 아니다.

## 2. 무엇을 언제 기록하나 (`structure.db`, 테이블 `wave_log`)
폐봉마다 1행, **멱등 키 (exchange, symbol, tf, bar_ts)** — 같은 폐봉을 몇 번 계산해도 1행(INSERT OR IGNORE; 갱신 없음, 첫 행이 영구).
P0 에서는 `/api/structure` 가 계산할 때 append 한다(= **열람 의존**: 아무도 안 보면 그 봉의 행이 없다 — §6). P1b 의 시간당 SYSTEM 작업이 이를 보완한다.
행에 `logged_by`('api'|'job') 를 남겨 비율을 보고한다. 기록 실패(락·예외)는 카운터만 올리고 API 는 200 을 유지하되 `errors[]` 에 드러낸다.

| 열 | 뜻 | 출처 |
|---|---|---|
| exchange, symbol, tf, bar_ts | 폐봉 시작 시각(UTC epoch 초). tf ∈ {1h, 4h, 1d} | 라우트(`closed_only` 절단 후) |
| logged_at, logged_by, structure_version | 기록 시각(UTC), 'api'/'job', `structure_v1` | 라우트 |
| close, atr_now | 폐봉 종가, atr_14 | `compute_structure` price/atr |
| top1_id, top1_kind, top1_direction, top1_in_wave, top1_fit, top1_n_guidelines, top1_hard_pass | 1위 가설(`elliott.hypotheses[0]`, 스케일 M 고정) | `enumerate_elliott` |
| ambiguous, none_valid, n_valid, n_unverifiable | 열거 상태 | 동일 |
| inv_price | 깨지는 가격 `invalidation_price` | 동일 |
| target_label, target_price | 1위 가설 `targets` 중 현재가에 가장 가까운 비율 목표(현 구현은 가설당 ≤1개; 없으면 NULL) | 동일 |
| d_inv, d_tgt | ATR 배수: d_inv = \|close − inv_price\| / atr_now, d_tgt = \|target_price − close\| / atr_now | 라우트 계산 |
| p_ref | d_inv / (d_inv + d_tgt) — 둘 다 > 0 일 때만, 아니면 NULL | 라우트 계산 |
| alt_id, alt_inv_price, alt_fit | 2위 가설 id·깨지는 가격·규칙 일치도(없으면 NULL) | `elliott.hypotheses[1]` |
| dow_state, dow_scale | 다우 상태(M)·헤드라인 스케일 | `dow`, `now.scale` |
| eff_ratio, regime | ER(14)·레짐 라벨(컷 0.35/0.55, `/api/context` 와 동일) | `src/indicators.efficiency_ratio` |
| grid_json | B1 P̂ 격자 전체(d×H 의 p_up/p_down/ci/n_eff/p_rw) | `possibility.reach_grid` |
| churn_30 | 최근 30봉 연속 행에서 top1_id 가 직전 행과 다른 비율(연속 쌍 < 10 이면 NULL) | 라우트(로그 조회) |

행 값은 **그 봉에서 계산된 값 그대로** 이며 나중에 고치지 않는다. 1h·1d 행도 같은 형식으로 기록하되 판정에는 쓰지 않는다(§3-9).

## 3. 사건(event)과 채점 (동결)
1. **사건 키 = 1위 가설 id** `"{scale}:{시작 피벗 ts ISO basic}:{kind}:{direction}:{in_wave}"` (예 `M:20261005T120000Z:impulse:up:3`).
   시작 키가 ts 가 아닌 idx 폴백(숫자)인 id 는 창 이동마다 바뀌므로 **채점 제외**(건수 보고). 근거: `src/structure.py _start_key`.
2. **키당 첫 기록만** 채점(재페인트 방어): 사건의 기준 봉 t0 = 그 id 가 `top1_id` 로 **처음** 기록된 `bar_ts`.
   같은 id 가 뒤에 다시 1위가 되거나 목표·무효화 가격이 갱신돼도 **첫 행의 inv_price·target_price·p_ref 가 영구**.
3. **유효 사건** = t0 행에서 target_price·inv_price 모두 존재, d_inv > 0, d_tgt > 0 (현재가가 두 가격 사이), 1위가 순위 가설(n_guidelines ≥ 1 —
   2파·B파 진행 가설은 `unverifiable` 로 순위 밖이라 자동 제외), 시각 존재. 미충족(목표 없음: 4파 진행·완성 가설 / 거리 ≤ 0 / idx 폴백)은
   '채점 불가' 로 건수 보고.
4. **해소**: t0 다음 폐봉부터 100봉(t0+1 .. t0+100) 안에서 — 상승형(direction=up)은 폐봉 high ≥ target_price → '목표 먼저', 폐봉 low ≤ inv_price →
   '무효화 먼저'; 하락형은 거울(low ≤ target_price, high ≥ inv_price). 정확 터치(=)도 도달. **같은 봉에서 둘 다 → '무효화 먼저'**
   (보수; B2 '같은 봉 동시=손절' 과 같은 규약 — H1 에 불리한 쪽으로 둔다). 100봉 안에 둘 다 없음 → '미해소', **제외하고 건수 보고**.
   창은 달력이 아니라 **폐봉 수**로 세며, 데이터 공백 봉은 '관측 없음' 으로 둔다(공백 비율 보고).
5. **성숙**: 판정 시점에 t0 + 100봉이 이미 지난 사건만(우측 절단 편향 방지 — `docs/shadow_rule_ab_prereg.md` §3 과 같은 이유:
   빨리 해소되는 쪽이 절단 시점에 과대표집된다).
6. **통계**: 해소·성숙 사건 i 에 대해 x_i = 1[목표 먼저] − p_ref,i. Δ̄ = 평균.
   CI = `src/shadow._cluster_bootstrap_ci(values=x, clusters=ISO주, n_boot=10000, seed=20261021)`.
   함수 서명(`src/shadow.py:283`, 2026-10-21 확인): `_cluster_bootstrap_ci(values: list, clusters: list, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple`
   — 클러스터 키 정렬 + numpy Generator 라 행 순서와 무관하게 재현된다. 기본 seed 20261014 는 그림자 A/B 용이므로 여기서는 **seed=20261021 을 명시**.
   클러스터 = t0 의 UTC ISO 연-주 문자열(`YYYY-Www`; 3심볼의 같은 주 = 한 클러스터). 클러스터 < 2 면 (None, None) = 판정불가.
   보조로 목표-먼저 비율의 Wilson 95% CI(n_eff = 사건 수 — 키당 1건이라 창 중첩은 없고 심볼 간 상관은 클러스터로만 처리)를 병기.
7. **P_ref 짝 맞춤**: P_ref 는 '무한 창·해소 조건부' 기준이므로 **해소된 사건의 비율과만** 비교한다(`src/possibility.py` 의 p_ref 규약과 동일).
   미해소를 포함한 무조건 비율은 서술로만 둔다.
8. **H2**: 같은 사건 집합에서 alt_id 가 있는 사건만, D_i = 1[1위 inv_price 가 t0+1..t0+50 안 터치] − 1[2위 alt_inv_price 가 같은 창 안 터치](같은 터치 규약).
   클러스터 CI(같은 시드) 상한 < 0 → '1위가 대안보다 덜 깨짐' 서술 허용. 그 외 서술 없음. 킬·통과와 무관.
9. **사전 선언 보조 수치**(판정 무관, 보고 의무): 미해소를 '목표 아님' 으로 센 보수 Δ̄; 심볼별·kind 별·in_wave 별·ambiguous 여부별 분할;
   상승/하락 거울 대칭(두 방향의 Δ̄ 부호·크기); logged_by 비율; 1h·1d 의 같은 통계(**서술만, 통과/킬 선언 없음**).

## 4. 판정 (동결, 1회 열람)
- **시점**: 4h 채점 사건(해소·성숙) **n ≥ 100** 또는 **T0 + 12개월** 중 먼저. 도달 시 리포트 1회 산출(`research/structure_report.py` 또는 동등 스크립트,
  입력은 structure.db 원본, 출력 `docs/structure_wave_forward_result_<date>.md`). 그 전에는 API `forward_test.wave` 에 `n_scored`(해소 건수)·`status`·`t0` 만
  노출하고 Δ̄·CI 는 계산·표시하지 않는다(중간 열람 금지).
- **통과**: CI 하한 > 0 **그리고** Δ̄ ≥ +0.05 → 패널 문구 '전방 적중 +x pp (n, CI)' 허용. 매매 입력은 여전히 아님.
- **킬**: 그 외 전부 — CI 가 0 포함, 또는 Δ̄ < +0.05, 또는 **판정불가**(12개월에 n < 100, 클러스터 < 2, 데이터 무결성 실패) →
  **영구 꼬리표 '예측력 없음(전방 검증 실패)'**, 비율 목표(가설 `targets`·측정 목표 선·도달 태그) **숨김**, 도형(피벗·파동 라벨·깨지는 가격) **유지**.
  연구 agenda 규칙 "판정불가 = no-go" 와 동일.
- **재파라미터화·재실험 금지**: 상수(k_atr, 지침 밴드, 100봉, +0.05, n=100, 시드 …) 변경, 심볼·TF 추가, 사건 정의 변경 전부 금지.
  변경하려면 새 family + 새 사전등록 + 장부 +1 이며 이 결과는 영구 병기된다.
- **검정력 공지(정직)**: n=100, p≈0.5 → SE≈0.05 이므로 CI 하한 > 0 이려면 Δ̄ ≳ +0.10 이 필요하다. 참 효과가 +0.05 라면 통과 확률 ≈ **17%**
  (독립 가정; 클러스터 상관이면 더 낮음), 참 +0.10 이라도 ≈ 52%, 80% 검정력의 최소 검출 효과 ≈ 0.14. 즉 **작은 참 효과는 거의 확실히 킬**된다 —
  알고 등록한다. 킬은 '효과 없음의 증명' 이 아니라 '표시할 근거 없음' 이다.

## 5. 표시 규칙 (예측 주장 아님)
- 꼬리표 `서술적 구조 — 예측 근거 없음` 은 판정 전·후 항상 붙는다. 규칙 일치도(fit_score)는 순서 번호이지 확률이 아니다.
- churn_30 > 0.30 → 기본 표시 스케일 L 강등(표시 품질). 채점 대상은 변함없이 **M 1위**(`enumerate_elliott(..., "M")`)이며 표시 강등과 무관.
- P̂ 격자 월간 신뢰도: 매월 `wave_log` 행에서 (d, H) 칸별 실현 도달률을 로그 행 자체로 계산해, 기록된 CI 안인 칸 비율 ≥ 90% 아니면 패널 적색 배지.
  휴리스틱(월 표본의 추가 분산 미반영)이며 숨기지 않는 것이 목적 — H1 과 무관.

## 6. 운영·한계 (정직 공지)
- 열람 의존(P0): 사건 t0 가 첫 출현보다 늦을 수 있다 → p_ref 는 t0 봉 값이라 **내부 정합**은 유지되지만, 열람이 시장 상태와 상관되면 선택 편향이 가능하다.
  `logged_by` 비율과 '첫 출현 대비 지연 봉수'(P1b 이후 재구성)를 보고하고, 시간당 작업 투입일을 사이드카에 기록한다.
- 읽기 전용·격리: `tests/test_structure_separation.py` — 트레이딩 모듈(watcher/trader/scoring/signals/calibration/advise)에 `structure|possibility` import 0.
  쓰기는 structure.db 와 `.structure_ref_cache.json` 뿐.
- 레짐 변화·거래소 변경·데이터 결측은 CI 에 반영되지 않는다(CI 는 표본 잡음만).
- 상수·알고리즘 변경(새 `structure_vN`) 시 이 family 는 '중단' 으로 기록되며 통과 선언이 불가능하다.

## 7. 시도장부 (research.db)
- 배포 절차에서 `src/trial_ledger.log_trial` 로 **2행 기산 — 이 문서(`structure_wave_fwd_v1`) + `docs/structure_chart_forward_prereg.md`(`structure_chart_fwd_v1`) → N 58→60**.
  현재 N = 58 (2026-10-21 `research.db` 읽기 전용 `COUNT(*)` 확인; 마지막 행 id 62 `shadow_rule_C_v1` — id 는 건너뛴 번호가 있어 N 과 다르다).
  결과와 무관하게 사전등록 시점에 1시도로 센다(장부 원칙: "평가된 모든 변형은 결과와 무관하게 1시도").
- 서명(`src/trial_ledger.py:33`, 2026-10-21 확인):
  ```python
  def log_trial(family: str, spec: dict | str, dataset: str,
                n_obs: int | None = None, mean_r: float | None = None,
                sharpe: float | None = None, note: str = "") -> None:
      """변형 1건 기록. spec 은 dict(정렬 직렬화) 또는 str. 재평가는 last_ts/지표만 갱신."""
  ```
  테이블 `trials` 는 UNIQUE(family, spec, dataset) — 재실행은 갱신(멱등). `family`/`dataset` 이 비면 ValueError.
- 기산 호출(동결):
  `log_trial("structure_wave_fwd_v1", {"prereg": "docs/structure_wave_forward_prereg.md", "sha256": "<사이드카 해시>", "version": "structure_v1", "tf": "4h", "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"], "resolve_bars": 100, "min_effect": 0.05, "n_judge": 100, "seed": 20261021}, dataset="gate_structure_fwd_<T0 날짜 YYYY-MM-DD>", note="사전등록(결과 전 기산) T0=<epoch>")`.
  판정 시 같은 행에 `n_obs` = 채점 n, `mean_r` = Δ̄(열 이름은 장부 공용 — Δ̄ 를 담는다고 note 에 명시), `sharpe` = None, note = 판정 문구로 갱신.
  배포 로그에 기산 전후 `trial_count()` 를 남긴다(58 → 60).

## 8. 보고 의무 (판정 리포트에 반드시)
n_logged(봉)·n_ids·유효 사건·채점 불가(목표 없음 / 거리 ≤ 0 / idx 폴백)·미해소·미성숙 건수, 심볼·kind·in_wave·ambiguous 분할, Δ̄·클러스터 CI·Wilson CI·n_cluster,
보수 Δ̄, H2 수치, 거울 대칭, logged_by 비율, churn 분포, 격자 월간 신뢰도 이력, 데이터 공백 비율, 상수 버전·sha256·T0. 나쁜 소식 먼저, 포장 금지.
