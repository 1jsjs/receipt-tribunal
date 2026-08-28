"""expenses CRUD API — feat/crud 브랜치 담당 (TASK-B004~B008)

구현 기준: docs/05 §9(API)·§10(검증)·§4(필드명 계약 — camelCase 응답)
"""
import re
from datetime import datetime

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from db import get_connection, DEFAULT_DEFENDANT, DEFENDANT_MAX, MEMO_MAX, PLEA_MAX
from constants import CATEGORIES, TRANSACTION_TYPES

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

# 날짜 형식 검증: YYYY-MM-DD (docs/05 §10)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 월 형식 검증: YYYY-MM, 월은 01~12만 허용 (2026-13/2026-00 거부)
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    """공통 에러 응답 (docs/05 §9)"""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _row_to_expense(row) -> dict:
    """DB row(snake_case) → API 응답 Expense(camelCase) 변환.

    B005~B007에서 재사용하기 위한 헬퍼.
    """
    return {
        "id": row["id"],
        "storeName": row["store_name"],
        "date": row["date"],
        "amount": row["amount"],
        "category": row["category"],
        "transactionType": row["transaction_type"],
        "defendant": row["defendant"],
        "memo": row["memo"],
        # 피고인 변론 — 항변하면 판결문 이유·정상참작에 반영된다 (판결 쪽, 최대 200자).
        "plea": row["plea"] if "plea" in row.keys() else "",
        # 업로드 시 상호명 대신 예금주 이름만 있던 건. 사용자가 메모·카테고리를 채워야 한다.
        "needsReview": bool(row["needs_review"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _validate_expense_body(body: dict) -> tuple[dict | None, JSONResponse | None]:
    """요청 바디를 직접 검증한다 (docs/05 §10). Pydantic 미사용 — 위반 시 항상 400.

    Returns
    -------
    (검증된 값 dict, None)  성공 시
    (None, JSONResponse)     실패 시 (400 에러)
    """
    if not isinstance(body, dict):
        return None, _error("INVALID_BODY", "요청 바디는 JSON 객체여야 합니다.", 400)

    store_name = body.get("storeName")
    date = body.get("date")
    amount = body.get("amount")
    category = body.get("category")
    transaction_type = body.get("transactionType")

    # storeName: 문자열, 공백만 금지, strip 후 최대 100자, strip한 값을 저장
    if not isinstance(store_name, str) or store_name.strip() == "":
        return None, _error("INVALID_STORE_NAME", "storeName은 비어 있을 수 없습니다.", 400)
    store_name = store_name.strip()
    if len(store_name) > 100:
        return None, _error("INVALID_STORE_NAME", "storeName은 최대 100자입니다.", 400)

    # date: YYYY-MM-DD 형식 + 실재하는 날짜.
    # 형식만 보는 정규식 통과 후, strptime으로 실제 존재하는 날짜인지 검증
    # (2026-02-31, 2026-13-45 같은 유령 날짜 거부).
    # 파싱은 검증 용도로만 쓰고, 저장은 원래 문자열 그대로 한다 (UTC 하루 밀림 방지).
    if not isinstance(date, str) or not _DATE_RE.match(date):
        return None, _error("INVALID_DATE", "date는 YYYY-MM-DD 형식이어야 합니다.", 400)
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None, _error("INVALID_DATE", "date는 실재하는 날짜여야 합니다.", 400)

    # amount: 정수, 1 이상 (bool은 int의 서브클래스이므로 배제)
    if isinstance(amount, bool) or not isinstance(amount, int):
        return None, _error("INVALID_AMOUNT", "amount는 정수여야 합니다.", 400)
    if amount < 1:
        return None, _error("INVALID_AMOUNT", "amount는 1 이상이어야 합니다.", 400)

    # category: 6종 코드 외 거부
    if category not in CATEGORIES:
        return None, _error("INVALID_CATEGORY", "category가 유효하지 않습니다.", 400)

    # transactionType: EXPENSE·TRANSFER 외 거부
    if transaction_type not in TRANSACTION_TYPES:
        return None, _error("INVALID_TRANSACTION_TYPE", "transactionType이 유효하지 않습니다.", 400)

    # defendant(피고인 이름): 선택 항목. 안 보내면 기본 피고인으로 채운다.
    defendant = body.get("defendant")
    if defendant is None or (isinstance(defendant, str) and defendant.strip() == ""):
        defendant = DEFAULT_DEFENDANT
    elif not isinstance(defendant, str):
        return None, _error("INVALID_DEFENDANT", "defendant는 문자열이어야 합니다.", 400)
    else:
        # 말없이 자르지 않는다. 넘치면 사용자에게 알린다.
        defendant = defendant.strip()
        if len(defendant) > DEFENDANT_MAX:
            return None, _error(
                "INVALID_DEFENDANT", f"피고인 이름은 최대 {DEFENDANT_MAX}자입니다.", 400
            )

    # memo(미분류 내역 메모): 선택 항목, 10자 이내
    memo = body.get("memo")
    if memo is None:
        memo = ""
    elif not isinstance(memo, str):
        return None, _error("INVALID_MEMO", "memo는 문자열이어야 합니다.", 400)
    else:
        memo = memo.strip()
        if len(memo) > MEMO_MAX:
            return None, _error("INVALID_MEMO", f"memo는 최대 {MEMO_MAX}자입니다.", 400)

    # plea(피고인 변론): 선택 항목, 200자 이내. 판결문 이유·정상참작(N빵 등) 근거로 쓰인다.
    plea = body.get("plea")
    if plea is None:
        plea = ""
    elif not isinstance(plea, str):
        return None, _error("INVALID_PLEA", "plea는 문자열이어야 합니다.", 400)
    else:
        plea = plea.strip()
        if len(plea) > PLEA_MAX:
            return None, _error("INVALID_PLEA", f"plea는 최대 {PLEA_MAX}자입니다.", 400)

    return {
        "store_name": store_name,
        "date": date,
        "amount": amount,
        "category": category,
        "transaction_type": transaction_type,
        "defendant": defendant,
        "memo": memo,
        "plea": plea,
    }, None


@router.post("")
def create_expense(body=Body(None)):
    """POST /api/expenses — 소비 저장 후 생성된 Expense 반환 (docs/05 §9)

    타입 어노테이션(: dict)을 붙이지 않는다. 붙이면 FastAPI가 핸들러 진입 전에
    자체 검증을 수행해 실패 시 422 기본 응답을 내므로, 계약서상 400 + 공통 에러
    형식을 보장할 수 없다. Body(None)으로 받아 파싱만 하고, 검증은 전부 아래 코드가 한다.
    """
    validated, error = _validate_expense_body(body)
    if error is not None:
        return error

    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO expenses
                 (store_name, date, amount, category, transaction_type,
                  defendant, memo, plea, needs_review, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))""",
            (
                validated["store_name"],
                validated["date"],
                validated["amount"],
                validated["category"],
                validated["transaction_type"],
                validated["defendant"],
                validated["memo"],
                validated["plea"],
            ),
        )
        conn.commit()
        new_id = cursor.lastrowid

        # 생성된 행을 다시 조회해 created_at/updated_at 포함 완전한 Expense 반환
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()

    return JSONResponse(
        status_code=201,
        content={"success": True, "data": _row_to_expense(row)},
    )


@router.get("")
def list_expenses(month=Query(None)):
    """GET /api/expenses?month=YYYY-MM — 해당 월 Expense 배열 반환 (docs/05 §9)

    month는 Query(None)으로 받아 직접 검증한다 (Query(...)로 필수 지정하면 422가 나감).
    TRANSFER도 포함해 반환한다 (목록에는 이체도 표시, 분석에서만 제외).
    """
    # month 형식 검증 (실재하는 월만 허용)
    if not isinstance(month, str) or not _MONTH_RE.match(month):
        return _error("INVALID_MONTH", "month는 YYYY-MM 형식이어야 합니다.", 400)

    conn = get_connection()
    try:
        # 월 필터는 문자열 앞 7자리 비교 (datetime 파싱 금지 — UTC로 하루 밀림 방지)
        # 정렬: 날짜 내림차순, 같은 날짜면 최근 입력(id 큰 것)이 위로
        rows = conn.execute(
            """SELECT * FROM expenses
               WHERE substr(date, 1, 7) = ?
               ORDER BY date DESC, id DESC""",
            (month,),
        ).fetchall()
    finally:
        conn.close()

    data = [_row_to_expense(row) for row in rows]
    return {"success": True, "data": data}


def _parse_id(raw_id: str) -> tuple[int | None, JSONResponse | None]:
    """경로 변수 id를 정수로 변환한다. 실패 시 400 (FastAPI 422 함정 회피).

    expense_id: int로 받으면 정수가 아닌 값에 FastAPI가 422를 내므로,
    문자열로 받아 여기서 직접 변환한다.
    """
    try:
        return int(raw_id), None
    except (ValueError, TypeError):
        return None, _error("INVALID_ID", "id는 정수여야 합니다.", 400)


# ─── 경로 변수 라우트 (@router.get("") 뒤에 등록 — 고정 경로가 먼저 매칭되도록) ───

@router.get("/{expense_id}")
def get_expense(expense_id: str):
    """GET /api/expenses/{id} — 단건 조회. 없으면 404. (docs/05 §9)"""
    parsed_id, error = _parse_id(expense_id)
    if error is not None:
        return error

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (parsed_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return _error("NOT_FOUND", "해당 id의 소비 내역이 없습니다.", 404)

    return {"success": True, "data": _row_to_expense(row)}


@router.put("/{expense_id}")
def update_expense(expense_id: str, body=Body(None)):
    """PUT /api/expenses/{id} — 수정 후 수정된 Expense 반환. (docs/05 §9)

    요청 바디는 POST와 동일. created_at은 건드리지 않고 updated_at만 갱신한다.
    대상 없으면 404, 바디 검증 실패면 400.
    """
    parsed_id, error = _parse_id(expense_id)
    if error is not None:
        return error

    # 바디 검증 (B004 헬퍼 재사용)
    validated, error = _validate_expense_body(body)
    if error is not None:
        return error

    conn = get_connection()
    try:
        # 대상 존재 확인
        existing = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (parsed_id,)
        ).fetchone()
        if existing is None:
            return _error("NOT_FOUND", "해당 id의 소비 내역이 없습니다.", 404)

        # updated_at만 갱신, created_at은 손대지 않음
        conn.execute(
            """UPDATE expenses
               SET store_name = ?, date = ?, amount = ?, category = ?,
                   transaction_type = ?, defendant = ?, memo = ?, plea = ?,
                   needs_review = 0, updated_at = datetime('now')
               WHERE id = ?""",
            (
                validated["store_name"],
                validated["date"],
                validated["amount"],
                validated["category"],
                validated["transaction_type"],
                validated["defendant"],
                validated["memo"],
                validated["plea"],
                parsed_id,
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (parsed_id,)
        ).fetchone()
    finally:
        conn.close()

    return {"success": True, "data": _row_to_expense(row)}


@router.delete("/{expense_id}")
def delete_expense(expense_id: str):
    """DELETE /api/expenses/{id} — 삭제 후 {"success": true} 반환. (docs/05 §9)

    대상 없으면 404. SQL DELETE는 대상이 없어도 에러를 안 내므로,
    반드시 먼저 SELECT로 존재를 확인한 뒤 삭제한다.
    """
    parsed_id, error = _parse_id(expense_id)
    if error is not None:
        return error

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (parsed_id,)
        ).fetchone()
        if existing is None:
            return _error("NOT_FOUND", "해당 id의 소비 내역이 없습니다.", 404)

        conn.execute("DELETE FROM expenses WHERE id = ?", (parsed_id,))
        conn.commit()
    finally:
        conn.close()

    # 204가 아니라 200 + {"success": true} (data 키 없음, 명세 그대로)
    return {"success": True}
