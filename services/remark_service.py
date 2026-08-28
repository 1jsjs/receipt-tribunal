"""기타 지출 논평 — '기타'가 많을 때 판결문 뒤에 붙는 한마디

미분류 정리를 건너뛰면 그 건들이 전부 '기타'로 들어간다. 기타가 커질수록
"돈이 어디로 갔는지 본인도 모른다"는 뜻이므로, 그만큼의 논평이 따라붙는다.

주의: 단정하지 않는다. 예금주 이름으로 찍힌 송금은 채무일 수도, 더치페이 정산일 수도,
용돈일 수도 있다. 재판 톤으로 '의심되나 증거 불충분'이라고 말하는 편이
사실에도 맞고 더 웃긴다.
"""

from constants import CATEGORY_OTHER

# 이 비중을 넘어야 논평이 붙는다 (금액 기준 %)
_NOTICE_THRESHOLD = 30.0
_SEVERE_THRESHOLD = 50.0


def build_remark(stats: dict) -> dict | None:
    """기타 비중이 높으면 논평을 만든다. 낮으면 None(화면에서 숨김).

    Parameters
    ----------
    stats : dict
        calculate_monthly_stats() 반환값

    Returns
    -------
    dict | None
        {"ratio", "amount", "count", "level", "message"}
    """
    if not stats.get("paymentCount"):
        return None

    other = next(
        (c for c in stats.get("categoryStats", []) if c["category"] == CATEGORY_OTHER),
        None,
    )
    if not other:
        return None

    ratio = other["percentage"]
    if ratio < _NOTICE_THRESHOLD:
        return None

    amount = other["amount"]
    count = other["count"]

    if ratio >= _SEVERE_THRESHOLD:
        level = "severe"
        message = (
            f"피고인은 이번 달 지출의 {ratio:.0f}%인 {amount:,}원을 '기타'로 남겼습니다. "
            f"사인 간 채무관계가 의심되나 증거 불충분입니다. "
            f"돈이 어디로 갔는지는 오직 피고인만 알고 있습니다."
        )
    else:
        level = "notice"
        message = (
            f"'기타' 지출이 {ratio:.0f}%({amount:,}원, {count}건)로 적지 않습니다. "
            f"본 재판부는 이 돈의 행방을 특정하지 못하였습니다. "
            f"다음 달에는 어디에 쓰는지 정도는 알고 쓰시기 바랍니다."
        )

    return {
        "ratio": ratio,
        "amount": amount,
        "count": count,
        "level": level,
        "message": message,
    }
