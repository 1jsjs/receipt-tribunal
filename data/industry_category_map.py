"""소상공인시장진흥공단 상가(상권)정보 업종 분류 → 서비스 6종 카테고리 매핑.

공공데이터 컬럼: 상권업종대분류명 / 상권업종중분류명 / 상권업종소분류명.
build_store_index.py(색인 생성)와 store_lookup.py(런타임 조회)가 공유한다.
데이터는 포함하지 않는다 — 규칙만.
"""
from constants import (
    CATEGORY_CAFE_SNACK,
    CATEGORY_CONVENIENCE_STORE,
    CATEGORY_DELIVERY_DINING,
    CATEGORY_GROCERIES,
    CATEGORY_OTHER,
    CATEGORY_SHOPPING_HOBBY,
)

# 소분류명에 이 토큰이 있으면 카페로 (음식 대분류 안에서만 적용)
_CAFE_SUB = ("카페", "커피", "빵", "도넛", "떡", "한과", "아이스크림", "빙수", "제과", "다방", "생과일")

# 음식 대분류 안에서 카페가 아니면 전부 배달·외식(주점 포함)
def _food(sub: str) -> str:
    return CATEGORY_CAFE_SNACK if any(t in sub for t in _CAFE_SUB) else CATEGORY_DELIVERY_DINING


# 소매 > 종합 소매: 편의점 / 슈퍼마켓·기타
def _general_retail(sub: str) -> str:
    if "편의점" in sub:
        return CATEGORY_CONVENIENCE_STORE
    return CATEGORY_GROCERIES


# 소매 > 의약·화장품: 화장품만 쇼핑, 약국·의료기기는 기타
def _pharm_cosmetic(sub: str) -> str:
    return CATEGORY_SHOPPING_HOBBY if "화장품" in sub else CATEGORY_OTHER


# 중분류명 → 카테고리 (소분류가 필요 없는 경우). 값이 함수면 소분류로 재판정.
_MID_RULES: dict[str, object] = {
    # ─ 음식 ─
    "한식": CATEGORY_DELIVERY_DINING,
    "중식": CATEGORY_DELIVERY_DINING,
    "일식": CATEGORY_DELIVERY_DINING,
    "서양식": CATEGORY_DELIVERY_DINING,
    "기타 외국식": CATEGORY_DELIVERY_DINING,
    "제과제빵떡케익": CATEGORY_CAFE_SNACK,
    "주점": CATEGORY_DELIVERY_DINING,
    "비알코올": _food,          # 대부분 카페
    "기타 간이": _food,          # 분식·치킨·피자·버거 = 배달 / 빵·도넛·아이스크림 = 카페
    "출장 음식": CATEGORY_DELIVERY_DINING,
    # ─ 소매 ─
    "종합 소매": _general_retail,
    "식료품 소매": CATEGORY_GROCERIES,
    "섬유·의복·신발 소매": CATEGORY_SHOPPING_HOBBY,
    "의약·화장품 소매": _pharm_cosmetic,
    "가전·통신 소매": CATEGORY_SHOPPING_HOBBY,
    "오락용품 소매": CATEGORY_SHOPPING_HOBBY,      # 문구·서점·완구·운동용품·음반
    "장식품 소매": CATEGORY_SHOPPING_HOBBY,
    "기타 상품 소매": CATEGORY_SHOPPING_HOBBY,     # 올리브영류 잡화
    "기타 생활용품 소매": CATEGORY_GROCERIES,      # 주방/가정용품·조명
    "가구 소매": CATEGORY_SHOPPING_HOBBY,
    "철물·건설자재 소매": CATEGORY_OTHER,
    "연료 소매": CATEGORY_OTHER,                   # 주유소
    # ─ 예술·스포츠 ─
    "유원지·오락": lambda sub: CATEGORY_OTHER if "복권" in sub else CATEGORY_SHOPPING_HOBBY,
    "스포츠 서비스": CATEGORY_SHOPPING_HOBBY,       # 헬스장·당구장·볼링장 = 취미
}


def map_industry(major: str, mid: str, sub: str) -> str:
    """(대분류명, 중분류명, 소분류명) → 6종 카테고리 코드. 매칭 없으면 OTHER."""
    mid = (mid or "").strip()
    sub = (sub or "").strip()

    rule = _MID_RULES.get(mid)
    if rule is None:
        # 중분류 미등록 → 대분류로 큰 틀만
        if (major or "").strip() == "음식":
            return _food(sub)
        return CATEGORY_OTHER

    if callable(rule):
        return rule(sub)
    return rule
