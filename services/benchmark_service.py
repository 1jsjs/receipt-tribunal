"""공공데이터 기준 소비 비교 — "평균보다 얼마나 더 썼나"

MZ 리액션 아래에 붙는 한 줄짜리 근거다. 룰 기반이며 LLM을 쓰지 않는다.
기준값과 출처는 data/benchmark_data.py 한 곳에서만 관리한다.
"""

from data.benchmark_data import (
    BENCHMARK,
    GROUP_LABEL,
    IS_ESTIMATED,
    SOURCE,
    TOTAL_MONTHLY,
)

# 평균과 이 비율 이내면 "비슷하다"로 본다 (±10%)
_SIMILAR_THRESHOLD = 10.0


def _diff_percent(user_amount: int, average: int) -> float | None:
    """평균 대비 몇 % 차이인지. 기준값이 0이면 비교 불가(None)."""
    if not average:
        return None
    return round((user_amount - average) / average * 100, 1)


def _direction(diff: float | None) -> str:
    """over(더 씀) / under(덜 씀) / similar(비슷) / unknown"""
    if diff is None:
        return "unknown"
    if diff > _SIMILAR_THRESHOLD:
        return "over"
    if diff < -_SIMILAR_THRESHOLD:
        return "under"
    return "similar"


def _headline(category_label: str, diff: float | None, direction: str) -> str:
    """재판 톤 한 줄. 프론트는 이걸 그대로 띄우면 된다."""
    if direction == "unknown":
        return f"{GROUP_LABEL}과 비교할 기준값이 없습니다."
    magnitude = abs(diff)
    if direction == "over":
        # 2배를 넘으면 배수로 말하는 편이 체감이 크다
        if magnitude >= 100:
            times = round((100 + diff) / 100, 1)
            return f"{GROUP_LABEL}의 {times}배를 {category_label}에 썼습니다."
        return f"{GROUP_LABEL}보다 {category_label}에 {magnitude:.0f}% 더 썼습니다."
    if direction == "under":
        return f"{GROUP_LABEL}보다 {category_label}에 {magnitude:.0f}% 적게 썼습니다."
    return f"{GROUP_LABEL}과 {category_label} 지출이 비슷합니다."


def build_benchmark(stats: dict) -> dict | None:
    """상위 카테고리와 총지출을 공공데이터 평균과 비교한다.

    Parameters
    ----------
    stats : dict
        calculate_monthly_stats() 반환값

    Returns
    -------
    dict | None
        비교할 데이터가 없으면(그 달 지출 0건) None
    """
    top = stats.get("topCategory")
    if not top or not stats.get("paymentCount"):
        return None

    category = top["category"]
    user_amount = top["amount"]
    average = BENCHMARK.get(category, 0)
    diff = _diff_percent(user_amount, average)
    direction = _direction(diff)

    total_user = stats.get("totalExpense", 0)
    total_diff = _diff_percent(total_user, TOTAL_MONTHLY)

    return {
        "groupLabel": GROUP_LABEL,
        "source": SOURCE,
        # 통계 비목을 우리 카테고리에 배분한 추정치인지 여부.
        # true면 화면에 "추정" 표기를 함께 띄운다.
        "isEstimated": IS_ESTIMATED,
        "category": category,
        "categoryLabel": top["label"],
        "userAmount": user_amount,
        "averageAmount": average,
        "diffPercent": diff,
        "direction": direction,
        "headline": _headline(top["label"], diff, direction),
        "totalUserAmount": total_user,
        "totalAverageAmount": TOTAL_MONTHLY,
        "totalDiffPercent": total_diff,
    }
