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
| GET | /api/analysis?month=YYYY-MM&defendant=(선택) | — | 아래 '분석 응답 전체 키' 참조 |
| POST | /api/import | multipart: **file** + (선택) **defendant** | {imported,parsed,defendant,needsReviewCount,source,rawRowCount,items,warning} |

Expense = {id, storeName, date, amount, category, transactionType,
           defendant, memo, plea, needsReview, createdAt, updatedAt}

## 분석 응답 전체 키 (GET /api/analysis 의 data — 15개, 이대로 렌더)
```
month, totalExpense, paymentCount, averagePaymentAmount, smallPaymentCount,
largestSingleExpense{amount,storeName,date,category},
topCategory{category,label,amount,percentage,count}, categoryStats[동일 구조 배열],
consumerType{code,label}, judgment{crime,evidence[],verdict,reasoning,sentence},
reactionMessage, defendant, needsReviewCount, benchmark(null 가능), remark(null 가능)
```
통계 카드는 이 필드명을 그대로 쓴다. 프론트에서 재계산 금지.

## 피고인 이름 (defendant)
- 사용자가 직접 입력한다. **10자 이내**, 넘기면 400(`INVALID_DEFENDANT`).
- 안 보내면 서버가 "익명의 자취생"으로 채운다. 필수가 아니다.
- 보내는 곳: POST/PUT 바디의 `defendant`, POST /api/import의 **폼 필드** `defendant`,
  GET /api/analysis의 쿼리 `defendant`. **10자 초과 400은 네 곳 모두 동일 적용.**
- **조회를 피고인으로 거르지 않는다.** 이름은 판결문에 표시하는 용도다.
  (이름 한 글자가 달라 빈 화면이 뜨는 사고를 막기 위해 의도적으로 필터를 안 건다.)
- GET /api/analysis 응답의 `defendant`가 판결문에 쓸 이름이다. 쿼리로 넘기면 그 값이,
  안 넘기면 그 달 기록에서 가장 많은 이름이 온다.

## 미분류 내역 (needsReview / memo)
통장 내역에는 가맹점 대신 **예금주 이름만** 찍히는 경우가 많다("김OO", "홍길동").
이런 건 기계가 카테고리를 정할 수 없어 `needsReview: true`로 표시된다.

- 업로드 응답의 `needsReviewCount`, 분석 응답의 `needsReviewCount`로 몇 건인지 알 수 있다.
- 프론트는 업로드 직후 **미분류 정리 화면**을 띄운다:
  각 행마다 `memo` 입력(**10자 이내**, 넘기면 400 `INVALID_MEMO`) + 카테고리 선택.
- 정리는 `PUT /api/expenses/{id}`로 보낸다. **PUT이 성공하면 서버가 needsReview를 자동으로
  false로 내린다.** 프론트가 따로 해제 요청을 보낼 필요 없다.
- 수동 입력으로 만든 건은 항상 `needsReview: false`다.

## 피고인 변론 (plea) — memo와 다른 필드다
- `memo`(10자, 입력 쪽)는 미분류 내역이 "뭐였는지" 적는 정리용이다.
- `plea`(**200자 이내**, 넘기면 400 `INVALID_PLEA`, 판결 쪽)는 사용자의 항변이다.
  거래에 "친구 4명 더치페이"처럼 적으면 그 달 분석 시 **N빵 정상참작**으로 잡혀
  판결문 `judgment.reasoning`과 `judgment.evidence`("정상참작: …")에 반영된다.
- POST/PUT `/api/expenses` 바디의 선택 필드. 두 입력 칸은 화면에서도 분리한다.

## 미분류 정리 건너뛰기 + 기타 논평
미분류가 20건씩 나오면 하나씩 메모를 다는 건 현실적이지 않다. 건너뛰기를 제공한다.

- `POST /api/expenses/skip-review?month=YYYY-MM` → `{"skipped": N, "month": "..."}`
  해당 월의 미분류를 전부 '기타'로 확정하고 needsReview를 내린다. month 없거나 형식 위반 시 400.
- 미분류 정리 화면에 **[건너뛰기]** 버튼을 두고 이 API를 부른다. 누르면 목록·분석을 새로 부른다.
- `GET /api/analysis` 응답의 **`remark`**: '기타' 비중이 30% 이상일 때만 채워지고, 아니면 **null**(영역 숨김).
```
"remark": {"ratio": 94.19, "amount": 360000, "count": 3,
           "level": "notice" | "severe",
           "message": "피고인은 이번 달 지출의 94%인 360,000원을 '기타'로 남겼습니다. …"}
```
- `message`를 그대로 띄운다. `level`이 severe면 강조 색을 써도 좋다.
- 판결문 **아래**, benchmark와 나란히 두면 자연스럽다.
- 설계 의도: 미분류를 **정리하면** 기타 비중이 내려가 논평이 사라지고, **건너뛰면** 논평이 붙는다.

## 공공데이터 비교 (benchmark)
MZ 리액션 **아래**에 붙는 근거 한 줄이다. `GET /api/analysis` 응답의 `benchmark`.

```
"benchmark": {
  "groupLabel": "전국 1인가구 평균",
  "source": "국가데이터처 「2025 통계로 보는 1인가구」 · 2024년 기준",
  "isEstimated": true,          // true면 화면에 "추정" 표기를 함께 띄울 것
  "category": "DELIVERY_DINING",
  "categoryLabel": "배달·외식",
  "userAmount": 178000,
  "averageAmount": 246000,
  "diffPercent": -27.6,
  "direction": "over" | "under" | "similar" | "unknown",
  "headline": "전국 1인가구 평균보다 배달·외식에 28% 적게 썼습니다.",
  "totalUserAmount": 246000, "totalAverageAmount": 1689000, "totalDiffPercent": -85.4
}
```
- **`headline`을 그대로 띄우면 된다.** 프론트에서 퍼센트를 다시 계산하지 말 것.
- **`benchmark`는 null일 수 있다**(그 달 지출 0건). null이면 이 영역을 통째로 숨긴다.
- `source`는 반드시 화면에 함께 표시한다. 공공데이터 인용이라 출처 표기가 필요하다.
- `direction`으로 색을 나눠도 좋다(over=경고색, under=긍정색).

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
