---
inclusion: always
---

# 프론트 ↔ 백엔드 계약 (서버 실측 기준 — 프론트는 이대로 붙이면 된다)

백엔드는 전부 구현·배포 완료 상태다. 프론트는 아래 형식을 그대로 신뢰하고 붙인다.
백엔드를 고쳐야 한다고 판단되면 멈추고 먼저 알릴 것.

## 응답 봉투 (모든 API 공통)
```
성공: {"success": true, "data": ...}
실패: {"success": false, "error": {"code": "...", "message": "..."}}
```
- 프론트는 **항상 `.data`를 벗겨서** 쓴다.
- 에러 메시지는 `error.message`에 한국어로 들어있다. 그대로 화면에 띄우면 된다.
- **예외 1개: DELETE 성공 응답에는 `data` 키가 없다.** `{"success": true}` 뿐이다.
  `.data`에 접근하면 undefined다.

## 상태 코드
- **POST /api/expenses 성공은 201** (200 아님). `res.ok`로 판정할 것, `status === 200` 금지.
- 그 외 성공 200 / 검증 실패 400 / 대상 없음 404

## 엔드포인트
| 메서드 | 경로 | 보내는 것 | 받는 것(data) |
|---|---|---|---|
| GET | /api/health | — | {message} |
| POST | /api/expenses | {storeName,date,amount,category,transactionType} | 생성된 Expense (201) |
| GET | /api/expenses?month=YYYY-MM | — | Expense 배열 (날짜 내림차순, TRANSFER 포함) |
| GET | /api/expenses/{id} | — | Expense 1건 |
| PUT | /api/expenses/{id} | POST와 동일 바디 | 수정된 Expense |
| DELETE | /api/expenses/{id} | — | (data 없음) |
| GET | /api/analysis?month=YYYY-MM | — | 통계+consumerType+judgment+reactionMessage |
| POST | /api/import | multipart, 필드명 **file** | {imported,parsed,source,rawRowCount,items,warning} |

Expense = {id, storeName, date, amount, category, transactionType, createdAt, updatedAt}

## 카테고리 — 프론트가 라벨 매핑을 직접 가져야 한다
**GET /api/expenses 응답에는 한글 라벨이 없다.** `category: "DELIVERY_DINING"` 코드만 온다.
목록 화면에 코드를 그대로 찍으면 안 되므로 프론트가 아래 표를 갖고 변환한다.
(GET /api/analysis의 categoryStats·topCategory에는 `label`이 함께 온다 — 거긴 그대로 쓰면 된다.)
```
DELIVERY_DINING    배달·외식
CONVENIENCE_STORE  편의점
CAFE_SNACK         카페·간식
GROCERIES          식재료·생필품
SHOPPING_HOBBY     쇼핑·취미
OTHER              기타
```
거래유형: `EXPENSE` = 소비 / `TRANSFER` = 이체
입력 폼의 셀렉트는 **화면에 한글 라벨을 보여주고 값은 영문 코드를 전송**한다.

## 값 규칙
- 날짜 `YYYY-MM-DD`, 월 `YYYY-MM`. 문자열 그대로 주고받는다(Date 객체로 변환하면 하루 밀린다).
- 금액은 숫자(18000). `"18,000원"` 문자열로 보내면 400. 콤마·"원"은 화면 표시에서만 붙인다.
- 월 조회는 month 파라미터가 필수다. 빼면 400이다.

## 파일 업로드
- `POST /api/import`, multipart/form-data, 필드명 `file`. 엑셀·CSV·텍스트 PDF, 10MB 이하.
- `?dryRun=true`를 붙이면 **저장하지 않고 파싱 결과만** 돌려준다 → 확인 화면에 쓰고,
  사용자가 확정하면 dryRun 없이 다시 호출한다.
- 응답의 `items`가 파싱된 거래 배열, `warning`이 null이 아니면 화면에 안내를 띄운다
  (예: 스캔 이미지 PDF는 지원하지 않음).
- 스캔본 PDF는 `items`가 빈 배열로 온다. "거래를 못 찾았다 + 수동 입력 안내"를 보여줄 것.

## 응답 지연 — 로딩 표시는 선택이 아니라 필수 (서버 실측)
```
GET /api/expenses    약 0.6초
GET /api/analysis    약 5초     ← Bedrock으로 판결 이유를 생성한다
POST /api/import     약 8초     ← Bedrock으로 파일을 정규화한다
```
분석과 업로드는 **5~9초 걸린다.** 로딩 표시가 없으면 앱이 멈춘 것처럼 보인다.
버튼 비활성화 + 재미있는 로딩 문구("법정 개정 중...", "증거 분석 중...")를 반드시 넣는다.
연타로 중복 요청이 나가지 않게 막을 것.

## 프론트가 하면 안 되는 것
- **분석 계산 금지, 소비 유형 재계산 금지.** 서버가 준 값을 그대로 렌더한다.
- 합계·비율·평균을 프론트에서 다시 구하지 않는다. 서버 값과 어긋난다.
- 필드명을 임의로 바꾸지 않는다(camelCase 그대로).
