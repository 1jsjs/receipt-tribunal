"""expenses CRUD API — TASK-B004~B008

구현 기준: docs/05 §9(API)·§10(검증)·§4(필드명 계약 — camelCase 응답)
상수는 constants.py(TASK-B003)를 단일 출처로 사용한다.

주의: Pydantic 모델을 쓰지 않고 raw body를 직접 검증한다.
      (Pydantic은 타입 위반 시 422를 내는데, 계약서상 검증 실패는 항상 400이어야 함)
"""
import re
from datetime import datetime

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from constants import CATEGORIES, TRANSACTION_TYPES
from db import get_connection

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

# 형식 검증 정규식 (docs/05 §5 날짜 규칙)
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

STORE_NAME_MAX = 100  # docs/05 §10


# ─────────────────────────── 공통 헬퍼 ───────────────────────────
def _error(status: int, code: str, message: str) -> JSONResponse:
    """공통 에러 응답 (docs/05 §9) — 검증 실패는 전부 400으로 통일"""
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _to_expense(row) -> dict:
    """DB row(snake_case) → 응답 Expense(camelCase). RULE 002 필드명 계약."""
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


def _validate(body) -> tuple[dict | None, JSONResponse | None]:
    """docs/05 §10 입력 검증. 통과 시 (정제된 값, None), 실패 시 (None, 400 응답)."""
    if not isinstance(body, dict):
        return None, _error(400, "VALIDATION_ERROR", "요청 본문은 JSON 객체여야 합니다.")

    # storeName — 빈 문자열·공백만 금지, 최대 100자
    store_name = body.get("storeName")
    if not isinstance(store_name, str) or not store_name.strip():
        return None, _error(400, "VALIDATION_ERROR", "storeName은 비어 있을 수 없습니다.")
    store_name = store_name.strip()
    if len(store_name) > STORE_NAME_MAX:
        return None, _error(400, "VALIDATION_ERROR", f"storeName은 최대 {STORE_NAME_MAX}자입니다.")

    # date — YYYY-MM-DD 형식 + 실재하는 날짜 (2026-02-31 같은 값 차단)
    date_value = body.get("date")
    if not isinstance(date_value, str) or not _DATE_RE.match(date_value):
        return None, _error(400, "VALIDATION_ERROR", "date는 YYYY-MM-DD 형식이어야 합니다.")
    try:
        datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return None, _error(400, "VALIDATION_ERROR", "존재하지 않는 날짜입니다.")

    # amount — 정수, 1 이상 (bool은 int로 취급되므로 명시적으로 제외)
    amount = body.get("amount")
    if isinstance(amount, bool):
        return None, _error(400, "VALIDATION_ERROR", "amount는 정수여야 합니다.")
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)  # 18000.0 같은 값은 허용해 정수로 정규화
    if not isinstance(amount, int):
        return None, _error(400, "VALIDATION_ERROR", "amount는 정수여야 합니다.")
    if amount < 1:
        return None, _error(400, "VALIDATION_ERROR", "amount는 1 이상이어야 합니다.")

    # category — 6종 코드만
    category = body.get("category")
    if category not in CATEGORIES:
        return None, _error(400, "VALIDATION_ERROR", f"category는 {', '.join(CATEGORIES)} 중 하나여야 합니다.")

    # transactionType — EXPENSE·TRANSFER만
    transaction_type = body.get("transactionType")
    if transaction_type not in TRANSACTION_TYPES:
        return None, _error(400, "VALIDATION_ERROR", "transactionType은 EXPENSE 또는 TRANSFER여야 합니다.")

    return {
        "storeName": store_name,
        "date": date_value,
        "amount": amount,
        "category": category,
        "transactionType": transaction_type,
    }, None


def _fetch_one(conn, expense_id: int):
    return conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()


# ─────────────────────── TASK-B004 저장 ───────────────────────
@router.post("")
def create_expense(body=Body(...)):
    """POST /api/expenses — 저장 후 생성된 Expense 반환"""
    data, err = _validate(body)
    if err:
        return err

    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO expenses (store_name, date, amount, category, transaction_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (data["storeName"], data["date"], data["amount"], data["category"], data["transactionType"]),
        )
        conn.commit()
        row = _fetch_one(conn, cur.lastrowid)
    finally:
        conn.close()

    return JSONResponse(status_code=201, content={"success": True, "data": _to_expense(row)})


# ──────────────────── TASK-B005 월별 조회 ────────────────────
@router.get("")
def list_expenses(month: str | None = Query(None, description="조회 월 (YYYY-MM)")):
    """GET /api/expenses?month=YYYY-MM — 날짜 내림차순 (동일 날짜는 최근 입력 순)"""
    # month를 필수(...)로 두면 FastAPI가 422를 내보내 공통 에러 형식이 깨진다 → 직접 검증해 400 통일
    if not month or not _MONTH_RE.match(month):
        return _error(400, "INVALID_MONTH", "month는 YYYY-MM 형식이어야 합니다.")

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE substr(date, 1, 7) = ? ORDER BY date DESC, id DESC",
            (month,),
        ).fetchall()
    finally:
        conn.close()

    return {"success": True, "data": [_to_expense(r) for r in rows]}


# ───────────────────── 단건 조회 (docs/02 #3) ─────────────────────
@router.get("/{expense_id}")
def get_expense(expense_id: int):
    """GET /api/expenses/{id} — 없으면 404"""
    conn = get_connection()
    try:
        row = _fetch_one(conn, expense_id)
    finally:
        conn.close()

    if row is None:
        return _error(404, "NOT_FOUND", "해당 소비 내역을 찾을 수 없습니다.")
    return {"success": True, "data": _to_expense(row)}


# ─────────────────────── TASK-B006 수정 ───────────────────────
@router.put("/{expense_id}")
def update_expense(expense_id: int, body=Body(...)):
    """PUT /api/expenses/{id} — 요청 형식은 POST와 동일, 수정된 Expense 반환"""
    data, err = _validate(body)
    if err:
        return err

    conn = get_connection()
    try:
        if _fetch_one(conn, expense_id) is None:
            return _error(404, "NOT_FOUND", "해당 소비 내역을 찾을 수 없습니다.")

        conn.execute(
            """UPDATE expenses
                  SET store_name = ?, date = ?, amount = ?, category = ?,
                      transaction_type = ?, updated_at = datetime('now')
                WHERE id = ?""",
            (data["storeName"], data["date"], data["amount"], data["category"],
             data["transactionType"], expense_id),
        )
        conn.commit()
        row = _fetch_one(conn, expense_id)
    finally:
        conn.close()

    return {"success": True, "data": _to_expense(row)}


# ─────────────────────── TASK-B007 삭제 ───────────────────────
@router.delete("/{expense_id}")
def delete_expense(expense_id: int):
    """DELETE /api/expenses/{id} — 성공 시 {"success": true}"""
    conn = get_connection()
    try:
        if _fetch_one(conn, expense_id) is None:
            return _error(404, "NOT_FOUND", "해당 소비 내역을 찾을 수 없습니다.")
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
    finally:
        conn.close()

    return {"success": True}
