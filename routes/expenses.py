"""expenses CRUD API — feat/crud 브랜치 담당 (TASK-B004~B008)

구현 기준: docs/05 §9(API)·§10(검증)·§4(필드명 계약 — camelCase 응답)
"""
import re

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from db import get_connection
from constants import CATEGORIES, TRANSACTION_TYPES

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

# 날짜 형식 검증: YYYY-MM-DD (docs/05 §10)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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

    # storeName: 문자열, 공백만 금지, 최대 100자
    if not isinstance(store_name, str) or store_name.strip() == "":
        return None, _error("INVALID_STORE_NAME", "storeName은 비어 있을 수 없습니다.", 400)
    if len(store_name) > 100:
        return None, _error("INVALID_STORE_NAME", "storeName은 최대 100자입니다.", 400)

    # date: YYYY-MM-DD 형식 (문자열 그대로 사용, datetime 변환 안 함)
    if not isinstance(date, str) or not _DATE_RE.match(date):
        return None, _error("INVALID_DATE", "date는 YYYY-MM-DD 형식이어야 합니다.", 400)

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

    return {
        "store_name": store_name,
        "date": date,
        "amount": amount,
        "category": category,
        "transaction_type": transaction_type,
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
                 (store_name, date, amount, category, transaction_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (
                validated["store_name"],
                validated["date"],
                validated["amount"],
                validated["category"],
                validated["transaction_type"],
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
