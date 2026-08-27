---
inclusion: always
---

# 기술 스택 (확정)

이 문서는 팀이 이미 확정한 기술 스택을 고정하기 위한 문서다. 이후 어떤 세션에서도 대안 기술(예: React, PostgreSQL, DynamoDB 등)을 제안하지 않는다.

## 백엔드
- FastAPI
- 실행: `appenv/bin/python -m uvicorn` 으로 실행
- 포트: 8501
- 배포 시 기존 `receipt_app.py`(streamlit) 프로세스를 종료하고, 이 포트를 새 FastAPI 앱이 사용한다.

## 프런트엔드
- 순수 HTML/CSS/JS 단일 `index.html` SPA
- React 등 프레임워크 금지. 화면 전환은 JS로 처리한다.
- 모바일 세로 시안 기준. 데스크톱에서는 `max-width: 480px` 중앙 고정 컨테이너로 표시한다.

## 저장소
- SQLite 파일 저장
- 업로드 원본 이미지는 기존에 검증된 S3 업로드 모듈(`receipt_app.py`의 `save_to_s3` 패턴)을 재사용해서, S3 버킷 `hackathon-e1-t07-docs`의 `receipts/` 경로에 저장한다. 새 버킷을 생성하지 않는다.

## Bedrock
- 모델 ID는 항상 `global.anthropic.claude-sonnet-5` (`global.` 접두사 필수. 접두사가 없으면 "on-demand throughput isn't supported" 에러가 발생한다.)
- 리전은 코드에 하드코딩하지 않는다. `/etc/environment`의 `AWS_DEFAULT_REGION` 값을 boto3가 자동으로 사용하도록 생략한다.
- 영수증 비전 인식은 `receipt_app.py`의 `analyze_receipt_image` 패턴(base64 인코딩 + `invoke_model` + image/text content block)을 재사용/확장한다.

## AWS 계정 제약
- 이 AWS 계정은 Bedrock과 S3만 사용 가능하다. DynamoDB/Lambda/Textract/Rekognition은 전부 AccessDenied이므로 사용을 시도하지 않는다.

## Mock 모드
- `MOCK_AI=1` 환경변수 설정 시, Bedrock 비전·판결문 호출을 고정 샘플 응답으로 대체하는 mock 모드로 동작한다 (로컬 개발/화면 확인용).

## 판정 로직
- 판정 로직(죄명·소비유형)은 LLM이 아닌 결정적 조건문 룰로 수행한다 (재현 가능해야 함).
- 판결문 산문(조문 부제/주문/이유/형량/유형설명)만 Bedrock으로 생성한다.

## 인증
- 로그인/OAuth/회원가입 없음. 닉네임 문자열만으로 사용자를 식별한다.

## 배포
- nohup으로 백그라운드 실행하고, 표준입력을 `/dev/null`로 분리해서 SSH 종료 후에도 프로세스가 유지되도록 한다.
- 배포 완료 조건: 외부에서 `http://18.135.105.80:8501` 접속 가능 + 로그 확인 + curl 응답 코드 확인.

## 로컬 개발 규칙 (중요)
- 개발은 로컬, 실행 환경은 EC2다. 로컬에는 AWS 자격증명이 없어서 Bedrock·S3 호출은 로컬에서 항상 실패한다 — 이는 정상이며, Access Key 발급·자격증명 설정을 절대 시도하지 말 것.
- 로컬 실행 확인은 반드시 `MOCK_AI=1` 환경에서 한다. 실제 AI 동작 검증은 서버 배포 후에만 수행한다.
- 패키지 설치는 서버에서 `appenv/bin/pip`로 한다 (시스템 pip 금지).

## 품질 규칙
- Bedrock 응답은 형식 검증 후 사용, 실패 시 1회 재시도, 최종 실패 시 사용자에게 재시도 안내 (빈 화면 금지).
- 카드번호 등 개인정보는 인식 단계에서 마스킹한다.
- 주요 함수·API 엔드포인트에 한국어 주석을 남긴다 (비전공 팀원이 읽을 수 있게).
