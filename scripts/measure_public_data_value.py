"""공공데이터(상권정보) 색인이 카테고리 분류에 실제로 얼마나 기여하는지 측정.

질문: 키워드 규칙만으로 충분한가? 공공데이터 색인이 OTHER를 얼마나 구제하나?

측정 방식 — 상호명 리스트 각각에 대해:
  A. classify_by_keyword(name)                      → 키워드만
  B. A가 OTHER면 classify_by_public_data(name)      → 공공데이터로 재시도
그리고 (키워드 히트 / 공공데이터 구제 / 끝까지 OTHER) 건수를 집계한다.

실행:
    # 서버 (data/store_category.sqlite 있음) — 진짜 수치
    appenv/bin/python scripts/measure_public_data_value.py

    # 로컬 데모 — 합성 색인을 즉석에서 만들어 파이프라인만 확인
    python3 scripts/measure_public_data_value.py --mini

    # 직접 만든 상호명 파일로 (한 줄에 하나)
    python3 scripts/measure_public_data_value.py --names my_merchants.txt
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constants import CATEGORY_LABELS, CATEGORY_OTHER  # noqa: E402
from services.category_rules import classify_by_keyword  # noqa: E402
from services import store_lookup  # noqa: E402

# 데모/회귀용 표본 — 체인(키워드로 잡힘) + 독립·로컬 상호(공공데이터로만 잡힘) 혼합.
# 실제 측정은 --names 로 진짜 거래내역 상호명을 넣는 게 정확하다.
_SAMPLE_NAMES = [
    # 키워드로 잡히는 프랜차이즈
    "배달의민족", "스타벅스 역삼점", "GS25 강남", "이마트 성수", "올리브영 홍대",
    "쿠팡", "메가커피", "교촌치킨 신촌", "CU 삼성점", "다이소 강남",
    # 키워드에 없는 독립/로컬 상호 (공공데이터 색인이 있어야 잡힘)
    "미원종합마트", "행복한과일가게", "동네커피로스터스", "왕곱창막창",
    "초록마을유기농", "바른몸스포츠센터", "손칼국수집", "청년다방 본점",
    "코인노래연습장", "무인양품매장",
    # 사람 이름 송금 등 — 어차피 정리 대상 (둘 다 못 잡는 게 정상)
    "김민수", "홍길동", "박○○",
]


def _load_names(args) -> list[str]:
    if args.names:
        return [l.strip() for l in Path(args.names).read_text(encoding="utf-8").splitlines() if l.strip()]
    return list(_SAMPLE_NAMES)


def _build_mini_index() -> None:
    """합성 상가정보로 store_category.sqlite 를 tmp에 만들고 store_lookup 을 그쪽으로."""
    import csv, io, tempfile, zipfile, importlib  # noqa: E401
    rows = [
        ("미원종합마트", "소매", "종합 소매", "슈퍼마켓"),
        ("행복한과일가게", "소매", "식료품 소매", "청과물 소매업"),
        ("동네커피로스터스", "음식", "비알코올 음료점", "커피 전문점"),
        ("왕곱창막창", "음식", "한식", "한식 육류요리 전문점"),
        ("초록마을유기농", "소매", "식료품 소매", "채소/과일 소매업"),
        ("바른몸스포츠센터", "예술·스포츠·여가", "스포츠 서비스", "체력단련시설 운영업"),
        ("손칼국수집", "음식", "한식", "한식 면요리 전문점"),
        ("청년다방", "음식", "비알코올 음료점", "커피 전문점"),
        ("코인노래연습장", "예술·스포츠·여가", "유원지·오락", "노래연습장 운영업"),
        ("무인양품매장", "소매", "기타 상품 소매", "그 외 기타 상품 전문 소매업"),
    ]
    tmp = Path(tempfile.mkdtemp(prefix="pdv_"))
    zp = tmp / "syn.zip"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["상호명", "상권업종대분류명", "상권업종중분류명", "상권업종소분류명"])
    for r in rows:
        w.writerow(r)
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("syn_상가정보.csv", buf.getvalue().encode("utf-8"))
    bm = importlib.import_module("data.build_store_index")
    bm._OUT = tmp / "store_category.sqlite"
    bm.build(zp)
    store_lookup._DB_PATH = bm._OUT
    store_lookup._exact = store_lookup._prefix = None
    store_lookup._loaded = False
    print(f"[mini] 합성 색인 생성: {bm._OUT}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", help="상호명 파일 (한 줄에 하나)")
    ap.add_argument("--mini", action="store_true", help="합성 색인을 즉석 생성해 데모")
    args = ap.parse_args()

    if args.mini:
        _build_mini_index()

    has_index = store_lookup._DB_PATH.is_file()
    print(f"공공데이터 색인: {'있음 → ' + str(store_lookup._DB_PATH) if has_index else '없음 (키워드 단계만 측정됨)'}")

    names = _load_names(args)
    kw_hit = pd_rescue = still_other = 0
    rescued: list[tuple[str, str]] = []
    final_dist: Counter = Counter()

    for name in names:
        cat = classify_by_keyword(name)
        if cat != CATEGORY_OTHER:
            kw_hit += 1
        else:
            pd_cat = None
            if has_index:
                try:
                    pd_cat = store_lookup.classify_by_public_data(name)
                except Exception:  # noqa: BLE001
                    pd_cat = None
            if pd_cat and pd_cat != CATEGORY_OTHER:
                pd_rescue += 1
                cat = pd_cat
                rescued.append((name, pd_cat))
            else:
                still_other += 1
        final_dist[cat] += 1

    n = len(names)
    print(f"\n표본 {n}건")
    print(f"  키워드로 분류      : {kw_hit:3d}  ({kw_hit / n:5.1%})")
    print(f"  공공데이터가 구제   : {pd_rescue:3d}  ({pd_rescue / n:5.1%})")
    print(f"  끝까지 OTHER       : {still_other:3d}  ({still_other / n:5.1%})")

    if rescued:
        print("\n공공데이터가 구제한 항목:")
        for name, cat in rescued:
            print(f"  {name:<24} → {cat} ({CATEGORY_LABELS.get(cat, cat)})")

    print("\n최종 카테고리 분포:")
    for cat, c in final_dist.most_common():
        print(f"  {CATEGORY_LABELS.get(cat, cat):<10} {c}")

    if not has_index:
        print("\n※ 색인이 없어 '키워드만' 결과다. 진짜 기여도는 서버에서 실행할 것.")


if __name__ == "__main__":
    main()
