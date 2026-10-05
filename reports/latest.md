# ContriLog 평가 결과 (2026-10-05 17:20)

> Agent와 같은 팀이 만든 synthetic 데이터(P001·P002)의 개수다. 비교·회귀 확인용이며 일반 성능 추정치가 아니다.

- LLM: ollama qwen3:32b (think=False) · 사용 가능: True · 호출 97회 (API 0 / 캐시 97 / 규칙 대체 0)

## 1. 응답 해석 (P001+P002 시뮬레이션 응답, 정답 라벨 대비)

| 해석기 | 전체 | 상태 확인 응답 | 지원 요청 응답 | 해석 주의 응답 | Block 종류 |
|---|---|---|---|---|---|
| rule | 31/46 (67%) | 20/29 (69%) | 11/17 (65%) | 9/18 (50%) | 9/10 (90%) |
| llm | 44/46 (96%) | 28/29 (97%) | 16/17 (94%) | 17/18 (94%) | 12/13 (92%) |
| oracle | 46/46 (100%) | 29/29 (100%) | 17/17 (100%) | 18/18 (100%) | 13/13 (100%) |

## 2. 정체 Agent 전체 (프로젝트 시작~종료 연속 실행)

| 프로젝트 | 해석기 | Memory | 질문 수 | 업무시간 외 질문 | Block 판정 | Block 종류 | 최종 상태 | 지원자 | 해결 판정 | 놓친 실제 Block |
|---|---|---|---|---|---|---|---|---|---|---|
| P001 | rule | OFF | 13 | 13 | 3/3 (100%) | 0/0 | 3/3 (100%) | 1/1 (100%) | 1/1 (100%) | - |
| P001 | rule | ON | 11 | 11 | 3/3 (100%) | 0/0 | 3/3 (100%) | 1/1 (100%) | 1/1 (100%) | - |
| P001 | llm | OFF | 13 | 13 | 3/3 (100%) | 0/0 | 3/3 (100%) | 1/1 (100%) | 1/1 (100%) | - |
| P001 | llm | ON | 11 | 11 | 3/3 (100%) | 0/0 | 3/3 (100%) | 1/1 (100%) | 1/1 (100%) | - |
| P001 | oracle | OFF | 13 | 13 | 3/3 (100%) | 0/0 | 3/3 (100%) | 1/1 (100%) | 1/1 (100%) | - |
| P001 | oracle | ON | 11 | 11 | 3/3 (100%) | 0/0 | 3/3 (100%) | 1/1 (100%) | 1/1 (100%) | - |
| P002 | rule | OFF | 26 | 22 | 10/15 (67%) | 4/5 (80%) | 10/15 (67%) | 2/3 (67%) | 4/9 (44%) | CASE08, CASE10, CASE12 |
| P002 | rule | ON | 25 | 21 | 10/15 (67%) | 4/5 (80%) | 10/15 (67%) | 2/3 (67%) | 4/9 (44%) | CASE08, CASE10, CASE12 |
| P002 | llm | OFF | 25 | 21 | 12/15 (80%) | 5/6 (83%) | 12/15 (80%) | 2/3 (67%) | 5/8 (62%) | CASE08, CASE12 |
| P002 | llm | ON | 22 | 19 | 11/15 (73%) | 5/5 (100%) | 11/15 (73%) | 2/3 (67%) | 4/8 (50%) | CASE06, CASE08, CASE12 |
| P002 | oracle | OFF | 25 | 21 | 12/15 (80%) | 6/6 (100%) | 12/15 (80%) | 3/4 (75%) | 5/8 (62%) | CASE08, CASE12 |
| P002 | oracle | ON | 22 | 19 | 11/15 (73%) | 5/5 (100%) | 11/15 (73%) | 2/3 (67%) | 4/8 (50%) | CASE06, CASE08, CASE12 |

## 3. 항목별 (Memory OFF)

### P001 · rule

| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |
|---|---|---|---|---|---|---|
| GTS-01 | CASE03 | T03·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | CONFIRMED_BLOCK (✓) | - |
| GTS-02 | CASE04 | T04·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-03 | CASE10 | T11·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_B ✓ | RESOLVED (✓) | - |

### P001 · llm

| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |
|---|---|---|---|---|---|---|
| GTS-01 | CASE03 | T03·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | CONFIRMED_BLOCK (✓) | - |
| GTS-02 | CASE04 | T04·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-03 | CASE10 | T11·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_B ✓ | RESOLVED (✓) | - |

### P001 · oracle

| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |
|---|---|---|---|---|---|---|
| GTS-01 | CASE03 | T03·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | CONFIRMED_BLOCK (✓) | - |
| GTS-02 | CASE04 | T04·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-03 | CASE10 | T11·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_B ✓ | RESOLVED (✓) | - |

### P002 · rule

| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |
|---|---|---|---|---|---|---|
| GTS-01 | CASE01 | T05·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-02 | CASE02 | T07·M_C | NOT_INFORMATIVE (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-03 | CASE02 | T09·M_E | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-04 | CASE02 | T10·M_A | NOT_INFORMATIVE (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-05 | CASE03 | T08·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_E ✓ | RESOLVED (✓) | - |
| GTS-06 | CASE04 | T11·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_A ✗ | RESOLVED (✓) | - |
| GTS-07 | CASE05 | T06·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | RESOLVED (✗) | RESOLVED |
| GTS-08 | CASE06 | T12·M_D | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_A ✓ | RESOLVED (✓) | - |
| GTS-09 | CASE07 | T13·M_E | - (-) | - | NORMAL (✓) | - |
| GTS-10 | CASE08 | T14·M_C | - (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-11 | CASE09 | T15·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_D | RESOLVED (✓) | - |
| GTS-12 | CASE10 | T16·M_E | REPORTS_ON_TRACK (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-13 | CASE11 | T17·M_A | REPORTS_BLOCKED (REPORTS_ON_TRACK) | M_B | RESOLVED (✗) | CONFIRMED_BLOCK, RESOLVED |
| GTS-14 | CASE12 | T18·M_C | - (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-15 | CASE13 | T19·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |

### P002 · llm

| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |
|---|---|---|---|---|---|---|
| GTS-01 | CASE01 | T05·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-02 | CASE02 | T07·M_C | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-03 | CASE02 | T09·M_E | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-04 | CASE02 | T10·M_A | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-05 | CASE03 | T08·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_E ✓ | RESOLVED (✓) | - |
| GTS-06 | CASE04 | T11·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_A ✗ | RESOLVED (✓) | - |
| GTS-07 | CASE05 | T06·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | RESOLVED (✗) | RESOLVED |
| GTS-08 | CASE06 | T12·M_D | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | RESOLVED (✓) | - |
| GTS-09 | CASE07 | T13·M_E | - (-) | - | NORMAL (✓) | - |
| GTS-10 | CASE08 | T14·M_C | - (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-11 | CASE09 | T15·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | RESOLVED (✓) | - |
| GTS-12 | CASE10 | T16·M_E | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_B ✓ | RESOLVED (✓) | - |
| GTS-13 | CASE11 | T17·M_A | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-14 | CASE12 | T18·M_C | - (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-15 | CASE13 | T19·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |

### P002 · oracle

| 항목 | Case | Task·담당 | 응답 해석 (기대) | 지원자 | 최종 (정답 여부) | 금지 상태 |
|---|---|---|---|---|---|---|
| GTS-01 | CASE01 | T05·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-02 | CASE02 | T07·M_C | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-03 | CASE02 | T09·M_E | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-04 | CASE02 | T10·M_A | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-05 | CASE03 | T08·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_E ✓ | RESOLVED (✓) | - |
| GTS-06 | CASE04 | T11·M_C | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_A ✗ | RESOLVED (✓) | - |
| GTS-07 | CASE05 | T06·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | RESOLVED (✗) | RESOLVED |
| GTS-08 | CASE06 | T12·M_D | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_A ✓ | RESOLVED (✓) | - |
| GTS-09 | CASE07 | T13·M_E | - (-) | - | NORMAL (✓) | - |
| GTS-10 | CASE08 | T14·M_C | - (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-11 | CASE09 | T15·M_B | REPORTS_BLOCKED (REPORTS_BLOCKED) | - | RESOLVED (✓) | - |
| GTS-12 | CASE10 | T16·M_E | REPORTS_BLOCKED (REPORTS_BLOCKED) | M_B ✓ | RESOLVED (✓) | - |
| GTS-13 | CASE11 | T17·M_A | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |
| GTS-14 | CASE12 | T18·M_C | - (REPORTS_BLOCKED) | - | NORMAL (✗) | - |
| GTS-15 | CASE13 | T19·M_D | REPORTS_ON_TRACK (REPORTS_ON_TRACK) | - | NORMAL (✓) | - |

## 4. LLM 해석 오답

| 응답 | 기대 | LLM | 문장 |
|---|---|---|---|
| P001 SIM-006 | CONFIRMS_COMPLETION  | REPORTS_ON_TRACK  | 도윤님이랑 같이 원인 찾아서 고쳤어요. 기간 필터 단위가 안 맞았던 거였고, 지금은 검색 정상으로 됩니다. |
| P002 SIM-017 | REPORTS_BLOCKED INTERNAL_ISSUE | REPORTS_BLOCKED EXTERNAL_DEPENDENCY | 규칙 초안은 만들었는데 사유 코드 두 개가 겹치는 건을 어떻게 분류할지 정해지지 않아서 막혀 있어요. 기획  |
| P002 SIM-029 | ACCEPTS_SUPPORT  | NOT_INFORMATIVE  | 앗, 제가 목요일에 운영 ingress에 CSP 헤더를 넣었는데 지도 타일 도메인을 img-src에 안 넣었 |
