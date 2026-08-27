"""소비 유형 판정(룰) + 판결문 템플릿 — TASK-B011·B012 (docs/05 §13·§14)

주의: 7번 균형 생존형은 조건식 없는 무조건 폴백이다.
"""

import random

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


# ═══════════════════════════════════════════════════════════════════════════════
# TASK-B012: 판결문 템플릿 + 조립 함수 (docs/05 §14)
# ═══════════════════════════════════════════════════════════════════════════════

# JudgmentTemplate 구조: { crimes[], verdicts[], sentences[], fallbackReasonings[] }
# 톤: 소비 습관에 대한 가벼운 놀림/위트. 개인공격·외모·건강 비하 금지.
# SMART_SOLO = 칭찬 톤(무혐의 계열), BALANCED = 증거 불충분 계열.

JUDGMENT_TEMPLATES: dict[str, dict] = {
    "TINY_OVERSPEND": {
        "crimes": [
            "티끌 낭비죄",
            "소액 결제 상습범",
            "편의점 카드 혹사죄",
        ],
        "verdicts": [
            "티끌 모아 태산이라더니, 진짜 태산을 만들었습니다.",
            "한 건 한 건은 작아 보여도 합치면 얘기가 달라집니다.",
            "카드 명세서가 스크롤을 멈추지 못하고 있습니다.",
        ],
        "sentences": [
            "다음 달은 하루 결제 2회 이하로 제한합니다.",
            "소액이라도 장바구니에 하루만 묵혀두십시오.",
            "일주일에 하루는 '무지출 데이'를 선고합니다.",
        ],
        "fallbackReasonings": [
            "소액 결제가 전체의 절반을 넘었습니다. 한 건당 금액은 작지만 누적되면 무시할 수 없는 규모입니다.",
            "결제 건수 대비 소액 비중이 높아 충동 소비 패턴이 의심됩니다. 티끌이 모여 통장을 위협하고 있습니다.",
            "빈번한 소액 결제가 확인되었습니다. 건당 부담은 적으나 월말 합산액은 상당합니다.",
        ],
    },
    "CONVENIENCE_KITCHEN": {
        "crimes": [
            "편의점 상습 출입죄",
            "냉장고 방임죄",
            "삼각김밥 중독 혐의",
        ],
        "verdicts": [
            "편의점이 아니라 거의 셰어하우스 부엌입니다.",
            "집에 냉장고가 있다는 사실을 기억하십시오.",
            "편의점 직원이 당신의 식단을 외우고 있습니다.",
        ],
        "sentences": [
            "이번 주는 편의점 출입을 주 3회로 제한합니다.",
            "최소 주 2회는 집에서 밥을 해 드십시오.",
            "편의점 대신 마트에서 장을 봐 보십시오.",
        ],
        "fallbackReasonings": [
            "편의점 결제 건수가 전 카테고리 중 압도적 1위입니다. 식사와 간식 대부분을 편의점에서 해결하고 있습니다.",
            "편의점 방문 횟수가 월 8회를 크게 넘었습니다. 편의점이 사실상 주방 역할을 대신하고 있습니다.",
            "편의점 이용 빈도가 비정상적으로 높습니다. 자취 생활의 편의를 넘어 의존 수준에 도달했습니다.",
        ],
    },
    "DELIVERY_APP": {
        "crimes": [
            "냉장고 유기죄",
            "주방 방치죄",
            "배달앱 상습 이용죄",
        ],
        "verdicts": [
            "냉장고는 가구가 아닙니다.",
            "주방이 울고 있습니다.",
            "당신의 식사는 현관 앞에서 완성되고 있습니다.",
        ],
        "sentences": [
            "다음 달 배달은 주 2회 이하로 제한합니다.",
            "최소 주 1회는 직접 장을 보십시오.",
            "이번 달에는 냉장고를 최소 3번 이용하십시오.",
        ],
        "fallbackReasonings": [
            "배달·외식 지출이 전체의 40%를 넘었습니다. 주방을 사용한 흔적이 보이지 않습니다.",
            "배달 비중이 지나치게 높습니다. 냉장고가 장식품으로 전락한 정황이 포착되었습니다.",
            "외식·배달 카테고리가 지출의 절대적 비중을 차지합니다. 자취방에 주방이 있는지 의문입니다.",
        ],
    },
    "SMALL_LUXURY": {
        "crimes": [
            "카페 과잉 출석죄",
            "소확행 과다 혐의",
            "디저트 상습 구매죄",
        ],
        "verdicts": [
            "커피 한 잔이 별거 아니긴 하죠. 그게 수십 잔이면 얘기가 다릅니다.",
            "소확행이 소확빈으로 바뀌고 있습니다.",
            "카페 스탬프는 다 모았지만 통장 잔고는 텅 비었습니다.",
        ],
        "sentences": [
            "이번 주는 카페 방문을 주 3회로 줄이십시오.",
            "텀블러를 들고 다니며 최소 절반은 집에서 내려 드십시오.",
            "디저트는 주 1회로 제한합니다.",
        ],
        "fallbackReasonings": [
            "카페·간식 지출 비율이 30%를 넘었습니다. 소소한 행복이 합산되면 소소하지 않습니다.",
            "카페와 디저트에 쓴 금액이 상당합니다. 한 잔의 여유가 통장의 위기로 이어지고 있습니다.",
            "카페·간식 카테고리 비중이 높습니다. 매일의 작은 사치가 월말에는 큰 부담이 됩니다.",
        ],
    },
    "HOBBY_SERIOUS": {
        "crimes": [
            "취향 과몰입죄",
            "통장 잔고 무시죄",
            "쇼핑 충동 상습범",
        ],
        "verdicts": [
            "취향은 존중합니다. 통장도 좀 존중해주세요.",
            "좋아하는 건 알겠는데, 지갑이 울고 있습니다.",
            "취미 생활에 진심인 건 좋지만 잔고도 진심으로 대해주세요.",
        ],
        "sentences": [
            "다음 달 쇼핑은 월 2회 이하로 자제하십시오.",
            "위시리스트에 3일 이상 묵힌 후에만 구매를 허가합니다.",
            "이번 달 취미 예산 상한선을 정해두십시오.",
        ],
        "fallbackReasonings": [
            "쇼핑·취미 지출이 전체의 30%를 넘었습니다. 취향에 진심인 만큼 지출도 진심입니다.",
            "쇼핑·취미 카테고리 비중이 높습니다. 좋아하는 것에 투자하는 건 좋지만 균형이 필요합니다.",
            "취미 관련 소비가 다른 생활비를 압박하고 있습니다. 즐거움의 대가가 통장 잔고입니다.",
        ],
    },
    "SMART_SOLO": {
        "crimes": [
            "무혐의 — 자취 모범생",
            "무혐의 — 알뜰 생활 달인",
            "무혐의 — 장보기의 정석",
        ],
        "verdicts": [
            "자취생의 정석을 보여주고 있습니다.",
            "냉장고와 좋은 관계를 유지하고 계십니다.",
            "마트 영수증이 빛나고 있습니다. 본 재판부는 감동했습니다.",
        ],
        "sentences": [
            "현재 생활 패턴을 유지하십시오. 본 재판부가 응원합니다.",
            "식재료 활용 능력이 인정됩니다. 계속 이대로 하십시오.",
            "알뜰한 소비 습관에 박수를 보냅니다. 형량 없음.",
        ],
        "fallbackReasonings": [
            "식재료·생필품 비율이 30%를 넘어 직접 요리하는 건강한 생활 패턴이 확인됩니다.",
            "마트와 식재료 지출이 높아 자취 생활을 야무지게 꾸려가고 있음이 입증됩니다.",
            "생필품·식재료 중심의 소비 구조입니다. 합리적 소비의 모범 사례로 판단됩니다.",
        ],
    },
    "BALANCED": {
        "crimes": [
            "증거 불충분 — 혐의 없음",
            "증거 불충분 — 무죄 추정",
            "증거 불충분 — 판단 유보",
        ],
        "verdicts": [
            "뚜렷한 소비 편향이 발견되지 않았습니다.",
            "통장이랑 사이좋게 지내고 있군요.",
            "어느 한쪽으로 치우치지 않는 균형 잡힌 소비입니다.",
        ],
        "sentences": [
            "특별한 형량 없이 석방합니다. 현 상태를 유지하십시오.",
            "무죄 석방. 다음 달에도 이 균형을 지켜주십시오.",
            "본 재판부는 추가 형량을 부과하지 않습니다.",
        ],
        "fallbackReasonings": [
            "특정 카테고리에 치우친 소비가 발견되지 않았습니다. 균형 잡힌 생활을 하고 있습니다.",
            "모든 카테고리의 비율이 고르게 분포되어 있습니다. 뚜렷한 과소비 패턴이 없습니다.",
            "지출 구조가 안정적입니다. 어느 한 곳에 과도하게 쏠리지 않는 건강한 소비입니다.",
        ],
    },
}


def _format_amount(amount: int) -> str:
    """금액을 '184,000원' 형식으로 포맷한다."""
    return f"{amount:,}원"


def _build_evidence(stats: dict, consumer_type_code: str) -> list[str]:
    """유형별로 관련 수치를 stats에서 뽑아 evidence 문자열 배열을 생성한다."""
    payment_count = stats.get("paymentCount", 0)
    small_payment_count = stats.get("smallPaymentCount", 0)
    total_expense = stats.get("totalExpense", 0)

    delivery = _get_category_stat(stats, "DELIVERY_DINING")
    convenience = _get_category_stat(stats, "CONVENIENCE_STORE")
    cafe = _get_category_stat(stats, "CAFE_SNACK")
    shopping = _get_category_stat(stats, "SHOPPING_HOBBY")
    groceries = _get_category_stat(stats, "GROCERIES")

    if consumer_type_code == "TINY_OVERSPEND":
        ratio = round(small_payment_count / payment_count * 100) if payment_count > 0 else 0
        return [
            f"소액(5,000원 이하) 결제 {small_payment_count}회",
            f"소액 비중 {ratio}%",
            f"총 결제 {payment_count}건",
        ]

    if consumer_type_code == "CONVENIENCE_KITCHEN":
        return [
            f"편의점 결제 {convenience['count']}회",
            f"편의점 지출 {_format_amount(convenience['amount'])}",
            f"전 카테고리 중 건수 1위",
        ]

    if consumer_type_code == "DELIVERY_APP":
        return [
            f"배달·외식 지출 {_format_amount(delivery['amount'])}",
            f"배달·외식 결제 {delivery['count']}회",
            f"배달·외식 비율 {delivery['percentage']}%",
        ]

    if consumer_type_code == "SMALL_LUXURY":
        return [
            f"카페·간식 지출 {_format_amount(cafe['amount'])}",
            f"카페·간식 비율 {cafe['percentage']}%",
            f"카페·간식 결제 {cafe['count']}회",
        ]

    if consumer_type_code == "HOBBY_SERIOUS":
        return [
            f"쇼핑·취미 지출 {_format_amount(shopping['amount'])}",
            f"쇼핑·취미 비율 {shopping['percentage']}%",
            f"쇼핑·취미 결제 {shopping['count']}회",
        ]

    if consumer_type_code == "SMART_SOLO":
        return [
            f"식재료·생필품 지출 {_format_amount(groceries['amount'])}",
            f"식재료·생필품 비율 {groceries['percentage']}%",
            f"총지출 {_format_amount(total_expense)}",
        ]

    # BALANCED
    return [
        f"총지출 {_format_amount(total_expense)}",
        f"총 결제 {payment_count}건",
    ]


def build_judgment(stats: dict, consumer_type: dict) -> dict:
    """판결문을 조립한다.

    Parameters
    ----------
    stats : dict
        calculate_monthly_stats() 반환값
    consumer_type : dict
        determine_consumer_type() 반환값 {"code": str, "label": str}

    Returns
    -------
    dict  {"crime", "evidence", "verdict", "reasoning", "sentence"} — docs/05 §12 judgment 형식
    """
    code = consumer_type["code"]
    template = JUDGMENT_TEMPLATES[code]

    crime = random.choice(template["crimes"])
    verdict = random.choice(template["verdicts"])
    sentence = random.choice(template["sentences"])
    reasoning = random.choice(template["fallbackReasonings"])

    evidence = _build_evidence(stats, code)

    return {
        "crime": crime,
        "evidence": evidence,
        "verdict": verdict,
        "reasoning": reasoning,
        "sentence": sentence,
    }
