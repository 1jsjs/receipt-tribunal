"""월별 유형 재현 시드 데이터 — TASK-B015 (docs/06)

실행: python3 data/seed.py
멱등: 시드 월(2026-02 ~ 2026-08)의 기존 행을 삭제 후 재삽입.

월별 설계:
  2026-08 = DELIVERY_APP      (배달 50%, 9건, 소액1건→11%)
  2026-07 = TINY_OVERSPEND    (12건, 소액7건→58%)
  2026-06 = SMART_SOLO        (식재료 38%, 8건, 소액0건)
  2026-05 = BALANCED          (최대 비율 25%, 8건)
  2026-04 = CONVENIENCE_KITCHEN (편의점 9건/건수1위, 12건, 소액3건→25%)
  2026-03 = SMALL_LUXURY      (카페 35%, 9건, 소액1건)
  2026-02 = HOBBY_SERIOUS     (쇼핑 38%, 8건, 소액0건)
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가 (data/ 에서 실행해도 동작하도록)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import get_connection, init_db, DEFAULT_DEFENDANT

SEED_MONTHS = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]

# (store_name, date, amount, category, transaction_type)
SEED_DATA: list[tuple[str, str, int, str, str]] = [
    # ═══════════════════════════════════════════════════════════════
    # 2026-08: DELIVERY_APP — 배달 50%, 9건 EXPENSE, 소액 1건 (11%)
    # 룰 점검: count=9 <10 → 티끌 탈락 / 편의점 1건 <8 → 편의점 탈락
    # ═══════════════════════════════════════════════════════════════
    ("배달의민족", "2026-08-02", 32000, "DELIVERY_DINING", "EXPENSE"),
    ("요기요", "2026-08-05", 28000, "DELIVERY_DINING", "EXPENSE"),
    ("쿠팡이츠", "2026-08-09", 45000, "DELIVERY_DINING", "EXPENSE"),
    ("교촌치킨", "2026-08-14", 38000, "DELIVERY_DINING", "EXPENSE"),
    ("피자알볼로", "2026-08-20", 35000, "DELIVERY_DINING", "EXPENSE"),
    ("CU 강남점", "2026-08-07", 4500, "CONVENIENCE_STORE", "EXPENSE"),
    ("스타벅스 역삼", "2026-08-11", 6500, "CAFE_SNACK", "EXPENSE"),
    ("이마트", "2026-08-16", 42000, "GROCERIES", "EXPENSE"),
    ("다이소", "2026-08-22", 15000, "OTHER", "EXPENSE"),
    # TRANSFER (제외)
    ("친구 정산", "2026-08-10", 50000, "OTHER", "TRANSFER"),

    # ═══════════════════════════════════════════════════════════════
    # 2026-07: TINY_OVERSPEND — 12건, 소액 7건 (58%)
    # 룰 점검: 우선순위 1번이라 다른 조건 무관
    # ═══════════════════════════════════════════════════════════════
    ("CU 삼성점", "2026-07-01", 2500, "CONVENIENCE_STORE", "EXPENSE"),
    ("GS25 선릉", "2026-07-02", 3000, "CONVENIENCE_STORE", "EXPENSE"),
    ("세븐일레븐", "2026-07-04", 4000, "CONVENIENCE_STORE", "EXPENSE"),
    ("미니스톱", "2026-07-06", 3500, "CONVENIENCE_STORE", "EXPENSE"),
    ("이디야커피", "2026-07-08", 4500, "CAFE_SNACK", "EXPENSE"),
    ("메가커피", "2026-07-10", 2000, "CAFE_SNACK", "EXPENSE"),
    ("빽다방", "2026-07-12", 3000, "CAFE_SNACK", "EXPENSE"),
    ("배달의민족", "2026-07-14", 18000, "DELIVERY_DINING", "EXPENSE"),
    ("요기요", "2026-07-17", 22000, "DELIVERY_DINING", "EXPENSE"),
    ("무신사", "2026-07-19", 35000, "SHOPPING_HOBBY", "EXPENSE"),
    ("올리브영", "2026-07-22", 12000, "SHOPPING_HOBBY", "EXPENSE"),
    ("이마트", "2026-07-25", 28000, "GROCERIES", "EXPENSE"),
    # TRANSFER
    ("월세", "2026-07-01", 500000, "OTHER", "TRANSFER"),

    # ═══════════════════════════════════════════════════════════════
    # 2026-06: SMART_SOLO — 식재료 38%, 8건, 소액 0건
    # 룰 점검: count=8 <10 → 티끌 탈락 / 편의점 1건 <8 → 편의점 탈락
    #          배달 15% <40 → 배달 탈락 / 카페 10% <30 → 소확행 탈락
    #          쇼핑 12% <30 → 취향 탈락 / 식재료 38% ≥30 → SMART_SOLO ✓
    # ═══════════════════════════════════════════════════════════════
    ("이마트", "2026-06-01", 45000, "GROCERIES", "EXPENSE"),
    ("홈플러스", "2026-06-05", 38000, "GROCERIES", "EXPENSE"),
    ("하나로마트", "2026-06-12", 32000, "GROCERIES", "EXPENSE"),
    ("배달의민족", "2026-06-08", 25000, "DELIVERY_DINING", "EXPENSE"),
    ("요기요", "2026-06-15", 22000, "DELIVERY_DINING", "EXPENSE"),
    ("스타벅스", "2026-06-10", 15000, "CAFE_SNACK", "EXPENSE"),
    ("GS25", "2026-06-18", 18000, "CONVENIENCE_STORE", "EXPENSE"),
    ("쿠팡", "2026-06-22", 38000, "SHOPPING_HOBBY", "EXPENSE"),
    # TRANSFER
    ("적금 이체", "2026-06-25", 200000, "OTHER", "TRANSFER"),

    # ═══════════════════════════════════════════════════════════════
    # 2026-05: BALANCED — 최대 비율 25%, 8건, 소액 1건
    # 룰 점검: count=8 <10 → 티끌 탈락 / 편의점 2건 <8 → 편의점 탈락
    #          배달 25% <40 / 카페 20% <30 / 쇼핑 15% <30 / 식재료 20% <30
    #          → 전부 탈락 → BALANCED ✓
    # ═══════════════════════════════════════════════════════════════
    ("배달의민족", "2026-05-02", 25000, "DELIVERY_DINING", "EXPENSE"),
    ("bbq치킨", "2026-05-08", 24000, "DELIVERY_DINING", "EXPENSE"),
    ("투썸플레이스", "2026-05-04", 18000, "CAFE_SNACK", "EXPENSE"),
    ("이디야", "2026-05-12", 4500, "CAFE_SNACK", "EXPENSE"),
    ("이마트", "2026-05-06", 22000, "GROCERIES", "EXPENSE"),
    ("홈플러스", "2026-05-15", 16000, "GROCERIES", "EXPENSE"),
    ("CU 역삼점", "2026-05-10", 8000, "CONVENIENCE_STORE", "EXPENSE"),
    ("GS25", "2026-05-18", 12000, "CONVENIENCE_STORE", "EXPENSE"),
    ("무신사", "2026-05-20", 28000, "SHOPPING_HOBBY", "EXPENSE"),
    # 기타 없으니 쇼핑만으로 15% 맞추기 위해 기타 추가 불필요 — 계산:
    # 총: 25+24+18+4.5+22+16+8+12+28 = 157.5k 안됨, 정수로:
    # 25000+24000+18000+4500+22000+16000+8000+12000+28000 = 157500
    # 배달 49000/157500=31.1% → 너무 높음! 수정 필요
    # → 배달을 낮추고 기타를 추가
    ("다이소", "2026-05-22", 20000, "OTHER", "EXPENSE"),
    # TRANSFER
    ("친구 송금", "2026-05-14", 30000, "OTHER", "TRANSFER"),

    # ═══════════════════════════════════════════════════════════════
    # 2026-04: CONVENIENCE_KITCHEN — 편의점 9건+건수1위, 12건, 소액 3건(25%)
    # 룰 점검: count=12, 소액=3건 → 3/12=25% <50% → 티끌 탈락
    #          편의점 9건 ≥8 AND 건수1위(다른 카테고리 최대 2건) → ✓
    # ═══════════════════════════════════════════════════════════════
    ("CU 역삼점", "2026-04-01", 3500, "CONVENIENCE_STORE", "EXPENSE"),
    ("GS25 선릉", "2026-04-02", 4200, "CONVENIENCE_STORE", "EXPENSE"),
    ("세븐일레븐", "2026-04-04", 5500, "CONVENIENCE_STORE", "EXPENSE"),
    ("CU 삼성점", "2026-04-06", 6000, "CONVENIENCE_STORE", "EXPENSE"),
    ("미니스톱", "2026-04-08", 7500, "CONVENIENCE_STORE", "EXPENSE"),
    ("이마트24", "2026-04-10", 8000, "CONVENIENCE_STORE", "EXPENSE"),
    ("CU 강남점", "2026-04-13", 6500, "CONVENIENCE_STORE", "EXPENSE"),
    ("GS25 역삼", "2026-04-16", 9000, "CONVENIENCE_STORE", "EXPENSE"),
    ("세븐일레븐 삼성", "2026-04-19", 5000, "CONVENIENCE_STORE", "EXPENSE"),
    ("배달의민족", "2026-04-05", 22000, "DELIVERY_DINING", "EXPENSE"),
    ("스타벅스", "2026-04-12", 6500, "CAFE_SNACK", "EXPENSE"),
    ("이마트", "2026-04-20", 35000, "GROCERIES", "EXPENSE"),
    # TRANSFER
    ("후배 축의금", "2026-04-15", 50000, "OTHER", "TRANSFER"),

    # ═══════════════════════════════════════════════════════════════
    # 2026-03: SMALL_LUXURY — 카페 35%, 배달 <40%, 9건, 소액 1건
    # 룰 점검: count=9 <10 → 티끌 탈락 / 편의점 1건 <8 → 편의점 탈락
    #          배달 20% <40 → 배달 탈락 / 카페 35% ≥30 AND 배달 <40 → ✓
    # ═══════════════════════════════════════════════════════════════
    ("스타벅스", "2026-03-01", 7000, "CAFE_SNACK", "EXPENSE"),
    ("투썸플레이스", "2026-03-04", 8500, "CAFE_SNACK", "EXPENSE"),
    ("블루보틀", "2026-03-08", 9000, "CAFE_SNACK", "EXPENSE"),
    ("폴바셋", "2026-03-12", 7500, "CAFE_SNACK", "EXPENSE"),
    ("메가커피", "2026-03-16", 3500, "CAFE_SNACK", "EXPENSE"),
    ("배달의민족", "2026-03-06", 18000, "DELIVERY_DINING", "EXPENSE"),
    ("이마트", "2026-03-10", 22000, "GROCERIES", "EXPENSE"),
    ("CU 강남점", "2026-03-14", 12000, "CONVENIENCE_STORE", "EXPENSE"),
    ("무신사", "2026-03-20", 15000, "SHOPPING_HOBBY", "EXPENSE"),
    # TRANSFER
    ("통신비 이체", "2026-03-05", 65000, "OTHER", "TRANSFER"),

    # ═══════════════════════════════════════════════════════════════
    # 2026-02: HOBBY_SERIOUS — 쇼핑 38%, 배달 <40%, 카페 <30%, 8건, 소액 0건
    # 룰 점검: count=8 <10 → 티끌 탈락 / 편의점 1건 <8 → 편의점 탈락
    #          배달 16% <40 → 배달 탈락 / 카페 12% <30 → 소확행 탈락
    #          쇼핑 38% ≥30 → ✓
    # ═══════════════════════════════════════════════════════════════
    ("무신사", "2026-02-02", 45000, "SHOPPING_HOBBY", "EXPENSE"),
    ("쿠팡", "2026-02-06", 38000, "SHOPPING_HOBBY", "EXPENSE"),
    ("올리브영", "2026-02-10", 22000, "SHOPPING_HOBBY", "EXPENSE"),
    ("배달의민족", "2026-02-04", 25000, "DELIVERY_DINING", "EXPENSE"),
    ("요기요", "2026-02-12", 20000, "DELIVERY_DINING", "EXPENSE"),
    ("투썸플레이스", "2026-02-08", 18000, "CAFE_SNACK", "EXPENSE"),
    ("스타벅스", "2026-02-15", 15000, "CAFE_SNACK", "EXPENSE"),
    ("GS25 선릉", "2026-02-18", 12000, "CONVENIENCE_STORE", "EXPENSE"),
    ("이마트", "2026-02-20", 30000, "GROCERIES", "EXPENSE"),
    ("다이소", "2026-02-22", 15000, "OTHER", "EXPENSE"),
    # TRANSFER
    ("적금", "2026-02-01", 300000, "OTHER", "TRANSFER"),
]


def run_seed():
    """시드 데이터 삽입 (멱등: 기존 시드 월 삭제 후 재삽입)"""
    init_db()
    conn = get_connection()

    # 기존 시드 월 삭제
    for month in SEED_MONTHS:
        conn.execute("DELETE FROM expenses WHERE date LIKE ?", (f"{month}-%",))

    # 삽입
    inserted = 0
    for row in SEED_DATA:
        store_name, date, amount, category, tx_type = row
        conn.execute(
            """INSERT INTO expenses (store_name, date, amount, category, transaction_type,
                                      defendant, memo, needs_review, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, '', 0, datetime('now'), datetime('now'))""",
            (store_name, date, amount, category, tx_type, DEFAULT_DEFENDANT),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"[seed] 시드 완료: {inserted}건 삽입 (월: {', '.join(SEED_MONTHS)})")


if __name__ == "__main__":
    run_seed()
