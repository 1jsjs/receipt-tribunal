# Requirements Document — 영수증 소비 재판소

## Introduction

"영수증 소비 재판소"는 자취생이 한 달치 영수증을 제출하면 소비 패턴을 분석하여 재판소 콘셉트의 판결문과 MBTI식 소비 유형을 선고하는 모바일 우선 웹 서비스다. 수동 입력만으로도 전 흐름이 동작해야 하며, 영수증 이미지 비전 인식은 자동 채움 보조 수단이다.

## Glossary

- **System**: 영수증 소비 재판소 웹 서비스 전체
- **SPA**: static/index.html 단일 파일로 구성된 순수 HTML/CSS/JS 프런트엔드
- **API_Server**: FastAPI 기반 백엔드 (포트 8501)
- **Vision_Module**: Bedrock Claude Sonnet 5 비전 호출로 영수증 이미지를 구조화 JSON으로 변환하는 모듈
- **Judgment_Engine**: 결정적 조건문 룰로 죄명과 소비 유형을 판정하는 모듈
- **Verdict_Generator**: Bedrock으로 판결문 산문(조문 부제, 주문, 이유, 형량, 유형 설명)을 생성하는 모듈
- **Category**: 6종 고정 분류 — 식비 / 카페·간식 / 쇼핑 / 교통·이동 / 여가·문화 / 기타
- **Subtype**: 판정 전용 세부 분류 — 배달앱 / 편의점 / 마트·장보기 / 카페 / 일반
- **Verdict**: 월간 소비 판결문 (죄명, 조문 부제, 주문, 이유, 형량, 소비 유형 포함)
- **Nickname**: 로그인 없이 사용자를 식별하는 유일한 문자열
- **Mock_Mode**: MOCK_AI=1 환경변수 설정 시 Bedrock 호출을 고정 샘플 응답으로 대체하는 모드

## Requirements

### Requirement 1: 온보딩 및 사용자 식별

**User Story:** As a 자취생, I want 닉네임만으로 빠르게 시작할 수 있도록, so that 회원가입 없이 즉시 소비 판결 서비스를 이용할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display an onboarding screen with a nickname input field, an optional age input field, a "영수증 등록하고 시작하기" button, and an "이미 등록한 내역 보기" button.
2. WHEN the user submits a nickname, THE API_Server SHALL create a new user record if the nickname does not exist, or return the existing user record if it does exist.
3. WHEN the user taps "이미 등록한 내역 보기" with an existing nickname, THE SPA SHALL navigate to the home screen and load the existing receipt and verdict data for that nickname.
4. IF the nickname field is empty on form submission, THEN THE SPA SHALL display a validation error and prevent navigation.
5. THE API_Server SHALL store the nickname as a primary key and age as an optional integer in the users table.

### Requirement 2: 영수증 등록 (수동 입력)

**User Story:** As a 자취생, I want 영수증 정보를 직접 입력할 수 있도록, so that 이미지 인식이 실패하거나 종이 영수증이 없어도 거래를 기록할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display a receipt registration form with fields for store name, date, amount, a single-select category chip group (6 categories), and an optional memo field.
2. WHEN the user has not selected a category, THE SPA SHALL highlight the category chip group in red and disable the submission button.
3. WHEN the user submits a valid receipt form, THE API_Server SHALL store the receipt with nickname, store, date, amount, category, subtype (default "일반" for manual entry), and memo in the receipts table.
4. IF the amount field contains a non-numeric or negative value, THEN THE SPA SHALL display a validation error and prevent submission.
5. THE SPA SHALL display the memo field with placeholder text "이 소비에 대한 한마디" to indicate the memo is included in the verdict prompt.

### Requirement 3: 영수증 이미지 비전 인식

**User Story:** As a 자취생, I want 영수증 사진을 올리면 자동으로 내용이 채워지도록, so that 입력 시간을 절약할 수 있다.

#### Acceptance Criteria

1. WHEN the user uploads one or more receipt images, THE Vision_Module SHALL send each image (base64 encoded) to Bedrock Claude Sonnet 5 (model ID: global.anthropic.claude-sonnet-5) and return structured JSON containing store name, date, amount, category (one of 6 categories), and subtype (one of 5 subtypes).
2. WHEN the Vision_Module returns a result, THE SPA SHALL auto-fill the registration form fields and display a warning banner "인식된 내용을 확인하고 수정해 주세요" to prompt user review.
3. IF the Vision_Module call fails or returns unparseable data, THEN THE System SHALL retry once, and if the retry also fails, display the empty registration form for manual input with a message indicating recognition failure.
4. WHEN the Vision_Module recognizes card numbers or personal information in the image, THE Vision_Module SHALL mask the sensitive data before storing or returning the result.
5. THE Vision_Module SHALL upload the original receipt image to S3 bucket "hackathon-e1-t07-docs" at the "receipts/" path using the existing save_to_s3 pattern.
6. WHERE Mock_Mode is active (MOCK_AI=1), THE Vision_Module SHALL return a fixed sample response without calling Bedrock.

### Requirement 4: 홈 화면 집계

**User Story:** As a 자취생, I want 이번 달 소비 현황을 한눈에 파악하도록, so that 내 지출 규모와 판결 대기 상태를 즉시 알 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display the current month's total expenditure as a large numeric value, the number of submitted receipts, and a "선고까지 D-N" badge showing the remaining days until month-end.
2. WHEN the current date is the last day of the month, THE SPA SHALL display "D-DAY" instead of a countdown number.
3. THE SPA SHALL display a top-3 category bar chart sorted by expenditure amount.
4. THE SPA SHALL display the 3 most recent receipt entries below the summary.
5. THE SPA SHALL display a "{M}월 소비 판결문 받기" button that navigates to the verdict generation flow.
6. WHEN the user has fewer than 5 receipts for the current month, THE SPA SHALL still display the home screen with available data and the verdict button (the guard condition is evaluated at verdict time, not at display time).

### Requirement 5: 소비 내역 조회

**User Story:** As a 자취생, I want 월별·카테고리별로 내 지출 내역을 확인하도록, so that 어디에 얼마를 썼는지 상세히 파악할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display a month selector and category filter chips at the top of the history screen.
2. WHEN the user selects a month and optional category filter, THE API_Server SHALL return receipts grouped by date with weekday labels and daily subtotals.
3. THE SPA SHALL render each receipt entry showing store name, category, and amount within date-grouped sections.
4. WHEN no receipts exist for the selected month and filter, THE SPA SHALL display an empty state message.

### Requirement 6: 소비 분석

**User Story:** As a 자취생, I want 이번 달 지출의 통계적 분석을 확인하도록, so that 판결을 받기 전에 내 소비 패턴을 이해할 수 있다.

#### Acceptance Criteria

1. THE API_Server SHALL compute and return monthly summary statistics: total expenditure, payment count, daily average, and per-category totals with counts.
2. THE SPA SHALL display category breakdown as horizontal bars sorted by amount descending.
3. THE SPA SHALL display a "최다 지출 카테고리" card and a "가장 큰 단일 지출" card highlighting the top category and largest single transaction.
4. THE SPA SHALL display an "이 증거로 판결받기" button navigating to the verdict generation flow.

### Requirement 7: 판정 룰 (결정적 조건문)

**User Story:** As a 개발자, I want 소비 유형 판정이 결정적 조건문으로 동작하도록, so that 동일 데이터에 항상 동일 결과가 나와 재현 가능하다.

#### Acceptance Criteria

1. THE Judgment_Engine SHALL evaluate rules in fixed priority order (rule 0 through rule 8) and select the first matching rule.
2. WHEN the month's receipt count is fewer than 5, THE Judgment_Engine SHALL return "증거 불충분" with type "균형 잡힌 생존형" without evaluating subsequent rules (guard rule 0).
3. WHEN delivery-app subtype expenditure is 35% or more of total expenditure, THE Judgment_Engine SHALL return charge "냉장고 유기죄" with type "냉장고보다 배달앱형" (rule 1).
4. WHEN convenience-store subtype payment count is 10 or more, THE Judgment_Engine SHALL return charge "편의점 상습 출석죄" with type "편의점이 내 부엌형" (rule 2).
5. WHEN cafe-snack category expenditure is 25% or more of total expenditure, THE Judgment_Engine SHALL return charge "카페인 정기후원죄" with type "소확행 충전형" (rule 3).
6. WHEN shopping category expenditure is 30% or more of total expenditure, THE Judgment_Engine SHALL return charge "필요와 욕망 혼동죄" with type "취향에 진심형" (rule 4).
7. WHEN expenditure during days 1–10 is 45% or more of total monthly expenditure, THE Judgment_Engine SHALL return charge "월초 재벌 행세죄" with type "월초 플렉스형" (rule 5).
8. WHEN payment count with amount 10,000 KRW or less is 15 or more, THE Judgment_Engine SHALL return charge "잔액 조금씩 빼돌린 죄" with type "티끌 과소비형" (rule 6).
9. WHEN mart-grocery subtype expenditure is 30% or more of total and delivery-app subtype expenditure is 15% or less of total, THE Judgment_Engine SHALL return "무혐의" with type "야무진 자취생형" (rule 7).
10. WHEN no rule from 1 through 7 matches, THE Judgment_Engine SHALL return "증거 불충분" with type "균형 잡힌 생존형" (fallback rule 8).

### Requirement 8: 판결문 생성 (Bedrock)

**User Story:** As a 자취생, I want 재판소 콘셉트의 위트있는 판결문을 받도록, so that 소비 분석이 재미있고 공유하고 싶은 콘텐츠가 된다.

#### Acceptance Criteria

1. WHEN the user requests a verdict for a specific month, THE Verdict_Generator SHALL receive the judgment result (charge, type), monthly statistics, subtype statistics, and user memos as prompt context and generate: a witty article subtitle (조문 부제), a one-line ruling (주문), a 2–3 sentence reasoning (이유) that may quote user memos, a 2–3 line sentence suggestion (형량), and a 2–3 sentence type description (유형 설명).
2. THE Verdict_Generator SHALL use the charge and type determined by the Judgment_Engine without modification — the generator produces prose only, not the verdict category.
3. WHEN a verdict already exists for the same nickname and month, THE API_Server SHALL return the stored verdict without regenerating.
4. WHEN the request includes force=true, THE Verdict_Generator SHALL regenerate and overwrite the existing verdict for that month.
5. IF the Verdict_Generator call fails or returns unparseable data, THEN THE System SHALL retry once, and if the retry also fails, return an error response with a user-facing retry message (empty screens are prohibited).
6. WHERE Mock_Mode is active (MOCK_AI=1), THE Verdict_Generator SHALL return a fixed sample verdict without calling Bedrock.
7. THE API_Server SHALL generate a case number (사건번호) in the format "{MM}{random 2-digit 01–99}" for each new verdict.

### Requirement 9: 판결문 표시

**User Story:** As a 자취생, I want 판결문이 진짜 법원 문서처럼 보이도록, so that 콘텐츠의 몰입감과 공유 가치가 높아진다.

#### Acceptance Criteria

1. THE SPA SHALL render the verdict in a paper-document style layout containing: header ("대한민국 소비재판소 / {M}월 소비 판결문 / 사건번호 {YYYY} 소비합 {4자리}"), defendant line ("자취생 {닉네임}" with age in parentheses if provided), trial period, evidence count, charge name (large, burgundy color), article subtitle, evidence items (1–4 actual statistics), ruling, reasoning, sentence, and a stamp.
2. WHEN the verdict charge is "무혐의" or "증거 불충분", THE SPA SHALL display an "무죄 ACQUITTED" stamp; otherwise THE SPA SHALL display a "유죄 CONVICTED" stamp with date and "소비재판소 재판장 통장".
3. WHEN the user's age is not provided, THE SPA SHALL omit the parenthesized age from the defendant line.
4. THE SPA SHALL display placeholder "이미지 저장" and "공유하기" buttons (non-functional, reserved for P1).
5. THE SPA SHALL display a "내 소비 유형 확인하기 →" button navigating to the type result screen.

### Requirement 10: 최종 소비 유형 표시

**User Story:** As a 자취생, I want 내 소비 유형을 MBTI처럼 카드로 확인하도록, so that 결과를 재미있게 소비하고 친구와 비교할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display a type result card containing: the charge name as a tag, the type name in large text, a 2–3 sentence description, and 3 key statistics displayed horizontally.
2. THE SPA SHALL display a "다음 달의 형량" badge with the sentence text from the verdict.
3. THE SPA SHALL display a "소비 유형 도감" grid showing all 8 types, with the current month's type highlighted (collection state persistence is deferred to P1).
4. THE SPA SHALL display a "다음 달 재판 시작하기" button that returns the user to the home screen.

### Requirement 11: 드립 상호작용

**User Story:** As a 자취생, I want 판결 화면에서 위트있는 드립을 볼 수 있도록, so that 서비스가 더 재미있고 반복 방문 동기가 생긴다.

#### Acceptance Criteria

1. WHEN the user taps the sentence text or type badge on the verdict or type screen, THE SPA SHALL display a random humor toast message selected from the hardcoded pool for that type.
2. THE System SHALL maintain 3–4 hardcoded humor messages per each of the 8 types (24–32 total messages).
3. THE SPA SHALL display the toast without any API call or Bedrock invocation (immediate local response).

### Requirement 12: 하단 탭 네비게이션

**User Story:** As a 자취생, I want 화면 하단에 항상 탭바가 보이도록, so that 어떤 화면에서도 원하는 섹션으로 즉시 이동할 수 있다.

#### Acceptance Criteria

1. WHILE the user is past the onboarding screen, THE SPA SHALL display a persistent bottom tab bar with 4 tabs: 홈, 등록, 내역, 판결.
2. WHEN the user taps a tab, THE SPA SHALL navigate to the corresponding screen without a full page reload (JS-based screen switching).
3. WHILE the user is on the onboarding screen, THE SPA SHALL hide the bottom tab bar.

### Requirement 13: 모바일 우선 레이아웃

**User Story:** As a 자취생, I want 모바일에서 최적화된 화면을 보도록, so that 스마트폰으로 편하게 이용할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL render all screens within a max-width 480px centered container on desktop viewports.
2. THE SPA SHALL use a mobile-first vertical layout as the primary design reference.
3. THE SPA SHALL implement all screen transitions using JavaScript DOM manipulation within a single index.html file without any framework dependency.

### Requirement 14: API 엔드포인트

**User Story:** As a 개발자, I want 명확한 REST API 인터페이스가 정의되도록, so that 프런트엔드와 백엔드가 독립적으로 개발·테스트될 수 있다.

#### Acceptance Criteria

1. THE API_Server SHALL expose POST /api/users/{nickname} that creates or retrieves a user record.
2. THE API_Server SHALL expose POST /api/receipts accepting a JSON body with nickname and items array, storing each item as a receipt record.
3. THE API_Server SHALL expose GET /api/receipts/{nickname}?month=YYYY-MM returning receipt records filtered by nickname and month.
4. THE API_Server SHALL expose GET /api/summary/{nickname}?month=YYYY-MM returning monthly aggregate statistics for the home and analysis screens.
5. THE API_Server SHALL expose POST /api/verdict/{nickname}?month=YYYY-MM&force=false that triggers judgment + verdict generation and returns the verdict record.
6. THE API_Server SHALL expose GET /api/history/{nickname} returning all past verdict records for the given nickname.
7. THE API_Server SHALL serve the SPA (static/index.html) and static assets from the root path.

### Requirement 15: 데이터 저장소

**User Story:** As a 개발자, I want 데이터가 SQLite에 영속 저장되도록, so that 서버 재시작 후에도 모든 데이터가 유지된다.

#### Acceptance Criteria

1. THE API_Server SHALL use SQLite as the sole persistent storage with tables: users (nickname PK, age, created_at), receipts (id, nickname, store, date, amount, category, subtype, memo, needs_review, s3_key), and verdicts (id, nickname, month, case_number, charge, article, evidence_json, ruling, reasoning, sentence, spending_type, type_description, created_at).
2. THE API_Server SHALL initialize the database schema on first startup if tables do not exist.
3. THE API_Server SHALL store receipt image references as s3_key values pointing to S3 objects rather than storing image data locally.

### Requirement 16: Mock 모드

**User Story:** As a 개발자, I want MOCK_AI=1 환경에서 Bedrock 없이 전 기능을 검증하도록, so that 로컬 개발 환경에서 AWS 자격증명 없이도 화면과 로직을 테스트할 수 있다.

#### Acceptance Criteria

1. WHERE Mock_Mode is active (MOCK_AI=1 environment variable), THE Vision_Module SHALL return a fixed sample receipt JSON response without invoking Bedrock.
2. WHERE Mock_Mode is active (MOCK_AI=1 environment variable), THE Verdict_Generator SHALL return a fixed sample verdict response without invoking Bedrock.
3. WHERE Mock_Mode is active (MOCK_AI=1 environment variable), THE System SHALL skip S3 upload operations and use a placeholder s3_key value.
4. WHILE Mock_Mode is inactive, THE System SHALL perform actual Bedrock and S3 operations using boto3 with the default region from /etc/environment.

### Requirement 17: 더미 시드 데이터

**User Story:** As a 개발자, I want 8종 죄명을 모두 재현하는 더미 데이터가 준비되도록, so that 데모에서 모든 판정 경로를 즉시 시연할 수 있다.

#### Acceptance Criteria

1. THE System SHALL provide a seed script (data/seed.py) that populates the database with 8 nicknames, each designed to trigger a distinct judgment rule.
2. THE seed script SHALL generate approximately 60 total receipt records for August (2025-08) distributed across the 8 nicknames such that each nickname's data exceeds the threshold for its target rule.
3. WHEN the seed script is executed, THE System SHALL clear existing seed data and re-insert fresh records to ensure repeatability.

### Requirement 18: 배포 및 운영

**User Story:** As a 운영자, I want 서비스가 SSH 종료 후에도 안정적으로 동작하도록, so that 데모 중 서비스 중단이 발생하지 않는다.

#### Acceptance Criteria

1. THE System SHALL run via nohup with stdin redirected from /dev/null so that the process persists after SSH session termination.
2. THE System SHALL bind to port 8501 and be accessible externally at http://18.135.105.80:8501.
3. THE System SHALL use appenv/bin/python -m uvicorn as the execution command.
4. WHEN the existing receipt_app.py (Streamlit) process occupies port 8501, THE deployment process SHALL terminate it before starting the FastAPI application.

### Requirement 19: 품질 및 오류 처리

**User Story:** As a 자취생, I want 오류가 발생해도 빈 화면 대신 안내를 받도록, so that 서비스가 항상 사용 가능하다는 신뢰를 가질 수 있다.

#### Acceptance Criteria

1. IF Bedrock returns an unparseable response, THEN THE System SHALL retry the call once, and if the retry also fails, display a user-facing error message with retry guidance.
2. THE System SHALL mask card numbers and personal information during the vision recognition stage before storing or displaying results.
3. THE API_Server SHALL include Korean-language comments on all major functions and API endpoint handlers for non-technical team member readability.
4. IF an API request fails with a server error, THEN THE SPA SHALL display a toast notification with error context rather than showing a blank screen.

---

## Priority Classification

### P0 (Must Have — Demo Complete)

- Requirements 1–19 전체 (온보딩 → 등록 → 홈 → 내역 → 분석 → 판결문 → 유형)
- 비전 자동 채움 + 수동 폴백
- Subtype 기반 결정적 판정 (8종 전부 재현)
- Bedrock 판결문 산문 생성
- Mock 모드 (MOCK_AI=1)
- 드립 상호작용
- 더미 시드 스크립트 (8월, 닉네임 8개)

### P1 (Deferred)

- 감형 처방전 화면 (08)
- 소비 유형 도감 수집 상태 영속 저장
- 판결문 이미지 저장 및 공유 기능
- 지난 판결문 목록 화면
- PDF/엑셀 지출내역 일괄 업로드

### Excluded

- 로그인 / OAuth / 회원가입
- 계좌 연동
- 모델 학습 / 개인화
- 예산 추천
- 랭킹 / 리더보드
- 회원 관리 어드민

---

## Correctness Properties

### Round-Trip Properties

1. **Receipt Storage Round-Trip**: FOR ALL valid receipt input data, storing via POST /api/receipts then retrieving via GET /api/receipts/{nickname}?month=YYYY-MM SHALL return records equivalent to the original input (fields preserved).
2. **Verdict Storage Round-Trip**: FOR ALL generated verdicts, storing then retrieving via GET /api/history/{nickname} SHALL return a verdict record with all fields matching the originally stored values.

### Invariants

1. **Judgment Determinism**: FOR ALL identical monthly receipt datasets, THE Judgment_Engine SHALL produce the same charge and type on every invocation (no randomness in rule evaluation).
2. **Rule Priority Order**: FOR ALL inputs matching multiple rules, THE Judgment_Engine SHALL select the rule with the lowest index (first-match semantics).
3. **Category Constraint**: FOR ALL receipt records, the category field SHALL contain exactly one of the 6 defined categories.
4. **Subtype Constraint**: FOR ALL receipt records, the subtype field SHALL contain exactly one of the 5 defined subtypes.
5. **Guard Precedence**: FOR ALL months with fewer than 5 receipts, THE Judgment_Engine SHALL return "증거 불충분" regardless of expenditure ratios.

### Idempotence

1. **Verdict Idempotence**: FOR ALL verdict requests without force=true, requesting the same nickname+month multiple times SHALL return the identical stored verdict (no regeneration).
2. **User Creation Idempotence**: FOR ALL existing nicknames, calling POST /api/users/{nickname} multiple times SHALL return the same user record without creating duplicates.

### Metamorphic Properties

1. **Adding Receipts Increases Total**: FOR ALL months, adding a receipt with amount > 0 SHALL result in a total expenditure greater than or equal to the previous total.
2. **Category Filter Subset**: FOR ALL months and categories, the set of receipts returned by a category filter SHALL be a subset of the unfiltered receipt list for that month.

### Error Condition Properties

1. **Empty Nickname Rejection**: FOR ALL requests with empty nickname string, THE API_Server SHALL return an error response.
2. **Invalid Amount Rejection**: FOR ALL receipt submissions with non-numeric or negative amount, THE System SHALL reject the input with a validation error.
3. **Bedrock Failure Graceful Degradation**: FOR ALL Bedrock call failures (after retry), THE System SHALL return a user-facing error message rather than an empty response or unhandled exception.
