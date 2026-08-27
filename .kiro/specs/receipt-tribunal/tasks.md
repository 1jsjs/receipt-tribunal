# Implementation Plan: 영수증 소비 재판소

## Overview

FastAPI 백엔드 + 순수 HTML/CSS/JS SPA + SQLite 저장소 구성의 소비 재판소 서비스를 구현한다. 백엔드 기반부터 시작하여 API 엔드포인트를 순차 구현하고, SPA 화면을 온보딩→홈→등록→내역→분석→판결문→유형 순서로 완성한다.

## Tasks

- [ ] 1. 데이터베이스 초기화
  - [ ] 1.1 db.py — SQLite 초기화 (users, receipts, verdicts 테이블, WAL 모드, FK 활성화, 인덱스)
    - `get_connection()` — Row factory, WAL, FK pragma 설정
    - `init_db()` — CREATE TABLE IF NOT EXISTS (기존 데이터 보존)
    - 스키마: users(nickname PK, age, created_at), receipts(id PK, nickname FK, store, date, amount, category CHECK 6종, subtype CHECK 5종, memo, needs_review, s3_key, created_at), verdicts(id PK, nickname FK, month, case_number, charge, spending_type, article, evidence_json, ruling, reasoning, sentence, type_description, created_at, UNIQUE(nickname,month))
    - 완료 조건: `python -c "from db import init_db; init_db()"` 실행 시 data.db 생성 + 3개 테이블 확인
    - _Requirements: 15.1, 15.2, 15.4, 15.5_

- [ ] 2. Bedrock 공통 래퍼
  - [ ] 2.1 core/bedrock.py — invoke_bedrock 래퍼 (Mock 모드 분기, 1회 재시도, JSON 추출)
    - `invoke_bedrock(operation, messages, mock_key, max_tokens)` → JSON 반환
    - Mock 모드(MOCK_AI=1): MOCK_RESPONSES["parse"] / ["verdict"] 고정 응답 즉시 반환
    - 실제 호출: boto3 bedrock-runtime, model_id="global.anthropic.claude-sonnet-5"
    - `_extract_json(raw_text)` — 마크다운 코드블록 제거 후 JSON 배열/객체 추출
    - `BedrockError` 커스텀 예외 (재시도 포함 최종 실패 시)
    - 완료 조건: `MOCK_AI=1 python -c "from core.bedrock import invoke_bedrock; print(invoke_bedrock('test', [], 'parse'))"` 성공
    - 의존: 없음
    - _Requirements: 16.1, 16.2, 19.1_

- [ ] 3. FastAPI 기본 뼈대
  - [ ] 3.1 main.py — FastAPI app 생성, 정적 파일 마운트, startup 이벤트에서 init_db 호출
    - StaticFiles mount는 모든 /api/* 라우트 등록 후 마지막 줄에 배치
    - `app.mount("/", StaticFiles(directory="static", html=True))` — 루트 접근 시 index.html 반환
    - static/ 디렉토리에 빈 index.html placeholder 생성
    - 완료 조건: `MOCK_AI=1 appenv/bin/python -m uvicorn main:app --port 8501` 실행 후 `curl localhost:8501` → HTML 응답
    - 의존: 1.1
    - _Requirements: 14.7, 18.3_

- [ ] 4. 사용자 API
  - [ ] 4.1 POST /api/users/{nickname} — 사용자 생성/조회 엔드포인트
    - nickname 빈 문자열 또는 12자 초과 시 422 반환
    - body에서 age(optional, 1~120) 수신
    - 기존 닉네임이면 기존 레코드 반환 (멱등)
    - 완료 조건: `curl -X POST localhost:8501/api/users/테스트유저 -d '{"age":25}'` → 200 + nickname/age/created_at JSON
    - 의존: 3.1
    - _Requirements: 1.2, 1.5, 14.1_

- [ ] 5. 영수증 저장 API
  - [ ] 5.1 POST /api/receipts — 영수증 일괄 저장 엔드포인트
    - body: {nickname, items: [{store, date, amount, category, subtype?, memo?}]}
    - 필드 검증: store 1~50자, date YYYY-MM-DD + 미래날짜 불가, amount 1~999999999 정수, category 6종 CHECK, subtype 5종 기본값 "일반"
    - 422: 필수 필드 누락, 유효하지 않은 값
    - 완료 조건: 유효 데이터 POST → 200 + `{"stored_count": N}` / 잘못된 데이터 → 422
    - 의존: 4.1
    - _Requirements: 2.3, 14.2, 14.8_

- [ ] 6. 영수증 조회 API
  - [ ] 6.1 GET /api/receipts/{nickname}?month=YYYY-MM — 월별 영수증 조회
    - 날짜 내림차순 정렬
    - 닉네임 미존재 시 빈 배열 반환
    - month 형식 오류 시 422
    - 완료 조건: 시드 데이터 삽입 후 GET → 날짜 내림차순 JSON 배열
    - 의존: 5.1
    - _Requirements: 5.2, 14.3, 14.8, 14.9_

- [ ] 7. 월간 집계 API
  - [ ] 7.1 core/analyze.py — 월간 집계 통계 계산 (total_amount, count, daily_average, categories, top_category, largest_transaction)
    - daily_average = total_amount ÷ 해당 월 달력 일수
    - top_category: 금액 동률 시 count 비교, count도 동률이면 고정 카테고리 순서
    - 닉네임 미존재 시 0/빈 객체 반환
    - 완료 조건: 테스트 데이터로 compute_summary 호출 시 올바른 집계 확인
    - 의존: 없음
    - _Requirements: 6.1, 6.7_

  - [ ] 7.2 GET /api/summary/{nickname}?month=YYYY-MM — 월간 집계 엔드포인트
    - core/analyze.py의 compute_summary 호출
    - 완료 조건: curl GET → JSON with total_amount, count, daily_average, categories, top_category, largest_transaction
    - 의존: 7.1, 6.1
    - _Requirements: 14.4_

- [ ] 8. 판정 룰 엔진
  - [ ] 8.1 core/judge.py — 결정적 판정 룰 (evaluate + _compute_stats + build_evidence)
    - 가드 룰: 5건 미만 → "증거 불충분" / "균형 잡힌 생존형"
    - 룰 1~7 우선순위 평가, 첫 매칭 선택
    - 폴백 룰 8: 아무것도 매칭 안 되면 "증거 불충분"
    - build_evidence: 죄명별 증거 4건 산출 (label + value)
    - 완료 조건: 8종 테스트 케이스로 evaluate 호출 시 각각 올바른 charge/type 반환
    - 의존: 없음
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_

  - [ ]* 8.2 tests/test_judge.py — 판정 룰 단위 테스트
    - 8종 룰 각각 트리거 + 우선순위 검증 + 가드 룰 검증
    - _Requirements: 7.1–7.11_

- [ ] 9. 판결문 생성 모듈
  - [ ] 9.1 core/verdict.py — Bedrock 판결문 산문 생성 (프롬프트 조립 + invoke_bedrock 호출 + 필드 검증)
    - 프롬프트에 charge, type, 월간 통계, 서브타입 통계, 메모 컨텍스트 포함
    - 응답 필드: article, ruling, reasoning, sentence, type_description
    - Mock 모드에서 고정 응답 반환
    - 완료 조건: `MOCK_AI=1` 환경에서 generate_verdict 호출 → 5개 필드 포함 dict 반환
    - 의존: 2.1
    - _Requirements: 8.1, 8.2, 8.5, 8.6_

- [ ] 10. 판결 엔드포인트
  - [ ] 10.1 POST /api/verdict/{nickname}?month=YYYY-MM&force=false — 판정→판결문→DB 저장 통합 엔드포인트
    - judge.evaluate → verdict.generate_verdict → verdicts 테이블 INSERT
    - case_number 생성: "{MM}{01~99 랜덤 2자리}"
    - force=false이고 기존 verdict 존재 시 저장된 것 반환
    - force=true → 기존 삭제 후 재생성
    - 실패 시 사용자 안내 메시지 (빈 화면 금지)
    - 완료 조건: `MOCK_AI=1` 환경에서 curl POST → verdict JSON 반환 (case_number, charge, article, ruling, reasoning, sentence, spending_type, type_description, created_at)
    - 의존: 8.1, 9.1, 6.1
    - _Requirements: 8.3, 8.4, 8.7, 14.5_

- [ ] 11. 판결문 조회 API
  - [ ] 11.1 GET /api/history/{nickname} — 과거 판결문 목록 (최신순)
    - 완료 조건: verdict 생성 후 GET → 배열에 해당 verdict 포함
    - 의존: 10.1
    - _Requirements: 14.6_

- [ ] 12. 파일 파싱 모듈
  - [ ] 12.1 core/parse.py — 파일 파싱 (xlsx/csv/pdf 추출 + Bedrock 정규화 + 청킹 + 검증 + 비전 폴백)
    - _extract_excel: pandas + openpyxl
    - _extract_csv: 인코딩 자동 감지 (utf-8 → euc-kr → cp949)
    - _extract_pdf: pdfplumber 텍스트 추출
    - _vision_fallback: pypdfium2 렌더 → core/vision.py 호출
    - chunk_and_normalize: 50행 초과 시 분할 처리
    - _validate_transactions: 필드 검증 (category/subtype 교정, 불량 행 DROP)
    - _upload_to_s3: S3 evidence/ 경로 업로드 (Mock 시 skip)
    - 개인정보 마스킹: 카드번호·전화번호
    - 완료 조건: `MOCK_AI=1` 환경에서 parse_file 호출 → 8건 고정 응답 반환
    - 의존: 2.1
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.10, 3.11, 19.2_

  - [ ] 12.2 core/vision.py — 스캔형 PDF 비전 폴백 (base64 인코딩 + Bedrock vision invoke)
    - 기존 receipt_app.py의 analyze_receipt_image 패턴 재사용
    - 완료 조건: Mock 모드에서 analyze_image_vision 호출 → 리스트 반환
    - 의존: 2.1
    - _Requirements: 3.4_

- [ ] 13. 파일 업로드 엔드포인트
  - [ ] 13.1 POST /api/upload — multipart/form-data 파일 업로드 → parse_file → 정규화 결과 반환
    - 파일 10MB 초과 시 413
    - 지원하지 않는 확장자 시 422
    - 파싱 실패 시 1회 재시도 → 최종 실패 시 500 + fallback:true
    - 응답: {transactions, s3_key, total_count, filtered_count}
    - 완료 조건: `MOCK_AI=1` 환경에서 테스트 파일 업로드 → 200 + transactions 배열
    - 의존: 12.1
    - _Requirements: 3.8, 3.9, 14.8_

- [ ] 14. Checkpoint — 백엔드 완성 확인
  - Ensure all API endpoints respond correctly under MOCK_AI=1, ask the user if questions arise.

- [ ] 15. 더미 시드 데이터
  - [ ] 15.1 data/seed.py — 닉네임 8개, 2026-08, 약 60건 영수증, 각 닉네임이 정확히 하나의 판정 룰 트리거
    - 닉네임별 데이터가 상위 우선순위 룰 임계값 미만 + 해당 룰 임계값 이상 설계
    - 각 닉네임 최소 5건 이상 (가드 룰 통과)
    - 실행 시 기존 시드 데이터 DELETE 후 재삽입 (멱등)
    - 완료 조건: `python data/seed.py && MOCK_AI=1 python -c "from core.judge import evaluate; from db import get_connection; ..."` 로 8종 charge 모두 재현
    - 의존: 1.1, 8.1
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [ ] 16. 합성 지출내역 파일
  - [ ] 16.1 samples/ 디렉토리에 합성 지출내역 파일 2종 생성 (엑셀 1개 + PDF 1개)
    - 각 파일 30~40행 허구 거래, 2026-08, 한국어 가맹점명, 6카테고리·5서브타입 혼합
    - 각 파일에 비지출 행 3건 이상 포함 (입금, 취소, 카드대금)
    - 엑셀: 배달 비중 35%+ (룰1 트리거) / PDF: 소액 15건+ (룰6 트리거)
    - 완료 조건: samples/ 에 .xlsx + .pdf 파일 존재, 각 파일 내용이 설계 조건 충족
    - 의존: 없음
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

- [ ] 17. SPA 골격
  - [ ] 17.1 static/index.html — SPA 기본 구조 (CSS 변수, 리셋, 컨테이너, 탭바, 화면전환 로직, API 헬퍼, 토스트, 로딩 오버레이)
    - ⚠️ 디자인 시안 첨부 후 진행
    - CSS 변수: --bg-dark, --paper, --burgundy, --gold, --text-light, --text-dark
    - max-width: 480px 중앙 컨테이너
    - 하단 탭바: 홈 | 등록 | 내역 | 판결 (온보딩에서는 숨김)
    - 화면전환: .screen div의 display 토글 + fadeIn 애니메이션
    - API 헬퍼: fetch 래퍼 (에러 처리, 타임아웃 15초, 로딩 자동 표시)
    - 토스트: showToast(msg, duration) — 2~4초 후 fade-out
    - 완료 조건: 브라우저에서 탭 클릭 시 빈 화면 전환 동작
    - 의존: 3.1
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 13.1, 13.2, 13.3, 13.4, 19.4, 19.5_

- [ ] 18. 01 온보딩 화면
  - [ ] 18.1 온보딩 화면 구현 (닉네임·나이 입력, 시작/기존내역 버튼, 클라이언트 유효성 검증)
    - ⚠️ 디자인 시안 첨부 후 진행
    - 닉네임 빈값/12자 초과 인라인 에러
    - 나이 1~120 범위 검증
    - "영수증 등록하고 시작하기" → POST /api/users/{nickname} → 홈 이동
    - "이미 등록한 내역 보기" → 닉네임 미존재 시 인라인 안내
    - 완료 조건: 닉네임 입력 후 시작 → 홈 화면 전환 + 유효성 에러 표시 동작
    - 의존: 17.1, 4.1
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7_

- [ ] 19. 03 등록 화면
  - [ ] 19.1 등록 화면 구현 (수동입력 폼 + 파일업로드 + 파싱결과 리뷰)
    - ⚠️ 디자인 시안 첨부 후 진행
    - 수동입력: 가맹점명, 날짜, 금액, 카테고리 칩, 메모 → POST /api/receipts
    - 파일업로드: input[type=file] → POST /api/upload → 파싱 결과 리뷰 리스트
    - 리뷰: needs_review 행 하이라이트, 필드 수정 가능, 수동 행 추가 버튼
    - 전체 저장: 확인된 행들 → POST /api/receipts → 홈 이동
    - 완료 조건: 수동 1건 등록 성공 + Mock 파일 업로드 → 파싱 결과 표시 → 저장 성공
    - 의존: 17.1, 5.1, 13.1
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.8, 3.12_

- [ ] 20. 02 홈 화면
  - [ ] 20.1 홈 화면 구현 (총지출, 영수증 N건, D-day, 상위3 카테고리 바차트, 최근3건, 판결문 버튼)
    - ⚠️ 디자인 시안 첨부 후 진행
    - GET /api/summary → 총지출(콤마+원), 건수, D-day 계산
    - 카테고리 top-3 가로 바차트
    - GET /api/receipts → 최근 3건 표시
    - 0건: 빈 상태 메시지 / <5건: 데이터 있는 만큼 표시 + 판결 버튼 활성
    - 완료 조건: 시드 데이터 기준 홈 화면 렌더링 정상 (금액·건수·차트)
    - 의존: 17.1, 7.2, 6.1
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [ ] 21. 04 내역 화면
  - [ ] 21.1 내역 화면 구현 (월 선택, 카테고리 필터, 날짜별 그룹핑, 일별 소계)
    - ⚠️ 디자인 시안 첨부 후 진행
    - 월 선택 드롭다운 (기본: 현재 월)
    - 카테고리 필터 칩 (수평 스크롤, "전체" 기본 선택)
    - 날짜별 역순 그룹: "{M}월 {D}일 ({요일})" 헤더 + 일별 소계
    - 각 항목: 가맹점명 + 카테고리 색상 dot + 금액
    - 상단: "총 N건 제출" + 총 금액
    - 빈 상태 메시지
    - 완료 조건: 시드 데이터로 내역 화면 정상 렌더링 (그룹핑·필터 동작)
    - 의존: 17.1, 6.1
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 22. 05 분석 화면
  - [ ] 22.1 분석 화면 구현 (총지출·횟수·일평균, 카테고리 막대, 하이라이트 카드, 판결 버튼)
    - ⚠️ 디자인 시안 첨부 후 진행
    - GET /api/summary → 총지출·횟수·일평균 표시
    - 카테고리별 행: 색상 dot + 이름 + 횟수 + 금액 + 비례 막대 (최대=100%)
    - "최다 지출 카테고리" 카드 + "가장 큰 단일 지출" 카드
    - "이 증거로 판결받기" → 판결문 생성 플로우
    - 빈 상태: 카테고리·하이라이트 숨김
    - 완료 조건: 시드 데이터로 분석 화면 렌더링 (막대 비율·카드 정상)
    - 의존: 17.1, 7.2
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 23. 06 판결문 화면
  - [ ] 23.1 판결문 화면 구현 (종이 스타일 레이아웃: 헤더, 피고인, 죄명, 증거, 주문, 형량, 도장)
    - ⚠️ 디자인 시안 첨부 후 진행
    - POST /api/verdict → 판결문 데이터 수신
    - 종이 레이아웃: 헤더(대한민국 소비재판소 / 사건번호) → 피고인(닉네임, 나이, 심리기간, 증거건수) → 죄명(burgundy 대형) → 조문 부제 → 증거 01~04 → 주문+이유 → 형량(다크박스) → 도장
    - 도장: 무혐의/증거불충분 → "무죄 ACQUITTED" (green), 그 외 → "유죄 CONVICTED" (burgundy)
    - 나이 미제공 시 "(나이)" 생략
    - 생성 중: 로딩 상태 ("판결문을 작성 중입니다…")
    - "이미지 저장" / "공유하기" 버튼 — 비활성 (P1)
    - "내 소비 유형 확인하기 →" → 유형 화면 이동
    - 완료 조건: Mock verdict 데이터로 판결문 화면 완전 렌더링 (도장 포함)
    - 의존: 17.1, 10.1
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ] 24. 07 소비 유형 화면
  - [ ] 24.1 소비 유형 화면 구현 (유형 카드, 통계 3종 박스, 형량 배지, 유형 도감 4×2 그리드)
    - ⚠️ 디자인 시안 첨부 후 진행
    - 헤더: "{YYYY}년 {M}월 · 최종 선고" + "당신의 소비 유형"
    - 유형 카드: 죄명 태그 + 유형명 대형 + 유형 설명 2~3문장 + 통계 3종 가로 박스
    - "다음 달의 형량" 배지 + sentence 텍스트
    - 유형 도감: 4×2 그리드, 8종 유형 + 죄명 부제, 현재 유형은 red dot
    - "{N}/8 수집" 표시 (현재 세션만 1/8)
    - "다음 달 재판 시작하기" → 홈 이동
    - 완료 조건: Mock verdict 데이터로 유형 화면 완전 렌더링 (그리드 8칸 + 현재 유형 표시)
    - 의존: 17.1, 23.1
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 25. 드립 상호작용
  - [ ] 25.1 DRIP_MESSAGES 객체 (8종 × 3~4개) + 토스트 표시 로직
    - 형량 영역/유형 배지 탭 시 해당 유형의 랜덤 드립 토스트
    - 같은 요소 반복 탭 시 메시지 순환 (중복 없이 전부 보여준 후 리셋)
    - 토스트 2~3초 후 fade-out, Bedrock 호출 없음 (즉시 로컬)
    - 완료 조건: 판결문/유형 화면에서 형량 영역 탭 → 드립 토스트 표시 + 반복 탭 시 다른 메시지
    - 의존: 23.1, 24.1
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 26. Checkpoint — SPA 전체 흐름 확인
  - Ensure MOCK_AI=1 환경에서 온보딩→등록(수동)→홈→내역→분석→판결문→유형 전체 흐름이 끊김 없이 동작하는지 확인. Ask the user if questions arise.

- [ ] 27. E2E 통합 검증
  - [ ] 27.1 MOCK_AI=1 환경에서 자동화 검증 스크립트 작성 (tests/test_e2e.py)
    - 시드 데이터 로드 후 8개 닉네임 전체에 대해 verdict 생성 → 8종 charge 모두 확인
    - 수동 입력 API 흐름: users → receipts → summary → verdict 순차 호출 확인
    - 파일 업로드 Mock 흐름: upload → receipts 저장 → verdict 확인
    - 완료 조건: `MOCK_AI=1 python -m pytest tests/test_e2e.py -v` 전체 통과
    - 의존: 15.1, 10.1, 13.1
    - _Requirements: 16.5, 17.1_

- [ ] 28. 서버 배포 및 검증
  - [ ] 28.1 서버 배포 (nohup + uvicorn + 포트 8501 + 프로세스 관리)
    - 기존 receipt_app.py (Streamlit) 프로세스 SIGTERM → 포트 해제 대기 (최대 10초)
    - `nohup appenv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8501 </dev/null >app.log 2>&1 &`
    - 30초 내 HTTP 200 확인, 실패 시 로그 출력
    - `curl http://18.135.105.80:8501` → 200 확인
    - 완료 조건: 외부에서 http://18.135.105.80:8501 접속 가능 + nohup 백그라운드 유지 + SSH 종료 후에도 프로세스 생존
    - 의존: 26 (모든 화면 완성 후)
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

- [ ] 29. Final Checkpoint — 완료 조건 전체 확인
  - 수동 입력만으로 01→07 흐름이 끊김 없이 동작
  - 샘플 파일 2개를 업로드하면 정규화→판결문까지 정상 동작
  - 외부에서 http://18.135.105.80:8501 접속 가능
  - nohup 백그라운드, SSH 종료에도 유지
  - .kiro/ 폴더 포함 커밋
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- UI 화면 task (17~25)에는 "⚠️ 디자인 시안 첨부 후 진행" 표시 — 시안 없이도 design.md의 HTML 스켈레톤 기반 구현 가능
- 로컬 실행은 반드시 `MOCK_AI=1` 환경에서 수행
- 서버 배포 후 실제 Bedrock/S3 동작 검증

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "7.1", "8.1", "16.1"] },
    { "id": 1, "tasks": ["3.1", "8.2", "9.1", "12.2"] },
    { "id": 2, "tasks": ["4.1", "12.1", "17.1"] },
    { "id": 3, "tasks": ["5.1", "13.1", "18.1"] },
    { "id": 4, "tasks": ["6.1", "7.2", "15.1"] },
    { "id": 5, "tasks": ["10.1", "19.1", "20.1", "21.1", "22.1"] },
    { "id": 6, "tasks": ["11.1", "23.1"] },
    { "id": 7, "tasks": ["24.1", "25.1"] },
    { "id": 8, "tasks": ["27.1"] },
    { "id": 9, "tasks": ["28.1"] }
  ]
}
```
