"""상호명 기반 카테고리 규칙 분류 + 공공데이터 보정.

parse_service가 파일에서 뽑아 정규화한 거래 리스트의 category를 최종 확정한다:
  1) 모델/규칙이 이미 6종 중 하나(OTHER 제외)로 넣었으면 그대로 둔다 — 문맥 판단 존중
  2) OTHER·미지정이면 키워드 규칙으로 재판정
  3) 그래도 OTHER면 공공데이터(소상공인 상가정보) 색인으로 보정 (색인 없으면 skip)

전부 결정적·오프라인 — LLM 호출 없음. IMPORT_DISABLE_PUBLIC_DATA=1로 3단계를 끌 수 있다.
"""
import os

from constants import (
    CATEGORIES,
    CATEGORY_CAFE_SNACK,
    CATEGORY_CONVENIENCE_STORE,
    CATEGORY_DELIVERY_DINING,
    CATEGORY_GROCERIES,
    CATEGORY_OTHER,
    CATEGORY_SHOPPING_HOBBY,
)

# ─── 키워드 규칙 (위에서부터 첫 매칭 채택 — 구체적인 카테고리를 앞에) ───
# 실제 은행 거래내역서(토스뱅크)의 '거래내용' 표기 형태를 반영한다.
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    (CATEGORY_CONVENIENCE_STORE, (
        "gs25", "지에스25", "cu ", "(cu)", "씨유", "세븐일레븐", "seven eleven",
        "7-eleven", "이마트24", "e마트24", "emart24", "미니스톱", "ministop", "편의점",
        "생협", "제로스토어", "무인매장", "storyway",
    )),
    (CATEGORY_CAFE_SNACK, (
        "스타벅스", "starbucks", "투썸", "twosome", "이디야", "ediya", "메가커피",
        "메가엠지씨", "컴포즈", "빽다방", "커피", "coffee", "카페", "cafe", "파리바게",
        "뚜레쥬르", "던킨", "dunkin", "크리스피", "krispy", "베이커리", "bakery",
        "디저트", "설빙", "배스킨", "baskin", "공차", "gongcha", "앤티앤스",
    )),
    (CATEGORY_DELIVERY_DINING, (
        "배달의민족", "배민", "우아한형제들", "쿠팡이츠", "요기요", "yogiyo",
        "땡겨요", "우버이츠", "uber eats", "맥도날드", "mcdonald", "버거킹",
        "burger king", "롯데리아", "kfc", "bhc", "bbq", "교촌", "치킨", "피자",
        "domino", "pizza", "쉐이크쉑", "shake shack", "김밥", "떡볶이", "분식",
        "국밥", "해장국", "식당", "칼국수", "쌀국수", "돈까스", "포차", "곱창",
        "삼겹", "마라", "초밥", "restaurant",
    )),
    (CATEGORY_GROCERIES, (
        "이마트", "emart", "홈플러스", "homeplus", "롯데마트", "하나로마트",
        "하나로클럽", "하나로", "농협", "노브랜드", "no brand", "코스트코", "costco",
        "다이소", "daiso", "슈퍼", "마트", "생필품", "정육", "청과", "수산",
        "한살림", "식자재",
    )),
    (CATEGORY_SHOPPING_HOBBY, (
        "무신사", "musinsa", "쿠팡", "coupang", "11번가", "지마켓", "gmarket",
        "옥션", "auction", "네이버쇼핑", "올리브영", "oliveyoung", "교보문고",
        "영풍문고", "문고", "yes24", "알라딘", "스팀", "steam", "닌텐도",
        "nintendo", "넷플릭스", "netflix", "왓챠", "watcha", "스포티파이",
        "spotify", "ikea", "이케아", "지그재그", "에이블리", "브랜디", "쇼핑",
        "백화점", "신세계", "cgv", "메가박스", "롯데시네마", "영화", "노래연습장",
        "노래방", "와우멤버십", "문구", "화장품", "의류", "패션",
    )),
]


def classify_by_keyword(store_name: str, memo: str = "") -> str:
    """상호명·메모를 키워드 규칙으로 분류. 매칭 없으면 OTHER."""
    text = f"{store_name} {memo}".lower()
    for category, keywords in _KEYWORD_RULES:
        for keyword in keywords:
            if keyword.lower() in text:
                return category
    return CATEGORY_OTHER


def refine_categories(items: list[dict]) -> None:
    """items 각 원소의 category를 최종 확정한다 (제자리 수정).

    items : [{"storeName": str, "category": str|None, "memo"?: str, ...}, ...]
    """
    for it in items:
        cat = it.get("category")
        if cat not in CATEGORIES or cat == CATEGORY_OTHER:
            it["category"] = classify_by_keyword(
                str(it.get("storeName", "")), str(it.get("memo", ""))
            )

    if os.environ.get("IMPORT_DISABLE_PUBLIC_DATA") == "1":
        return

    pending = [it for it in items if it.get("category") == CATEGORY_OTHER]
    if not pending:
        return
    try:
        from services.store_lookup import classify_by_public_data
    except Exception:  # noqa: BLE001 — 공공데이터 색인은 선택 사항
        return
    for it in pending:
        try:
            hit = classify_by_public_data(str(it.get("storeName", "")))
        except Exception:  # noqa: BLE001
            hit = None
        if hit in CATEGORIES:
            it["category"] = hit
