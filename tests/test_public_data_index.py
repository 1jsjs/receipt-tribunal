"""공공데이터 상권정보 색인 — 생성→조회→카테고리 보정 엔드투엔드 검증.

실제 배포 색인(data/store_category.sqlite, 129MB, git 무시)은 로컬에 없다.
대신 상가정보 CSV와 같은 컬럼 구조의 **소형 합성 데이터**로 색인을 만들어
build_store_index → store_lookup → category_rules.refine_categories 전 경로가
실제로 동작하는지 확인한다. (LLM 미사용, 전부 오프라인·결정적)

    python3 -m unittest tests.test_public_data_index -v
"""
import csv
import importlib
import io
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from data.industry_category_map import map_industry  # noqa: E402

# 상가정보 원본과 동일한 컬럼명 (build_store_index가 이 이름으로 읽는다)
_COLS = ["상호명", "상권업종대분류명", "상권업종중분류명", "상권업종소분류명"]

# (상호명, 대분류, 중분류, 소분류) — 합성. 실제 데이터 아님.
_SYNTHETIC_ROWS = [
    ("미원종합마트", "소매", "종합 소매", "슈퍼마켓"),
    ("미원종합마트", "소매", "종합 소매", "슈퍼마켓"),
    ("행복한과일가게", "소매", "식료품 소매", "청과물 소매업"),
    ("동네커피로스터스", "음식", "비알코올 음료점", "커피 전문점"),
    ("동네커피로스터스", "음식", "비알코올 음료점", "커피 전문점"),
    ("왕곱창막창", "음식", "한식", "한식 육류요리 전문점"),
    ("장수치킨호프", "음식", "주점", "호프/맥주"),
    ("스물다섯씨유", "소매", "종합 소매", "체인화 편의점"),
    ("초록마을유기농", "소매", "식료품 소매", "채소/과일 소매업"),
    ("바른몸스포츠센터", "예술·스포츠·여가", "스포츠 서비스", "체력단련시설 운영업"),
]


def _make_index(rows) -> Path:
    """합성 행으로 ZIP(CSV 1개)을 만들고 build_store_index.build()를 돌려
    store_category.sqlite 경로를 돌려준다."""
    tmpdir = Path(tempfile.mkdtemp(prefix="storeidx_"))
    zip_path = tmpdir / "상가정보_합성.zip"

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_COLS)
    for name, major, mid, sub in rows:
        w.writerow([name, major, mid, sub])
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("소상공인시장진흥공단_상가정보_합성_202601.csv",
                    buf.getvalue().encode("utf-8"))

    build_mod = importlib.import_module("data.build_store_index")
    out = tmpdir / "store_category.sqlite"
    build_mod._OUT = out          # 출력 경로를 tmp로 (리포 data/를 건드리지 않는다)
    build_mod.build(zip_path)
    return out


class IndustryMapTest(unittest.TestCase):
    """공공데이터 업종분류 → 우리 6종 매핑 규칙 (데이터 없이 순수 함수)."""

    def test_food_and_retail_mapping(self):
        self.assertEqual(map_industry("소매", "종합 소매", "체인화 편의점"), "CONVENIENCE_STORE")
        self.assertEqual(map_industry("소매", "종합 소매", "슈퍼마켓"), "GROCERIES")
        self.assertEqual(map_industry("음식", "비알코올 음료점", "커피 전문점"), "CAFE_SNACK")
        self.assertEqual(map_industry("음식", "한식", "한식 육류요리 전문점"), "DELIVERY_DINING")
        self.assertEqual(map_industry("음식", "주점", "호프/맥주"), "DELIVERY_DINING")
        self.assertEqual(map_industry("소매", "식료품 소매", "채소/과일 소매업"), "GROCERIES")
        self.assertEqual(map_industry("예술·스포츠·여가", "스포츠 서비스", "체력단련시설 운영업"),
                         "SHOPPING_HOBBY")

    def test_unknown_maps_to_other(self):
        self.assertEqual(map_industry("부동산", "부동산 중개", "아파트 중개"), "OTHER")


class IndexBuildAndLookupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_path = _make_index(_SYNTHETIC_ROWS)
        # store_lookup의 모듈 전역 상태를 tmp 색인으로 갈아끼운다
        import services.store_lookup as sl
        cls._sl = sl
        cls._orig_path = sl._DB_PATH
        sl._DB_PATH = cls.index_path
        sl._exact = sl._prefix = None
        sl._loaded = False

    @classmethod
    def tearDownClass(cls):
        sl = cls._sl
        sl._DB_PATH = cls._orig_path
        sl._exact = sl._prefix = None
        sl._loaded = False

    def test_index_file_created_with_rows(self):
        import sqlite3
        self.assertTrue(self.index_path.is_file())
        conn = sqlite3.connect(self.index_path)
        exact = conn.execute("SELECT COUNT(*) FROM store_exact").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(exact, 5)

    def test_exact_lookup(self):
        f = self._sl.classify_by_public_data
        self.assertEqual(f("미원종합마트"), "GROCERIES")
        self.assertEqual(f("동네커피로스터스"), "CAFE_SNACK")
        self.assertEqual(f("왕곱창막창"), "DELIVERY_DINING")
        self.assertEqual(f("스물다섯씨유"), "CONVENIENCE_STORE")

    def test_lookup_normalizes_pg_tail_and_corp_paren(self):
        f = self._sl.classify_by_public_data
        # 결제망 접미사·법인표기·괄호가 붙어도 정규화 후 매칭돼야 한다
        self.assertEqual(f("(주)동네커피로스터스_KCP"), "CAFE_SNACK")
        self.assertEqual(f("왕곱창막창_TOSS"), "DELIVERY_DINING")

    def test_unknown_store_returns_none(self):
        self.assertIsNone(self._sl.classify_by_public_data("존재하지않는가게123"))

    def test_refine_categories_promotes_other_via_public_data(self):
        """parse_service가 OTHER로 남긴 항목을 공공데이터로 승격하는 실제 경로.

        '초록마을유기농'은 키워드 규칙에 안 걸리고(마트/슈퍼 등 없음) 공공데이터
        색인에서만 잡힌다 — 공공데이터 단계가 실제로 동작함을 보증한다.
        """
        from services.category_rules import refine_categories
        items = [
            {"storeName": "초록마을유기농", "category": "OTHER"},      # 공공데이터 → GROCERIES
            {"storeName": "동네커피로스터스", "category": "OTHER"},    # 키워드('커피') → CAFE_SNACK
            {"storeName": "김한생", "category": "OTHER"},              # 어디에도 없음 → OTHER 유지
        ]
        refine_categories(items)
        self.assertEqual(items[0]["category"], "GROCERIES")
        self.assertEqual(items[1]["category"], "CAFE_SNACK")
        self.assertEqual(items[2]["category"], "OTHER")

    def test_disable_flag_skips_public_data(self):
        from services.category_rules import refine_categories
        items = [{"storeName": "초록마을유기농", "category": "OTHER"}]
        with unittest.mock.patch.dict("os.environ", {"IMPORT_DISABLE_PUBLIC_DATA": "1"}):
            refine_categories(items)
        # 공공데이터 단계를 건너뛰므로 키워드로 못 잡는 이 상호는 OTHER로 남는다
        self.assertEqual(items[0]["category"], "OTHER")


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
