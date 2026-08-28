---
inclusion: always
---

# 확정 스택 + 환경 제약 (변경 제안 금지)

## 확정 스택
- Frontend: 순수 HTML + CSS + JavaScript (React 등 프레임워크 금지, 빌드 없음)
- Backend: FastAPI (Python) + SQLite (내장 sqlite3. RDS·별도 DB 서버 금지)
- AI: Bedrock Claude — **호출 지점은 아래 2곳뿐이다. 새로 늘리지 말 것.**
  1. 판결문 "이유(reasoning)+형량(sentence)" 생성 — 호출 1회로 JSON 반환 (services/verdict_service.py)
  2. 업로드한 지출내역 파일의 표준 JSON 정규화·카테고리 분류 (services/parse_service.py)
  죄명·주문·소비유형 판정은 룰/템플릿이다. 두 곳 모두 실패 시 폴백이 있어 빈 화면이 되지 않는다.
- 배포: EC2 + nohup + 포트 8501 (현재 uvicorn으로 구동 중. v1 streamlit은 종료됨)

## 환경 제약 (어기면 AccessDenied/접속 불가 — 실측 확인된 사실)
- 외부에 열린 앱 포트는 8501 하나뿐. 서버는 반드시 8501로 리슨 (3000/80 금지)
- 이 AWS 계정은 Bedrock과 S3만 사용 가능. DynamoDB/Lambda/Textract 등 제안 금지
- Bedrock 모델 ID: global.anthropic.claude-sonnet-5 (global. 접두사 필수)
- region_name 하드코딩 금지 (서버 환경변수 AWS_DEFAULT_REGION=eu-west-2 사용), Access Key 발급 금지
- 서버 실행: appenv/bin/python -m uvicorn, 패키지는 appenv/bin/pip
- 개발은 로컬, 실행은 EC2. 로컬에는 AWS 자격증명이 없어 Bedrock 호출은 항상 실패한다 —
  정상이며, 자격증명 설정을 시도하지 말 것. 로컬 확인은 MOCK_AI=1 환경변수로

## 이미 당한 함정 (같은 실수 반복 금지 — 전부 실측으로 확인됨)

### 1. Bedrock 응답에서 content[0]["text"]를 꺼내지 말 것
Claude Sonnet 5는 content 배열의 **첫 블록으로 thinking을 반환**한다.
content[0]["text"]는 KeyError가 나고, 모든 호출이 조용히 폴백으로 떨어져 AI가 실종된다.
반드시 type == "text"인 블록을 찾아서 쓸 것. (verdict_service.py·parse_service.py 참고)

### 2. FastAPI가 400 대신 422를 내는 경로를 만들지 말 것
우리 계약서상 검증 실패는 **항상 400 + {"success": false, "error": {"code","message"}}** 이다.
그런데 아래는 전부 FastAPI 기본 422({"detail": [...]})를 낸다. 프론트가 error.message를
읽으므로 undefined가 된다.
- `body: dict = Body(...)` — 타입 어노테이션만 붙여도 FastAPI가 선검증한다
- `Query(...)` / `File(...)` 로 필수 지정
- `expense_id: int` 처럼 경로 변수에 타입 지정
해결: 어노테이션 없이 `Body(None)` / `Query(None)` / `File(None)` 로 받아서 직접 검증하고
400을 반환한다. 기존 라우터들이 이미 이 방식이니 그대로 따를 것.
(남은 구멍: 깨진 JSON 문법은 Starlette가 파싱 단계에서 422를 낸다. main.py에
 RequestValidationError 핸들러가 필요하나 아직 미처리.)

### 3. 라우트 등록 순서
`/api/expenses/{id}` 같은 경로 변수 라우트는 고정 경로보다 **뒤에** 등록해야 한다.
앞에 두면 `/api/expenses?month=...` 요청까지 {id}로 잡아먹는다.
같은 이유로 파일 업로드 경로는 `/api/expenses/import`가 아니라 **`/api/import`** 다.

## 작업 규칙
- 설계 원본은 docs/ 폴더 (팀 작성). docs에 정의되지 않은 기능을 임의로 추가하지 말 것
- 프론트-백엔드 필드명은 docs의 데이터 계약(camelCase)을 그대로 사용, 임의 변경 금지
- 카테고리·거래유형 상수는 constants.py가 단일 출처다. 새로 정의하지 말고 import할 것
- task 한 번에 하나, 항상 실행 가능한 상태 유지
- 서버 재기동 시 이전 프로세스가 남아 있으면 옛 코드로 테스트하게 된다. 포트를 정리하고 띄울 것
- 시드 데이터(77건, 2026-02~08)는 데모의 핵심이다. 테스트로 만든 행만 지우고 시드는 훼손 금지
