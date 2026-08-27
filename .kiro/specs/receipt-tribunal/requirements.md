# Requirements Document

## Introduction

"영수증 소비 재판소"는 자취생이 한 달치 지출내역 파일(PDF/xlsx/CSV)을 제출하면 소비 패턴을 분석하여 재판소 콘셉트의 판결문과 MBTI식 소비 유형을 선고하는 모바일 우선 웹 서비스다. 수동 입력만으로도 전 흐름이 동작해야 하며, 파일 업로드 파싱은 대량 입력 보조 수단이다.

## Glossary

- **System**: 영수증 소비 재판소 웹 서비스 전체
- **SPA**: static/index.html 단일 파일로 구성된 순수 HTML/CSS/JS 프런트엔드
- **API_Server**: FastAPI 기반 백엔드 (포트 8501)
- **Parse_Module**: 지출내역 파일(PDF/xlsx/CSV)을 파싱하여 표준 JSON 트랜잭션 리스트로 변환하는 모듈. 엑셀/CSV는 pandas+openpyxl로 원시 셀 추출, PDF는 pdfplumber 텍스트 추출 → Bedrock 텍스트 호출로 정규화·분류. 스캔형 PDF만 pypdfium2 렌더 → 비전 폴백.
- **Vision_Module**: Bedrock Claude Sonnet 5 비전 호출로 이미지를 구조화 JSON으로 변환하는 모듈 (스캔형 PDF 폴백 전용, P1에서 영수증 사진 직접 업로드 지원 예정)
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

1. THE SPA SHALL display an onboarding screen with a nickname input field (maximum 12 characters), an optional age input field (integer, 1–120), a "영수증 등록하고 시작하기" button, and an "이미 등록한 내역 보기" button.
2. WHEN the user submits a nickname via "영수증 등록하고 시작하기", THE API_Server SHALL create a new user record if the nickname does not exist, or return the existing user record if it does exist, and THE SPA SHALL navigate to the home screen.
3. WHEN the user taps "이미 등록한 내역 보기" with an existing nickname, THE SPA SHALL navigate to the home screen and load the existing receipt and verdict data for that nickname.
4. IF the nickname field is empty or exceeds 12 characters on form submission, THEN THE SPA SHALL display an inline validation message below the nickname field indicating the constraint and prevent navigation.
5. THE API_Server SHALL store the nickname as a primary key and age as an optional integer in the users table.
6. IF the user taps "이미 등록한 내역 보기" with a nickname that does not exist in the database, THEN THE SPA SHALL display an inline message indicating no records were found for that nickname and remain on the onboarding screen.
7. IF the age field contains a value outside the range 1–120 or a non-integer value, THEN THE SPA SHALL display an inline validation message below the age field and prevent submission.

### Requirement 2: 영수증 등록 (수동 입력)

**User Story:** As a 자취생, I want 영수증 정보를 직접 입력할 수 있도록, so that 파일 파싱이 실패하거나 소수 건만 추가할 때도 거래를 기록할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display a receipt registration form with fields for store name (required, max 50 characters), date (required, YYYY-MM-DD format, not in the future), amount (required, integer between 1 and 999,999,999 KRW), a single-select category chip group (6 categories), and an optional memo field (max 100 characters).
2. WHILE the user has not selected a category or any required field (store name, date, amount) is empty, THE SPA SHALL highlight the incomplete field group in red and disable the submission button.
3. WHEN the user submits a valid receipt form, THE API_Server SHALL store the receipt with nickname, store, date, amount, category, subtype (default "일반" for manual entry), and memo in the receipts table, and return the created receipt record with its assigned id.
4. IF the amount field contains a non-numeric, zero, or negative value, THEN THE SPA SHALL display a validation error below the amount field and prevent submission.
5. THE SPA SHALL display the memo field with placeholder text "이 소비에 대한 한마디" to indicate the memo is included in the verdict prompt.
6. WHEN the API_Server successfully stores the receipt, THE SPA SHALL display a success confirmation and navigate the user to the home screen.
7. IF the API_Server returns an error on receipt submission, THEN THE SPA SHALL display a toast notification indicating the failure reason and preserve the user's entered form data.

### Requirement 3: 지출내역 파일 파싱 (File Upload)

**User Story:** As a 자취생, I want 카드사/은행 지출내역 파일을 올리면 자동으로 내용이 채워지도록, so that 수십 건의 지출을 일일이 입력하지 않아도 된다.

#### Acceptance Criteria

1. WHEN the user uploads one or more files (PDF, xlsx, or CSV, each no larger than 10 MB), THE Parse_Module SHALL extract transaction data and return a standardized JSON array where each element contains: date (string YYYY-MM-DD), store (string), amount (positive integer in KRW), category (one of 6 fixed categories), subtype (one of 5 fixed subtypes), and needs_review (boolean).
2. FOR xlsx and CSV files, THE Parse_Module SHALL use pandas + openpyxl for raw row extraction without hardcoding bank-specific parsers, then send the extracted text to Bedrock Claude Sonnet 5 (model ID: global.anthropic.claude-sonnet-5) for normalization into the standard JSON schema including category and subtype classification.
3. FOR text-based PDF files, THE Parse_Module SHALL use pdfplumber to extract text content, then send the extracted text to Bedrock for normalization into the standard JSON schema.
4. FOR image-only (scanned) PDF files where pdfplumber extracts no meaningful text, THE Parse_Module SHALL render pages to images using pypdfium2, then use the existing Vision_Module (base64 + Bedrock vision) as fallback for recognition.
5. THE Parse_Module SHALL filter out non-expenditure rows (deposits, cancellations, card payment deductions) and only return actual spending transactions.
6. THE Parse_Module SHALL remove commas and currency symbols from amount values and convert to integer KRW.
7. WHEN the Parse_Module cannot confidently classify a transaction's category or subtype, THE Parse_Module SHALL set needs_review=true for that row.
8. WHEN the Parse_Module returns results, THE SPA SHALL display all parsed rows in a list form for user review, with needs_review rows highlighted, allowing the user to edit any field before final submission.
9. IF the Parse_Module call fails or returns unparseable data, THEN THE System SHALL retry once, and if the retry also fails, display the empty manual registration form with a message indicating parsing failure.
10. THE Parse_Module SHALL upload the original file to S3 bucket "hackathon-e1-t07-docs" at the "evidence/" path using a timestamp-based unique key.
11. WHERE Mock_Mode is active (MOCK_AI=1), THE Parse_Module SHALL return a fixed sample transaction list without calling Bedrock, and SHALL skip the S3 upload.
12. THE SPA SHALL provide a manual row-add button allowing users to add additional receipt entries manually alongside parsed results.

### Requirement 4: 홈 화면 집계

**User Story:** As a 자취생, I want 이번 달 소비 현황을 한눈에 파악하도록, so that 내 지출 규모와 판결 대기 상태를 즉시 알 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display the current month's total expenditure as a large numeric value formatted with comma separators and "원" suffix, the number of submitted receipts ("영수증 N건 제출됨"), and a "선고까지 D-N" badge showing the remaining days until month-end.
2. WHEN the current date is the last day of the month, THE SPA SHALL display "D-DAY" instead of a countdown number.
3. THE SPA SHALL display a top-3 category bar chart sorted by expenditure amount; IF fewer than 3 categories have data, THE SPA SHALL show only the available categories.
4. THE SPA SHALL display the 3 most recent receipt entries below the summary showing store name, category, date, and amount; IF fewer than 3 receipts exist, show only the available entries.
5. THE SPA SHALL display a "{M}월 소비 판결문 받기" button that navigates to the verdict generation flow.
6. IF the user has zero receipts for the current month, THEN THE SPA SHALL display a zero-data state message encouraging receipt registration.
7. IF the user has fewer than 5 receipts for the current month, THEN THE SPA SHALL still display the home screen with available data and the verdict button (the guard condition is evaluated at verdict time, not at display time).

### Requirement 5: 소비 내역 조회

**User Story:** As a 자취생, I want 월별·카테고리별로 내 지출 내역을 확인하도록, so that 어디에 얼마를 썼는지 상세히 파악할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display a month selector defaulting to the current month and a horizontally scrollable category filter chip group ("전체" followed by the 6 fixed categories) at the top of the history screen, where "전체" is selected by default and shows receipts across all categories.
2. WHEN the user selects a month and optional category filter, THE API_Server SHALL return receipts filtered by nickname, month (YYYY-MM), and category (or all categories if "전체"), grouped by date in reverse chronological order, with each group containing a date header in "{M}월 {D}일 ({요일})" format and a daily subtotal in "{금액}원" format with thousands separators.
3. THE SPA SHALL render each receipt entry showing store name, category label with category color dot, and amount formatted with thousands separators and "원" suffix, within date-grouped sections.
4. THE SPA SHALL display the total receipt count (format: "총 {N}건 제출") and total expenditure amount for the selected month and filter at the top of the list area.
5. WHEN no receipts exist for the selected month and filter combination, THE SPA SHALL display an empty state message indicating no spending records exist for the selected period.
6. IF the API request for receipt history fails, THEN THE SPA SHALL display a toast notification with error context rather than showing a blank screen.

### Requirement 6: 소비 분석

**User Story:** As a 자취생, I want 이번 달 지출의 통계적 분석을 확인하도록, so that 판결을 받기 전에 내 소비 패턴을 이해할 수 있다.

#### Acceptance Criteria

1. THE API_Server SHALL compute and return monthly summary statistics for the requested nickname and month: total expenditure, payment count, daily average (total expenditure divided by the calendar days of the requested month), and per-category totals with counts for each of the 6 fixed categories.
2. THE SPA SHALL display each category row showing a colored dot, category name, payment count (e.g., "11회"), amount, and a proportional horizontal bar whose width is relative to the highest-amount category (highest = 100% width), sorted by amount descending.
3. THE SPA SHALL display a "최다 지출 카테고리" card showing the category name and its percentage of total expenditure, and a "가장 큰 단일 지출" card showing the store name and amount of the single highest-amount receipt in the month.
4. THE SPA SHALL display an "이 증거로 판결받기" button navigating to the verdict generation flow.
5. THE SPA SHALL display a summary section containing: total expenditure as a large numeric value with "원" suffix, payment count as "{N}회", and daily average as "일평균 {amount}원".
6. IF the requested month has zero receipts for the given nickname, THEN THE SPA SHALL display an empty state message indicating no spending data exists and hide the category breakdown and highlight cards.
7. IF two or more categories share the highest expenditure amount, THEN THE API_Server SHALL select the one with the higher payment count as "최다 지출 카테고리", and if counts are also equal, select the first in the fixed category order.

### Requirement 7: 판정 룰 (결정적 조건문)

**User Story:** As a 개발자, I want 소비 유형 판정이 결정적 조건문으로 동작하도록, so that 동일 데이터에 항상 동일 결과가 나와 재현 가능하다.

#### Acceptance Criteria

1. WHEN the Judgment_Engine receives a nickname and month, THE Judgment_Engine SHALL collect all receipts for that nickname and month, compute total expenditure as the sum of their amount values, compute total payment count as the number of those receipts, and evaluate rules in fixed priority order (rule 0 through rule 8), selecting the first matching rule and returning exactly one result containing a charge string and a type string.
2. WHEN the month's receipt count is fewer than 5, THE Judgment_Engine SHALL return charge "증거 불충분" with type "균형 잡힌 생존형" without evaluating subsequent rules (guard rule 0).
3. IF total expenditure is 0 after the guard rule passes, THEN THE Judgment_Engine SHALL return charge "증거 불충분" with type "균형 잡힌 생존형" (fallback, to avoid division-by-zero in percentage calculations).
4. WHEN delivery-app subtype (subtype="배달앱") expenditure is 35% or more of total expenditure, THE Judgment_Engine SHALL return charge "냉장고 유기죄" with type "냉장고보다 배달앱형" (rule 1).
5. WHEN convenience-store subtype (subtype="편의점") payment count is 10 or more, THE Judgment_Engine SHALL return charge "편의점 상습 출석죄" with type "편의점이 내 부엌형" (rule 2).
6. WHEN cafe-snack category (category="카페·간식") expenditure is 25% or more of total expenditure, THE Judgment_Engine SHALL return charge "카페인 정기후원죄" with type "소확행 충전형" (rule 3).
7. WHEN shopping category (category="쇼핑") expenditure is 30% or more of total expenditure, THE Judgment_Engine SHALL return charge "필요와 욕망 혼동죄" with type "취향에 진심형" (rule 4).
8. WHEN expenditure during days 1–10 of the month (receipt date day-of-month between 1 and 10, inclusive) is 45% or more of total monthly expenditure, THE Judgment_Engine SHALL return charge "월초 재벌 행세죄" with type "월초 플렉스형" (rule 5).
9. WHEN payment count with amount 10,000 KRW or less (amount ≤ 10000) is 15 or more, THE Judgment_Engine SHALL return charge "잔액 조금씩 빼돌린 죄" with type "티끌 과소비형" (rule 6).
10. WHEN mart-grocery subtype (subtype="마트·장보기") expenditure is 30% or more of total expenditure AND delivery-app subtype (subtype="배달앱") expenditure is 15% or less of total expenditure, THE Judgment_Engine SHALL return charge "무혐의" with type "야무진 자취생형" (rule 7).
11. WHEN no rule from 1 through 7 matches, THE Judgment_Engine SHALL return charge "증거 불충분" with type "균형 잡힌 생존형" (fallback rule 8).

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

1. THE SPA SHALL render the verdict in a paper-document style layout with sections in this order: header ("대한민국 소비재판소 / {M}월 소비 판결문 / 사건번호 {YYYY} 소비합 {4자리}"), defendant info ("피 고 인: 자취생 {닉네임} ({나이})" / "심리기간: {YYYY}.{MM}.01 – {MM}.{말일}" / "증거건수: 영수증 N건 / 결제 N회"), charge section (large burgundy text), article subtitle, evidence section (numbered 01–04 with actual statistics), ruling section (bold ruling + reasoning paragraph), sentence section (dark box with action suggestions), and stamp area.
2. WHEN the verdict charge is "무혐의" or "증거 불충분", THE SPA SHALL display a circular "무죄 ACQUITTED" stamp; otherwise THE SPA SHALL display a circular "유죄 CONVICTED" stamp with date "{YYYY}년 {MM}월 {말일}일" and text "소비재판소 재판장 통장".
3. WHEN the user's age is not provided, THE SPA SHALL omit the parenthesized age from the defendant line (display "자취생 {닉네임}" only).
4. THE SPA SHALL display "이미지 저장" and "공유하기" buttons that are visually present but non-functional (reserved for P1), and SHALL NOT trigger any action on tap.
5. THE SPA SHALL display a "내 소비 유형 확인하기 →" button navigating to the type result screen.
6. WHILE the verdict is being generated, THE SPA SHALL display a loading state with a brief message (e.g., "판결문을 작성 중입니다…") rather than a blank screen.

### Requirement 10: 최종 소비 유형 표시

**User Story:** As a 자취생, I want 내 소비 유형을 MBTI처럼 카드로 확인하도록, so that 결과를 재미있게 소비하고 친구와 비교할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL display a type result card containing: the charge name as a tag badge, the type name in large text, a 2–3 sentence description (from the verdict's type_description field), and 3 key statistics (the type-specific trigger metrics from judgment) displayed in horizontal boxes.
2. THE SPA SHALL display a "다음 달의 형량" badge with the sentence text from the verdict.
3. THE SPA SHALL display a "소비 유형 도감" grid in 4×2 layout showing all 8 types with charge subtitle, where the current month's type is highlighted with a red dot indicator and displays "{N}/8 수집" (collection state persistence is deferred to P1, so current session only shows 1/8).
4. THE SPA SHALL display a "다음 달 재판 시작하기" button that returns the user to the home screen.
5. THE SPA SHALL display a screen header showing "{YYYY}년 {M}월 · 최종 선고" and "당신의 소비 유형".

### Requirement 11: 드립 상호작용

**User Story:** As a 자취생, I want 판결 화면에서 위트있는 드립을 볼 수 있도록, so that 서비스가 더 재미있고 반복 방문 동기가 생긴다.

#### Acceptance Criteria

1. WHEN the user taps the sentence text (형량 영역) or type badge on the verdict screen (06) or type screen (07), THE SPA SHALL display a random humor toast message selected from the hardcoded pool for the current verdict's type.
2. THE System SHALL maintain 3–4 hardcoded humor messages per each of the 8 types (24–32 total messages) stored as a JavaScript object in the SPA code.
3. THE SPA SHALL display the toast for 2–3 seconds then auto-dismiss with a fade-out animation, without any API call or Bedrock invocation (immediate local response).
4. WHEN the user taps the same element multiple times, THE SPA SHALL show a different message from the pool each time (cycling through available messages before repeating).

### Requirement 12: 하단 탭 네비게이션

**User Story:** As a 자취생, I want 화면 하단에 항상 탭바가 보이도록, so that 어떤 화면에서도 원하는 섹션으로 즉시 이동할 수 있다.

#### Acceptance Criteria

1. WHILE the user is past the onboarding screen, THE SPA SHALL display a bottom tab bar fixed to the viewport bottom (position: fixed) with 4 tabs in left-to-right order: 홈, 등록, 내역, 판결, where each tab contains an icon and a text label below the icon.
2. WHEN the user taps a tab, THE SPA SHALL switch the visible screen to the corresponding section without a full page reload (JS-based div switching) and visually indicate the tapped tab as active by differentiating its style (e.g., color or opacity) from the remaining inactive tabs.
3. WHILE the user is on the onboarding screen, THE SPA SHALL hide the bottom tab bar completely (display: none).
4. WHEN the SPA finishes loading after the user has completed onboarding, THE SPA SHALL display the 홈 tab as the default active tab with the 홈 screen visible.
5. WHILE the user scrolls content within any screen, THE SPA SHALL keep the bottom tab bar visible and fixed at the viewport bottom without scrolling away.

### Requirement 13: 모바일 우선 레이아웃

**User Story:** As a 자취생, I want 모바일에서 최적화된 화면을 보도록, so that 스마트폰으로 편하게 이용할 수 있다.

#### Acceptance Criteria

1. THE SPA SHALL render all screens within a max-width 480px centered container on desktop viewports (viewport width > 480px), with the remaining viewport area filled by the app's dark background color.
2. ON mobile viewports (viewport width ≤ 480px), THE SPA SHALL fill the entire viewport width without horizontal margins.
3. THE SPA SHALL implement all screen transitions using JavaScript DOM manipulation within a single index.html file without any framework dependency (no React, Vue, Angular, or similar).
4. THE SPA SHALL prevent horizontal overflow/scrolling on all screens at viewport widths ≥ 320px.

### Requirement 14: API 엔드포인트

**User Story:** As a 개발자, I want 명확한 REST API 인터페이스가 정의되도록, so that 프런트엔드와 백엔드가 독립적으로 개발·테스트될 수 있다.

#### Acceptance Criteria

1. THE API_Server SHALL expose POST /api/users/{nickname} that creates a new user record if the nickname does not exist or returns the existing user record if it does, responding with a JSON object containing nickname, age (nullable), and created_at fields.
2. THE API_Server SHALL expose POST /api/receipts accepting a JSON body with nickname (string) and items array where each item contains store (string, required), date (string YYYY-MM-DD, required), amount (positive integer, required), category (one of 6 fixed categories, required), subtype (one of 5 fixed subtypes, optional, defaults to "일반"), and memo (string, optional), storing each valid item as a receipt record and responding with the count of stored records.
3. THE API_Server SHALL expose GET /api/receipts/{nickname}?month=YYYY-MM returning a JSON array of receipt records filtered by nickname and month, each containing id, store, date, amount, category, subtype, and memo, sorted by date descending.
4. THE API_Server SHALL expose GET /api/summary/{nickname}?month=YYYY-MM returning a JSON object containing: total_amount, count, daily_average, categories (per-category totals/counts), top_category, and largest_transaction (with store, amount, date).
5. THE API_Server SHALL expose POST /api/verdict/{nickname}?month=YYYY-MM&force=false that triggers judgment + verdict generation and returns a JSON verdict record containing case_number, charge, article, ruling, reasoning, sentence, spending_type, type_description, and created_at.
6. THE API_Server SHALL expose GET /api/history/{nickname} returning a JSON array of all past verdict records sorted by created_at descending.
7. THE API_Server SHALL serve the SPA (static/index.html) and static assets from the root path.
8. IF a request contains an invalid month query parameter (not matching YYYY-MM format) or a missing required field in the receipts POST body, THEN THE API_Server SHALL respond with HTTP 422 status and a JSON body containing a detail field describing the validation error.
9. IF a request references a nickname that has no user record for GET endpoints, THEN THE API_Server SHALL return an empty result set rather than an error.

### Requirement 15: 데이터 저장소

**User Story:** As a 개발자, I want 데이터가 SQLite에 영속 저장되도록, so that 서버 재시작 후에도 모든 데이터가 유지된다.

#### Acceptance Criteria

1. THE API_Server SHALL use SQLite as the sole persistent storage with tables: users (nickname TEXT PK, age INTEGER nullable, created_at TEXT), receipts (id INTEGER PK autoincrement, nickname TEXT NOT NULL references users, store TEXT NOT NULL, date TEXT NOT NULL, amount INTEGER NOT NULL storing Korean won units, category TEXT NOT NULL constrained to one of the 6 defined categories, subtype TEXT NOT NULL constrained to one of the 5 defined subtypes, memo TEXT nullable, needs_review INTEGER NOT NULL default 0, s3_key TEXT nullable), and verdicts (id INTEGER PK autoincrement, nickname TEXT NOT NULL references users, month TEXT NOT NULL in YYYY-MM format, case_number TEXT NOT NULL, charge TEXT NOT NULL, article TEXT NOT NULL, evidence_json TEXT NOT NULL, ruling TEXT NOT NULL, reasoning TEXT NOT NULL, sentence TEXT NOT NULL, spending_type TEXT NOT NULL, type_description TEXT NOT NULL, created_at TEXT NOT NULL), with a UNIQUE constraint on (nickname, month) in the verdicts table.
2. IF the database tables do not exist on application startup, THEN THE API_Server SHALL create all tables using CREATE TABLE IF NOT EXISTS, preserving any existing data in an already-initialized database file.
3. THE API_Server SHALL store uploaded source file references as s3_key values pointing to S3 objects rather than storing file data locally.
4. THE API_Server SHALL enable SQLite WAL (Write-Ahead Logging) mode on connection to support concurrent read/write access.
5. THE API_Server SHALL enforce foreign key constraints (PRAGMA foreign_keys = ON).

### Requirement 16: Mock 모드

**User Story:** As a 개발자, I want MOCK_AI=1 환경에서 Bedrock 없이 전 기능을 검증하도록, so that 로컬 개발 환경에서 AWS 자격증명 없이도 화면과 로직을 테스트할 수 있다.

#### Acceptance Criteria

1. WHERE Mock_Mode is active (MOCK_AI=1 environment variable), THE Parse_Module SHALL return a fixed sample receipt list JSON response without invoking Bedrock.
2. WHERE Mock_Mode is active (MOCK_AI=1 environment variable), THE Verdict_Generator SHALL return a fixed sample verdict response without invoking Bedrock.
3. WHERE Mock_Mode is active (MOCK_AI=1 environment variable), THE System SHALL skip S3 upload operations and use a placeholder s3_key value (e.g., "mock/placeholder.pdf").
4. WHILE Mock_Mode is inactive, THE System SHALL perform actual Bedrock and S3 operations using boto3 with the default region from /etc/environment.
5. THE mock responses SHALL be realistic enough to exercise the full UI flow (onboarding → registration → home → history → analysis → verdict → type) including all required fields.

### Requirement 17: 더미 시드 데이터

**User Story:** As a 개발자, I want 8종 죄명을 모두 재현하는 더미 데이터가 준비되도록, so that 데모에서 모든 판정 경로를 즉시 시연할 수 있다.

#### Acceptance Criteria

1. THE System SHALL provide a seed script (data/seed.py) that populates the database with 8 nicknames, each designed to trigger exactly one distinct judgment rule when evaluated in priority order.
2. THE seed script SHALL generate approximately 60 total receipt records for August (2026-08) distributed across the 8 nicknames such that each nickname's data exceeds the threshold for its target rule while staying below thresholds of all higher-priority rules.
3. WHEN the seed script is executed, THE System SHALL clear existing seed data (DELETE from receipts and users where nickname matches seed nicknames) and re-insert fresh records to ensure repeatability.
4. THE seed script SHALL ensure each nickname has at least 5 receipts to pass the guard rule (rule 0).

### Requirement 18: 배포 및 운영

**User Story:** As a 운영자, I want 서비스가 SSH 종료 후에도 안정적으로 동작하도록, so that 데모 중 서비스 중단이 발생하지 않는다.

#### Acceptance Criteria

1. THE System SHALL run via nohup with stdin redirected from /dev/null and stdout/stderr redirected to a log file so that the process persists after SSH session termination.
2. THE System SHALL bind to port 8501 and respond to HTTP GET requests at http://18.135.105.80:8501 with HTTP status 200 and HTML content within 5 seconds.
3. THE System SHALL use `appenv/bin/python -m uvicorn` as the execution command.
4. WHEN the existing receipt_app.py (Streamlit) process occupies port 8501, THE deployment process SHALL send SIGTERM to that process, wait up to 10 seconds for it to exit, then start the FastAPI application only after confirming the port is released.
5. IF the FastAPI process fails to start or does not respond with HTTP 200 within 30 seconds of launch, THEN THE deployment process SHALL output an error message indicating startup failure and preserve the log file for diagnosis.
6. WHEN deployment completes successfully, THE deployment process SHALL verify accessibility by performing a curl request to http://18.135.105.80:8501 and confirming an HTTP 200 response.

### Requirement 19: 품질 및 오류 처리

**User Story:** As a 자취생, I want 오류가 발생해도 빈 화면 대신 안내를 받도록, so that 서비스가 항상 사용 가능하다는 신뢰를 가질 수 있다.

#### Acceptance Criteria

1. IF Bedrock returns a response that fails JSON parsing or is missing required fields, THEN THE System SHALL retry the call once within 5 seconds, and IF the retry also fails, THEN THE System SHALL return a user-facing error message suggesting the user try again.
2. THE System SHALL mask card numbers by replacing all digits except the first 4 and last 4 with asterisks (e.g., 1234-****-****-5678), and mask phone numbers by replacing the middle digits with asterisks, during file parsing before storing results.
3. THE API_Server SHALL include Korean-language comments on all API endpoint handler functions and all functions in core/ modules.
4. IF an API request fails with a server error (HTTP 5xx) or does not respond within 10 seconds, THEN THE SPA SHALL display a toast notification for 4 seconds containing a brief description of the failed operation and a retry prompt.
5. WHILE the SPA is waiting for an API response, THE SPA SHALL display a loading indicator within 300 milliseconds, and IF 15 seconds elapse without a response, THEN THE SPA SHALL dismiss the loading indicator and display a timeout error with retry prompt.

### Requirement 20: 데모용 합성 지출내역 파일

**User Story:** As a 개발자, I want 데모용 합성 지출내역 파일(엑셀 1개 + PDF 1개)이 준비되도록, so that 파일 업로드→정규화→판결문 전체 흐름을 즉시 시연할 수 있다.

#### Acceptance Criteria

1. THE System SHALL provide 2 synthetic expenditure files in samples/ directory: one xlsx file simulating a credit card statement and one text-based PDF file simulating a bank account statement.
2. EACH synthetic file SHALL contain 30–40 rows of fictitious transactions with realistic Korean store names, dates within a single month (2026-08), amounts in KRW, and a mix of all 6 categories and 5 subtypes.
3. EACH synthetic file SHALL include at least 3 non-expenditure rows (deposits, cancellations, or card payment deductions) to verify the Parse_Module correctly filters them out.
4. WHEN either synthetic file is uploaded and parsed, THE Parse_Module SHALL produce a transaction list whose expenditure-only amounts sum matches the sum of actual spending rows in the source file.
5. THE synthetic data in both files SHALL be designed such that one file triggers one specific judgment rule (e.g., rule 1 — delivery-heavy) and the other file triggers a different rule (e.g., rule 6 — many small payments), enabling demonstration of different verdict outcomes.

---

## Priority Classification

### P0 (Must Have — Demo Complete)

- Requirements 1–20 전체 (온보딩 → 등록 → 파일 파싱 → 홈 → 내역 → 분석 → 판결문 → 유형)
- 지출내역 파일 파싱 (PDF/xlsx/CSV)
- 데모용 합성 지출내역 파일 2개 (카드사 스타일 엑셀 + 텍스트 PDF)
- 수동 입력 폴백
- Subtype 기반 결정적 판정 (8종 전부 재현)
- Bedrock 판결문 산문 생성
- Mock 모드 (MOCK_AI=1)
- 드립 상호작용
- 더미 시드 스크립트 (2026년 8월, 닉네임 8개)
- 성공 기준: 샘플 파일 2개를 업로드하면 정규화→판결문까지 정상 동작 / 수동 입력만으로 전 흐름 동작 / 데모 무중단

### P1 (Deferred)

- 영수증 이미지 비전 인식 (사진 업로드)
- 감형 처방전 화면
- 소비 유형 도감 수집 상태 영속 저장
- 판결문 이미지 저장 및 공유 기능
- 지난 판결문 목록 화면

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
3. **File Parse Round-Trip**: FOR ALL valid expenditure files (xlsx/CSV/PDF), parsing then storing via POST /api/receipts SHALL result in receipt records whose amounts sum equals the total of expenditure-only rows in the source file (excluding deposits, cancellations, card payment deductions).

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
