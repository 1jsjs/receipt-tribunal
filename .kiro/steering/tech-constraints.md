---
inclusion: always
---

# 확정 스택 + 환경 제약 (변경 제안 금지)

## 확정 스택 (8/28 팀 결정)
- Frontend: 순수 HTML + CSS + JavaScript (React 등 프레임워크 금지, 빌드 없음)
- Backend: FastAPI (Python) + SQLite (내장 sqlite3. RDS·별도 DB 서버 금지)
- AI: Bedrock Claude — 판결문 "이유" 산문 생성 1곳만. 죄명·형량·소비유형 판정은 룰/템플릿.
  Bedrock 실패 시 템플릿 폴백 (빈 화면 금지)
- 배포: EC2 + nohup + 포트 8501

## 환경 제약 (어기면 AccessDenied/접속 불가 — 실측 확인된 사실)
- 외부에 열린 앱 포트는 8501 하나뿐. 서버는 반드시 8501로 리슨 (3000/80 금지)
- 배포 시 기존 streamlit 프로세스를 종료한 뒤 uvicorn 실행
- 이 AWS 계정은 Bedrock과 S3만 사용 가능. DynamoDB/Lambda/Textract 등 제안 금지
- Bedrock 모델 ID: global.anthropic.claude-sonnet-5 (global. 접두사 필수)
- region_name 하드코딩 금지 (서버 환경변수 AWS_DEFAULT_REGION=eu-west-2 사용), Access Key 발급 금지
- 서버 실행: appenv/bin/python -m uvicorn, 패키지는 appenv/bin/pip
- 개발은 로컬, 실행은 EC2. 로컬에는 AWS 자격증명이 없어 Bedrock 호출은 항상 실패한다 —
  정상이며, 자격증명 설정을 시도하지 말 것. 로컬 확인은 MOCK_AI=1 환경변수로 (고정 샘플 응답)

## 작업 규칙
- 설계 원본은 docs/ 폴더 (팀 작성). docs에 정의되지 않은 기능을 임의로 추가하지 말 것
- 프론트-백엔드 필드명은 docs의 데이터 계약(camelCase)을 그대로 사용, 임의 변경 금지
- task 한 번에 하나, 항상 실행 가능한 상태 유지
