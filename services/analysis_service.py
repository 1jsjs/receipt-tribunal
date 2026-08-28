"""월간 통계 계산 — TASK-B009·B010 (docs/05 §11). EXPENSE만 대상, TRANSFER 제외."""

from db import get_connection, DEFAULT_DEFENDANT

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


def get_month_context(month: str) -> dict:
    """그 달의 피고인 이름과 미분류 건수를 구한다.

    피고인은 그 달에 가장 많이 기록된 이름을 쓴다 (업로드할 때 입력한 이름).
    조회 자체를 피고인으로 필터하지는 않는다 — 이름 한 글자가 달라 빈 화면이 뜨는
    사고를 막기 위함이다. 이름은 판결문에 표시하는 용도다.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT defendant, COUNT(*) AS c FROM expenses
                WHERE date LIKE ? || '%' AND defendant != ''
                GROUP BY defendant ORDER BY c DESC LIMIT 1""",
            (month + "-",),
        ).fetchone()
        needs_review = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE date LIKE ? || '%' AND needs_review = 1",
            (month + "-",),
        ).fetchone()[0]
    finally:
        conn.close()

    return {
        "defendant": row["defendant"] if row else DEFAULT_DEFENDANT,
        "needsReviewCount": needs_review,
    }
