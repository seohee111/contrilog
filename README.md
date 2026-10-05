# ContriLog

> 회사 프로젝트 팀의 회의록·문서 수정 이력·Task Board·메시지를 근거로, 팀원의 기여 Claim을 Evidence와 연결하고 업무 정체를 **후보 → 확인 → 확정 → 지원 → 해결**의 단계로 다루는 AI Team Manager.

## 빠른 시작 (제출·심사용)

- 공개 저장소: https://github.com/seohee111/contrilog (branch: `main`)
- 데이터: `data/`의 P001·P002는 팀이 만든 **synthetic 회사 프로젝트 데이터**입니다. 실제 개인정보는 없습니다.
  `data/ground_truth/`는 평가 전용이며 Agent 코드는 접근하지 않습니다(테스트로 강제).
- Python 3.10 이상 (개발·검증: Python 3.10.12)

```bash
git clone https://github.com/seohee111/contrilog.git && cd contrilog
# 제출 ZIP을 쓸 때: mkdir contrilog && unzip <ZIP> -d contrilog && cd contrilog
# (격리 테스트 일부가 프로젝트 폴더 이름 contrilog를 전제로 하므로 폴더 이름을 contrilog로 둡니다)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # pydantic, pytest, anthropic(선택 백엔드용 SDK)
.venv/bin/pip install -e .                  # contrilog 패키지 설치 (scripts·테스트가 import)
```

**답장 해석 LLM — Qwen3 32B + Ollama (로컬 실행, 기본값)**

```bash
ollama pull qwen3:32b          # Ollama 설치 후 한 번 (약 20GB)
ollama serve                   # http://localhost:11434 (이미 서비스로 떠 있으면 생략)
```

Ollama에 연결할 수 없으면 답장 해석은 규칙 해석기로 자동 대체됩니다. Claude API(`--provider anthropic`)는 선택 기능이며,
쓰려면 프로젝트 루트 `.env`에 `ANTHROPIC_API_KEY=...`를 둡니다(`.env`는 저장소·제출물에 포함하지 않음). 평가 수치는 Ollama Qwen3 32B 기준입니다.

| 목적 | 명령 |
|---|---|
| 데이터 검증 | `.venv/bin/python scripts/validate_data.py` |
| 자동화 테스트 (714개) | `.venv/bin/python -m pytest -q` |
| 웹 시연 (PM 대시보드) | `.venv/bin/python scripts/web_demo.py` → http://127.0.0.1:8790 (`--port`, `--host`, `--provider` 선택) |
| 전체 평가 (규칙/LLM/오라클 × P001·P002 × Memory OFF/ON) | `.venv/bin/python scripts/evaluate_all.py` → `reports/latest.md`, `reports/latest.json` |
| 전체 평가 (LLM 없이 규칙·오라클만) | `.venv/bin/python scripts/evaluate_all.py --no-llm` |

웹 시연은 시나리오 ①(P002 웹훅 서명 오류)을 고르고 [새로 시작] → [다음 단계]로 진행합니다. 지원 요청은 PM이 [지원 요청 승인]을 눌러야 전송됩니다.
`reports/`에는 보고서 수치의 근거가 된 평가 결과(2026-10-05)가 들어 있습니다. `evaluate_all.py`를 다시 실행하면 `reports/latest.*`가 새 결과로 바뀝니다.

## 원칙

- 사람의 기여도를 점수화하거나 순위를 매기지 않는다. (schema에 score/rank류 필드가 없고, 테스트로 강제한다)
- 활동량이 많다고 높은 기여로, 활동 기록이 없다고 바로 정체로 판단하지 않는다.
- 성격·근태·성실성 등 사람을 프로파일링하지 않는다.
- Memory는 사람이 아니라 **Agent 자신의 과거 판단과 그 결과**를 저장한다. (`AgentMemory`에는 member 필드가 없다)

## 현재 개발 단계

**Phase 0 — 데이터·평가 기반 구축 (완료)**

- Pydantic 데이터 모델, synthetic 프로젝트 P001(팀원 4명, 10개 Case), 입력/정답 분리, 검증 스크립트, unit test.

**Phase 1 — Time-aware 관찰 환경 + Tool layer (완료)**

- `as_of` 시점에 알 수 있었던 정보만 담는 `ProjectSnapshot`, Task 상태의 과거 시점 복원.
- 메인 정체 관리 Agent Tool 7종(관찰 4 + 행동 3)과 별도의 기여 주장 검증 보조 기능용 Claim Tool, 시뮬레이션 응답의 행동 후 공개, 지원 요청 Human-in-the-loop, Tool 호출 로그.

**Phase 2 — Contribution Claim 검증 Agent (완료, 결정적 구현)**

- `contrilog/agent/claim_verification/`: Claim → atomic 분해 → 검색 계획 → Tool 호출 → 근거 평가 → 판정.
  각 계층은 Protocol(`ClaimDecomposer`, `EvidenceSearchPlanner`, `EvidenceEvaluator`, `ClaimJudge`)로 분리되어 LLM 구현으로 교체 가능.
- Agent는 `session.tools`만 받는다. 실행 결과는 `ClaimVerificationRun`(atomic claim, 검색 단계, ContributionEvidence, AgentDecision, 평가용 요약).
- Ground Truth evidence를 관찰 가능성 기준으로 정리: static(공개 기록 ID) / interactive(행동 후 응답의 의미 기대값) / inaccessible(개인 DM).

**Phase 3 — Interactive Verification (완료, 결정적 구현)**

- PENDING의 이유를 구조화(`VerificationGap`)하고, gap별로 확인 대상·Task·질문을 정해 `CheckInTool`로 묻는다.
- 응답(RPL-*)을 같은 EvidenceEvaluator로 근거 평가하고 같은 Judge로 재판정한다. 실행 trace(`rounds`, `interactions`)를 남긴다.
- 시간은 환경 계층(`contrilog/runtime/`)이 진행시키며 Agent를 재개한다 (Agent는 시간을 옮길 수 없음).

**Phase 4 — Question-aware Simulation + Interactive Evaluation (완료)**

- 확인 질문의 목적을 구조화한 `QuestionIntent`(STATUS_CHECK / COMPLETION_CONFIRMATION / COUNTERPART_CONFIRMATION).
  Agent는 gap에서 의도를 정해 CheckInTool에 전달하고, 시뮬레이션은 질문 문장이 아니라 의도로 응답을 고른다.
- 응답 해석을 `ReplySemantic`으로 trace에 남기고, Ground Truth 기대값도 같은 enum으로 표현한다.
- `contrilog/evaluation/interactive_evaluation.py` + `scripts/evaluate_interactive.py`: 대상·Task·의도·응답 사용·의미 해석·최종 판정 채점.

**Phase 5 — Stagnation Detection / Verification / Intervention Agent (완료, 결정적 구현)**

- `contrilog/agent/stagnation/`: (Task, 담당자) 단위 상태 머신. 신호 조합 정책(`StagnationPolicy`)과 기준값(`StagnationThresholds`) 분리.
- 후보 → STATUS_CHECK → 막힘/정상 진행 → (막힘이면) 지원 후보 분석 → 지원 요청 PROPOSED → 사람 승인 → SENT → 후속 관찰 → RESOLVED.
- 환경: `contrilog/runtime/stagnation.py`(시간 진행), `contrilog/simulation/human.py`(사람 승인 시뮬레이션).
- 평가: `contrilog/evaluation/stagnation_evaluation.py` + `scripts/evaluate_stagnation.py`.

**Phase 6 — Memory + Feedback (완료, 결정적 구현)**

- `contrilog/memory/`: append-only 저장소(InMemory / JSONL), 상황 기준 검색, bounded adjustment.
- Stagnation Agent가 자기 판단의 사후 결과(TRUE_POSITIVE / FALSE_POSITIVE / UNRESOLVED / RESOLUTION_SUCCESS)를 기록하고,
  같은 상황(마감 구간·공백 비율·Task 상태·팀 맥락)에서만 허용 공백을 제한적으로 완화·복원한다. 사람 식별 정보는 쓰지 않는다.
- 팀 전체 휴지기(공개 기록이 60시간 이상 끊긴 구간)를 데이터에서 계산해 공백에서 뺀다.
- 평가: `contrilog/evaluation/memory_evaluation.py` + `scripts/compare_memory.py` (OFF / CONTEXT_ONLY / MEMORY_ONLY / ON 비교).
- 구현하지 않은 것: UI, LLM 호출, 외부 API, Agent framework, Vector DB.

**Phase 7 — 두 번째 평가 프로젝트 P002 (완료)**

- 회사 프로젝트 맥락의 독립 평가 데이터(아래 "Synthetic 프로젝트 P002"). 생성기 `scripts/build_p002_data.py`.
- P001도 회사 맥락(본업 병행 사내 TF)으로 텍스트를 바꿨다. ID·시각·사건 구조는 그대로라 모든 평가 결과가 이전과 같다.
- 평가 계층에서 P001 하드코딩을 제거했다. 평가 스크립트는 `[PROJECT_ID]` 인자를 받는다 (기본 P001).
- Ground Truth 확장: `candidate_expected`, `block_kind`, 팀 내 지원 없이 해결된 Block 허용, 응답 단위 의미 정답 `reply_labels.json`.

**Phase 8 — LLM 응답 해석기 · 전체 평가 · 시연 (완료)**

- `contrilog/llm/`: 팀원 답장의 의미(막힘/정상/완료, 내부/외부 요인)를 LLM이 JSON Schema 구조화 출력으로 분류한다.
  기본은 로컬 Qwen3 32B(Ollama, 팀 기록 외부 전송 없음), 선택으로 Claude API(`.env`의 `ANTHROPIC_API_KEY`).
  실패 시 규칙 해석기로 대체, 같은 문장은 `.cache/`에 캐시. 상태 전이·사람 승인·Memory 범위·RESOLVED 조건은 그대로 규칙.
- 프롬프트에는 범주 정의만 둔다. 평가 데이터의 표현 유형을 힌트로 담았던 초안(reply-v1, 46/46)은 폐기했고 reply-v2(44/46)가 공식 수치다.
- `scripts/evaluate_replies.py`(답장 46건 단독 비교), `scripts/evaluate_all.py`(규칙/LLM/오라클 × P001·P002 × Memory OFF/ON → `reports/latest.md`).
- `scripts/demo.py`: 한 Task의 관찰 → 확인 → Block → 지원 제안 → **터미널에서 PM 승인** → 해결 → Memory 시연.
- `scripts/web_demo.py` + `frontend/index.html`: 같은 흐름의 웹 PM 대시보드 (업무 상태 요약, 7단계 진행, 담당자 대화·AI 해석, PM 승인·거절 버튼, AI 판단 보정, 시연 모드).
  실행기 `contrilog/webui/`는 제안이 생기면 시간을 멈추고 사람의 결정을 기다린다 (HumanApprovalGate로만 적용).
- 대회 제출 문서는 경진대회 제출 패키지로 별도 제출하며, 공개 저장소에는 실행·검증에 필요한 소스코드와 데이터만 포함합니다.

## 폴더 구조

```
contrilog/
├── contrilog/                  # Python 패키지
│   ├── schemas/                # Pydantic 모델
│   │   ├── enums.py            #   ContributionType, ClaimStatus, StagnationState 등
│   │   ├── base.py             #   StrictModel(extra=forbid), ID 형식 타입
│   │   ├── project.py          #   Project, Milestone, Member
│   │   ├── activity.py         #   Meeting, MeetingUtterance, DocumentHistory, Task, Message
│   │   ├── contribution.py     #   ContributionClaim, ContributionEvidence
│   │   ├── agent_records.py    #   AgentDecision, AgentMemory
│   │   ├── simulation.py       #   SimulatedReply (check-in/지원 요청에 대한 팀원 응답)
│   │   ├── input_bundle.py     #   ProjectInput (Agent 입력 전체 묶음)
│   │   ├── snapshot.py         #   ProjectSnapshot (as_of 시점 관찰 묶음)
│   │   ├── tooling.py          #   OutboundAction, InboundReply, ToolCallLog
│   │   └── ground_truth.py     #   평가 전용. schemas/__init__에서 re-export 하지 않음
│   ├── data_access/            # Agent 입력 로더 (data/input/ 만 읽음), 입력 무결성 검사, snapshot.py
│   ├── simulation/             # 시뮬레이션 응답 로더, responder.py (행동 후에만 응답 예약·전달)
│   ├── agent/                  # (다음 단계) Agent 판단 로직
│   ├── tools/                  # Agent Tool layer: session, 관찰 Tool, 행동 Tool, 호출 로그
│   ├── memory/                 # (다음 단계) Agent Memory 저장소
│   └── evaluation/             # Ground Truth 로더 + 정답↔입력 무결성 검사 (평가 전용)
├── data/
│   ├── input/P001/             # Agent가 보는 데이터
│   ├── simulation/P001/        # Agent가 질문했을 때만 tool로 돌려줄 팀원 응답
│   ├── ground_truth/P001/      # 평가용 정답 (Agent 코드는 접근 금지)
│   └── agent_memory/           # (다음 단계) Agent Memory 저장 위치
├── frontend/                   # 웹 시연 화면 (index.html)
├── scripts/validate_data.py    # 전체 데이터 검증
└── tests/                      # unit test
```

### 입력과 정답의 분리

| 계층 | 읽는 데이터 | 금지 |
|---|---|---|
| `agent`, `tools`, `memory`, `data_access`, `simulation`, `schemas`(ground_truth.py 제외) | `data/input/`, (tool 경유) `data/simulation/` | `contrilog.evaluation`, `contrilog.schemas.ground_truth` import, 정답 디렉터리 경로 문자열 |
| `evaluation` | `data/ground_truth/` + 입력 | — |

`tests/test_isolation.py`가 다음을 검사합니다.

- AST로 Agent 쪽 모듈의 절대/상대/동적 import를 모두 풀어서 금지 모듈이 없는지
- Agent 쪽 모듈을 import하고 입력을 로드한 뒤 `sys.modules`에 평가 모듈이 올라오지 않는지 (subprocess)
- `sys.addaudithook`으로 `load_project_input` 실행 중 열린 파일이 모두 `data/input/P001/` 아래인지
- `input/P001`이 정답 디렉터리를 가리키는 심볼릭 링크이거나 `../`로 우회해도 로더가 거부하는지
- 입력·시뮬레이션 JSON에 정답 라벨(`IDEA`, `VERIFIED`, `CONFIRMED_BLOCK` 등), `CASE01`, `GTC-01` 같은 정답 ID, `expected`, `ground_truth` 같은 문자열이 없는지

## 데이터 구조

### 입력 (`data/input/P001/`)

| 파일 | 모델 | 주요 필드 |
|---|---|---|
| `project.json` | `Project` | 조직(organization), 기간, member_ids, milestones |
| `members.json` | `Member` | member_id(`M_A`), label(`A`), name, role |
| `meetings.json` | `Meeting` | 시작/종료, attendee_ids, agenda |
| `meeting_utterances.json` | `MeetingUtterance` | meeting_id, sequence, speaker_id, spoken_at, text |
| `document_history.json` | `DocumentHistory` | document_id/title/type, author_id, change_summary, diff_excerpt, chars_added/deleted |
| `tasks.json` | `Task` | assignee_ids, due_date, status, status_history, related_document_ids, depends_on_task_ids |
| `messages.json` | `Message` | channel, channel_type(CHANNEL/DIRECT_MESSAGE), sender/recipients, reply_to_message_id |
| `contribution_claims.json` | `ContributionClaim` | 팀원이 제출한 원문 Claim. 입력에서는 항상 `claimed_type=null`, `status=PENDING_VERIFICATION` |

Task 상태에는 일부러 `BLOCKED`가 없습니다. Block 여부는 Agent가 확인을 거쳐 판단할 대상이기 때문입니다.

### ID 체계

| 대상 | 형식 | 예 |
|---|---|---|
| 프로젝트 / 팀원 | `P\d{3}` / `M_[A-Z]` | `P001`, `M_C` |
| 회의 / 발언 | `MT\d{2}` / `UT-<회의>-\d{2}` | `MT05`, `UT-MT05-04` |
| 문서 / 리비전 | `DOC-*` / `REV-\d{3}` | `DOC-EVSEARCH`, `REV-055` |
| Task / 메시지 | `T\d{2}` / `MSG-\d{3}` | `T11`, `MSG-038` |
| Claim / atomic claim | `CLM-\d{2}` / `CLM-\d{2}-\d{2}` | `CLM-06`, `CLM-06-01` |
| Agent 출력 | `EV-*`, `DEC-*`, `MEM-*` | |

ID 형식은 정규식으로 schema에 고정되어 있어서, 잘못된 종류의 ID가 다른 필드에 들어가면 validation이 실패합니다.

### Agent 출력 모델 (다음 단계에서 생성)

- `ContributionEvidence`: 원본 기록(발언/리비전/Task/메시지) 또는 Agent가 받은 응답(`RPL-*`) ↔ Claim·기여 연결. 시뮬레이션 내부 ID(`SIM-*`)는 인용할 수 없음. `relation`은 SUPPORTS / CONTRADICTS / CONTEXT. 점수·가중치 없음.
- `ContributionClaim` (atomic): `parent_claim_id`와 `claimed_type`을 가진 분리된 Claim.
- `AgentDecision`: `as_of` 시점까지의 데이터로 내린 판단. Claim 검증, 기여 귀속, 정체 상태, check-in, 개입 제안, 후속 확인을 포함합니다.
- `AgentMemory`: 신호 패턴, 당시 판단, 사후 결과(CORRECT / FALSE_POSITIVE / …), 교훈. 사람 식별 필드는 없습니다.

### 시뮬레이션 (`data/simulation/P001/simulated_replies.json`)

Agent가 특정 시간 창 안에서 특정 팀원에게 check-in하거나 지원 요청을 했을 때만 돌려줄 자연어 응답입니다. 정답 라벨이 아니라 사람이 했을 법한 답변이며, 입력 로더는 이 파일을 읽지 않습니다.

### 평가용 정답 (`data/ground_truth/P001/`)

| 파일 | 모델 | 평가 대상 |
|---|---|---|
| `cases.json` | `GroundTruthCase` | Case 설명, 소속 정답 항목, 채점 시 주의점 |
| `contributions.json` | `GroundTruthContribution` | 누가 · 어떤 Contribution Type · expected evidence IDs |
| `claim_judgments.json` | `GroundTruthClaimJudgment` | 원본 Claim → atomic claim별 claimed_type, expected status, 지지/반박 evidence IDs |
| `stagnations.json` | `GroundTruthStagnation` | 실제 Block 여부, Block 시작 시각(허용 오차), 기대 상태 경로, 금지 상태, 기대 최종 상태, 기대 개입, 해결 시각, 후보화 기대(`candidate_expected`: True/False/None=채점 안 함), Block 종류(`block_kind`) |
| `reply_labels.json` | `GroundTruthReplyLabel` | 시뮬레이션 응답(SIM-*) 하나하나의 의미 정답과 Block 종류 (응답 해석기 단독 평가용). 모든 응답에 라벨이 있어야 한다 |

Expected evidence ID는 Agent가 만드는 `EV-*`가 아니라 **원본 기록 ID**입니다. 실행마다 Evidence ID가 달라져도 같은 기준으로 채점할 수 있습니다.

ClaimStatus 판정 기준:

- `VERIFIED`: 주장을 지지하는 Evidence가 있고 반박하는 Evidence는 없다.
- `INSUFFICIENT_EVIDENCE`: 주장자를 해당 행위와 연결하는 Evidence가 없다. 다른 사람의 관련 기록은 있을 수 있다.
- `CONFLICTING_EVIDENCE`: 지지하는 Evidence와 반박하는 Evidence가 함께 있다.

## Synthetic 프로젝트 P001

**TeamLens — 사내 협업 로그 대시보드** (신규 서비스 TF, 본업 병행, 2026-09-01 ~ 10-16)

팀원들이 본업과 병행하는 사내 TF라서 주간 회의가 월요일 저녁 7시이고, 업무 시간 외·연휴 직전 작업이 섞여 있다.

| 팀원 | 이름 | 역할 |
|---|---|---|
| A (`M_A`) | 윤서진 | 프론트엔드, 분석 실험 |
| B (`M_B`) | 한도윤 | 문서·일정 관리, 배포 서버 |
| C (`M_C`) | 박지후 | 백엔드 API |
| D (`M_D`) | 이하은 | 데이터 파이프라인, 발표 기획 |

데이터 규모: 회의 7회, 발언 49개, 문서 리비전 63개(문서 15개), Task 11개, 메시지 44개, Claim 9개, 시뮬레이션 응답 6개.

주요 일정: 매주 월요일 19시 회의, 9/11 설계 확정, 9/24~26 추석 연휴, 10/2 중간보고서(본부 리뷰), 10/9 한글날, 10/13 최종 발표(경영진 데모), 10/15 TF 회고용 기여 내역 제출.

### 10개 Case

| Case | 상황 | 기대 결과 | 핵심 근거 |
|---|---|---|---|
| 01 | A가 9/7 회의에서 단계형 정체 탐지를 제안했고, C가 9/9 설계 문서 3.2절에 반영함 | A / IDEA / VERIFIED | UT-MT02-03, UT-MT02-05, REV-005 |
| 02 | B가 발표 4단 구성을 제안했다고 Claim했지만, 9/28 회의의 최초 제안자는 D | B의 IDEA Claim: INSUFFICIENT_EVIDENCE (D / IDEA) | UT-MT05-04 |
| 03 | C의 GitHub 연동 작업이 9/15 403 이후 끊김. 회사 organization의 OAuth 앱 승인(보안팀) 대기로 프로젝트 끝까지 미해결 | C·T03: CONFIRMED_BLOCK | REV-014, MSG-009, UT-MT04-02 |
| 04 | D의 데이터셋 작업이 9일간 기록 없음. 실제로는 로컬에서 작업 중이었고 9/23 업로드함 | D·T04: NORMAL (False Positive 테스트) | REV-012 → REV-019/020, MSG-014 |
| 05 | A가 baseline F1 0.97을 보고 전처리 window 누수를 발견했고, D가 수정함 | A / REVIEW / VERIFIED (변경량 작음) | MSG-018, REV-029, REV-033 |
| 06 | B의 중간보고서 수정이 9회·2.5만자 이상이지만 대부분 참고문헌·서식·부록 정리 | B / EXECUTION / VERIFIED (순위·중요도 판단 금지) | REV-018 등 9건, MSG-016 |
| 07 | C가 Dashboard API를 배포하던 중 CORS 실패. B가 nginx OPTIONS 405를 찾아 해결 | C / EXECUTION, B / SUPPORT (B는 Claim 안 함) | REV-022, MSG-020~023, REV-031 |
| 08 | Timeline UI는 D가 제안하고 A가 구현함. A는 "아이디어 제안 + 구현"으로 Claim | D / IDEA / VERIFIED, A / EXECUTION / VERIFIED, A의 IDEA Claim: CONFLICTING_EVIDENCE | UT-MT03-04/05 vs REV-013, MSG-008 |
| 09 | B가 데모 캡처(10/5)가 기능 완료(10/9)보다 앞선 일정 충돌을 발견하고 순서를 조정함 | B / COORDINATION / VERIFIED | MSG-028, REV-040, UT-MT06-01 |
| 10 | 마감 직전 C의 Claim 검증 API가 Evidence 검색 0건 문제로 정체됨(ms/s 단위 불일치). B의 지원으로 해결 | STAGNATION_CANDIDATE → CONFIRMED_BLOCK → B 지원 → RESOLVED | REV-055, MSG-038~040, REV-058 |

Case 사이의 일관성:

- C는 T03이 막혀 있는 동안 T06(Case 07)·T11(Case 10)에서는 정상적으로 활동합니다. 그래서 정체는 (팀원, Task) 단위로 판단해야 합니다.
- Case 03과 Case 04의 활동 감소는 같은 주(9/15~9/22)에 일어납니다. 겉보기 신호는 비슷하지만 확인 응답에 따라 결과가 갈립니다.
- 추석 연휴(9/24~26) 동안은 전원의 활동이 줄어듭니다. 이 감소를 정체 근거로 쓰면 안 됩니다.

## Synthetic 프로젝트 P002

**ShipTrack — 배송 지연 사전 알림 서비스** (물류플랫폼실 배송경험팀, 정규 업무, 2026-04-27 ~ 06-19)

P001과 독립적으로 만든 두 번째 평가 데이터다. 사람·Task·기록·문장을 새로 썼다 (P001 Case 복사 없음).
평일 주간 근무 팀이라 주말·근로자의 날·회사 지정 휴무(5/4)·어린이날·대체공휴일(5/25)·지방선거(6/3)에는 공개 기록이 없다.

| 팀원 | 이름 | 역할 |
|---|---|---|
| A (`M_A`) | 문가은 | PM |
| B (`M_B`) | 장현우 | 백엔드 (수집 API·택배사 연동·DB) |
| C (`M_C`) | 오수빈 | 앱·웹 프론트엔드 |
| D (`M_D`) | 신재민 | 데이터·ML |
| E (`M_E`) | 류다인 | 플랫폼·QA |

데이터 규모: 회의 8회, 발언 53개, 리비전 90개(문서 26개), Task 20개, 메시지 50개(DM 2개), Claim 4개,
시뮬레이션 응답 40개(상태 확인 24 · 지원 요청 16), 사람 결정 9개(승인 4 · 거절 5), 정체 정답 15개.

| Case | 상황 (인수인계 11.1 항목) | 정답 |
|---|---|---|
| 01 | D·T05 모델 학습 중 기록 공백 (정상 장시간 공백) | NORMAL, 응답 REPORTS_ON_TRACK |
| 02 | C·T07 피그마 / E·T09 로컬 부하 테스트 / A·T10 노션 작성 (오탐 반복) | 3건 모두 NORMAL |
| 03 | B·T08 웹훅 서명 401 — 원인은 E의 게이트웨이 본문 변환 (실제 Block, 지원자 여럿) | RESOLVED, 지원자 E |
| 04 | C·T11 운영에서만 지도 회색 — 원인은 E의 CSP 헤더. 단어 겹침은 A가 최대 (잘못된 지원자 후보) | RESOLVED, 지원자 E |
| 05 | B·T06 외부 업체 운영 키 미발급, '안내 문구 수정' 리비전 (해결되지 않는 Block) | CONFIRMED_BLOCK, RESOLVED 금지 |
| 06 | D·T12 사유 분류 기준 부재 → 지원 제안을 사람이 거절 → 회의에서 해결 | RESOLVED, 제안 대상 A, 전송 금지 |
| 07 | E·T13 사외 교육 중 응답 없음 (응답 없는 Candidate) | NORMAL, 후보 여부 채점 안 함 |
| 08 | C·T14 iOS 푸시 — 첫 확인에 무응답, 이후 공개 채널에 막힘 보고 (응답 없는 실제 Block) | RESOLVED, 지원자 E |
| 09 | B·T15 "막혔다기보다는요…" 다른 팀 스키마 확정 대기 (복합 응답, 외부 의존) | RESOLVED, 지원 요청 없음 |
| 10 | E·T16 "문제 없을 줄 알았는데…" V7 down 실패 (복합 응답) | RESOLVED, 지원자 B |
| 11 | A·T17 "남은 이슈는 0건" (복합 응답) | NORMAL, Block 확정 금지 |
| 12 | T18 공동 담당(E 주, C 부) — C가 디바이스팜 결재 대기 (여러 담당자) | C·T18 RESOLVED (외부) |
| 13 | D·T19 Case01과 같은 종류의 공백 재발 (Memory 효과 확인) | NORMAL, 후보 여부 채점 안 함 |
| 14~17 | Claim: E SUPPORT / C EXECUTION+IDEA(아이디어는 A) / D EXECUTION / A COORDINATION | VERIFIED 4, INSUFFICIENT 1 |

주의: 정답은 Agent가 맞힐 수 있는지와 무관하게 실제 상황대로 적었다. 데이터 작성자가 현재 규칙(단서 어휘·용어 겹침)을 알고 있었으므로,
응답 문장과 기록은 '사람이 실제로 쓸 법한 표현'을 기준으로 썼고 규칙을 통과·실패시키려고 고치지 않았다. 그래도 같은 팀이 만든 데이터라는 한계가 있다.
P002 결과는 테스트로 고정하지 않는다 (P002에 맞춘 튜닝 방지).

```bash
.venv/bin/python scripts/build_p002_data.py        # P002 JSON 재생성 (생성기와 파일이 다르면 tests/test_p002.py 실패)
.venv/bin/python scripts/validate_data.py P002
.venv/bin/python scripts/evaluate_stagnation.py P002
.venv/bin/python scripts/compare_memory.py P002
```

## Time-aware 관찰 환경 (Phase 1)

```python
from datetime import datetime, timedelta, timezone
from contrilog.data_access import get_project_snapshot
from contrilog.tools import ToolSession

KST = timezone(timedelta(hours=9))
snap = get_project_snapshot("P001", as_of=datetime(2026, 10, 3, 17, tzinfo=KST))  # 그 시점 정보만

s = ToolSession("P001", as_of=datetime(2026, 10, 8, 10, tzinfo=KST))
s.tools["ProjectStatusTool"].get_status(task_id="T11")            # 상태·마감·마지막 활동 (판단 없음)
s.tools["DocumentHistoryTool"].search(query="기간 필터", author_id="M_C")
a = s.tools["CheckInTool"].send(task_id="T11", member_id="M_C", question="진행 상황이 궁금해요")
s.advance_to(datetime(2026, 10, 8, 11, tzinfo=KST))                # 시간은 앞으로만
s.tools["InboxTool"].list_replies()                                # 도착한 응답만
p = s.tools["SupportRequestTool"].propose(task_id="T11", about_member_id="M_C", supporter_id="M_B", message="...")
s.human.approve(p.actions[0].action_id, approver_id="M_A")         # 사람만 승인 가능
s.tools["SupportRequestTool"].send(action_id=p.actions[0].action_id)
s.call_log                                                          # ToolCallLog 목록 (원문 없이 ID만)
```

### 공개 규칙

| 기록 | 보이는 조건 |
|---|---|
| Project / Member | 항상 |
| 회의 + 발언 | 회의 종료 후 (`ended_at <= as_of`) |
| 문서 리비전 / 메시지 / Claim | 각 시각 `<= as_of` |
| Task | `created_at <= as_of`, 상태·마감일과 각 이력은 as_of까지 재구성, 아직 없는 문서·Task 링크 제거 |
| 개인 DM | **Agent에게 항상 비공개** (접근 정책 `data_access/access_policy.py`. 원본 데이터에는 남아 있음) |
| check-in·지원 요청 응답 | Agent가 보낸 뒤, 응답 지연이 지나야 InboxTool에 나타남 |

### Tool 목록

| Tool | operation | 반환 (모든 항목에 원본 `source_id`) |
|---|---|---|
| ProjectStatusTool | `get_status` | Task 상태·마감(변경 이력 포함)·담당자·상태 이력·마지막 활동·최근 리비전, 팀원별 마지막 기록 |
| MeetingSearchTool | `search` | 발언자, 시각, 회의, 발언 원문 (`UT-*`) |
| DocumentHistoryTool | `search` | 작성자, 시각, 문서, section(현재 데이터에 없음), 변경 요약·diff (`REV-*`) |
| MessageSearchTool | `search` | 공유 프로젝트 채널 메시지만: 채널, 발신자, 시각, 본문, 스레드 (`MSG-*`) |
| ClaimTool | `list_claims`, `register_atomic_claim` | 원본 Claim(`SUBMITTED`)과 Agent가 분리한 atomic claim(`AGENT_DERIVED`) |
| CheckInTool | `send`, `list_sent` | 보낸 질문 (`ACT-*`, 즉시 SENT) |
| SupportRequestTool | `propose`, `send`, `list_requests` | 지원 요청 (PROPOSED → 사람이 APPROVED/REJECTED → SENT) |
| InboxTool | `list_replies` | 도착한 응답 (`RPL-*`) |

## Claim 검증 Agent (Phase 2)

```python
from contrilog.tools import ToolSession
from contrilog.agent.claim_verification import ClaimVerificationAgent

session = ToolSession("P001", as_of=datetime(2026, 10, 16, tzinfo=KST))
agent = ClaimVerificationAgent(tools=session.tools)
run = agent.verify_claim(claim_id="CLM-06")
for r in run.atomic_results:   # 평가용 machine-readable 요약
    print(r.atomic_claim_id, r.predicted_contribution_type, r.predicted_status,
          r.supporting_source_ids, r.contradicting_source_ids, r.confidence)
```

판정 규칙: 반박+지지 → CONFLICTING / 반박만 → INSUFFICIENT / 직접 근거+유형별 충분 조건 → VERIFIED /
간접 근거만 또는 실행 완료 미확인 → PENDING / 근거 없음 → INSUFFICIENT.
INSUFFICIENT_EVIDENCE는 "기여하지 않았다"가 아니라 "공유된 기록으로 확인되지 않는다"는 뜻이다.
근거의 개수·분량은 판정과 확신도에 쓰지 않는다.

## Interactive Verification (Phase 3)

```python
from contrilog.runtime import run_interactive_verification

session = ToolSession("P001", as_of=...)
agent = ClaimVerificationAgent(tools=session.tools)
run = run_interactive_verification(session, agent, "CLM-50")   # verify → (시간 진행) → continue → finalize
for rd in run.rounds:          # INITIAL → REEVALUATION(응답 수신) → FINAL(대기 종료)
    print(rd.phase, rd.as_of, [s.status for s in rd.atomic_states], [g.kind for g in rd.gaps])
for i in run.interactions:     # 누구에게, 어떤 Task로, 무엇을 물었고, 어떤 응답을 받았는가
    print(i.target_member_id, i.task_id, i.question, i.reply_ids, i.status)
```

| gap | 의미 (Judge의 PENDING 분기) | 확인 대상 |
|---|---|---|
| `COMPLETION_UNCONFIRMED` | 실행 직접 근거는 있으나 완료 근거 없음 | 관련 Task 담당자 (주장자 우선) |
| `DIRECT_EVIDENCE_MISSING` | 간접 근거만 있음 | 행위의 상대방 (Claim이 지목한 팀원 → 간접 근거의 주체), 그 사람이 담당한 관련 Task로 질문 |

종료 조건: 같은 (atomic claim, gap, 대상, Task) 질문 반복 금지 · atomic claim당 질문 2회(gap 종류 수) ·
대상이 없거나 응답으로도 해결되지 않으면 PENDING 유지 · 환경의 대기 시간이 끝나면 `NO_REPLY`로 닫음.

## Question-aware Simulation / Interactive Evaluation (Phase 4)

| gap (왜 묻는가) | question_intent (무엇을 확인하는가) | 응답 해석 (ReplySemantic) |
|---|---|---|
| `COMPLETION_UNCONFIRMED` | `COMPLETION_CONFIRMATION` | `CONFIRMS_COMPLETION` / `REPORTS_INCOMPLETE` / `NOT_INFORMATIVE` |
| `DIRECT_EVIDENCE_MISSING` | `COUNTERPART_CONFIRMATION` | `CONFIRMS_COUNTERPART` / `DENIES_COUNTERPART` / `NOT_INFORMATIVE` |
| (일반 진행 확인, 향후 Stagnation) | `STATUS_CHECK` | |

시뮬레이션 응답 선택: trigger · 응답자 · 대상 · Task · 시간 창 · **question_intent**. 질문 문장은 보지 않는다.
같은 사람·같은 Task·같은 시각이라도 의도가 다르면 다른 응답이 오고, 해당 의도의 응답이 없으면 응답이 없다.

```bash
.venv/bin/python scripts/evaluate_interactive.py   # 시나리오별 채점(JSON) + 개수 집계 (성능 추정치 아님)
```

## Stagnation Agent (Phase 5)

```python
from contrilog.agent.stagnation import StagnationAgent
from contrilog.runtime import run_stagnation_monitoring
from contrilog.simulation.human import HumanDecisionSimulator

session = ToolSession("P001", as_of=datetime(2026, 9, 1, 9, tzinfo=KST))
agent = StagnationAgent(tools=session.tools)
run_stagnation_monitoring(session, agent, until=datetime(2026, 10, 16, 21, tzinfo=KST),
                          human=HumanDecisionSimulator("P001"))
for run in agent.runs():     # StagnationRun: 신호·전이·질문·지원 분석·승인·후속 관찰·timeline
    print(run.task_id, run.assignee_id, [s.value for s in run.state_sequence])
```

후보 조건(모두 충족): 시작된 미완료 Task · 마감 7일 이내 · 마지막 Task 기록 이후 `clamp(0.5×남은 시간, 24h, 72h)` 이상 ·
미완료 선행 Task 대기 아님 · 최근 '정상 진행' 응답 없음(마감 24h 전까지) · 최근 48h 안에 묻지 않음.
RESOLVED는 지원 요청 이후(또는 Block 확정 이후) Task 문서의 수정 리비전이나 Task 상태 진전이 관찰되어야 한다.

```bash
.venv/bin/python scripts/evaluate_stagnation.py   # 프로젝트 전체 연속 모니터링 → Case03/04/10 채점 + 라벨 없는 후보
```

## Memory + Feedback (Phase 6)

```python
from contrilog.agent.stagnation import StagnationAgent, FeedbackSettings
from contrilog.memory import JsonlMemoryStore

agent = StagnationAgent(tools=session.tools,
                        feedback=FeedbackSettings(store=JsonlMemoryStore("data/agent_memory/P001.jsonl")))
# feedback=None이면 Memory OFF (기존 정책 그대로)
```

| 피드백 | 언제 | 보정 근거 |
|---|---|---|
| TRUE_POSITIVE | 후보 → 상태 확인 → 막힘 응답 | -1 (완화를 기본값 쪽으로 되돌림) |
| FALSE_POSITIVE | 후보 → 상태 확인 → 정상 진행 응답 | +1 |
| UNRESOLVED | 후보 → 응답 없음·불명확 → 종료 | 0 (상태 확인 불가) |
| RESOLUTION_SUCCESS | 지원 개입 → 실제 해결 근거 관찰 | 정책 보정 없음 (선정 근거 종류의 결과 기록) |

보정 = clamp(floor(같은 상황의 net) × 12h, 0, 24h), 마감 24h 이내는 보정 없음. 판단 시각 이전에 만들어진 Memory만 쓴다.

```bash
.venv/bin/python scripts/compare_memory.py   # 모드별 전체 재생 비교 + Memory 검증 항목
```

## 실행 / Validation

```bash
cd contrilog
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # pydantic, pytest 만 설치

.venv/bin/python scripts/validate_data.py   # schema + 참조 무결성 + 정답↔입력 연결 검사
.venv/bin/python -m pytest -v               # unit test
```

`validate_data.py`는 오류가 있으면 각 오류를 출력하고 exit code 1로 종료합니다.

| 테스트 파일 | 검사 내용 |
|---|---|
| `tests/test_schemas.py` | 모든 JSON의 schema 통과, enum 외 값 거부, extra 필드·naive datetime·잘못된 ID 거부, score/rank/프로파일링 필드 부재, Agent 출력 모델 불변식, 정답 모델 내부 규칙 |
| `tests/test_referential_integrity.py` | 입력·시뮬레이션의 참조 ID 유효성, 깨진 참조와 판단이 섞인 입력 Claim을 검사기가 잡아내는지 |
| `tests/test_ground_truth.py` | expected evidence ID 존재, 10개 Case별 기대값, Block 구간에 해당 Task 리비전이 없는지 |
| `tests/test_isolation.py` | 입력/정답 분리 (위 "입력과 정답의 분리" 참고) |
| `tests/test_snapshot.py` | 모든 기록이 자기 시각 1초 전엔 없고 그 시각엔 있는지, 12시간 간격 snapshot 전체에 as_of 이후 시각 문자열이 없는지, Task 상태 복원 |
| `tests/test_future_leak.py` | Case03/04/10 확인·업로드·해결 이전 누출 차단, check-in 후에만 응답, 검색 Tool별 미래 기록 차단 |
| `tests/test_tools.py` | 원본 ID 추적성, 판단 필드 부재, Human-in-the-loop, 원본/atomic Claim 구분, 호출 로그 |
| `tests/test_pre_agent_fixes.py` | 마감일 이력 복원, RPL-* Evidence 허용·SIM-* 거부, 개인 DM 접근 차단(검색어·필터·전체 조회·파생 정보·로그) |
| `tests/test_claim_agent.py` | Ground Truth가 있는 모든 Claim 비교, Case별 결과, Case08 근거 분리, 근거 ⊂ 검색 결과, 호출 로그 |
| `tests/test_claim_agent_boundary.py` | Agent 코드 정적 검사(금지 import·동적 접근·session 내부·하드코딩 ID), 실행 중 파일 미오픈 |
| `tests/test_claim_agent_generalization.py` | Claim ID 변경, 다른 표현의 새 Claim, 처음 보는 주제, 무관한 기록 추가, 활동량 증가 |
| `tests/test_claim_agent_time.py` | 결과물 생성 전/후 판정, 회의 종료 전 비공개, 미제출 Claim 거부, 근거 시각 ≤ as_of |
| `tests/test_ground_truth_observability.py` | 기대 근거의 접근 가능성, DM → inaccessible, interactive 기대값의 도달 가능성 |
| `tests/test_interactive_verification.py` | PENDING→CheckIn→VERIFIED, 응답 부족 시 PENDING 유지, 대상 선택, 시간 누출, DM 미사용, 반복·상한 |
| `tests/test_interactive_generalization.py` | Case ID·Claim ID·팀원 이름 변경, 새 시나리오(실행·지원), noise |
| `tests/test_interactive_boundary.py` | 허용 operation, Agent·runtime의 Ground Truth/시뮬레이션 비의존, 파일 접근 출처, trace의 Ground Truth 미포함 |
| `tests/test_interactive_ground_truth.py` | interactive Ground Truth 기대값(평가 계층 전용)으로 행동 채점 |
| `tests/test_question_aware_simulation.py` | 같은 사람·Task·시각의 의도별 다른 응답, 문구 무관, 의도 불일치 시 응답 없음, 지원 Claim의 상대방 확인, 미완료·부인·무관 응답 해석 |
| `tests/test_interactive_evaluation.py` | 평가기 채점, 의도 mutation 검출, Claim ID·Case ID·이름·문구·noise 변경, 새 시나리오 4종 |
| `tests/test_stagnation_agent.py` | Case03/04 분기, Case10 E2E 순서, 지원자 근거, 승인 후 전송, 후속 근거 후 RESOLVED, 정책·해석 단위 규칙 |
| `tests/test_stagnation_evaluation.py` | 평가기 채점(Case03/04/10), 라벨 없는 후보 보고, 오해석·근거 없는 해결 검출 |
| `tests/test_stagnation_generalization.py` | Case·Task·Member ID 변경, 이름 변경, noise, 새 막힘·정상 진행 시나리오, Case04 변형 |
| `tests/test_stagnation_time.py` | 응답·승인·지원 응답·해결 근거의 시간 누출 방지 |
| `tests/test_stagnation_boundary.py` | 허용 operation, 정적 검사 범위, 실행 중 파일 접근 출처, DM 미포함 |
| `tests/test_memory_store.py` | append-only·영속 저장소, 상황 기준·과거 한정 검색, bounded adjustment |
| `tests/test_memory_agent.py` | OFF 동일성, Case04 FP·Case03/10 TP·RESOLUTION_SUCCESS Memory, applied_memory_ids, 휴지기 맥락, 실제 Block 보존 |
| `tests/test_memory_sequence.py` | X(FP) → Y(다른 사람, 같은 상황) 질문 감소 → Z(실제 막힘) 탐지, 담당자·ID·이름·Task ID·noise 변경, 상황이 다르면 미적용 |
| `tests/test_memory_time.py` | 미래 Memory 미사용, 결정성, 실행 중 Ground Truth 미접근, Memory 파일은 memory 계층만 씀 |
| `tests/test_memory_evaluation.py` | 모드별 비교표(실제 결과 고정), 실제 Block·Case04 보존, 탐지 지연, 감소의 출처 |
| `tests/test_tool_isolation.py` | Tool 전체 실행 중 정답 파일 미오픈·평가 모듈 미로드, 관찰 Tool은 시뮬레이션 파일도 열지 않음 |
