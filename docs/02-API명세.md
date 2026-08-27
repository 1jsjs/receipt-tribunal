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
| 6 | GET | /api/analysis?month=YYYY-MM | month 쿼리 | 통계+consumerType+judgment+reactionMessage 전체 (05 §12) | 400 월 형식 |

## 필드명 계약 (RULE 002~005 — 임의 변경 금지)
- camelCase: `storeName` `amount` `transactionType` `createdAt` `consumerType` `reactionMessage`
- 카테고리 코드 6종: `DELIVERY_DINING` `CONVENIENCE_STORE` `CAFE_SNACK` `GROCERIES` `SHOPPING_HOBBY` `OTHER`
- 거래 유형: `EXPENSE` `TRANSFER`
- 금액은 숫자(18000) — "18,000원" 문자열 금지
- 날짜 `YYYY-MM-DD`, 월 `YYYY-MM`
