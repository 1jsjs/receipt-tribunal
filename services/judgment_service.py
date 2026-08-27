"""소비 유형 판정(룰) + 판결문 템플릿 — TASK-B011·B012 (docs/05 §13·§14)

주의: 7번 균형 생존형은 조건식 없는 무조건 폴백이다.
"""

# ─── 소비 유형 코드 상수 (프론트와 공유 — docs/05 §12 consumerType.code) ───
# TINY_OVERSPEND   : 티끌 과소비형
# CONVENIENCE_KITCHEN : 편의점이 내 부엌형
# DELIVERY_APP     : 냉장고보다 배달앱형
# SMALL_LUXURY     : 소확행 충전형
# HOBBY_SERIOUS    : 취향에 진심형
# SMART_SOLO       : 야무진 자취생형
# BALANCED         : 균형 생존형

CONSUMER_TYPES: dict[str, str] = {
    "TINY_OVERSPEND": "티끌 과소비형",
    "CONVENIENCE_KITCHEN": "편의점이 내 부엌형",
    "DELIVERY_APP": "냉장고보다 배달앱형",
    "SMALL_LUXURY": "소확행 충전형",
    "HOBBY_SERIOUS": "취향에 진심형",
    "SMART_SOLO": "야무진 자취생형",
    "BALANCED": "균형 생존형",
}


def _get_category_stat(stats: dict, category_code: str) -> dict:
    """categoryStats 리스트에서 특정 카테고리의 stat dict를 꺼낸다."""
    for s in stats.get("categoryStats", []):
        if s["category"] == category_code:
            return s
    return {"amount": 0, "count": 0, "percentage": 0.0}


def determine_consumer_type(stats: dict) -> dict:
    """calculate_monthly_stats 결과를 받아 소비 유형을 판정한다.

    Parameters
    ----------
    stats : dict
        services.analysis_service.calculate_monthly_stats()의 반환값

    Returns
    -------
    dict  {"code": str, "label": str}  — docs/05 §12 consumerType 형식
    """
    payment_count: int = stats.get("paymentCount", 0)
    small_payment_count: int = stats.get("smallPaymentCount", 0)

    # 카테고리별 통계 꺼내기
    delivery = _get_category_stat(stats, "DELIVERY_DINING")
    convenience = _get_category_stat(stats, "CONVENIENCE_STORE")
    cafe = _get_category_stat(stats, "CAFE_SNACK")
    shopping = _get_category_stat(stats, "SHOPPING_HOBBY")
    groceries = _get_category_stat(stats, "GROCERIES")

    # 비율(percentage) 값
    delivery_pct: float = delivery["percentage"]
    cafe_pct: float = cafe["percentage"]
    shopping_pct: float = shopping["percentage"]
    groceries_pct: float = groceries["percentage"]

    # ─── 우선순위 1~6 순서대로 첫 매칭 채택 ───

    # 1. 티끌 과소비형: 결제 >= 10회 AND 소액비중 >= 50%
    if payment_count >= 10:
        small_ratio = small_payment_count / payment_count
        if small_ratio >= 0.5:
            return {"code": "TINY_OVERSPEND", "label": CONSUMER_TYPES["TINY_OVERSPEND"]}

    # 2. 편의점이 내 부엌형: 편의점 건수 >= 8 AND 전 카테고리 중 건수 1위
    if convenience["count"] >= 8:
        # 건수 1위 판정: 다른 모든 카테고리보다 건수가 크거나 같아야 함
        all_counts = [s["count"] for s in stats.get("categoryStats", [])]
        max_count = max(all_counts) if all_counts else 0
        if convenience["count"] == max_count:
            return {"code": "CONVENIENCE_KITCHEN", "label": CONSUMER_TYPES["CONVENIENCE_KITCHEN"]}

    # 3. 냉장고보다 배달앱형: 배달·외식 비율 >= 40%
    if delivery_pct >= 40:
        return {"code": "DELIVERY_APP", "label": CONSUMER_TYPES["DELIVERY_APP"]}

    # 4. 소확행 충전형: 카페·간식 비율 >= 30% AND 배달·외식 < 40%
    if cafe_pct >= 30 and delivery_pct < 40:
        return {"code": "SMALL_LUXURY", "label": CONSUMER_TYPES["SMALL_LUXURY"]}

    # 5. 취향에 진심형: 쇼핑·취미 비율 >= 30%
    if shopping_pct >= 30:
        return {"code": "HOBBY_SERIOUS", "label": CONSUMER_TYPES["HOBBY_SERIOUS"]}

    # 6. 야무진 자취생형: 식재료·생필품 비율 >= 30%
    if groceries_pct >= 30:
        return {"code": "SMART_SOLO", "label": CONSUMER_TYPES["SMART_SOLO"]}

    # 7. 균형 생존형: 무조건 폴백 (조건식 없음)
    return {"code": "BALANCED", "label": CONSUMER_TYPES["BALANCED"]}
