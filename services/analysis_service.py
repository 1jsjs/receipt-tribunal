"""월간 통계 계산 — TASK-B009·B010 (docs/05 §11). EXPENSE만 대상, TRANSFER 제외."""

from db import get_connection

# 카테고리 코드 → 화면 라벨 (docs/05 §7)
CATEGORY_LABELS: dict[str, str] = {
    "DELIVERY_DINING": "배달·외식",
    "CONVENIENCE_STORE": "편의점",
    "CAFE_SNACK": "카페·간식",
    "GROCERIES": "식재료·생필품",
    "SHOPPING_HOBBY": "쇼핑·취미",
    "OTHER": "기타",
}

# topCategory 동률 시 우선순위 (docs/05 §11)
CATEGORY_PRIORITY: list[str] = [
    "DELIVERY_DINING",
    "CONVENIENCE_STORE",
    "CAFE_SNACK",
    "GROCERIES",
    "SHOPPING_HOBBY",
    "OTHER",
]

# 소액 결제 기준 (docs/05 §11)
SMALL_PAYMENT_THRESHOLD = 5000


def calculate_monthly_stats(month: str) -> dict:
    """월간 통계를 계산해 docs/05 §12 data 부분(통계 필드만) 딕셔너리로 반환.

    Parameters
    ----------
    month : str
        "YYYY-MM" 형식 문자열

    Returns
    -------
    dict with keys: month, totalExpense, paymentCount, averagePaymentAmount,
    smallPaymentCount, largestSingleExpense, topCategory, categoryStats
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT store_name, date, amount, category
            FROM expenses
            WHERE transaction_type = 'EXPENSE'
              AND date LIKE ? || '%'
            """,
            (month + "-",),
        ).fetchall()
    finally:
        conn.close()

    # --- 기본 통계 ---
    total_expense = 0
    payment_count = len(rows)
    small_payment_count = 0
    largest_row = None  # (amount, store_name, date, category)

    # 카테고리별 집계
    cat_amount: dict[str, int] = {c: 0 for c in CATEGORY_PRIORITY}
    cat_count: dict[str, int] = {c: 0 for c in CATEGORY_PRIORITY}

    for row in rows:
        amt = row["amount"]
        cat = row["category"]

        total_expense += amt

        if amt <= SMALL_PAYMENT_THRESHOLD:
            small_payment_count += 1

        # 최대 단일 지출 (동일 금액이면 먼저 나온 것 유지 — 순서 무관, 하나만 반환)
        if largest_row is None or amt > largest_row["amount"]:
            largest_row = row

        # 카테고리 집계
        if cat in cat_amount:
            cat_amount[cat] += amt
            cat_count[cat] += 1

    # --- 평균 ---
    average_payment_amount = (
        round(total_expense / payment_count) if payment_count > 0 else 0
    )

    # --- categoryStats (6종 모두 포함) ---
    category_stats: list[dict] = []
    for cat in CATEGORY_PRIORITY:
        amt = cat_amount[cat]
        cnt = cat_count[cat]
        pct = round(amt / total_expense * 100, 2) if total_expense > 0 else 0.0
        category_stats.append(
            {
                "category": cat,
                "label": CATEGORY_LABELS[cat],
                "amount": amt,
                "percentage": pct,
                "count": cnt,
            }
        )

    # --- topCategory: 금액 최대 → 동률 시 건수 최대 → 그래도 동률이면 CATEGORY_PRIORITY 순서 ---
    top_category = None
    if payment_count > 0:
        # 정렬 기준: (-amount, -count, priority_index)
        top_entry = min(
            category_stats,
            key=lambda s: (-s["amount"], -s["count"], CATEGORY_PRIORITY.index(s["category"])),
        )
        top_category = {
            "category": top_entry["category"],
            "label": top_entry["label"],
            "amount": top_entry["amount"],
            "percentage": top_entry["percentage"],
            "count": top_entry["count"],
        }

    # --- largestSingleExpense ---
    largest_single_expense = None
    if largest_row is not None:
        largest_single_expense = {
            "amount": largest_row["amount"],
            "storeName": largest_row["store_name"],
            "date": largest_row["date"],
            "category": largest_row["category"],
        }

    return {
        "month": month,
        "totalExpense": total_expense,
        "paymentCount": payment_count,
        "averagePaymentAmount": average_payment_amount,
        "smallPaymentCount": small_payment_count,
        "largestSingleExpense": largest_single_expense,
        "topCategory": top_category,
        "categoryStats": category_stats,
    }


def fetch_month_expenses(month: str) -> list[dict]:
    """해당 월의 EXPENSE 행 원본을 반환한다 (TRANSFER 제외).

    판결문 생성 시 개별 거래의 memo(N빵·더치페이 등)를 참고하는 용도.
    memo 컬럼이 없는 구버전 DB에서도 죽지 않도록 방어적으로 조회한다.

    Returns
    -------
    list[dict]  [{"storeName", "date", "amount", "category", "memo"}, ...]
    """
    conn = get_connection()
    try:
        has_memo = any(
            r["name"] == "memo" for r in conn.execute("PRAGMA table_info(expenses)")
        )
        memo_col = "memo" if has_memo else "'' AS memo"
        rows = conn.execute(
            f"""
            SELECT store_name, date, amount, category, {memo_col}
            FROM expenses
            WHERE transaction_type = 'EXPENSE'
              AND date LIKE ? || '%'
            ORDER BY date ASC, id ASC
            """,
            (month + "-",),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "storeName": r["store_name"],
            "date": r["date"],
            "amount": r["amount"],
            "category": r["category"],
            "memo": r["memo"] or "",
        }
        for r in rows
    ]
