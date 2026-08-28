"""services.category_rules — 키워드 분류 + 공공데이터 보정.

    python3 -m unittest tests.test_category_rules -v
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from constants import (  # noqa: E402
    CATEGORIES,
    CATEGORY_CAFE_SNACK,
    CATEGORY_CONVENIENCE_STORE,
    CATEGORY_DELIVERY_DINING,
    CATEGORY_GROCERIES,
    CATEGORY_OTHER,
    CATEGORY_SHOPPING_HOBBY,
)
from services.category_rules import classify_by_keyword, refine_categories  # noqa: E402
from services.store_lookup import _DB_PATH  # noqa: E402

_HAS_INDEX = _DB_PATH.is_file()


class KeywordTest(unittest.TestCase):
    def test_each_category(self):
        cases = [
            ("GS25 금암점", CATEGORY_CONVENIENCE_STORE),
            ("CU 아중점", CATEGORY_CONVENIENCE_STORE),
            ("세븐일레븐 전북대점", CATEGORY_CONVENIENCE_STORE),
            ("컴포즈커피", CATEGORY_CAFE_SNACK),
            ("스타벅스 전주객사점", CATEGORY_CAFE_SNACK),
            ("파리바게뜨 학동점", CATEGORY_CAFE_SNACK),
            ("배달의민족", CATEGORY_DELIVERY_DINING),
            ("쿠팡이츠", CATEGORY_DELIVERY_DINING),
            ("한길 양평해장국", CATEGORY_DELIVERY_DINING),
            ("이마트 전주점", CATEGORY_GROCERIES),
            ("홈플러스 전주점", CATEGORY_GROCERIES),
            ("올리브영 광주점", CATEGORY_SHOPPING_HOBBY),
            ("CGV 전주", CATEGORY_SHOPPING_HOBBY),
            ("무신사", CATEGORY_SHOPPING_HOBBY),
            ("예스정형외과병원", CATEGORY_OTHER),
            ("한국전력공사", CATEGORY_OTHER),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(classify_by_keyword(name), expected)

    def test_memo_participates(self):
        self.assertEqual(classify_by_keyword("결제대행", "배달의민족 주문"), CATEGORY_DELIVERY_DINING)


class RefineTest(unittest.TestCase):
    def test_keeps_non_other_reclassifies_other(self):
        items = [
            {"storeName": "쿠팡이츠", "category": CATEGORY_OTHER},        # 잘못된 OTHER → 재분류
            {"storeName": "동네분식", "category": CATEGORY_CAFE_SNACK},   # 비-OTHER → 유지 (모델 판단 존중)
            {"storeName": "완전무명ZZ", "category": None},                # 미지정 → 키워드 → OTHER
        ]
        with mock.patch.dict(os.environ, {"IMPORT_DISABLE_PUBLIC_DATA": "1"}):
            refine_categories(items)
        self.assertEqual(items[0]["category"], CATEGORY_DELIVERY_DINING)
        self.assertEqual(items[1]["category"], CATEGORY_CAFE_SNACK)
        self.assertEqual(items[2]["category"], CATEGORY_OTHER)
        for it in items:
            self.assertIn(it["category"], CATEGORIES)

    @unittest.skipUnless(_HAS_INDEX, "data/store_category.sqlite 없음")
    def test_public_data_fills_remaining_other(self):
        items = [{"storeName": "토부", "category": CATEGORY_OTHER}]  # 주점 — 키워드 못 잡음
        refine_categories(items)
        self.assertEqual(items[0]["category"], CATEGORY_DELIVERY_DINING)

    @unittest.skipUnless(_HAS_INDEX, "data/store_category.sqlite 없음")
    def test_disable_flag_skips_public_data(self):
        items = [{"storeName": "토부", "category": CATEGORY_OTHER}]
        with mock.patch.dict(os.environ, {"IMPORT_DISABLE_PUBLIC_DATA": "1"}):
            refine_categories(items)
        self.assertEqual(items[0]["category"], CATEGORY_OTHER)


if __name__ == "__main__":
    unittest.main(verbosity=2)
