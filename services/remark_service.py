"""행방불명 지출 논평 — '이 돈 어디 갔는지 모르겠다'가 많을 때 붙는 한마디

무엇을 세는가:
  그 달 소비+이체(INCOME 제외) 중 **카테고리가 OTHER인 금액**.
  수입(용돈·급여)은 '행방불명 지출'이 아니므로 세지 않는다.
  상호명 대신 예금주 이름만 찍힌 송금이 여기 들어온다. 미분류 정리를 건너뛰면 더 커진다.

왜 이체까지 세는가:
  사람 이름 송금은 Bedrock이 TRANSFER로 분류해 분석(총지출·유형 판정)에서 빠진다.
  그래서 소비 카테고리만 보면 이 돈이 통째로 안 보인다. 정작 "돈이 어디로 갔는지
  모르겠다"의 본체가 이쪽이므로, 논평만큼은 이체를 포함해 계산한다.
  (총지출·유형 판정은 기존대로 EXPENSE만 쓴다 — 여기서 바꾸지 않는다)

주의: 단정하지 않는다. 예금주 송금은 채무일 수도, 더치페이 정산일 수도, 용돈일 수도 있다.
재판 톤으로 '의심되나 증거 불충분'이라고 말하는 편이 사실에도 맞고 더 웃긴다.
"""

from constants import CATEGORY_OTHER
from db import get_connection

# 이 비중을 넘어야 논평이 붙는다 (그 달 전체 거래 금액 대비 %)
_NOTICE_THRESHOLD = 30.0
_SEVERE_THRESHOLD = 50.0


def _collect(month: str) -> dict | None:
    """그 달의 전체 거래 금액과, 그중 정체를 모르는(OTHER) 금액을 센다."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                 COALESCE(SUM(amount), 0) AS total,
                 COALESCE(SUM(CASE WHEN category = ? THEN amount ELSE 0 END), 0) AS unknown_amount,
                 COALESCE(SUM(CASE WHEN category = ? THEN 1 ELSE 0 END), 0) AS unknown_count
               FROM expenses
               WHERE substr(date, 1, 7) = ? AND transaction_type != 'INCOME'""",
            (CATEGORY_OTHER, CATEGORY_OTHER, month),
        ).fetchone()
    finally:
        conn.close()

    if not row or not row["total"]:
        return None
    return {
        "total": row["total"],
        "amount": row["unknown_amount"],
        "count": row["unknown_count"],
    }


def build_remark(month: str) -> dict | None:
    """행방불명 금액이 많으면 논평을 만든다. 적으면 None(화면에서 숨김).

    Returns
    -------
    dict | None  {"ratio", "amount", "count", "level", "message"}
    """
    data = _collect(month)
    if not data or not data["amount"]:
        return None

    ratio = round(data["amount"] / data["total"] * 100, 1)
    if ratio < _NOTICE_THRESHOLD:
        return None

    amount, count = data["amount"], data["count"]

    if ratio >= _SEVERE_THRESHOLD:
        level = "severe"
        message = (
            f"피고인은 이번 달 거래의 {ratio:.0f}%인 {amount:,}원을 정체 불명으로 남겼습니다. "
            f"사인 간 채무관계가 의심되나 증거 불충분입니다. "
            f"돈이 어디로 갔는지는 오직 피고인만 알고 있습니다."
        )
    else:
        level = "notice"
        message = (
            f"용처를 알 수 없는 거래가 {ratio:.0f}%({amount:,}원, {count}건)로 적지 않습니다. "
            f"본 재판부는 이 돈의 행방을 특정하지 못하였습니다. "
            f"다음 달에는 어디에 쓰는지 정도는 알고 쓰시기 바랍니다."
        )

    return {"ratio": ratio, "amount": amount, "count": count,
            "level": level, "message": message}
