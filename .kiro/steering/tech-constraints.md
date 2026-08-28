---
inclusion: always
---

# 스택·환경 제약 + 실측으로 당한 함정 (변경 제안 금지)

## 지금 단계
**백엔드는 전부 구현·검증·배포 완료. 남은 것은 프론트(static/)뿐이다.**
프론트 작업 중 백엔드를 고쳐야 한다고 판단되면 **멈추고 먼저 알릴 것.** 임의 수정 금지.

## 확정 스택
- Frontend: 순수 HTML + CSS + JavaScript (프레임워크·빌드 없음, FastAPI가 정적 서빙)
- Backend: FastAPI + SQLite (내장 sqlite3)
- AI: Bedrock Claude — **호출 지점 2곳뿐. 새로 늘리지 말 것.**
  1. 판결문 이유·형량 생성 (services/verdict_service.py)
  2. 업로드 파일의 표준 JSON 정규화·카테고리 분류 (services/parse_service.py)
  죄명·소비유형 판정은 룰/템플릿이다. 두 곳 모두 실패 시 폴백이 있어 빈 화면이 되지 않는다.
- 공공데이터: 소상공인 상가(상권)정보 색인으로 카테고리 보정 (LLM 아님, 오프라인 조회)
- 배포: EC2 18.135.105.80 + nohup + 포트 8501 (uvicorn 구동 중)

## 환경 제약 (어기면 AccessDenied/접속 불가 — 실측 확인됨)
- 외부에 열린 앱 포트는 **8501 하나뿐** (3000/80 금지)
- 이 AWS 계정은 **Bedrock과 S3만** 사용 가능. DynamoDB/Lambda/Textract 등 제안 금지
- Bedrock 모델 ID: `global.anthropic.claude-sonnet-5` (global. 접두사 필수)
- region_name 하드코딩 금지 (서버 환경변수 AWS_DEFAULT_REGION=eu-west-2), Access Key 발급 금지
- 서버 실행은 `appenv/bin/python -m uvicorn`, 패키지는 `appenv/bin/pip`
- 로컬에는 AWS 자격증명이 없다. Bedrock 호출은 항상 실패하는 게 정상이며 자격증명 설정을
  시도하지 말 것. 로컬 확인은 `MOCK_AI=1`

## 실측으로 당한 함정 (같은 실수 반복 금지)

### 1. Bedrock 응답에서 `content[0]["text"]`를 꺼내지 말 것
Claude Sonnet 5는 content 배열 **첫 블록으로 thinking을 반환**한다. KeyError가 나고
모든 호출이 조용히 폴백으로 떨어져 **AI가 실종된 것처럼 보인다**(화면은 멀쩡하다).
반드시 `type == "text"`인 블록을 찾아 쓸 것.

### 2. Bedrock 요청에 `temperature`·`top_p`를 넣지 말 것
Sonnet 5가 둘 다 거부한다(`ValidationException: deprecated for this model`).
서버 실측: 파라미터 없음만 OK. 실패 시 §1과 똑같이 조용히 폴백으로 떨어진다.
샘플링 조정이 필요하면 프롬프트로 해결할 것.

### 3. FastAPI가 400 대신 422를 내는 경로를 만들지 말 것
계약상 검증 실패는 **항상 400 + `{"success": false, "error": {...}}`** 다.
아래는 전부 FastAPI 기본 422(`{"detail": [...]}`)를 낸다 → 프론트가 `error.message`를
읽으므로 undefined가 된다.
- `body: dict = Body(...)` — **타입 어노테이션만 붙여도** FastAPI가 선검증한다
- `Query(...)` / `File(...)` 로 필수 지정
- `expense_id: int` 처럼 경로 변수에 타입 지정
해결: 어노테이션 없이 `Body(None)`/`Query(None)`/`File(None)`로 받아 직접 검증하고 400 반환.
기존 라우터가 이미 이 방식이니 그대로 따를 것.
(남은 구멍: 깨진 JSON 문법은 Starlette가 파싱 단계에서 422를 낸다 — 미처리)

### 4. 라우트 등록 순서
경로 변수 라우트(`/{expense_id}`)는 고정 경로보다 **뒤에** 등록해야 한다.
앞에 두면 `/api/expenses?month=` 와 `/api/expenses/skip-review` 까지 잡아먹는다.
같은 이유로 업로드 경로는 `/api/expenses/import`가 아니라 **`/api/import`** 다.

### 5. 로컬 MOCK 통과를 신뢰하지 말 것
MOCK은 Bedrock 요청 형식도, Bedrock의 **판단**도 흉내내지 못한다. 실제로 두 번 당했다.
- `temperature` 거부 → 로컬 26개 테스트 통과, 서버에서 전 요청 실패
- 사람 이름 송금을 규칙은 EXPENSE로, Bedrock은 TRANSFER로 분류 → 로컬에서만 기능이 동작
**Bedrock이 관여하는 기능은 배포 후 `app.log`의 "Bedrock 호출 실패" 카운트까지 확인할 것.**

## 작업 규칙
- 설계 원본은 docs/ (팀 작성). docs에 없는 기능을 임의로 추가하지 말 것
- 필드명은 camelCase 계약 그대로. 카테고리·거래유형 상수는 constants.py가 단일 출처
- task 한 번에 하나, 항상 실행 가능한 상태 유지
- 서버 재기동 시 이전 프로세스가 남아 있으면 옛 코드로 테스트하게 된다. 포트를 정리하고 띄울 것
- **시드 77건(2026-02~08)은 데모의 핵심이다.** 테스트로 만든 행만 지우고 시드는 훼손 금지
