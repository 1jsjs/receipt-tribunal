"""배포 서버에서 실제 Bedrock 호출이 살아 있는지 + 출력이 쓸 만한지 눈으로 확인.

로컬에서는 의미 없다 (자격증명 없음 → 항상 폴백). EC2에서 돌린다:

    appenv/bin/python scripts/smoke_bedrock.py

하는 일:
  1. verdict_service.generate_verdict 를 실호출 → 이유·형량 출력, 폴백 여부 판정
  2. parse_service.normalize 를 실호출 → 표준 JSON 변환 결과 출력, 폴백 여부 판정
  3. 간단한 품질 체크(한국어 / 종결어미 '~다' / 수치 인용 / 카테고리 유효)

폴백으로 떨어졌으면 종료 코드 1. app.log 의 "Bedrock 호출 실패" 와 함께 보면 된다.
"""
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if os.environ.get("MOCK_AI") == "1":
    sys.exit("MOCK_AI=1 상태다. 이 스크립트는 실제 Bedrock 확인용이므로 MOCK_AI 를 끄고 실행할 것.")

from services import parse_service, verdict_service  # noqa: E402

_FALLBACK_MARK_R = "§FALLBACK-REASONING§"
_FALLBACK_MARK_S = "§FALLBACK-SENTENCE§"

_STATS = {
    "month": "2026-08", "totalExpense": 432000, "paymentCount": 42, "smallPaymentCount": 21,
    "largestSingleExpense": {"amount": 89000, "storeName": "무신사", "date": "2026-08-21",
                             "category": "SHOPPING_HOBBY"},
    "categoryStats": [
        {"category": "DELIVERY_DINING", "label": "배달·외식", "amount": 184000, "percentage": 42.6, "count": 12},
        {"category": "CONVENIENCE_STORE", "label": "편의점", "amount": 96000, "percentage": 22.2, "count": 15},
    ],
}
_CT = {"code": "DELIVERY_APP", "label": "냉장고보다 배달앱형"}
_JUDGMENT = {
    "crime": "냉장고 유기죄",
    "evidence": ["배달·외식 지출 184,000원", "배달·외식 결제 12회"],
    "verdict": "냉장고는 가구가 아닙니다.",
    "reasoning": _FALLBACK_MARK_R,
    "sentence": _FALLBACK_MARK_S,
}

_RAW_ROWS = [
    {"거래일자": "2026.08.02", "적요": "배달의민족", "금액": "19,800"},
    {"거래일자": "2026.08.05", "적요": "스타벅스코리아 역삼점", "금액": "6,500"},
    {"거래일자": "2026.08.07", "적요": "GS25 강남", "금액": "3,200"},
    {"거래일자": "2026.08.10", "적요": "토스뱅크 김민수", "금액": "50,000"},
    {"거래일자": "2026.08.14", "적요": "쿠팡", "금액": "38,000"},
]

_VALID_CATEGORIES = {
    "DELIVERY_DINING", "CONVENIENCE_STORE", "CAFE_SNACK",
    "GROCERIES", "SHOPPING_HOBBY", "OTHER",
}


def _has_digit(text: str) -> bool:
    return any(c.isdigit() for c in text)


def check_verdict() -> bool:
    print("\n=== 1. 판결문 이유·형량 (verdict_service) ===")
    buf = io.StringIO()
    with redirect_stdout(buf):
        out = verdict_service.generate_verdict(_STATS, _CT, _JUDGMENT, "박진수", [])
    log = buf.getvalue().strip()
    if log:
        print("  [로그]", log.replace("\n", " | "))

    used_fallback = out["reasoning"] == _FALLBACK_MARK_R or out["sentence"] == _FALLBACK_MARK_S
    print(f"  이유 : {out['reasoning']}")
    print(f"  형량 : {out['sentence']}")

    if used_fallback:
        print("  ✗ 폴백 템플릿으로 떨어졌다 — Bedrock 호출 실패.")
        return False

    ok = True
    if not _has_digit(out["reasoning"]):
        print("  ⚠ 이유에 수치 인용이 없다 (프롬프트는 1개 이상 요구).")
        ok = False
    if not out["sentence"].rstrip().endswith(("다.", "다", "라.")):
        print("  ⚠ 형량 종결어미가 '~다' 계열이 아니다.")
        ok = False
    print("  ✓ 실제 생성됨" + ("" if ok else " (품질 경고 있음)"))
    return True


def check_parse() -> bool:
    print("\n=== 2. 지출내역 정규화 (parse_service) ===")
    buf = io.StringIO()
    with redirect_stdout(buf):
        items, source = parse_service.normalize(_RAW_ROWS)
    log = buf.getvalue().strip()
    if log:
        print("  [로그]", log.replace("\n", " | "))

    print(f"  source = {source}  (원시 {len(_RAW_ROWS)}행 → 표준 {len(items)}건)")
    for it in items:
        print(f"    - {it['date']} {it['storeName']:<20} {it['amount']:>8,}  "
              f"{it['category']:<18} {it['transactionType']:<8} "
              f"{'[정리요]' if it.get('needsReview') else ''}")

    bad_cat = [it for it in items if it["category"] not in _VALID_CATEGORIES]
    if bad_cat:
        print(f"  ✗ 유효하지 않은 카테고리: {[it['category'] for it in bad_cat]}")
        return False

    if source == "bedrock":
        print("  ✓ Bedrock 정규화 사용")
        return True
    print(f"  ✗ '{source}' — Bedrock 실패로 규칙 폴백. (로컬이면 정상, 서버면 문제)")
    return False


if __name__ == "__main__":
    results = [check_verdict(), check_parse()]
    print("\n" + "=" * 50)
    if all(results):
        print("결과: 두 경로 모두 실제 Bedrock 사용 확인.")
        sys.exit(0)
    print("결과: 하나 이상이 폴백으로 떨어졌다. app.log 확인 필요.")
    sys.exit(1)
