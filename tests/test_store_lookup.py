"""services.store_lookup + 공공데이터 보정 통합 테스트 — feat/import-classify

색인 파일(data/store_category.sqlite)이 없으면 전체 스킵.
색인은 data/build_store_index.py로 생성 (커밋 대상 아님).

    python3 -m unittest tests.test_store_lookup -v
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from services.store_lookup import _DB_PATH, classify_by_public_data, normalize_store_name  # noqa: E402

_HAS_INDEX = _DB_PATH.is_file()


class NormalizeTest(unittest.TestCase):
    def test_strips_pg_tail_keeps_service_word(self):
        self.assertEqual(normalize_store_name("쿠팡이츠_KCP"), "쿠팡이츠")
        self.assertEqual(normalize_store_name("우아한형제들_TOSS"), "우아한형제들")
        # PG 토큰이 아닌 접미사(_택시9)는 보존
        self.assertEqual(normalize_store_name("카카오_택시9"), "카카오택시9")

    def test_strips_parens_corp_punct_space(self):
        self.assertEqual(normalize_store_name("씨제이올리브영(주)올리브영 광주"), "씨제이올리브영올리브영광주")
        self.assertEqual(normalize_store_name("(주)아성다이소"), "아성다이소")
        self.assertEqual(normalize_store_name("한길 양평해장국"), "한길양평해장국")


@unittest.skipUnless(_HAS_INDEX, "data/store_category.sqlite 없음 — build_store_index.py로 생성 필요")
class PublicDataLookupTest(unittest.TestCase):
    def test_known_local_merchants(self):
        cases = {
            "미원종합마트": "GROCERIES",
            "커몬뮤직플렉스코인노래연습장": "SHOPPING_HOBBY",
            "사보르커피": "CAFE_SNACK",
            "신창대형약국": "OTHER",
            "예스정형외과병원": "OTHER",
            "토부": "DELIVERY_DINING",           # 주점 — 키워드는 못 잡는 케이스
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_by_public_data(name), expected)

    def test_branch_suffix_stripped(self):
        # "파리바게뜨학동삼성점" → 지점 표기 제거 후/접두사로 카페 매칭
        self.assertEqual(classify_by_public_data("파리바게뜨학동삼성점"), "CAFE_SNACK")

    def test_unknown_returns_none(self):
        self.assertIsNone(classify_by_public_data("존재하지않는가게이름ZZZ123"))
        self.assertIsNone(classify_by_public_data(""))

    def test_pg_names_not_forced(self):
        # 결제대행/이체 상대방 이름은 매칭되면 안 됨 (오분류 방지)
        for name in ("토스페이", "대표_네이버페이", "카카오_택시9", "김태현"):
            with self.subTest(name=name):
                self.assertIsNone(classify_by_public_data(name))


if __name__ == "__main__":
    unittest.main(verbosity=2)
