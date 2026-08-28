# API 명세 — 프론트↔백엔드 계약서 (상세 JSON 예시: docs/05 §9·§12)

공통 응답: 성공 `{"success": true, "data": ...}` / 실패 `{"success": false, "error": {"code","message"}}`

| # | 메서드 | 경로 | 넣는 것 (요청) | 나오는 것 (응답 data) | 실패 시 |
|---|--------|------|----------------|----------------------|---------|
| 0 | GET | /api/health | — | {message: "server is running"} | — |
| 1 | POST | /api/expenses | {storeName, date, amount, category, transactionType} | 생성된 Expense (id·createdAt 포함) | 400 검증 실패 |
| 2 | GET | /api/expenses?month=YYYY-MM | month 쿼리 | Expense 배열 (날짜 내림차순) | 400 월 형식 |
| 3 | GET | /api/expenses/{id} | — | Expense 1건 | 404 없음 |
| 4 | PUT | /api/expenses/{id} | 1번과 동일 바디 | 수정된 Expense | 400/404 |
| 5 | DELETE | /api/expenses/{id} | — | {"success": true} | 404 없음 |
| 6 | GET | /api/analysis?month=YYYY-MM&defendant=(선택) | month 쿼리 | data 키 15개: 통계 6종+largestSingleExpense+topCategory+categoryStats+consumerType+judgment+reactionMessage+defendant+needsReviewCount+**benchmark**(null가능)+**remark**(null가능) — 상세는 05 §12 | 400 월 형식 |
| 7 | POST | /api/import | multipart: **file**(필수) + **defendant**(선택) | {imported, parsed, defendant, needsReviewCount, source, rawRowCount, items, warning} | 400 형식·크기·파일없음 |

| 8 | POST | /api/expenses/skip-review?month=YYYY-MM | month 쿼리 | {skipped, month} | 400 월 형식 |

## 파일 업로드 (7번)
- 엑셀(.xlsx/.xls)·CSV·**텍스트** PDF, 10MB 이하. 스캔 이미지 PDF는 미지원(items가 빈 배열).
- `?dryRun=true`를 붙이면 저장하지 않고 파싱 결과만 준다 → 확인 화면에 쓰고,
  사용자가 확정하면 dryRun 없이 다시 호출한다.
- `source`가 `bedrock`이면 LLM 정규화, `rules(fallback)`이면 Bedrock 실패 후 규칙 폴백이다.

## 피고인·미분류 (신규 필드)
- `defendant`: 사용자가 직접 입력하는 피고인 이름. **10자 이내**, 초과 시 400.
  생략하면 서버가 "익명의 자취생"으로 채운다. **조회를 이 값으로 거르지 않는다**(판결문 표시용).
- `needsReview`: 상호명 대신 예금주 이름만 있어 카테고리를 정할 수 없는 건이면 true.
  업로드 응답의 `needsReviewCount`로 몇 건인지 알 수 있다.
- `memo`: 미분류 건에 사용자가 붙이는 정리용 메모(입력 쪽). **10자 이내**, 초과 시 400.
- 미분류 정리는 4번(PUT)으로 보낸다. **PUT이 성공하면 needsReview가 자동으로 false가 된다.**
- `plea`: 피고인 변론(판결 쪽). 선택, **200자 이내**, 초과 시 400(`INVALID_PLEA`).
  거래에 "친구 4명 더치페이"처럼 적으면 판결문 이유에 N빵 정상참작으로 반영된다.

## 필드명 계약 (RULE 002~005 — 임의 변경 금지)
- camelCase: `storeName` `amount` `transactionType` `createdAt` `consumerType` `reactionMessage` `defendant` `memo` `plea` `needsReview` `needsReviewCount`
- 카테고리 코드 6종: `DELIVERY_DINING` `CONVENIENCE_STORE` `CAFE_SNACK` `GROCERIES` `SHOPPING_HOBBY` `OTHER`
- 거래 유형: `EXPENSE` `TRANSFER`
- 금액은 숫자(18000) — "18,000원" 문자열 금지
- 날짜 `YYYY-MM-DD`, 월 `YYYY-MM`
