"""소비 벤치마크 기준값 — 공공데이터 출처, 카테고리별 월평균 지출

⚠️ 숫자를 바꿀 때는 반드시 SOURCE도 같이 고칠 것. 화면에 출처가 함께 표시된다.

현재 기준: 전국 1인가구 평균 (2024년)
  - 국가데이터처 「2025 통계로 보는 1인가구」 (2025.12 공표)
  - 1인가구 월평균 소비지출 1,689,000원
  - 비목별 비중: 음식·숙박 18.2% / 식료품·비주류음료 12.2%
  → 우리 카테고리 6종에 맞춰 배분한 값이 아래 BENCHMARK다.

TODO(교체 예정): 29세 이하 1인가구 수치로 교체.
  KOSIS 「가구주 연령별 가구당 월평균 가계수지」에서
  (가구주 연령 29세 이하 × 가구원수 1인 × 12대 비목)으로 조회해 받으면 된다.
  교체 시 BENCHMARK 금액과 SOURCE·GROUP_LABEL만 바꾸면 나머지 코드는 그대로 동작한다.
"""

from constants import (
    CATEGORY_CAFE_SNACK,
    CATEGORY_CONVENIENCE_STORE,
    CATEGORY_DELIVERY_DINING,
    CATEGORY_GROCERIES,
    CATEGORY_OTHER,
    CATEGORY_SHOPPING_HOBBY,
)

# 화면에 표시할 비교 집단 이름
GROUP_LABEL = "전국 1인가구 평균"

# 화면에 함께 표시할 출처 (통계 표기는 반드시 사실 그대로)
SOURCE = "국가데이터처 「2025 통계로 보는 1인가구」 · 2024년 기준"

# 비교 집단의 월평균 소비지출 총액 (원)
TOTAL_MONTHLY = 1_689_000

# 카테고리별 월평균 지출 (원)
#
# 통계의 12대 비목을 우리 6종에 대응시킨 값이다. 대응 근거를 각 줄에 남긴다.
# 통계 비목이 우리 카테고리와 1:1로 맞지 않으므로, 아래는 '추정 배분'임을 밝힌다.
BENCHMARK: dict[str, int] = {
    # 음식·숙박 18.2%(307,398원) 중 숙박을 제외한 외식·배달분
    CATEGORY_DELIVERY_DINING: 246_000,
    # 식료품·비주류음료 12.2%(206,058원) 중 편의점 구매분
    CATEGORY_CONVENIENCE_STORE: 62_000,
    # 음식·숙박 중 카페·간식분
    CATEGORY_CAFE_SNACK: 61_000,
    # 식료품·비주류음료 중 장보기분 + 가정용품·가사서비스 일부
    CATEGORY_GROCERIES: 144_000,
    # 오락·문화 + 의류·신발
    CATEGORY_SHOPPING_HOBBY: 190_000,
    # 그 외 비목 합계 (보건·교통·통신·교육 등)
    CATEGORY_OTHER: 986_000,
}

# 배분이 추정치임을 화면에서 밝히기 위한 플래그.
# 29세 이하 실측 표로 교체하면 False로 바꾼다.
IS_ESTIMATED = True
