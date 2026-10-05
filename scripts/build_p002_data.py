"""Synthetic 평가 프로젝트 P002 생성기 (입력 · 시뮬레이션 · Ground Truth).

사용법: python scripts/build_p002_data.py   → data/{input,simulation,ground_truth}/P002/*.json 을 다시 쓴다.

P002는 P001과 독립적인 두 번째 평가용 프로젝트다 (P001의 Case를 복사하지 않았다).
  ShipTrack — 배송 지연 사전 알림 서비스 / 물류플랫폼실 배송경험팀 (정규 업무, 평일 주간 근무)
  2026-04-27 ~ 06-19, 팀원 5명. 근로자의 날·회사 지정 휴무(5/4)·어린이날·대체공휴일(5/25)·지방선거(6/3)와
  주말 동안에는 팀 전체 공개 기록이 없다 (휴일을 외부 지식으로 넣지 않고, 기록 공백으로만 드러난다).

작성 원칙
- 기록은 '이 팀이 실제로 남겼을 법한' 공개 기록이다. 문제의 원인과 해결자는 사람이 읽으면 연결할 수 있지만,
  문제 보고와 같은 단어를 쓴다는 보장은 없다 (지원자 선정의 의미 이해를 평가하기 위함).
- Ground Truth는 Agent가 맞힐 수 있는지와 무관하게 실제 상황대로 적는다.
  현재 규칙 기반 Agent가 처리하지 못하는 상황(응답 없는 실제 Block, 부 담당자의 Block, 복합 응답 등)도 포함한다.
- 이 데이터는 Agent 코드 작성자와 같은 팀이 만들었다. 결과를 일반 성능으로 해석하지 않는다.

기록 번호(REV-*, MSG-*)는 시각 순서로 자동 부여되고, Ground Truth는 기록 키로 참조한 뒤 번호로 바뀐다.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
PID = "P002"
ROOT = Path(__file__).resolve().parents[1] / "data"


def ts(m, d, h, mi=0) -> str:
    return datetime(2026, m, d, h, mi, tzinfo=KST).isoformat()


# ====================================================================== 프로젝트 · 팀원
PROJECT = {
    "project_id": PID,
    "name": "ShipTrack — 배송 지연 사전 알림 서비스",
    "organization": "물류플랫폼실 배송경험팀 (2026 2분기)",
    "description": "택배사 배송 이벤트를 수집해 지연이 예상되는 주문을 고객에게 먼저 알려 주는 서비스. "
                   "택배사 연동, 지연 예측 모델, 알림 설정·배송 추적 화면, 운영 인프라를 포함한다.",
    "start_date": "2026-04-27",
    "end_date": "2026-06-19",
    "member_ids": ["M_A", "M_B", "M_C", "M_D", "M_E"],
    "milestones": [
        {"milestone_id": "MS01", "name": "요구사항·설계 확정", "due_date": "2026-05-08"},
        {"milestone_id": "MS02", "name": "사내 베타 오픈", "due_date": "2026-05-29"},
        {"milestone_id": "MS03", "name": "고객사 파일럿 오픈", "due_date": "2026-06-12"},
        {"milestone_id": "MS04", "name": "정식 릴리스 및 회고", "due_date": "2026-06-19"},
    ],
}

MEMBERS = [
    ("M_A", "A", "문가은", "PM (요구사항·일정·고객사 커뮤니케이션)"),
    ("M_B", "B", "장현우", "백엔드 (이벤트 수집 API·택배사 연동·DB)"),
    ("M_C", "C", "오수빈", "앱·웹 프론트엔드"),
    ("M_D", "D", "신재민", "데이터·ML (지연 예측·사유 분류)"),
    ("M_E", "E", "류다인", "플랫폼·QA (CI/CD·인프라·테스트)"),
]

DOCS = {
    "DOC-PRD": ("요구사항 정의서", "DESIGN_DOC"),
    "DOC-SCHEDULE": ("프로젝트 일정표", "SCHEDULE"),
    "DOC-EVENTAPI": ("배송 이벤트 수집 API", "CODE"),
    "DOC-MIGRATION": ("DB 마이그레이션", "CODE"),
    "DOC-CARRIER": ("택배사 연동 어댑터", "CODE"),
    "DOC-WEBHOOK": ("배송 상태 웹훅 수신", "CODE"),
    "DOC-SETTLE": ("정산 리포트 배치", "CODE"),
    "DOC-APPBASE": ("앱 기본 구조", "CODE"),
    "DOC-SETTINGSUI": ("알림 설정 화면", "CODE"),
    "DOC-TRACKMAP": ("배송 추적 지도 화면", "CODE"),
    "DOC-PUSH": ("앱 푸시 권한 처리", "CODE"),
    "DOC-FEATURE": ("지연 예측 피처 파이프라인", "CODE"),
    "DOC-MODEL": ("지연 예측 모델 노트북", "NOTEBOOK"),
    "DOC-REASON": ("지연 사유 분류 규칙", "CODE"),
    "DOC-CICD": ("CI/CD 파이프라인", "CONFIG"),
    "DOC-GATEWAY": ("API 게이트웨이 설정", "CONFIG"),
    "DOC-APPSIGN": ("앱 서명·배포 설정", "CONFIG"),
    "DOC-INGRESS": ("운영 ingress 설정", "CONFIG"),
    "DOC-LOADTEST": ("부하 테스트", "CODE"),
    "DOC-MONITOR": ("모니터링 대시보드", "CONFIG"),
    "DOC-RUNBOOK": ("장애 대응 런북", "REPORT"),
    "DOC-ROLLBACK": ("롤백 스크립트", "CODE"),
    "DOC-E2E": ("배송 알림 E2E 테스트", "CODE"),
    "DOC-ONBOARD": ("파일럿 고객 온보딩 가이드", "REPORT"),
    "DOC-PILOTFB": ("파일럿 고객 피드백 정리", "REPORT"),
    "DOC-RETRO": ("프로젝트 회고", "REPORT"),
}

# ====================================================================== 문서 리비전
REVS = []


def rev(key, doc, author, when, summary, diff, added, deleted=0):
    title, dtype = DOCS[doc]
    REVS.append(dict(key=key, document_id=doc, document_title=title, document_type=dtype, author_id=author,
                     edited_at=when, change_summary=summary, diff_excerpt=diff, chars_added=added,
                     chars_deleted=deleted))


# ---- 1주차 (4/27 ~ 4/30, 5/1·5/4 휴무, 5/5 어린이날)
rev("a_prd_toc", "DOC-PRD", "M_A", ts(4, 27, 16, 20), "요구사항 정의서 초안 목차",
    "1. 배경 / 2. 사용자 시나리오 / 3. 기능 요구사항 / 4. 비기능 요구사항 / 5. 일정", 820)
rev("a_sched", "DOC-SCHEDULE", "M_A", ts(4, 27, 17, 0), "프로젝트 일정표 작성",
    "5/8 요구사항·설계 확정 / 5/29 사내 베타 / 6/12 고객사 파일럿 / 6/19 정식 릴리스\n주간 회의: 매주 월요일 10:30", 1260)
rev("b_event_skel", "DOC-EVENTAPI", "M_B", ts(4, 28, 11, 30), "이벤트 수집 API 스켈레톤 (POST /events)",
    "@router.post(\"/events\")\nasync def ingest(event: DeliveryEvent): ...", 2140)
rev("e_ci_wf", "DOC-CICD", "M_E", ts(4, 28, 15, 0), "GitHub Actions 빌드·테스트 워크플로",
    "jobs:\n  test:\n    runs-on: ubuntu-latest\n    steps: [checkout, setup-python, pytest]", 1380)
rev("c_app_tabs", "DOC-APPBASE", "M_C", ts(4, 28, 16, 30), "앱 프로젝트 생성 및 탭 구조",
    "<Tab.Navigator> 홈 / 배송 / 알림 / 설정 </Tab.Navigator>", 3020)
rev("d_feat_explore", "DOC-FEATURE", "M_D", ts(4, 29, 14, 0), "배송 이벤트 로그 탐색 (2025년 1~12월)",
    "events = load_events(\"2025-01\", \"2025-12\")  # 1,284만 건, 택배사 4곳", 2650)
rev("b_mig_v1", "DOC-MIGRATION", "M_B", ts(4, 29, 17, 20), "V1~V3 마이그레이션: shipments, delivery_events 테이블",
    "CREATE TABLE delivery_events (id bigserial, invoice_no text, status text, occurred_at timestamptz, ...)", 1890)
rev("c_app_sso", "DOC-APPBASE", "M_C", ts(4, 29, 17, 40), "사내 SSO 로그인 연동",
    "const { token } = await sso.login(); api.setToken(token)", 1730)
rev("a_prd_func", "DOC-PRD", "M_A", ts(4, 29, 18, 10), "사용자 시나리오·기능 요구사항 초안",
    "3.1 지연 예상 시 고객에게 앱 푸시 또는 알림톡 발송\n3.2 고객이 알림 채널과 빈도를 설정", 4120)
rev("e_ci_stg", "DOC-CICD", "M_E", ts(4, 30, 11, 0), "스테이징 배포 잡 추가 (main 머지 시)",
    "deploy-staging:\n  needs: test\n  if: github.ref == 'refs/heads/main'", 960)
rev("d_feat_label", "DOC-FEATURE", "M_D", ts(4, 30, 15, 30), "지연 라벨 생성 (약속 도착일 +1일 초과)",
    "df[\"delayed\"] = (df.delivered_at.dt.date - df.promised_date).dt.days >= 1", 1120)
rev("b_event_dedup", "DOC-EVENTAPI", "M_B", ts(4, 30, 16, 40), "이벤트 스키마 검증·중복 제거",
    "dedup_key = (invoice_no, status, occurred_at)", 1540)
rev("c_app_home", "DOC-APPBASE", "M_C", ts(4, 30, 18, 0), "로그인 후 홈 화면 더미 데이터",
    "const MOCK_SHIPMENTS = [...]", 1210)

# ---- 2주차 (5/6 ~ 5/8)
rev("e_gw_route", "DOC-GATEWAY", "M_E", ts(5, 6, 9, 30), "스테이징 API 게이트웨이 라우팅 설정",
    "routes:\n  - path: /api/*\n    upstream: shiptrack-api\n  - path: /webhooks/*\n    upstream: shiptrack-api", 880)
rev("d_feat_v1", "DOC-FEATURE", "M_D", ts(5, 6, 14, 0), "피처 추출 1차: 택배사·지역·요일·물량",
    "features = [carrier, region, weekday, daily_volume, hub_backlog]", 2380)
rev("a_prd_review", "DOC-PRD", "M_A", ts(5, 6, 15, 0), "리뷰 반영: 알림 채널·빈도 요구사항",
    "3.2 알림 채널: 앱 푸시 / 알림톡, 빈도: 즉시 / 하루 1회 묶음", 1460, 320)
rev("c_app_401", "DOC-APPBASE", "M_C", ts(5, 7, 11, 0), "토큰 만료 처리 (401 응답 시 토큰 재발급 후 재시도)",
    "if (res.status === 401) { await refreshToken(); return retry(req) }", 980)
rev("e_ci_health", "DOC-CICD", "M_E", ts(5, 7, 15, 20), "DB 서비스 컨테이너 헬스체크 대기 추가 (통합 테스트 타임아웃 수정)",
    "services:\n  postgres:\n    options: --health-cmd pg_isready --health-interval 5s", 420)
rev("a_prd_nfr", "DOC-PRD", "M_A", ts(5, 7, 16, 30), "비기능 요구사항 추가 (지연 감지 후 5분 이내 알림)",
    "4.1 지연 예측 결과 생성 후 5분 이내 알림 발송", 640)
rev("a_prd_reason", "DOC-PRD", "M_A", ts(5, 8, 11, 0), "지연 사유 코드 정의 추가",
    "3.4 지연 사유 코드: 기상 / 물량 폭주 / 주소 오류 / 수취인 부재 / 택배사 내부 사정\n"
    "사유가 여러 개 해당할 때의 우선순위는 추후 정함", 1180)
rev("d_feat_batch", "DOC-FEATURE", "M_D", ts(5, 8, 16, 0), "피처 저장 테이블·일 단위 배치",
    "schedule: \"0 3 * * *\"  # 매일 03시 피처 갱신", 1340)
rev("c_app_client", "DOC-APPBASE", "M_C", ts(5, 8, 17, 0), "공통 API 클라이언트 정리",
    "export const api = createClient({ baseURL: env.API_URL })", 1650, 420)

# ---- 3주차 (5/11 ~ 5/15)
rev("b_carrier_if", "DOC-CARRIER", "M_B", ts(5, 11, 15, 0), "택배사 어댑터 인터페이스 정의",
    "class CarrierAdapter(Protocol):\n    def fetch_events(self, invoice_no: str) -> list[DeliveryEvent]: ...", 1420)
rev("c_settings_route", "DOC-SETTINGSUI", "M_C", ts(5, 11, 14, 20), "알림 설정 화면 라우트·빈 컴포넌트 추가",
    "<Stack.Screen name=\"NotificationSettings\" component={NotificationSettings} />", 640)
rev("d_baseline", "DOC-MODEL", "M_D", ts(5, 11, 15, 30), "baseline LightGBM 학습 노트북",
    "baseline = LGBMRegressor().fit(X_train, y_train)\n# 검증 MAE 0.97일", 5230)
rev("b_mig_v7", "DOC-MIGRATION", "M_B", ts(5, 12, 11, 0), "V7 마이그레이션: delivery_events 월별 파티션 테이블 전환",
    "CREATE TABLE delivery_events_p (LIKE delivery_events) PARTITION BY RANGE (occurred_at);\n"
    "INSERT INTO delivery_events_p SELECT * FROM delivery_events;\n"
    "ALTER TABLE delivery_events RENAME TO delivery_events_old; ALTER TABLE delivery_events_p RENAME TO delivery_events;",
    2760)
rev("d_search_submit", "DOC-MODEL", "M_D", ts(5, 12, 17, 10), "학습 설정 확정, 하이퍼파라미터 탐색 잡 제출",
    "study = submit_search(space, trials=300, cluster=\"ml-gpu\")", 1870)
rev("e_gw_transform", "DOC-GATEWAY", "M_E", ts(5, 13, 11, 0), "요청 본문 변환 플러그인 활성화 (JSON 정규화·필드명 소문자 통일)",
    "plugins:\n  - name: request-transformer\n    config:\n      normalize_json: true\n      lowercase_keys: true\n"
    "    routes: [\"*\"]", 610)
rev("b_event_it", "DOC-EVENTAPI", "M_B", ts(5, 13, 15, 30), "이벤트 수집 API 통합 테스트",
    "def test_ingest_dedup(client): ...", 2210)
rev("b_carrier_nuri", "DOC-CARRIER", "M_B", ts(5, 13, 16, 0), "누리택배 어댑터",
    "class NuriAdapter(CarrierAdapter): ...", 2980)
rev("e_appsign", "DOC-APPSIGN", "M_E", ts(5, 14, 10, 30), "iOS 배포용 인증서·프로비저닝 프로필 등록 (App ID: com.shiptrack.app)",
    "app_id: com.shiptrack.app\ncapabilities: [Sign In with Apple, Associated Domains]\nprofile: ShipTrack AppStore", 740)
rev("b_carrier_baro", "DOC-CARRIER", "M_B", ts(5, 15, 14, 0), "바로배송 어댑터",
    "class BaroAdapter(CarrierAdapter): ...", 2540)
rev("e_ci_app", "DOC-CICD", "M_E", ts(5, 15, 16, 0), "앱 빌드 워크플로 (Android·iOS)",
    "build-ios:\n  runs-on: macos-14\n  steps: [fastlane match, fastlane build]", 1290)
rev("c_settings_store", "DOC-SETTINGSUI", "M_C", ts(5, 15, 17, 0), "알림 설정 상태 store 골격",
    "const useSettings = create(() => ({ channel: \"push\", frequency: \"instant\" }))", 720)

# ---- 4주차 (5/18 ~ 5/22)
rev("b_webhook_parse", "DOC-WEBHOOK", "M_B", ts(5, 18, 15, 0), "웹훅 엔드포인트·이벤트 파싱 (POST /webhooks/{carrier})",
    "@router.post(\"/webhooks/{carrier}\")\nasync def receive(carrier: str, request: Request): ...", 2310)
rev("a_prd_map", "DOC-PRD", "M_A", ts(5, 19, 10, 20), "배송 추적 지도 화면 요구사항 추가",
    "3.6 배송 추적 지도 화면\n- 지도 타일 위에 택배 현재 위치 마커 표시\n- 예상 도착 시간과 지연 여부 표시\n"
    "- 운영 환경에서 지도 타일이 끊김 없이 로드되어야 함", 1350)
rev("e_load_draft", "DOC-LOADTEST", "M_E", ts(5, 19, 11, 0), "k6 시나리오 초안 (이벤트 수집 API)",
    "export const options = { scenarios: { ingest: { executor: \"constant-arrival-rate\", rate: 500 } } }", 1640)
rev("a_onboard_toc", "DOC-ONBOARD", "M_A", ts(5, 19, 14, 0), "온보딩 가이드 목차",
    "1. 서비스 소개 / 2. 계정 발급 / 3. 알림 템플릿 설정 / 4. 문의 채널", 530)
rev("b_carrier_hangyeol", "DOC-CARRIER", "M_B", ts(5, 19, 16, 0), "한결로지스 어댑터",
    "class HangyeolAdapter(CarrierAdapter): ...", 2710)
rev("b_webhook_hmac", "DOC-WEBHOOK", "M_B", ts(5, 20, 11, 0), "택배사 서명(HMAC-SHA256) 검증 추가",
    "body = json.dumps(await request.json()).encode()\nsig = hmac.new(secret, body, sha256).hexdigest()\n"
    "if not compare_digest(sig, request.headers[\"X-Signature\"]): raise HTTPException(401)", 960)
rev("b_carrier_ongil", "DOC-CARRIER", "M_B", ts(5, 20, 14, 0), "온길익스프레스 어댑터 (샌드박스 키로 개발)",
    "class OngilAdapter(CarrierAdapter):\n    BASE_URL = \"https://sandbox.ongil-ex.example/api\"", 2480)
rev("d_v1_result", "DOC-MODEL", "M_D", ts(5, 20, 15, 0), "탐색 결과 정리, v1 모델 선정 (검증 MAE 0.82일)",
    "best = study.best_trial  # num_leaves=63, lr=0.05\n# 검증 MAE 0.82일 (baseline 0.97일)", 3460)
rev("e_load_more", "DOC-LOADTEST", "M_E", ts(5, 21, 15, 0), "시나리오 2종 추가 (웹훅 폭주, 조회 혼합)",
    "scenarios.webhook_burst = {...}; scenarios.mixed_read = {...}", 1120)
rev("c_settings_impl", "DOC-SETTINGSUI", "M_C", ts(5, 22, 14, 0), "알림 설정 화면 구현 (채널·빈도 토글)",
    "<Toggle label=\"앱 푸시\" /> <Toggle label=\"알림톡\" /> <Segmented options={[\"즉시\", \"하루 1회\"]} />", 4380)
rev("a_sched_beta", "DOC-SCHEDULE", "M_A", ts(5, 22, 16, 0), "사내 베타 체크리스트 추가",
    "5/29 사내 베타: 수집 API · 웹훅 · 알림 설정 · 모니터링", 610)

# ---- 5주차 (5/25 대체공휴일, 5/26 ~ 5/29)
rev("c_settings_save", "DOC-SETTINGSUI", "M_C", ts(5, 26, 15, 40), "설정 저장 API 연동",
    "await api.put(\"/me/notification-settings\", settings)", 860)
rev("d_reason_draft", "DOC-REASON", "M_D", ts(5, 26, 15, 0), "지연 사유 분류 규칙 초안 (키워드 기반)",
    "RULES = {\"기상\": [\"태풍\", \"폭설\", \"호우\"], \"물량 폭주\": [\"물량\", \"적체\"], ...}", 1980)
rev("e_gw_exempt", "DOC-GATEWAY", "M_E", ts(5, 26, 15, 10), "웹훅 경로(/webhooks/*) 요청 본문 변환 예외 추가",
    "  - name: request-transformer\n    routes: [\"/api/*\"]   # /webhooks/* 제외 (서명 대상 원문 보존)", 180, 40)
rev("e_monitor_draft", "DOC-MONITOR", "M_E", ts(5, 26, 16, 30), "Grafana 대시보드 초안 (수집 API 지표)",
    "panels: [ingest_rps, ingest_p95, webhook_4xx]", 1530)
rev("c_map_tiles", "DOC-TRACKMAP", "M_C", ts(5, 26, 17, 30), "지도 컴포넌트 추가 (타일 레이어, 위치 마커)",
    "<MapView><TileLayer url={TILE_URL} /><Marker position={current} /></MapView>", 2890)
rev("b_webhook_fix", "DOC-WEBHOOK", "M_B", ts(5, 27, 10, 30), "raw body 기준 서명 검증으로 수정 (게이트웨이 예외 경로 반영)",
    "body = await request.body()\nsig = hmac.new(secret, body, sha256).hexdigest()", 310, 120)
rev("a_onboard_move", "DOC-ONBOARD", "M_A", ts(5, 27, 15, 0), "온보딩 가이드 본문 이전 (노션 → 공유 문서)",
    "2. 계정 발급: 고객사 관리자 계정은 ... / 3. 알림 템플릿 설정: ...", 6840)
rev("e_monitor_rules", "DOC-MONITOR", "M_E", ts(5, 27, 16, 0), "알림 규칙 3종 (수집 지연, 웹훅 실패율, 5xx)",
    "alert: IngestLag > 5m / WebhookFailRate > 2% / Http5xx > 1%", 940)
rev("c_map_markers", "DOC-TRACKMAP", "M_C", ts(5, 27, 17, 0), "배송 상태별 마커 색상 (집화·이동 중·배송 출발·지연)",
    "const MARKER_COLOR = { picked: \"gray\", in_transit: \"blue\", out_for_delivery: \"green\", delayed: \"red\" }", 760)
rev("e_load_report", "DOC-LOADTEST", "M_E", ts(5, 28, 10, 0), "부하 테스트 결과 리포트 (500rps에서 p95 320ms)",
    "ingest: p95 320ms, 에러율 0.02% / webhook_burst: p95 410ms", 2950)
rev("d_reason_dup", "DOC-REASON", "M_D", ts(5, 28, 11, 0), "라벨 검수 샘플 200건 결과 기록 (기상·물량 폭주 중복 38건)",
    "# 200건 중 38건이 '기상'과 '물량 폭주' 규칙에 동시에 해당", 640)
rev("e_csp", "DOC-INGRESS", "M_E", ts(5, 28, 14, 0), "운영 ingress 보안 헤더 적용 (HSTS, X-Frame-Options, CSP)",
    "add_header Strict-Transport-Security \"max-age=31536000\";\nadd_header X-Frame-Options DENY;\n"
    "add_header Content-Security-Policy \"default-src 'self'; img-src 'self' data:\";", 520)
rev("e_ci_prod", "DOC-CICD", "M_E", ts(5, 28, 17, 0), "운영 배포 잡 (수동 승인)",
    "deploy-prod:\n  environment: production  # 승인 후 배포", 730)
rev("a_sched_scope", "DOC-SCHEDULE", "M_A", ts(5, 29, 14, 10), "파일럿 범위 조정: 택배사 3개사로 시작, 온길 연동은 운영 키 수령 후",
    "6/12 파일럿: 누리택배·바로배송·한결로지스\n온길익스프레스: 운영 키 수령 후 연동 (택배사 연동 마감 6/12로 이동)", 540, 120)

# ---- 6주차 (6/1 ~ 6/5, 6/3 지방선거)
rev("a_prd_priority", "DOC-PRD", "M_A", ts(6, 1, 14, 0), "지연 사유 중복 시 우선순위 규칙 추가",
    "3.4.1 사유가 여러 개면: 택배사가 제공한 사유 > 기상 > 물량 폭주 > 그 밖", 420)
rev("d_reason_fix", "DOC-REASON", "M_D", ts(6, 1, 15, 0), "중복 사유 우선순위 규칙 반영해 분류 로직 수정",
    "PRIORITY = [\"택배사 제공\", \"기상\", \"물량 폭주\", \"주소 오류\", \"수취인 부재\"]", 690, 210)
rev("e_csp_fix", "DOC-INGRESS", "M_E", ts(6, 2, 9, 0), "CSP img-src에 지도 타일 도메인 추가",
    "img-src 'self' data: https://tiles.mapvendor.example;", 60, 20)
rev("a_pilotfb_form", "DOC-PILOTFB", "M_A", ts(6, 2, 10, 30), "피드백 수집 양식",
    "고객사 / 항목 / 심각도 / 처리 상태", 480)
rev("c_map_confirm", "DOC-TRACKMAP", "M_C", ts(6, 2, 11, 0), "운영 지도 타일 로드 확인, 타일 URL 상수 정리",
    "export const TILE_URL = \"https://tiles.mapvendor.example/{z}/{x}/{y}.png\"", 230, 90)
rev("d_reason_check", "DOC-REASON", "M_D", ts(6, 2, 14, 0), "분류 결과 검수 (200건 중 불일치 3건)",
    "# 우선순위 규칙 적용 후 수작업 라벨과 불일치 3건", 520)
rev("b_settle_skel", "DOC-SETTLE", "M_B", ts(6, 2, 14, 0), "정산 리포트 배치 잡 골격",
    "@job(schedule=\"0 6 1 * *\")\ndef monthly_delay_report(): ...", 1260)
rev("c_push_android", "DOC-PUSH", "M_C", ts(6, 2, 15, 0), "푸시 권한 요청 흐름 (Android)",
    "await PermissionsAndroid.request(PERMISSIONS.POST_NOTIFICATIONS)", 1340)
rev("b_carrier_notice", "DOC-CARRIER", "M_B", ts(6, 2, 16, 0), "온길익스프레스 미연동 시 안내 문구 수정",
    "OngilAdapter.fetch_events → \"온길익스프레스 배송 정보는 준비 중입니다\" 문구 반환", 160, 90)
rev("e_runbook_toc", "DOC-RUNBOOK", "M_E", ts(6, 4, 10, 0), "런북 목차·연락 체계",
    "1. 장애 등급 / 2. 연락 체계 / 3. 롤백 절차 / 4. 사후 보고", 1320)
rev("c_push_ios", "DOC-PUSH", "M_C", ts(6, 4, 10, 0), "iOS 권한 요청 추가",
    "await messaging().requestPermission({ alert: true, badge: true, sound: true })", 680)
rev("a_pilotfb_first", "DOC-PILOTFB", "M_A", ts(6, 4, 10, 30), "1차 피드백 12건 정리",
    "누리몰: 알림 문구 길이 / 바로마켓: 하루 1회 묶음 시각 / ...", 2240)
rev("b_settle_query", "DOC-SETTLE", "M_B", ts(6, 4, 11, 0), "지연 건수 집계 쿼리 초안 (dw.delivery_events 기준)",
    "SELECT carrier, count(*) FROM dw.delivery_events WHERE delayed GROUP BY carrier", 980)
rev("e_rollback", "DOC-ROLLBACK", "M_E", ts(6, 4, 14, 0), "스테이징 롤백 스크립트 (앱 이미지 + DB down 마이그레이션)",
    "kubectl rollout undo deploy/shiptrack-api\nflyway undo -target=6", 1120)
rev("e_monitor_panel", "DOC-MONITOR", "M_E", ts(6, 4, 16, 0), "대시보드 패널 정리, 런북 링크 추가",
    "panels: [..., alert_runbook_link]", 610, 230)
rev("a_sched_pilot", "DOC-SCHEDULE", "M_A", ts(6, 5, 15, 0), "파일럿 오픈 체크리스트",
    "6/12 10:00 운영 배포 / 고객사 3곳 계정 발급 / 알림 템플릿 확인", 580)

# ---- 7주차 (6/8 ~ 6/12)
rev("d_v2_feat", "DOC-MODEL", "M_D", ts(6, 8, 15, 0), "6월 데이터 반영 피처 갱신",
    "train_range = (\"2025-06\", \"2026-05\")", 830)
rev("e_e2e_android", "DOC-E2E", "M_E", ts(6, 8, 16, 0), "E2E 시나리오 12종 (Android)",
    "describe(\"지연 알림 수신\", () => { ... })  # 12 scenarios", 4120)
rev("b_v7_down", "DOC-ROLLBACK", "M_B", ts(6, 9, 11, 0), "V7 down 마이그레이션 추가 (파티션 테이블 → 단일 테이블 복원)",
    "CREATE TABLE delivery_events_flat AS SELECT * FROM delivery_events;\nDROP TABLE delivery_events;\n"
    "ALTER TABLE delivery_events_flat RENAME TO delivery_events;", 880)
rev("c_e2e_ios", "DOC-E2E", "M_C", ts(6, 9, 11, 0), "iOS 테스트 타깃 추가",
    "devices: [\"iPhone 15 / iOS 17\", \"iPhone 13 / iOS 16\"]", 540)
rev("b_settle_fix", "DOC-SETTLE", "M_B", ts(6, 9, 16, 0), "변경된 스키마(dw.delivery_events_v2) 기준으로 집계 쿼리 수정",
    "FROM dw.delivery_events_v2 WHERE delay_flag GROUP BY carrier_code", 340, 280)
rev("e_runbook_rerun", "DOC-RUNBOOK", "M_E", ts(6, 9, 16, 0), "롤백 리허설 재실행 성공, 런북 롤백 절차 수정",
    "3. 롤백 절차: 앱 이미지 롤백 → V7 down → 데이터 검증 쿼리", 1460, 380)
rev("e_e2e_verify", "DOC-E2E", "M_E", ts(6, 9, 17, 0), "알림 수신 검증 단계 추가",
    "await expect(notification).toContain(\"배송이 지연될 예정\")", 760)
rev("e_appsign_push", "DOC-APPSIGN", "M_E", ts(6, 10, 9, 40), "App ID에 Push Notifications capability 추가, 프로비저닝 프로필 재발급",
    "capabilities: [Sign In with Apple, Associated Domains, Push Notifications]", 120, 60)
rev("a_pilotfb_final", "DOC-PILOTFB", "M_A", ts(6, 10, 15, 0), "고객사 피드백 최종 정리 (3개사, 27건 반영 완료)",
    "총 27건: 반영 24 / 다음 분기 3 / 미해결 0", 3870)
rev("d_v2_submit", "DOC-MODEL", "M_D", ts(6, 10, 16, 0), "v2 재학습 잡 제출",
    "study_v2 = submit_search(space, trials=300, cluster=\"ml-gpu\")", 640)
rev("c_push_fix", "DOC-PUSH", "M_C", ts(6, 10, 16, 0), "iOS 푸시 권한 문제 해결 (entitlements에 aps-environment 추가)",
    "<key>aps-environment</key><string>production</string>", 120)

# ---- 8주차 (6/15 ~ 6/19)
rev("a_retro_toc", "DOC-RETRO", "M_A", ts(6, 15, 15, 0), "회고 문서 틀",
    "1. 잘된 점 / 2. 아쉬운 점 / 3. 다음 분기에 할 일", 450)
rev("c_e2e_ios_result", "DOC-E2E", "M_C", ts(6, 16, 14, 0), "iOS E2E 실행 결과 반영 (12종 통과)",
    "iOS 17: 12/12 통과, iOS 16: 12/12 통과", 380)
rev("d_v2_result", "DOC-MODEL", "M_D", ts(6, 16, 15, 0), "v2 결과 정리 (검증 MAE 0.74일), 운영 모델 교체",
    "# v2 검증 MAE 0.74일 (v1 0.82일)", 2310)
rev("a_retro_body", "DOC-RETRO", "M_A", ts(6, 19, 11, 0), "회고 내용 정리",
    "잘된 점: 사내 베타·파일럿 일정 준수 / 아쉬운 점: 외부 키·결재 대기 / 다음 분기: 온길 연동", 3210)

# ====================================================================== 메시지
MSGS = []


def msg(key, channel, sender, when, text, reply_to=None, dm_to=None):
    MSGS.append(dict(key=key, channel=channel, sender_id=sender, sent_at=when, text=text, reply_to=reply_to,
                     dm_to=dm_to))


msg("a_sched", "#shiptrack", "M_A", ts(4, 27, 17, 5), "일정표 공유 문서에 올렸어요. 주간 회의는 매주 월요일 10시 30분입니다.")
msg("e_ci", "#shiptrack-dev", "M_E", ts(4, 29, 18, 0), "CI 워크플로 올렸어요. PR 올리면 테스트가 자동으로 돕니다.")
msg("b_event1", "#shiptrack-dev", "M_B", ts(4, 30, 17, 0),
    "이벤트 수집 API 1차 올렸어요. 중복 이벤트는 (운송장번호, 상태, 시각) 기준으로 거릅니다.")
msg("a_holiday", "#shiptrack", "M_A", ts(4, 30, 18, 20), "내일이랑 다음 주 월요일은 회사 휴무, 화요일은 어린이날이에요. 수요일에 봬요!")
msg("e_stg", "#shiptrack-dev", "M_E", ts(5, 6, 9, 40), "스테이징 열었어요. stg.shiptrack.internal 로 들어오시면 됩니다.")
msg("b_ci_fail", "#shiptrack-dev", "M_B", ts(5, 7, 14, 10),
    "CI에서 통합 테스트가 DB 연결 타임아웃으로 계속 실패하네요. 로컬에선 통과하는데 원인을 못 찾겠어요.")
msg("e_ci_fix", "#shiptrack-dev", "M_E", ts(5, 7, 15, 30),
    "CI 러너에서 DB 컨테이너 헬스체크가 빠져 있어서 테스트가 DB 뜨기 전에 시작되고 있었어요. 워크플로에 헬스체크 대기 추가했어요.",
    reply_to="b_ci_fail")
msg("b_ci_thanks", "#shiptrack-dev", "M_B", ts(5, 7, 15, 45), "됐어요! 감사합니다.", reply_to="b_ci_fail")
msg("a_prd_done", "#shiptrack", "M_A", ts(5, 8, 17, 30), "요구사항 정의서 v1.0으로 확정했어요. 수고 많으셨어요!")
msg("b_v7", "#shiptrack-dev", "M_B", ts(5, 12, 11, 20), "delivery_events를 월별 파티션 테이블로 바꿨어요(V7). 기간 조회가 훨씬 빨라졌습니다.")
msg("e_gw", "#shiptrack-dev", "M_E", ts(5, 13, 11, 10),
    "게이트웨이에서 요청 JSON을 정규화하도록 켰어요. 택배사마다 필드명 대소문자가 달라서요.")
msg("a_week3", "#shiptrack", "M_A", ts(5, 15, 17, 30), "이번 주 수고하셨어요. 다음 주 회의에서 사내 베타 범위 정할게요.")
msg("b_ongil_req", "#shiptrack", "M_B", ts(5, 20, 14, 30),
    "온길익스프레스는 샌드박스 키로만 개발해 뒀어요. 운영 키는 업체 계약 담당자한테 요청했습니다.")
msg("d_v1", "#shiptrack-data", "M_D", ts(5, 20, 15, 20), "지연 예측 v1 결과 올렸어요. baseline 대비 MAE가 15% 정도 줄었습니다.")
msg("b_401", "#shiptrack-dev", "M_B", ts(5, 20, 16, 40),
    "웹훅에 서명 검증을 넣었더니 스테이징에서 누리택배 이벤트가 전부 401로 떨어지네요. 로컬 테스트는 통과하는데 이상하네요.")
msg("c_design_review", "#shiptrack", "M_C", ts(5, 21, 16, 30), "알림 설정 화면 디자인 리뷰 끝났어요. 내일부터 코드로 옮길게요.")
msg("b_ongil_again", "#shiptrack", "M_B", ts(5, 22, 10, 0), "온길 운영 키 아직 회신이 없어서 다시 메일 보냈어요.")
msg("dm_b_e", "dm", "M_B", ts(5, 26, 9, 30),
    "다인님 웹훅 401 건 혹시 게이트웨이에서 본문이 바뀌거나 하는 게 있을까요? 오늘 같이 봐 주실 수 있나요?", dm_to=["M_E"])
msg("dm_e_b", "dm", "M_E", ts(5, 26, 9, 45), "네 오후에 같이 봐요. 짚이는 게 하나 있어요.", dm_to=["M_B"])
msg("e_gw_fix", "#shiptrack-dev", "M_E", ts(5, 26, 15, 20),
    "게이트웨이 본문 변환 플러그인이 웹훅 경로에도 걸려 있어서, 앱에 들어오는 본문이 택배사가 서명한 원문과 달라지고 있었어요. "
    "웹훅 경로는 변환 대상에서 뺐습니다.", reply_to="b_401")
msg("a_marker", "#shiptrack", "M_A", ts(5, 27, 10, 0),
    "지도 화면 마커는 배송 상태별로 색을 다르게 하면 고객이 한눈에 볼 수 있을 것 같아요. 집화·이동 중·배송 출발·지연 4색이면 어떨까요?")
msg("c_marker_ok", "#shiptrack", "M_C", ts(5, 27, 10, 15), "좋아요, 그렇게 할게요.", reply_to="a_marker")
msg("b_webhook_ok", "#shiptrack-dev", "M_B", ts(5, 27, 10, 40),
    "스테이징에서 누리택배 웹훅 정상 수신 확인했어요. 다인님 감사합니다!", reply_to="b_401")
msg("e_load", "#shiptrack-qa", "M_E", ts(5, 28, 10, 10), "부하 테스트 결과 올렸어요. 500rps에서 p95 320ms라 베타 기준은 충족합니다.")
msg("d_dup", "#shiptrack-data", "M_D", ts(5, 28, 11, 20),
    "사유 코드 중에 '기상'이랑 '물량 폭주'가 같이 걸리는 건이 200건 중 38건이에요. 어느 쪽으로 볼지 기준이 있어야 할 것 같아요.")
msg("e_headers", "#shiptrack-dev", "M_E", ts(5, 28, 14, 10), "보안 점검 지적사항 반영해서 운영 ingress에 보안 헤더 넣었어요.")
msg("e_beta", "#shiptrack", "M_E", ts(5, 29, 9, 30), "사내 베타 운영 배포 끝났어요!")
msg("c_gray", "#shiptrack-dev", "M_C", ts(5, 29, 10, 20),
    "운영 베타에서 배송 추적 지도가 회색 화면으로만 나와요. 로컬이랑 스테이징은 정상인데… 원인 좀 더 볼게요.")
msg("a_scope", "#shiptrack", "M_A", ts(5, 29, 14, 0),
    "파일럿은 누리·바로·한결 3개사로 시작하고, 온길은 운영 키 나오면 붙이는 걸로 조정할게요. 택배사 연동 마감도 6/12로 옮겨 둘게요.")
msg("e_training", "#shiptrack", "M_E", ts(5, 29, 16, 0), "다음 주 월·화는 사외 교육이라 메신저 확인이 늦을 수 있어요.")
msg("a_beta_done", "#shiptrack", "M_A", ts(5, 29, 17, 30), "베타 오픈 수고하셨어요! 다음 주 수요일은 선거일이라 휴무입니다.")
msg("c_policy", "#shiptrack-dev", "M_C", ts(6, 1, 10, 5),
    "혹시 지난주에 운영 쪽 설정 바뀐 게 있을까요? 콘솔에 이미지 로드가 정책 위반으로 거부됐다고 나와요.", reply_to="c_gray")
msg("e_csp_fix", "#shiptrack-dev", "M_E", ts(6, 2, 8, 50),
    "제가 목요일에 운영 ingress에 CSP 헤더를 넣었는데 img-src에 지도 타일 도메인을 안 넣었어요. 바로 추가할게요.", reply_to="c_gray")
msg("c_map_thanks", "#shiptrack-dev", "M_C", ts(6, 2, 11, 15), "다인님 덕분에 운영에서도 지도 잘 나와요. 감사합니다!", reply_to="c_gray")
msg("b_schema", "#shiptrack-data", "M_B", ts(6, 4, 15, 0),
    "데이터플랫폼팀에서 다음 주에 dw.delivery_events 스키마를 바꾼다고 공지했네요. 컬럼명이 바뀐다는데 확정본은 아직이래요.")
msg("e_v7_fail", "#shiptrack-dev", "M_E", ts(6, 4, 18, 10),
    "스테이징 롤백 리허설 해 봤는데 DB 마이그레이션 down이 V7에서 실패하네요. 내일 다시 볼게요.")
msg("a_pilot_week", "#shiptrack", "M_A", ts(6, 5, 17, 0), "다음 주 금요일 파일럿 오픈입니다. 각자 남은 Task 확인 부탁드려요.")
msg("c_push_stuck", "#shiptrack-dev", "M_C", ts(6, 8, 14, 20),
    "iOS에서 푸시 권한 팝업이 아예 안 떠요. 안드로이드는 되는데… 며칠째 이것만 보고 있는데 원인을 모르겠어요.")
msg("b_v7_down", "#shiptrack-dev", "M_B", ts(6, 9, 11, 10),
    "V7 down 스크립트 추가했어요. 파티션 테이블을 단일 테이블로 복원하는 순서로 짰습니다.", reply_to="e_v7_fail")
msg("b_schema_done", "#shiptrack-data", "M_B", ts(6, 9, 13, 0), "데이터플랫폼팀 스키마 확정본 나왔어요(dw.delivery_events_v2). 오늘 반영할게요.")
msg("e_push", "#shiptrack-dev", "M_E", ts(6, 10, 10, 0),
    "앱 ID에 Push Notifications capability가 빠져 있었어요. 프로비저닝 프로필 다시 만들어서 올렸어요.", reply_to="c_push_stuck")
msg("c_devicefarm", "#shiptrack-qa", "M_C", ts(6, 10, 10, 0),
    "iOS E2E 돌리려고 보니 디바이스팜 계정이 지난주에 만료됐네요. 구매팀에 갱신 요청 올렸어요.")
msg("b_ongil_later", "#shiptrack", "M_B", ts(6, 10, 17, 0), "온길 운영 키는 여전히 회신이 없어요. 정식 릴리스 이후로 미룰게요.")
msg("c_devicefarm2", "#shiptrack-qa", "M_C", ts(6, 12, 11, 0), "디바이스팜 갱신 결재가 아직 안 나서 iOS E2E는 못 돌리고 있어요.")
msg("e_pilot", "#shiptrack", "M_E", ts(6, 12, 10, 0), "파일럿 고객사 3곳 운영 배포 완료했어요.")
msg("a_pilot_done", "#shiptrack", "M_A", ts(6, 12, 17, 0), "파일럿 오픈 수고하셨습니다!")
msg("c_devicefarm_done", "#shiptrack-qa", "M_C", ts(6, 16, 13, 0), "디바이스팜 갱신됐어요! iOS E2E 돌립니다.")
msg("d_v2", "#shiptrack-data", "M_D", ts(6, 16, 15, 20), "v2 모델 결과 올렸어요. 검증 MAE 0.74일로 v1보다 좋아졌어요.")
msg("e_release", "#shiptrack", "M_E", ts(6, 19, 10, 0), "정식 릴리스 배포 완료!")
msg("a_release", "#shiptrack", "M_A", ts(6, 19, 16, 0), "릴리스 수고하셨어요. 회고 폼은 오늘까지입니다.")

# ====================================================================== 회의
ALL = ["M_A", "M_B", "M_C", "M_D", "M_E"]
MEETINGS = [
    ("MT01", "킥오프: 목표·역할·일정", (4, 27, 10, 0), (4, 27, 11, 20), ALL, ["서비스 목표", "역할 분담", "일정"], [
        ("M_A", 2, "오늘부터 ShipTrack 킥오프입니다. 택배사 배송 이벤트를 모아서 지연이 예상되는 주문을 고객에게 먼저 알려 주는 게 목표예요. "
                   "6월 12일 고객사 파일럿, 19일 정식 릴리스입니다."),
        ("M_B", 10, "백엔드는 제가 맡을게요. 이벤트 수집 API부터 만들고, 택배사 연동은 4개사 어댑터로 나누려고요."),
        ("M_D", 18, "지연 예측 모델은 제가 할게요. 작년 배송 이벤트 로그로 피처부터 뽑아 보겠습니다."),
        ("M_C", 25, "앱이랑 웹 화면은 제가 맡을게요. 이번 주는 앱 기본 구조랑 로그인부터 잡겠습니다."),
        ("M_E", 31, "저는 CI/CD랑 스테이징 환경, 게이트웨이 설정 맡을게요. 다음 주 중에 스테이징 열어 둘게요."),
        ("M_A", 40, "요구사항 정의서는 제가 이번 주에 초안 쓰고 다음 회의에서 같이 리뷰해요. 5월 1일이랑 4일은 회사 휴무라 다음 회의는 6일 수요일입니다."),
        ("M_D", 52, "지연 기준은 약속 도착일보다 하루 이상 늦는 걸로 잡으면 될까요?"),
        ("M_A", 55, "네, 일단 그 기준으로 가고 정의서에 적어 둘게요."),
    ]),
    ("MT02", "요구사항·설계 리뷰", (5, 6, 10, 30), (5, 6, 11, 30), ALL, ["요구사항 리뷰", "택배사 범위", "Task 분배"], [
        ("M_A", 1, "정의서 초안 기준으로 리뷰할게요. 이번 주 금요일에 설계 확정하는 게 목표예요."),
        ("M_B", 8, "택배사 연동은 누리택배, 바로배송, 한결로지스, 온길익스프레스 4개사예요. 다음 주부터 어댑터 들어갈게요."),
        ("M_D", 15, "지연 사유 코드가 정의서에 있으면 좋겠어요. 나중에 사유별로 알림 문구를 다르게 쓰려면 필요해요."),
        ("M_A", 18, "네, 사유 코드는 제가 금요일까지 정의서에 추가할게요."),
        ("M_C", 25, "알림 설정 화면은 채널(앱 푸시·알림톡)이랑 빈도를 고르는 정도면 될까요?"),
        ("M_A", 28, "네, 그 두 가지면 충분해요. 정의서에도 그렇게 적을게요."),
        ("M_E", 32, "스테이징은 오늘 아침에 열었어요. 게이트웨이 거쳐서 들어오게 해 놨습니다."),
        ("M_A", 40, "Task는 회의 끝나고 보드에 만들어 둘게요."),
    ]),
    ("MT03", "3주차 주간 회의", (5, 11, 10, 30), (5, 11, 11, 15), ALL, ["진행 상황", "파일럿 고객사"], [
        ("M_A", 1, "이번 주부터 본격 구현이에요. 진행 상황 공유 부탁드려요."),
        ("M_B", 5, "이벤트 수집 API는 이번 주 금요일 마감 맞출 수 있어요. 오늘부터 택배사 어댑터도 같이 시작합니다."),
        ("M_D", 11, "모델은 baseline 학습 노트북 오늘 올릴게요."),
        ("M_C", 16, "앱 기본 구조는 리뷰 끝났고, 이번 주부터 알림 설정 화면 들어가요."),
        ("M_E", 22, "CI/CD는 거의 끝났고 이번 주에 앱 서명 설정이랑 게이트웨이 정리할게요."),
        ("M_A", 30, "파일럿 고객사는 세 곳으로 확정됐어요. 온보딩 가이드는 다음 주부터 제가 쓸게요."),
    ]),
    ("MT04", "4주차 주간 회의", (5, 18, 10, 30), (5, 18, 11, 20), ALL, ["사내 베타 범위", "신규 Task"], [
        ("M_A", 1, "사내 베타가 29일이에요. 이번 주에 웹훅 수신, 부하 테스트, 지도 화면, 온보딩 가이드 Task 새로 만들게요."),
        ("M_B", 7, "택배사 어댑터는 누리·바로 끝났고 이번 주에 한결이랑 온길 들어갑니다. 웹훅도 제가 할게요."),
        ("M_C", 14, "알림 설정 화면은 이번 주에 디자인 리뷰 받고 코드로 옮길게요. 지도 화면은 그다음에 시작할게요."),
        ("M_E", 20, "부하 테스트는 제가 k6로 할게요. 이벤트 수집 API 기준 500rps 목표로 잡겠습니다."),
        ("M_D", 27, "모델은 이번 주 안에 v1 확정할게요."),
        ("M_A", 33, "지도 화면 요구사항은 내일 정의서에 추가해 둘게요."),
    ]),
    ("MT05", "5주차 주간 회의 (대체공휴일로 화요일)", (5, 26, 10, 30), (5, 26, 11, 20), ALL, ["사내 베타 점검", "신규 Task"], [
        ("M_A", 1, "어제 대체공휴일이라 오늘 회의해요. 금요일 사내 베타 전에 남은 거 점검할게요."),
        ("M_B", 6, "웹훅은 스테이징에서만 서명 검증이 401로 떨어지는 문제가 있어서 오늘 다인님이랑 같이 보기로 했어요. "
                   "온길은 운영 키 회신을 아직 못 받았어요."),
        ("M_E", 13, "부하 테스트는 로컬에서 돌린 결과를 목요일에 리포트로 올릴게요."),
        ("M_C", 18, "알림 설정 화면은 오늘 리뷰 올리고, 이번 주부터 지도 화면 들어가요."),
        ("M_A", 24, "온보딩 가이드는 노션에서 고객사 담당자들이랑 같이 보고 있고 이번 주에 공유 문서로 옮길게요."),
        ("M_D", 30, "모델 v1은 끝났고, 지연 사유 분류 규칙 시작할게요."),
        ("M_A", 36, "모니터링 대시보드랑 사유 분류 Task 오늘 만들게요."),
    ]),
    ("MT06", "6주차 주간 회의", (6, 1, 10, 30), (6, 1, 11, 20), ["M_A", "M_B", "M_C", "M_D"],
     ["베타 피드백", "사유 중복 기준", "신규 Task"], [
        ("M_A", 1, "베타 피드백 정리하고 파일럿 준비 들어갈게요. 다인님은 오늘 사외 교육이라 빠졌어요."),
        ("M_A", 6, "재민님이 올린 사유 중복 건은 택배사가 알려 준 사유를 우선하고, 없으면 기상을 우선하는 걸로 정할게요. 정의서에도 반영할게요."),
        ("M_D", 10, "네, 그 기준으로 오늘 분류 로직 고칠게요."),
        ("M_C", 15, "지도 화면이 운영에서만 회색으로 나와서 막혀 있어요. 오늘 다시 볼게요."),
        ("M_B", 21, "택배사 연동은 온길 키만 남았고, 이번 주부터 정산 리포트 배치 시작할게요."),
        ("M_C", 27, "이번 주에 앱 푸시 권한 처리도 시작할게요."),
        ("M_A", 33, "푸시 권한, 정산 배치, 런북, 고객 피드백 정리 Task 만들게요."),
    ]),
    ("MT07", "7주차 주간 회의 (파일럿 주)", (6, 8, 10, 30), (6, 8, 11, 20), ALL, ["파일럿 준비", "막힌 일", "신규 Task"], [
        ("M_A", 1, "금요일 파일럿 오픈 주예요. 막힌 거 있으면 오늘 말해 주세요."),
        ("M_E", 6, "롤백 리허설에서 V7 down 마이그레이션이 계속 실패해서 거기서 멈춰 있어요."),
        ("M_B", 11, "V7은 제가 만든 거라 같이 볼게요. 정산 배치는 데이터플랫폼팀 스키마 확정을 기다리는 중이에요."),
        ("M_C", 17, "푸시 권한 쪽 보고 있어요."),
        ("M_D", 22, "모델 v2 재학습은 6월 데이터 넣어서 이번 주에 돌릴게요."),
        ("M_A", 28, "고객사 피드백은 이번 주에 통화로 마무리할게요. 통합 테스트 Task는 다인님이랑 수빈님이 같이 맡아 주세요."),
    ]),
    ("MT08", "8주차 주간 회의 (릴리스 주)", (6, 15, 10, 30), (6, 15, 11, 10), ALL, ["릴리스 점검", "회고"], [
        ("M_A", 1, "이번 주 금요일 정식 릴리스예요. 남은 건 통합 테스트랑 모델 v2예요."),
        ("M_C", 6, "디바이스팜 갱신 결재가 아직이라 iOS E2E는 대기 중이에요."),
        ("M_D", 11, "v2 재학습은 내일 끝나요. 결과 보고 바로 올릴게요."),
        ("M_E", 15, "안드로이드 E2E는 다 통과했어요."),
        ("M_A", 20, "회고 문서 틀은 제가 만들어 둘게요. 기여 내역은 금요일까지 회고 폼에 적어 주세요."),
    ]),
]

# ====================================================================== Task
TASKS = []


def task(tid, title, desc, created_by, created, assignees, docs, due, history, deps=(), due_changes=()):
    """history: [(시각, 변경자, 상태, note)] — 첫 항목은 생성 시점(TODO)."""
    hist, prev = [], None
    for when, by, to, *note in history:
        hist.append({"changed_at": when, "changed_by": by, "from_status": prev, "to_status": to,
                     "note": note[0] if note else None})
        prev = to
    TASKS.append({
        "task_id": tid, "project_id": PID, "title": title, "description": desc, "created_by": created_by,
        "created_at": created, "assignee_ids": list(assignees),
        "due_date": due_changes[-1][3] if due_changes else due, "status": prev, "status_history": hist,
        "related_document_ids": list(docs), "depends_on_task_ids": list(deps),
        "due_date_history": [{"changed_at": w, "changed_by": b, "from_due_date": f, "to_due_date": t, "note": n}
                             for w, b, f, t, n in due_changes],
    })


def started(tid, title, desc, created, assignee, docs, due, steps, **kw):
    task(tid, title, desc, "M_A", created, kw.pop("assignees", [assignee]), docs, due,
         [(created, "M_A", "TODO")] + steps, **kw)


started("T01", "요구사항 정의서", "서비스 범위·기능·비기능 요구사항 정리", ts(4, 27, 11, 30), "M_A", ["DOC-PRD"], "2026-05-08",
        [(ts(4, 27, 14, 0), "M_A", "IN_PROGRESS"), (ts(5, 6, 15, 0), "M_A", "IN_REVIEW"), (ts(5, 7, 17, 0), "M_A", "DONE")])
started("T02", "배송 이벤트 수집 API", "택배사 배송 이벤트 수집·중복 제거·저장", ts(4, 27, 11, 35), "M_B",
        ["DOC-EVENTAPI", "DOC-MIGRATION"], "2026-05-15",
        [(ts(4, 28, 9, 40), "M_B", "IN_PROGRESS"), (ts(5, 13, 16, 0), "M_B", "IN_REVIEW"), (ts(5, 14, 11, 0), "M_A", "DONE")])
started("T03", "앱 기본 구조·로그인", "앱 프로젝트 구조, 사내 SSO 로그인, 공통 API 클라이언트", ts(4, 27, 11, 40), "M_C",
        ["DOC-APPBASE"], "2026-05-08",
        [(ts(4, 28, 10, 0), "M_C", "IN_PROGRESS"), (ts(5, 8, 17, 10), "M_C", "IN_REVIEW"), (ts(5, 11, 10, 0), "M_A", "DONE")])
started("T04", "CI/CD·스테이징 환경", "빌드·테스트·배포 파이프라인, 스테이징, API 게이트웨이, 앱 서명", ts(4, 27, 11, 45), "M_E",
        ["DOC-CICD", "DOC-GATEWAY", "DOC-APPSIGN"], "2026-05-15",
        [(ts(4, 28, 9, 30), "M_E", "IN_PROGRESS"), (ts(5, 15, 17, 0), "M_E", "DONE")])
started("T05", "지연 예측 모델 v1", "배송 지연(약속 도착일 +1일 초과) 예측 모델 학습·평가", ts(4, 28, 11, 0), "M_D",
        ["DOC-FEATURE", "DOC-MODEL"], "2026-05-22",
        [(ts(5, 6, 13, 30), "M_D", "IN_PROGRESS"), (ts(5, 21, 11, 0), "M_D", "IN_REVIEW"), (ts(5, 21, 17, 30), "M_A", "DONE")])
started("T06", "택배사 연동 어댑터", "누리택배·바로배송·한결로지스·온길익스프레스 4개사 배송 조회 어댑터", ts(5, 6, 11, 40), "M_B",
        ["DOC-CARRIER"], "2026-05-29", [(ts(5, 11, 10, 0), "M_B", "IN_PROGRESS")],
        due_changes=[(ts(5, 29, 14, 5), "M_A", "2026-05-29", "2026-06-12", "온길 운영 키 대기. 파일럿은 3개사로 시작"),
                     (ts(6, 11, 16, 0), "M_A", "2026-06-12", "2026-07-10", "온길 운영 키 미수령. 정식 릴리스 이후 연동")])
started("T07", "알림 설정 화면", "알림 채널(앱 푸시·알림톡)과 빈도 설정 화면", ts(5, 6, 11, 45), "M_C", ["DOC-SETTINGSUI"],
        "2026-05-27",
        [(ts(5, 11, 14, 0), "M_C", "IN_PROGRESS"), (ts(5, 26, 16, 0), "M_C", "IN_REVIEW"), (ts(5, 27, 11, 0), "M_A", "DONE")])
started("T08", "배송 상태 웹훅 수신", "택배사 웹훅 수신, 서명 검증, 이벤트 변환", ts(5, 18, 11, 30), "M_B", ["DOC-WEBHOOK"],
        "2026-05-29",
        [(ts(5, 18, 13, 0), "M_B", "IN_PROGRESS"), (ts(5, 27, 11, 0), "M_B", "IN_REVIEW"), (ts(5, 28, 10, 0), "M_A", "DONE")],
        deps=["T02"])
started("T09", "부하 테스트", "이벤트 수집 API·웹훅 부하 테스트 (목표 500rps)", ts(5, 18, 11, 35), "M_E", ["DOC-LOADTEST"],
        "2026-05-29", [(ts(5, 19, 10, 30), "M_E", "IN_PROGRESS"), (ts(5, 28, 11, 0), "M_E", "DONE")])
started("T10", "파일럿 고객 온보딩 가이드", "파일럿 고객사용 계정 발급·알림 템플릿 설정 가이드", ts(5, 18, 11, 40), "M_A",
        ["DOC-ONBOARD"], "2026-05-29",
        [(ts(5, 19, 10, 0), "M_A", "IN_PROGRESS"), (ts(5, 27, 15, 10), "M_A", "IN_REVIEW"), (ts(5, 28, 11, 0), "M_A", "DONE")])
started("T11", "배송 추적 지도 화면", "지도 위 택배 현재 위치·상태별 마커·예상 도착 시간 표시", ts(5, 18, 11, 45), "M_C",
        ["DOC-TRACKMAP"], "2026-06-05",
        [(ts(5, 26, 17, 0), "M_C", "IN_PROGRESS"), (ts(6, 2, 11, 10), "M_C", "IN_REVIEW"), (ts(6, 4, 10, 0), "M_A", "DONE")])
started("T12", "지연 사유 분류 규칙", "배송 이벤트 메모로 지연 사유 코드를 분류하는 규칙", ts(5, 26, 11, 30), "M_D",
        ["DOC-REASON"], "2026-06-05",
        [(ts(5, 26, 13, 0), "M_D", "IN_PROGRESS"), (ts(6, 2, 14, 10), "M_D", "IN_REVIEW"), (ts(6, 4, 11, 0), "M_A", "DONE")])
started("T13", "모니터링 대시보드", "수집·웹훅·API 지표 대시보드와 알림 규칙", ts(5, 26, 11, 35), "M_E", ["DOC-MONITOR"],
        "2026-06-05", [(ts(5, 26, 14, 0), "M_E", "IN_PROGRESS"), (ts(6, 5, 11, 0), "M_E", "DONE")])
started("T14", "앱 푸시 권한 처리", "Android·iOS 알림 권한 요청과 푸시 수신 처리", ts(6, 1, 11, 30), "M_C", ["DOC-PUSH"],
        "2026-06-12",
        [(ts(6, 2, 10, 0), "M_C", "IN_PROGRESS"), (ts(6, 11, 10, 0), "M_C", "IN_REVIEW"), (ts(6, 11, 17, 0), "M_A", "DONE")])
started("T15", "정산 리포트 배치", "택배사별 월간 지연 건수 리포트 배치 (데이터 웨어하우스 기준)", ts(6, 1, 11, 35), "M_B",
        ["DOC-SETTLE"], "2026-06-12",
        [(ts(6, 2, 9, 30), "M_B", "IN_PROGRESS"), (ts(6, 10, 15, 0), "M_B", "IN_REVIEW"), (ts(6, 11, 11, 0), "M_A", "DONE")])
started("T16", "장애 대응 런북·롤백 리허설", "장애 등급·연락 체계 정리와 스테이징 롤백 리허설", ts(6, 1, 11, 40), "M_E",
        ["DOC-RUNBOOK", "DOC-ROLLBACK"], "2026-06-12",
        [(ts(6, 4, 9, 30), "M_E", "IN_PROGRESS"), (ts(6, 10, 10, 0), "M_E", "IN_REVIEW"), (ts(6, 11, 15, 0), "M_A", "DONE")])
started("T17", "파일럿 고객 피드백 정리", "사내 베타·파일럿 고객사 피드백 수집과 반영 여부 정리", ts(6, 1, 11, 45), "M_A",
        ["DOC-PILOTFB"], "2026-06-15", [(ts(6, 2, 9, 0), "M_A", "IN_PROGRESS"), (ts(6, 11, 10, 0), "M_A", "DONE")])
started("T18", "배송 알림 E2E 통합 테스트", "Android·iOS 실기기에서 지연 알림 수신까지 E2E 검증", ts(6, 8, 11, 30), "M_E",
        ["DOC-E2E"], "2026-06-17",
        [(ts(6, 8, 14, 0), "M_E", "IN_PROGRESS"), (ts(6, 16, 15, 0), "M_E", "IN_REVIEW"), (ts(6, 17, 11, 0), "M_A", "DONE")],
        assignees=["M_E", "M_C"], deps=["T14"])
started("T19", "지연 예측 모델 v2 재학습", "2026년 5월까지의 데이터로 재학습, 운영 모델 교체", ts(6, 8, 11, 35), "M_D",
        ["DOC-MODEL"], "2026-06-18",
        [(ts(6, 8, 13, 0), "M_D", "IN_PROGRESS"), (ts(6, 16, 15, 10), "M_D", "IN_REVIEW"), (ts(6, 17, 10, 0), "M_A", "DONE")])
started("T20", "프로젝트 회고 문서", "릴리스 회고와 기여 내역 정리", ts(6, 15, 11, 30), "M_A", ["DOC-RETRO"], "2026-06-19",
        [(ts(6, 15, 14, 0), "M_A", "IN_PROGRESS"), (ts(6, 19, 15, 0), "M_A", "DONE")])

# ====================================================================== Claim
CLAIMS = [
    ("CLM-01", "M_E", ts(6, 18, 17, 0),
     "웹훅 서명 검증이 스테이징에서만 401로 실패할 때, 게이트웨이의 요청 본문 변환 설정이 원인인 걸 찾아서 웹훅 경로를 변환 대상에서 빼 "
     "현우님이 문제를 해결하도록 도왔습니다."),
    ("CLM-02", "M_C", ts(6, 19, 10, 0), "배송 추적 지도 화면을 구현했고, 배송 상태별 마커 색상 아이디어도 제가 냈습니다."),
    ("CLM-03", "M_D", ts(6, 19, 11, 0), "지연 예측 모델 v1과 v2를 학습하고 결과를 정리했습니다."),
    ("CLM-04", "M_A", ts(6, 19, 14, 0),
     "온길익스프레스 운영 키가 늦어지자 파일럿 택배사 범위를 3개사로 줄이고 택배사 연동 일정을 옮기는 조정을 했습니다."),
]

# ====================================================================== 시뮬레이션 응답
# (키, trigger, 응답자, 대상 담당자, Task, from, until, 지연(분), 의도, 본문, 정답 의미, Block 종류, 주석)
SIM = []


def sim(key, trigger, responder, about, tid, frm, until, delay, intent, text, semantic, block_kind=None, note=""):
    SIM.append(dict(key=key, trigger=trigger, responder=responder, about=about, task=tid, frm=frm, until=until,
                    delay=delay, intent=intent, text=text, semantic=semantic, block_kind=block_kind, note=note))


def status(key, who, tid, frm, until, delay, text, semantic, block_kind=None, note=""):
    sim(key, "CHECKIN", who, who, tid, frm, until, delay, "STATUS_CHECK", text, semantic, block_kind, note)


def support(key, supporter, about, tid, frm, until, delay, text, semantic, note=""):
    sim(key, "SUPPORT_REQUEST", supporter, about, tid, frm, until, delay, None, text, semantic, None, note)


END = ts(6, 19, 23, 59)
# --- 일상적인 상태 확인 응답 (Case가 없는 기간)
status("t01", "M_A", "T01", ts(4, 27, 11, 30), ts(5, 8, 23, 59), 40,
       "정의서 초안은 거의 다 썼어요. 수요일 리뷰 전에 올려 둘게요.", "REPORTS_ON_TRACK")
status("t02", "M_B", "T02", ts(4, 27, 11, 35), ts(5, 15, 23, 59), 30,
       "수집 API는 계획대로 가고 있어요. 이번 주에 통합 테스트까지 붙일 예정입니다.", "REPORTS_ON_TRACK")
status("t03", "M_C", "T03", ts(4, 27, 11, 40), ts(5, 11, 23, 59), 50,
       "로그인까지 붙였고 지금은 공통 API 클라이언트 정리하는 중이에요.", "REPORTS_ON_TRACK")
status("t04", "M_E", "T04", ts(4, 27, 11, 45), ts(5, 16, 0, 0), 35,
       "CI는 다 됐고 앱 빌드 워크플로만 남았어요. 금요일 전에는 끝낼게요.", "REPORTS_ON_TRACK")
status("t05_early", "M_D", "T05", ts(4, 28, 11, 0), ts(5, 13, 0, 0), 45,
       "피처 정리하는 중이고, 다음 주부터 모델 학습 들어가요.", "REPORTS_ON_TRACK")
status("t06_early", "M_B", "T06", ts(5, 6, 11, 40), ts(5, 21, 0, 0), 30,
       "누리·바로는 붙였고 나머지 두 곳 진행 중이에요.", "REPORTS_ON_TRACK")
status("t07_early", "M_C", "T07", ts(5, 6, 11, 45), ts(5, 18, 0, 0), 40,
       "설정 화면 구조 잡는 중이에요. 다음 주에 디자인 리뷰 받을 예정이에요.", "REPORTS_ON_TRACK")
status("t20", "M_A", "T20", ts(6, 15, 11, 30), END, 30,
       "회고 문서 틀 만들어 뒀고 금요일에 정리해서 올릴게요.", "REPORTS_ON_TRACK")
# --- Case 응답
status("case_d_gap", "M_D", "T05", ts(5, 13, 0, 0), ts(5, 22, 23, 59), 150,
       "하이퍼파라미터 탐색을 학습 클러스터에 걸어 둬서 한동안 올릴 게 없었어요. 중간 결과를 보면 baseline보다 오차가 15% 정도 줄고 있어서 "
       "계획대로 가고 있고, 수요일(20일)에 결과 노트북 올릴게요.", "REPORTS_ON_TRACK")
status("case_c_figma", "M_C", "T07", ts(5, 18, 0, 0), ts(5, 28, 0, 0), 60,
       "피그마로 화면 시안 잡고 있어요. 목요일 디자인 리뷰 끝나면 바로 코드로 옮길 거라 일정은 괜찮아요.", "REPORTS_ON_TRACK",
       note="진행·예정을 나타내는 정형 어휘 없이 정상 진행을 말함")
status("case_e_load", "M_E", "T09", ts(5, 19, 10, 30), ts(5, 29, 0, 0), 45,
       "로컬에서 k6로 시나리오 돌리면서 병목 구간 찾고 있어요. 결과는 목요일에 리포트로 정리해서 올릴 예정입니다.", "REPORTS_ON_TRACK")
status("case_a_notion", "M_A", "T10", ts(5, 19, 10, 0), ts(5, 29, 0, 0), 30,
       "가이드 본문은 노션에서 고객사 담당자들이랑 같이 보면서 쓰고 있어요. 거의 다 써서 수요일에 공유 문서로 옮겨 둘게요.",
       "REPORTS_ON_TRACK", note="작업 장소가 기록 밖(노션)이라는 설명")
status("case_b_webhook", "M_B", "T08", ts(5, 20, 16, 0), ts(5, 27, 10, 30), 50,
       "웹훅 서명 검증에서 막혀 있어요. 로컬에선 통과하는데 스테이징에만 올리면 누리택배 이벤트가 전부 401이에요. "
       "서명 만드는 방식은 택배사 문서대로 맞춘 것 같은데 왜 다른지 이틀째 못 찾고 있어요.", "REPORTS_BLOCKED", "INTERNAL_ISSUE")
status("case_b_ongil", "M_B", "T06", ts(5, 21, 0, 0), ts(6, 5, 0, 0), 40,
       "누리·바로·한결 3개사는 연동 끝났고, 온길익스프레스만 운영 API 키가 안 나와서 더 진행할 수가 없어요. "
       "업체 계약 담당자한테 두 번 메일 보냈는데 아직 답이 없어요.", "REPORTS_BLOCKED", "EXTERNAL_DEPENDENCY")
status("case_b_ongil_late", "M_B", "T06", ts(6, 5, 0, 0), END, 40,
       "온길 운영 키는 여전히 회신이 없어요. 나머지 3개사는 파일럿에서 잘 돌고 있어서, 온길은 정식 릴리스 이후로 미뤘어요.",
       "REPORTS_BLOCKED", "EXTERNAL_DEPENDENCY", note="남은 범위가 외부 회신 대기로 멈춘 상태. 다른 범위가 잘 돈다는 말이 섞여 있음")
status("case_c_map", "M_C", "T11", ts(5, 29, 10, 0), ts(6, 2, 9, 0), 70,
       "운영 베타에서만 지도가 회색으로 나오고 타일이 하나도 안 불러와져요. 브라우저 콘솔에는 이미지 로드가 정책 위반으로 거부됐다는 에러가 "
       "찍히는데, 제 코드는 바뀐 게 없어서 어디를 봐야 할지 몰라 막혀 있어요.", "REPORTS_BLOCKED", "INTERNAL_ISSUE",
       note="원인은 팀 내부 운영 설정 변경 (외부 의존 아님)")
status("case_d_reason", "M_D", "T12", ts(5, 28, 11, 0), ts(6, 1, 15, 0), 40,
       "규칙 초안은 만들었는데 사유 코드 두 개가 겹치는 건을 어떻게 분류할지 정해지지 않아서 막혀 있어요. "
       "기획 쪽 기준이 있어야 진행할 수 있을 것 같아요.", "REPORTS_BLOCKED", "INTERNAL_ISSUE",
       note="팀 내 의사결정(기획 기준) 대기")
status("case_c_push", "M_C", "T14", ts(6, 8, 12, 0), ts(6, 10, 16, 0), 30,
       "iOS 빌드에서 푸시 권한 팝업이 안 떠서 막혀 있어요. 코드는 안드로이드랑 같은 흐름인데 iOS만 안 돼요.",
       "REPORTS_BLOCKED", "INTERNAL_ISSUE", note="첫 확인(6/4~6/8 오전)에는 응답하지 않았고, 이후 다시 물으면 답한다")
status("case_b_schema", "M_B", "T15", ts(6, 5, 0, 0), ts(6, 9, 16, 0), 45,
       "막혔다기보다는요, 데이터플랫폼팀이 원천 테이블 스키마를 바꾼다고 해서 그게 확정될 때까지 손을 못 대고 있어요. "
       "확정만 되면 하루면 끝나요.", "REPORTS_BLOCKED", "EXTERNAL_DEPENDENCY",
       note="'막혔다기보다는' 완곡 부정 + 다른 팀 결정 대기 (외부 의존)")
status("case_e_rollback", "M_E", "T16", ts(6, 4, 18, 10), ts(6, 9, 11, 0), 35,
       "문제 없을 줄 알았는데 스테이징에서 롤백 리허설을 돌려 보니 DB 마이그레이션 V7 되돌리기가 계속 실패해요. "
       "파티션 테이블로 바꾼 버전이라 down 스크립트를 어떻게 짜야 할지 몰라서 거기서 멈춰 있어요.", "REPORTS_BLOCKED", "INTERNAL_ISSUE",
       note="'문제 없을 줄 알았는데'는 막힘을 부정하는 말이 아님")
status("case_a_zero", "M_A", "T17", ts(6, 5, 0, 0), ts(6, 11, 10, 0), 30,
       "고객사 세 곳 통화는 다 끝났고 남은 미해결 이슈는 0건이에요. 오늘 오후에 최종 정리본 올릴게요.", "REPORTS_ON_TRACK",
       note="'0건'은 남은 문제가 없다는 뜻")
status("case_e_e2e", "M_E", "T18", ts(6, 10, 0, 0), ts(6, 16, 14, 0), 40,
       "제 쪽 안드로이드 시나리오는 다 돌렸어요. iOS 쪽은 수빈님 디바이스팜 계정 갱신 결재가 안 나서 대기 중이고, 그게 풀려야 통합 결과를 "
       "낼 수 있어요.", "REPORTS_BLOCKED", "EXTERNAL_DEPENDENCY",
       note="응답자 본인 몫은 끝났지만 Task는 공동 담당자의 외부 결재 대기로 멈춤")
status("case_c_e2e", "M_C", "T18", ts(6, 10, 0, 0), ts(6, 16, 14, 0), 40,
       "iOS E2E를 돌려야 하는데 디바이스팜 계정이 만료돼서 구매팀 갱신 결재를 기다리는 중이에요. 결재 나기 전엔 진행할 수가 없어요.",
       "REPORTS_BLOCKED", "EXTERNAL_DEPENDENCY")
status("case_d_v2", "M_D", "T19", ts(6, 10, 16, 0), ts(6, 17, 0, 0), 120,
       "재학습 잡이 아직 돌고 있어요. 지난번이랑 같은 방식이라 16일 화요일에 결과 확인하고 바로 올릴게요.", "REPORTS_ON_TRACK")
# --- 지원 요청 응답 (그럴 법한 지원자 모두: 실제로 도울 수 있는 사람은 수락, 아닌 사람은 사양·다른 사람 추천)
W8 = (ts(5, 20, 16, 0), ts(5, 27, 10, 30))
support("s08_e", "M_E", "M_B", "T08", *W8, 40,
        "네, 오늘 오후에 현우님이랑 같이 볼게요. 지난주에 게이트웨이에서 요청 본문 변환을 켜 둔 게 있어서 그쪽부터 확인해 보면 될 것 같아요.",
        "ACCEPTS_SUPPORT")
support("s08_c", "M_C", "M_B", "T08", *W8, 60,
        "웹훅 쪽은 제가 다뤄 본 적이 없어서 도움이 될지 모르겠어요. 게이트웨이 설정은 다인님이 하셨으니 다인님께 여쭤보는 게 빠를 것 같아요.",
        "DECLINES_SUPPORT", note="거절 어휘 없이 다른 사람을 추천")
support("s08_d", "M_D", "M_B", "T08", *W8, 60, "이번 주는 모델 마무리 때문에 시간이 없어요. 죄송해요.", "DECLINES_SUPPORT")
support("s08_a", "M_A", "M_B", "T08", *W8, 30, "서명 검증은 제가 봐도 잘 모를 것 같아요. 개발 쪽에서 보시는 게 좋겠어요.",
        "DECLINES_SUPPORT")
W11 = (ts(5, 29, 10, 0), ts(6, 2, 9, 0))
support("s11_e", "M_E", "M_C", "T11", *W11, 50,
        "앗, 제가 목요일에 운영 ingress에 CSP 헤더를 넣었는데 지도 타일 도메인을 img-src에 안 넣었을 수 있어요. 바로 확인해 볼게요.",
        "ACCEPTS_SUPPORT")
support("s11_a", "M_A", "M_C", "T11", *W11, 30,
        "저는 화면 기획만 해서 원인까지는 잘 모르겠어요. 운영에서만 그렇다면 인프라 쪽 변경을 먼저 확인해 보시는 게 좋을 것 같아요.",
        "DECLINES_SUPPORT", note="관련 기획 문서 작성자지만 원인 해결은 못 한다고 답함")
support("s11_b", "M_B", "M_C", "T11", *W11, 60, "지도 쪽은 제가 다뤄 본 적이 없어서 도움드리기 어려워요.", "DECLINES_SUPPORT")
support("s11_d", "M_D", "M_C", "T11", *W11, 60, "프론트 지도 라이브러리는 잘 몰라서요, 도와드리기 어려울 것 같아요.", "DECLINES_SUPPORT")
W14 = (ts(6, 4, 15, 0), ts(6, 10, 9, 40))
support("s14_e", "M_E", "M_C", "T14", *W14, 40, "네, 앱 서명이랑 프로비저닝은 제가 설정했으니 그쪽부터 같이 볼게요.", "ACCEPTS_SUPPORT")
support("s14_b", "M_B", "M_C", "T14", *W14, 60, "iOS 앱은 경험이 없어서 도움드리기 어려워요.", "DECLINES_SUPPORT")
support("s14_d", "M_D", "M_C", "T14", *W14, 60, "앱 쪽은 제가 잘 몰라요. 다른 분께 부탁드리는 게 좋겠어요.", "DECLINES_SUPPORT")
support("s14_a", "M_A", "M_C", "T14", *W14, 30, "기술적인 부분이라 제가 도와드리긴 어려워요.", "DECLINES_SUPPORT")
W16 = (ts(6, 4, 18, 10), ts(6, 9, 11, 0))
support("s16_b", "M_B", "M_E", "T16", *W16, 40,
        "네, V7은 제가 만든 거라 내일 오전에 같이 볼게요. 파티션 전환이라 down을 이름만 바꿔서는 못 되돌려요.", "ACCEPTS_SUPPORT")
support("s16_c", "M_C", "M_E", "T16", *W16, 60, "DB 마이그레이션은 잘 몰라서 도움이 안 될 것 같아요.", "DECLINES_SUPPORT")
support("s16_d", "M_D", "M_E", "T16", *W16, 60, "데이터 쪽이긴 한데 운영 DB 마이그레이션은 제 영역이 아니라서 어려워요.", "DECLINES_SUPPORT")
support("s16_a", "M_A", "M_E", "T16", *W16, 30, "제가 직접 도와드리긴 어렵고, 현우님께 같이 봐 달라고 말씀드려 볼게요.", "DECLINES_SUPPORT",
        note="'볼게요'가 있지만 본인이 지원하겠다는 뜻이 아님")

# ====================================================================== 사람의 승인·거절 (지원 요청 제안에 대한 결정)
# (Task, 지원받는 담당자, 결정자, 결정, from, until, 지연(분), note)
DECISIONS = [
    ("T08", "M_B", "M_A", "APPROVE", ts(5, 20, 16, 0), ts(5, 27, 10, 30), 30, "좋아요, 같이 봐 주세요."),
    ("T11", "M_C", "M_A", "APPROVE", ts(5, 29, 10, 0), ts(6, 2, 9, 0), 40, "베타 중이라 빨리 보면 좋겠어요."),
    ("T12", "M_D", "M_A", "REJECT", ts(5, 28, 11, 0), ts(6, 1, 15, 0), 30,
     "월요일 회의에서 제가 기준을 정해서 바로 공유할게요. 지원 요청은 안 보내셔도 돼요."),
    ("T14", "M_C", "M_A", "APPROVE", ts(6, 4, 15, 0), ts(6, 10, 9, 40), 30, "파일럿 전에 풀려야 해요. 진행해 주세요."),
    ("T15", "M_B", "M_A", "REJECT", ts(6, 4, 15, 0), ts(6, 9, 16, 0), 30,
     "데이터플랫폼팀 일정 문제라 팀 내 지원으로 풀 일이 아니에요. 제가 그쪽 팀장님께 일정 확인할게요."),
    ("T16", "M_E", "M_A", "APPROVE", ts(6, 4, 18, 10), ts(6, 9, 11, 0), 20, "현우님이 보면 빠를 것 같아요."),
    ("T06", "M_B", "M_A", "REJECT", ts(5, 20, 0, 0), END, 30, "외부 업체 회신 문제라 팀원이 도울 수 있는 일이 아니에요."),
    ("T17", "M_A", "M_B", "REJECT", ts(6, 4, 0, 0), ts(6, 12, 0, 0), 30, "가은님께 확인해 보니 막힌 게 아니라 거의 끝났다고 하네요."),
    ("T18", "M_E", "M_A", "REJECT", ts(6, 10, 0, 0), ts(6, 17, 0, 0), 30, "디바이스팜 결재 대기라 팀 내 지원으로 풀 일이 아니에요."),
]


# ====================================================================== 번호 부여
def assign_ids():
    revs = sorted(REVS, key=lambda r: (r["edited_at"], r["key"]))
    rid = {r["key"]: f"REV-{i:03d}" for i, r in enumerate(revs, 1)}
    msgs = sorted(MSGS, key=lambda m: (m["sent_at"], m["key"]))
    mid = {m["key"]: f"MSG-{i:03d}" for i, m in enumerate(msgs, 1)}
    sims = {s["key"]: f"SIM-{i:03d}" for i, s in enumerate(SIM, 1)}
    return revs, rid, msgs, mid, sims


REVS_SORTED, RID, MSGS_SORTED, MID, SID = assign_ids()


def R(*keys):
    return [RID[k] for k in keys]


def M(*keys):
    return [MID[k] for k in keys]


# ====================================================================== Ground Truth
def checkin(tid, who, content, semantic):
    return {"kind": "CHECKIN_REPLY", "task_id": tid, "responder_id": who, "about_member_id": None,
            "expected_content": content, "question_intent": "STATUS_CHECK", "expected_semantic_outcome": semantic}


def support_reply(tid, supporter, about, content):
    return {"kind": "SUPPORT_REPLY", "task_id": tid, "responder_id": supporter, "about_member_id": about,
            "expected_content": content, "question_intent": None, "expected_semantic_outcome": "ACCEPTS_SUPPORT"}


def stagnation(gid, case, member, tid, *, block, evaluation_as_of, final, evidence, interactive=(), started=None,
               cause=None, kind=None, sequence=None, forbidden=None, intervention=None, resolved=None,
               inaccessible=(), candidate_expected=True, tolerance=24):
    if forbidden is None:
        forbidden = [] if block else ["CONFIRMED_BLOCK", "RESOLVED"]
    return {"gt_stagnation_id": gid, "case_id": case, "project_id": PID, "member_id": member, "task_id": tid,
            "is_actual_block": block, "block_started_at": started, "block_start_tolerance_hours": tolerance,
            "block_cause": cause, "evaluation_as_of": evaluation_as_of, "expected_final_state": final,
            "expected_state_sequence": sequence, "forbidden_states": forbidden, "expected_intervention": intervention,
            "resolved_at": resolved, "expected_evidence_ids": list(evidence),
            "expected_interactive_evidence": list(interactive), "inaccessible_source_ids": list(inaccessible),
            "candidate_expected": candidate_expected, "block_kind": kind}


def supported_by(member, earliest):
    return {"intervention_type": "SUPPORT", "supporter_member_id": member, "earliest_at": earliest}


CRB = ["STAGNATION_CANDIDATE", "CONFIRMED_BLOCK", "RESOLVED"]
CB = ["STAGNATION_CANDIDATE", "CONFIRMED_BLOCK"]

STAGNATIONS = [
    stagnation("GTS-01", "CASE01", "M_D", "T05", block=False, evaluation_as_of=ts(5, 22, 0, 0), final="NORMAL",
               evidence=R("d_search_submit", "d_v1_result") + M("d_v1") + ["T05"],
               interactive=[checkin("T05", "M_D", "학습 클러스터에서 탐색이 도는 중이라 기록이 없었을 뿐 계획대로 진행 중", "REPORTS_ON_TRACK")]),
    stagnation("GTS-02", "CASE02", "M_C", "T07", block=False, evaluation_as_of=ts(5, 28, 0, 0), final="NORMAL",
               evidence=R("c_settings_store", "c_settings_impl") + M("c_design_review") + ["T07"],
               interactive=[checkin("T07", "M_C", "피그마로 시안 작업 중이며 일정 문제 없음", "REPORTS_ON_TRACK")]),
    stagnation("GTS-03", "CASE02", "M_E", "T09", block=False, evaluation_as_of=ts(5, 29, 0, 0), final="NORMAL",
               evidence=R("e_load_more", "e_load_report") + M("e_load") + ["T09"],
               interactive=[checkin("T09", "M_E", "로컬에서 부하 테스트를 돌리는 중, 목요일 리포트 예정", "REPORTS_ON_TRACK")]),
    stagnation("GTS-04", "CASE02", "M_A", "T10", block=False, evaluation_as_of=ts(5, 29, 0, 0), final="NORMAL",
               evidence=R("a_onboard_toc", "a_onboard_move") + ["UT-MT05-05", "T10"],
               interactive=[checkin("T10", "M_A", "노션에서 고객사와 함께 작성 중, 수요일에 공유 문서로 이전", "REPORTS_ON_TRACK")]),
    stagnation("GTS-05", "CASE03", "M_B", "T08", block=True, started=ts(5, 20, 16, 40), kind="INTERNAL_ISSUE",
               cause="API 게이트웨이의 요청 본문 변환(JSON 정규화)이 웹훅 경로에도 적용되어, 앱이 받은 본문이 택배사가 서명한 원문과 달라 "
                     "HMAC 검증이 항상 실패(401)",
               evaluation_as_of=ts(5, 29, 0, 0), final="RESOLVED", sequence=CRB,
               intervention=supported_by("M_E", ts(5, 20, 16, 40)), resolved=ts(5, 27, 10, 30),
               evidence=R("b_webhook_hmac", "e_gw_transform", "e_gw_exempt", "b_webhook_fix")
               + M("b_401", "e_gw_fix") + ["T08"],
               interactive=[checkin("T08", "M_B", "스테이징에서만 서명 검증 401, 원인을 못 찾아 막힘", "REPORTS_BLOCKED"),
                            support_reply("T08", "M_E", "M_B", "게이트웨이 본문 변환을 의심하며 지원 수락")],
               inaccessible=M("dm_b_e", "dm_e_b")),
    stagnation("GTS-06", "CASE04", "M_C", "T11", block=True, started=ts(5, 29, 10, 20), kind="INTERNAL_ISSUE",
               cause="운영 ingress에 추가한 Content-Security-Policy의 img-src에 지도 타일 도메인이 없어 운영에서만 타일 로드가 차단됨",
               evaluation_as_of=ts(6, 5, 0, 0), final="RESOLVED", sequence=CRB,
               intervention=supported_by("M_E", ts(5, 29, 10, 20)), resolved=ts(6, 2, 9, 0),
               evidence=R("e_csp", "e_csp_fix", "c_map_confirm") + M("c_gray", "c_policy", "e_csp_fix") + ["T11"],
               interactive=[checkin("T11", "M_C", "운영에서만 지도 타일이 정책 위반으로 차단되어 막힘", "REPORTS_BLOCKED"),
                            support_reply("T11", "M_E", "M_C", "본인이 넣은 CSP 헤더를 원인으로 짚으며 지원 수락")]),
    stagnation("GTS-07", "CASE05", "M_B", "T06", block=True, started=ts(5, 21, 9, 0), kind="EXTERNAL_DEPENDENCY",
               cause="외부 업체(온길익스프레스)가 운영 API 키를 발급하지 않음 — 프로젝트 종료까지 회신 없음",
               evaluation_as_of=ts(6, 19, 12, 0), final="CONFIRMED_BLOCK", sequence=CB, forbidden=["RESOLVED"],
               evidence=R("b_carrier_ongil") + M("b_ongil_req", "b_ongil_again", "a_scope", "b_ongil_later") + ["T06"],
               interactive=[checkin("T06", "M_B", "온길 운영 키 미발급, 업체 회신 없음으로 진행 불가", "REPORTS_BLOCKED")]),
    stagnation("GTS-08", "CASE06", "M_D", "T12", block=True, started=ts(5, 28, 11, 20), kind="INTERNAL_ISSUE",
               cause="지연 사유 코드가 여러 개 해당할 때의 우선순위가 요구사항에 정해지지 않아 분류 기준을 확정할 수 없음 (기획 결정 필요)",
               evaluation_as_of=ts(6, 5, 0, 0), final="RESOLVED", sequence=CRB,
               intervention=supported_by("M_A", ts(5, 28, 11, 20)), resolved=ts(6, 1, 15, 0),
               evidence=R("a_prd_reason", "d_reason_dup", "a_prd_priority", "d_reason_fix") + M("d_dup")
               + ["UT-MT06-02", "T12"],
               interactive=[checkin("T12", "M_D", "사유 중복 시 분류 기준이 없어 막힘, 기획 기준 필요", "REPORTS_BLOCKED")]),
    stagnation("GTS-09", "CASE07", "M_E", "T13", block=False, evaluation_as_of=ts(6, 5, 0, 0), final="NORMAL",
               evidence=R("e_monitor_rules", "e_monitor_panel") + M("e_training") + ["T13"], candidate_expected=None),
    stagnation("GTS-10", "CASE08", "M_C", "T14", block=True, started=ts(6, 4, 15, 0), kind="INTERNAL_ISSUE",
               cause="iOS App ID에 Push Notifications capability가 없어 프로비저닝 프로필·entitlements에 푸시 권한이 빠짐",
               evaluation_as_of=ts(6, 12, 0, 0), final="RESOLVED", sequence=CRB,
               intervention=supported_by("M_E", ts(6, 4, 15, 0)), resolved=ts(6, 10, 16, 0),
               evidence=R("e_appsign", "c_push_ios", "e_appsign_push", "c_push_fix") + M("c_push_stuck", "e_push")
               + ["T14"],
               interactive=[checkin("T14", "M_C", "iOS에서만 푸시 권한 팝업이 뜨지 않아 막힘", "REPORTS_BLOCKED"),
                            support_reply("T14", "M_E", "M_C", "앱 서명·프로비저닝 설정자로서 지원 수락")]),
    stagnation("GTS-11", "CASE09", "M_B", "T15", block=True, started=ts(6, 4, 15, 0), kind="EXTERNAL_DEPENDENCY",
               cause="데이터플랫폼팀(다른 팀)의 원천 테이블 스키마 변경 확정 대기",
               evaluation_as_of=ts(6, 12, 0, 0), final="RESOLVED", sequence=CRB, resolved=ts(6, 9, 16, 0),
               evidence=R("b_settle_query", "b_settle_fix") + M("b_schema", "b_schema_done") + ["UT-MT07-03", "T15"],
               interactive=[checkin("T15", "M_B", "다른 팀의 스키마 확정을 기다리느라 진행 못 함 (외부 의존)", "REPORTS_BLOCKED")]),
    stagnation("GTS-12", "CASE10", "M_E", "T16", block=True, started=ts(6, 4, 18, 10), kind="INTERNAL_ISSUE",
               cause="파티션 테이블로 바꾼 V7 마이그레이션에 down 스크립트가 없어 롤백 리허설 실패",
               evaluation_as_of=ts(6, 12, 0, 0), final="RESOLVED", sequence=CRB,
               intervention=supported_by("M_B", ts(6, 4, 18, 10)), resolved=ts(6, 9, 11, 0),
               evidence=R("b_mig_v7", "e_rollback", "b_v7_down", "e_runbook_rerun") + M("e_v7_fail", "b_v7_down")
               + ["T16"],
               interactive=[checkin("T16", "M_E", "V7 down 마이그레이션 실패로 롤백 리허설이 멈춤", "REPORTS_BLOCKED"),
                            support_reply("T16", "M_B", "M_E", "V7 작성자로서 지원 수락")]),
    stagnation("GTS-13", "CASE11", "M_A", "T17", block=False, evaluation_as_of=ts(6, 12, 0, 0), final="NORMAL",
               evidence=R("a_pilotfb_first", "a_pilotfb_final") + ["T17"],
               interactive=[checkin("T17", "M_A", "고객사 통화 완료, 미해결 이슈 0건, 최종본 업로드 예정", "REPORTS_ON_TRACK")]),
    stagnation("GTS-14", "CASE12", "M_C", "T18", block=True, started=ts(6, 10, 10, 0), kind="EXTERNAL_DEPENDENCY",
               cause="iOS 실기기 테스트용 디바이스팜 계정 만료 — 구매팀 갱신 결재 대기",
               evaluation_as_of=ts(6, 17, 0, 0), final="RESOLVED", sequence=CRB, resolved=ts(6, 16, 14, 0),
               evidence=R("c_e2e_ios", "c_e2e_ios_result") + M("c_devicefarm", "c_devicefarm2", "c_devicefarm_done")
               + ["UT-MT08-02", "T18"],
               interactive=[checkin("T18", "M_C", "디바이스팜 갱신 결재 대기로 iOS E2E 진행 불가", "REPORTS_BLOCKED")]),
    stagnation("GTS-15", "CASE13", "M_D", "T19", block=False, evaluation_as_of=ts(6, 17, 0, 0), final="NORMAL",
               evidence=R("d_v2_submit", "d_v2_result") + M("d_v2") + ["T19"], candidate_expected=None,
               interactive=[checkin("T19", "M_D", "재학습 잡이 도는 중, 16일 결과 업로드 예정", "REPORTS_ON_TRACK")]),
]

CONTRIBUTIONS = [
    ("GTC-01", "CASE14", "M_E", "SUPPORT", "웹훅 401의 원인(게이트웨이 본문 변환)을 찾아 웹훅 경로를 변환 대상에서 제외",
     R("e_gw_exempt", "b_webhook_fix") + M("e_gw_fix", "b_webhook_ok"), ["T08"], "CLM-01", M("dm_b_e", "dm_e_b")),
    ("GTC-02", "CASE15", "M_C", "EXECUTION", "배송 추적 지도 화면 구현",
     R("c_map_tiles", "c_map_markers", "c_map_confirm") + ["T11"], ["T11"], "CLM-02", []),
    ("GTC-03", "CASE15", "M_A", "IDEA", "배송 상태별 마커 색상(4색) 제안",
     M("a_marker", "c_marker_ok") + R("c_map_markers"), ["T11"], None, []),
    ("GTC-04", "CASE16", "M_D", "EXECUTION", "지연 예측 모델 v1·v2 학습과 결과 정리",
     R("d_baseline", "d_v1_result", "d_v2_result") + ["T05", "T19"], ["T05", "T19"], "CLM-03", []),
    ("GTC-05", "CASE17", "M_A", "COORDINATION", "온길 운영 키 지연에 맞춰 파일럿 택배사 범위와 연동 일정을 조정",
     M("a_scope") + R("a_sched_scope") + ["T06"], ["T06"], "CLM-04", []),
    ("GTC-06", "CASE08", "M_E", "SUPPORT", "iOS 푸시 권한 문제의 원인(App ID capability 누락)을 찾아 프로비저닝 프로필 재발급",
     R("e_appsign_push") + M("e_push"), ["T14"], None, []),
    ("GTC-07", "CASE10", "M_B", "SUPPORT", "V7 down 마이그레이션을 작성해 롤백 리허설 재개를 지원",
     R("b_v7_down") + M("b_v7_down"), ["T16"], None, []),
    ("GTC-08", "CASE04", "M_E", "SUPPORT", "운영 CSP의 img-src에 지도 타일 도메인을 추가해 운영 지도 표시 문제 해결",
     R("e_csp_fix") + M("e_csp_fix"), ["T11"], None, []),
]

JUDGMENTS = [
    ("GTCL-01", "CASE14", "CLM-01", "M_E", "SUPPORT", "웹훅 경로를 게이트웨이 변환 대상에서 빼 B의 401 문제 해결을 도왔다",
     "VERIFIED", M("e_gw_fix", "b_webhook_ok") + R("e_gw_exempt"), [], "GTC-01"),
    ("GTCL-02", "CASE15", "CLM-02", "M_C", "EXECUTION", "배송 추적 지도 화면을 구현했다",
     "VERIFIED", R("c_map_tiles", "c_map_markers", "c_map_confirm"), [], "GTC-02"),
    ("GTCL-03", "CASE15", "CLM-02", "M_C", "IDEA", "배송 상태별 마커 색상 아이디어를 냈다",
     "INSUFFICIENT_EVIDENCE", [], M("a_marker", "c_marker_ok"), None),
    ("GTCL-04", "CASE16", "CLM-03", "M_D", "EXECUTION", "지연 예측 모델 v1과 v2를 학습하고 결과를 정리했다",
     "VERIFIED", R("d_v1_result", "d_v2_result") + ["T05", "T19"], [], "GTC-04"),
    ("GTCL-05", "CASE17", "CLM-04", "M_A", "COORDINATION", "파일럿 택배사 범위와 연동 일정을 조정했다",
     "VERIFIED", M("a_scope") + R("a_sched_scope"), [], "GTC-05"),
]

CASES = [
    ("CASE01", "모델 학습 중 정상적인 장시간 공백 (D·T05)",
     "D는 5/12 하이퍼파라미터 탐색 잡을 학습 클러스터에 제출한 뒤 결과가 나온 5/20까지 Task 문서 기록을 남기지 않았다. 실제로는 계획대로 진행 중이었다.",
     ["GTS-01"], [], [], ["기록 공백만으로 Block 확정 금지. 확인 질문 후 정상 진행으로 돌아가야 한다."]),
    ("CASE02", "기록 밖 작업으로 인한 오탐 반복 (C·T07, E·T09, A·T10)",
     "피그마 시안(C), 로컬 부하 테스트(E), 노션 공동 작성(A)처럼 Task 문서 밖에서 일하는 동안 기록이 비었다. 세 건 모두 정상 진행이었다.",
     ["GTS-02", "GTS-03", "GTS-04"], [], [],
     ["같은 종류의 오탐이 반복되는 상황. Memory가 같은 상황의 판단을 보정하는지 볼 수 있다.",
      "C의 응답은 '진행 중'·'예정' 같은 정형 어휘 없이 정상 진행을 말한다."]),
    ("CASE03", "실제 Block + 지원 후보가 여럿 (B·T08 웹훅 서명 검증)",
     "B의 웹훅 HMAC 검증이 스테이징에서만 401로 실패했다. 원인은 E가 5/13 켠 게이트웨이 요청 본문 변환(JSON 정규화)이 웹훅 경로에도 "
     "적용된 것. E가 웹훅 경로를 예외 처리하고 B가 raw body 기준으로 검증을 고쳐 5/27 해결.",
     ["GTS-05"], [], [],
     ["C의 기록(토큰 만료 시 401 처리)도 '401'이라는 단어를 공유하지만 원인과 무관하다. 올바른 지원자는 게이트웨이 설정자 E.",
      "E는 5/7 B의 CI 문제를 도운 공개 기록이 있다.", "B→E 개인 DM(5/26)은 Agent가 볼 수 없다."]),
    ("CASE04", "단어만 겹치는 잘못된 지원자 후보 (C·T11 지도 화면)",
     "5/28 E가 운영 ingress에 CSP 헤더를 넣으면서 img-src에 지도 타일 도메인을 빠뜨려, 5/29 사내 베타부터 운영에서만 지도가 회색으로 나왔다. "
     "C의 보고에는 'CSP'라는 단어가 없고, A의 요구사항 문서가 '지도 타일·마커·운영 로드'라는 단어를 가장 많이 공유한다.",
     ["GTS-06"], [], ["GTC-08"],
     ["용어 겹침만 보면 A(요구사항 작성자)가 가장 관련 깊어 보이지만 A는 원인을 고칠 수 없다. 올바른 지원자는 같은 날 운영 보안 헤더를 바꾼 E.",
      "실제 해결은 C가 공개 채널에 운영 설정 변경을 물은 뒤 E가 CSP를 고친 것이다 (Agent 개입과 무관하게 해결됨)."]),
    ("CASE05", "해결되지 않는 외부 의존 Block (B·T06 택배사 연동)",
     "온길익스프레스가 운영 API 키를 발급하지 않아 4번째 택배사 연동이 멈췄다. PM이 파일럿 범위를 3개사로 줄이고 마감을 두 번 옮겼지만 "
     "프로젝트 종료까지 키는 오지 않았다.",
     ["GTS-07"], [], [],
     ["외부 업체 문제라 팀 내 지원 요청은 기대하지 않는다.",
      "6/2 리비전 '온길익스프레스 미연동 시 안내 문구 수정'은 문제 해결이 아니라 미연동 상태를 안내하는 변경이다. RESOLVED 금지."]),
    ("CASE06", "지원 제안을 사람이 거절, 담당자 측에서 해결 (D·T12 사유 분류)",
     "지연 사유 코드가 여러 개 해당할 때의 우선순위가 정해지지 않아 D가 분류 기준을 확정하지 못했다. 기준을 정할 사람은 PM(A). "
     "A는 지원 요청을 보내지 말라고 거절하고 6/1 회의에서 기준을 정했으며, D가 같은 날 분류 로직을 고쳤다.",
     ["GTS-08"], [], [],
     ["지원 제안(A) 자체는 적절하다. 사람이 거절했으므로 지원 요청은 전송되면 안 된다.",
      "해결은 지원 요청 없이 후속 기록(6/1 분류 로직 수정)으로 확인된다."]),
    ("CASE07", "응답이 없는 후보 (E·T13 모니터링 대시보드)",
     "E는 5/29 공개 채널에 다음 주 월·화 사외 교육을 알렸다. 그 사이 확인 질문에 답하지 않았고, 6/4 작업을 이어 6/5 완료했다. 실제 Block은 없었다.",
     ["GTS-09"], [], [],
     ["응답이 없다고 Block으로 추측하면 안 된다. 확인 질문 자체는 해도 되고 안 해도 된다 (공개 부재 공지가 있었음)."]),
    ("CASE08", "확인 질문에 답하지 않은 실제 Block (C·T14 iOS 푸시 권한)",
     "6/4 iOS 권한 요청을 붙인 뒤 iOS에서만 권한 팝업이 뜨지 않았다. C는 6/4~6/8 오전 확인 질문에 답하지 않았고, 6/8 공개 채널에 막혔다고 "
     "적었다. 원인은 App ID의 Push Notifications capability 누락이며, 앱 서명 설정자 E가 6/10 프로필을 재발급해 해결됐다.",
     ["GTS-10"], [], ["GTC-06"],
     ["첫 확인에 응답이 없어도 이후 공개 기록(6/8 메시지)이나 재확인으로 Block을 확인할 수 있다.",
      "E의 5/14 리비전(capability 목록에 Push 없음)이 원인과 연결되는 공개 기록이다."]),
    ("CASE09", "완곡한 표현의 외부 의존 Block (B·T15 정산 배치)",
     "다른 팀(데이터플랫폼팀)이 원천 테이블 스키마를 바꾸기로 하면서 확정본이 나올 때까지 B가 집계 쿼리를 진행할 수 없었다. 6/9 확정본이 나와 같은 날 반영했다.",
     ["GTS-11"], [], [],
     ["응답이 '막혔다기보다는요'로 시작하지만 실제로는 진행할 수 없는 상태다.",
      "다른 팀 결정 대기라 팀 내 지원 요청은 기대하지 않는다 (사람도 거절)."]),
    ("CASE10", "'문제 없을 줄 알았는데'로 시작하는 실제 Block (E·T16 롤백 리허설)",
     "B가 5/12 만든 V7 마이그레이션(파티션 전환)에 down 스크립트가 없어 E의 롤백 리허설이 실패했다. 6/9 B가 down 스크립트를 추가해 해결.",
     ["GTS-12"], [], ["GTC-07"],
     ["응답의 '문제 없을 줄 알았는데'는 막힘을 부정하는 말이 아니다.", "올바른 지원자는 V7 작성자 B."]),
    ("CASE11", "'0건'이 포함된 정상 진행 응답 (A·T17 고객 피드백)",
     "A는 고객사와 통화로 피드백을 정리하느라 문서 기록이 비었다. 확인 질문에 '남은 미해결 이슈는 0건'이라고 답했고 다음 날 최종본을 올렸다.",
     ["GTS-13"], [], [], ["'0건'은 남은 문제가 없다는 뜻이다. Block 확정 금지."]),
    ("CASE12", "공동 담당 Task에서 부 담당자의 Block (C·T18 E2E 통합 테스트)",
     "T18의 주 담당자는 E, 공동 담당자는 C다. E의 Android 몫은 끝났지만, C의 iOS 실기기 테스트가 디바이스팜 계정 만료(구매 결재 대기)로 "
     "6/10~6/16 멈췄다.",
     ["GTS-14"], [], [],
     ["막힌 사람은 부 담당자 C다. 주 담당자에게만 묻는 Agent는 C의 상태를 확인하지 못한다.",
      "주 담당자 E의 응답도 Task가 공동 담당자의 외부 결재 때문에 멈췄다고 말한다."]),
    ("CASE13", "같은 상황의 정상 공백 재발 (D·T19 모델 v2 재학습)",
     "D가 6/10 재학습 잡을 제출하고 6/16 결과를 올렸다. CASE01과 같은 종류의 정상 공백이다.",
     ["GTS-15"], [], [],
     ["확인 질문 여부는 채점하지 않는다 (Memory 보정 효과를 보는 항목). Block 확정은 금지."]),
    ("CASE14", "다른 팀원의 문제 해결 지원 (E, SUPPORT)",
     "E가 웹훅 401의 원인을 게이트웨이 설정에서 찾아 예외 처리했다 (CASE03과 같은 사건). E는 회고 폼에 이를 Claim으로 제출했다.",
     [], ["GTCL-01"], ["GTC-01"], ["개인 DM(5/26)은 근거로 쓰면 안 된다. 공개 채널 메시지와 리비전으로 확인할 수 있다."]),
    ("CASE15", "구현과 아이디어를 함께 주장 (C, EXECUTION + IDEA)",
     "C는 지도 화면을 구현했고, 상태별 마커 색상 아이디어도 자신이 냈다고 Claim했다. 마커 색상은 5/27 A가 공개 채널에서 제안하고 C가 수락했다.",
     [], ["GTCL-02", "GTCL-03"], ["GTC-02", "GTC-03"],
     ["C가 마커 색상을 구현한 리비전은 실행 근거이지 아이디어 근거가 아니다."]),
    ("CASE16", "모델 학습 (D, EXECUTION)", "D가 지연 예측 모델 v1·v2를 학습하고 결과를 정리했다.",
     [], ["GTCL-04"], ["GTC-04"], []),
    ("CASE17", "외부 지연에 따른 범위·일정 조정 (A, COORDINATION)",
     "온길 운영 키가 늦어지자 A가 파일럿 택배사 범위를 3개사로 줄이고 택배사 연동 마감을 옮겼다.",
     [], ["GTCL-05"], ["GTC-05"], []),
]


# ====================================================================== 직렬화
def build():
    members = [{"member_id": m, "project_id": PID, "label": lab, "name": n, "role": r} for m, lab, n, r in MEMBERS]
    meetings, utterances = [], []
    for mid, title, s, e, att, agenda, utts in MEETINGS:
        start = datetime(2026, *s, tzinfo=KST)
        meetings.append({"meeting_id": mid, "project_id": PID, "title": title, "started_at": start.isoformat(),
                         "ended_at": datetime(2026, *e, tzinfo=KST).isoformat(), "attendee_ids": att, "agenda": agenda})
        for i, (speaker, minute, text) in enumerate(utts, 1):
            utterances.append({"utterance_id": f"UT-{mid}-{i:02d}", "meeting_id": mid, "sequence": i,
                               "speaker_id": speaker, "spoken_at": (start + timedelta(minutes=minute)).isoformat(),
                               "text": text})
    revisions = [{"revision_id": RID[r["key"]], "project_id": PID,
                  **{k: v for k, v in r.items() if k != "key"}} for r in REVS_SORTED]
    messages = [{"message_id": MID[m["key"]], "project_id": PID, "channel": m["channel"],
                 "channel_type": "DIRECT_MESSAGE" if m["dm_to"] else "CHANNEL", "sender_id": m["sender_id"],
                 "recipient_ids": m["dm_to"] or [], "sent_at": m["sent_at"], "text": m["text"],
                 "reply_to_message_id": MID[m["reply_to"]] if m["reply_to"] else None} for m in MSGS_SORTED]
    claims = [{"claim_id": c, "project_id": PID, "member_id": who, "submitted_at": at, "source": "SELF_REPORT_FORM",
               "source_message_id": None, "text": text, "parent_claim_id": None, "claimed_type": None,
               "status": "PENDING_VERIFICATION"} for c, who, at, text in CLAIMS]
    replies = [{"reply_id": SID[s["key"]], "project_id": PID, "trigger": s["trigger"], "responder_id": s["responder"],
                "about_member_id": s["about"], "task_id": s["task"], "available_from": s["frm"],
                "available_until": s["until"], "reply_text": s["text"], "reply_delay_minutes": s["delay"],
                "question_intent": s["intent"]} for s in SIM]
    decisions = [{"decision_id": f"HDC-{i:03d}", "project_id": PID, "approver_id": approver, "decision": decision,
                  "action_type": "SUPPORT_REQUEST", "task_id": tid, "about_member_id": about, "available_from": frm,
                  "available_until": until, "delay_minutes": delay, "note": note}
                 for i, (tid, about, approver, decision, frm, until, delay, note) in enumerate(DECISIONS, 1)]
    labels = [{"reply_id": SID[s["key"]], "project_id": PID, "expected_semantic": s["semantic"],
               "expected_block_kind": s["block_kind"], "note": s["note"]} for s in SIM]
    cases = [{"case_id": c, "title": t, "scenario": sc,
              "contribution_ids": [x for x in contrib if x.startswith("GTC-")],
              "claim_judgment_ids": [x for x in judg if x.startswith("GTCL-")],
              "stagnation_ids": [x for x in stag if x.startswith("GTS-")], "evaluation_notes": notes}
             for c, t, sc, stag, judg, contrib, notes in CASES]
    contributions = [{"gt_contribution_id": g, "case_id": c, "project_id": PID, "member_id": m, "contribution_type": t,
                      "description": d, "expected_evidence_ids": ev, "related_task_ids": tasks, "related_claim_id": clm,
                      "expected_interactive_evidence": [], "inaccessible_source_ids": inacc}
                     for g, c, m, t, d, ev, tasks, clm, inacc in CONTRIBUTIONS]
    judgments = [{"gt_claim_id": g, "case_id": c, "claim_id": clm, "claimant_id": m, "claimed_type": t,
                  "atomic_claim": a, "expected_status": st, "expected_supporting_evidence_ids": sup,
                  "expected_contradicting_evidence_ids": con, "related_gt_contribution_id": rel}
                 for g, c, clm, m, t, a, st, sup, con, rel in JUDGMENTS]
    return {
        "input": {"project.json": PROJECT, "members.json": members, "meetings.json": meetings,
                  "meeting_utterances.json": utterances, "document_history.json": revisions, "tasks.json": TASKS,
                  "messages.json": messages, "contribution_claims.json": claims},
        "simulation": {"simulated_replies.json": replies, "human_decisions.json": decisions},
        "ground_truth": {"cases.json": cases, "contributions.json": contributions,
                         "claim_judgments.json": judgments, "stagnations.json": STAGNATIONS,
                         "interactive_scenarios.json": [], "reply_labels.json": labels},
    }


def main() -> None:
    for layer, files in build().items():
        out = ROOT / layer / PID
        out.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (out / name).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PID}: revisions={len(REVS)} messages={len(MSGS)} tasks={len(TASKS)} replies={len(SIM)} "
          f"stagnations={len(STAGNATIONS)}")


if __name__ == "__main__":
    main()
