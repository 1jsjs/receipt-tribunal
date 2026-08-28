"""services.parse_service — 파일 추출 + 규칙 정규화 + 카테고리 보정 통합.

pandas/pdfplumber 없으면 파일 파싱 테스트는 스킵. 규칙 정규화·보정 테스트는 항상 실행.

    python3 -m unittest tests.test_parse_service -v
"""
import glob
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from constants import CATEGORIES  # noqa: E402
from services.parse_service import _rule_normalize, normalize  # noqa: E402

try:
    import pandas  # noqa: F401
    import pdfplumber  # noqa: F401
    _HAS_PARSE_DEPS = True
except ImportError:
    _HAS_PARSE_DEPS = False


class RuleNormalizeTest(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"MOCK_AI": "1"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_normalizes_and_refines_category(self):
        raw = [
            {"거래일자": "2026-08-13", "적요": "배달의민족", "금액": "19,800"},
            {"거래일자": "2026.08.14", "가맹점": "GS25 금암점", "금액": "5,100원"},
            {"날짜": "20260815", "내용": "토스페이", "출금": "1,860"},
            {"거래일자": "합계", "적요": "", "금액": ""},  # 거래 아님 → 제외
        ]
        items, source = normalize(raw)
        self.assertEqual(source, "rules(mock)")
        self.assertEqual(len(items), 3)
        by_store = {i["storeName"]: i["category"] for i in items}
        self.assertEqual(by_store["배달의민족"], "DELIVERY_DINING")
        self.assertEqual(by_store["GS25 금암점"], "CONVENIENCE_STORE")
        self.assertEqual(by_store["토스페이"], "OTHER")  # PG명 → 억지 분류 안 함
        for i in items:
            self.assertIn(i["category"], CATEGORIES)
            self.assertRegex(i["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertGreaterEqual(i["amount"], 1)

    def test_empty_rows(self):
        self.assertEqual(normalize([]), ([], "empty"))

    def test_transfer_detected_from_row_text(self):
        raw = [{"거래일자": "2026-08-01", "적요": "김철수", "금액": "300,000", "구분": "계좌이체"}]
        items = _rule_normalize(raw)
        self.assertEqual(items[0]["transactionType"], "TRANSFER")


@unittest.skipUnless(_HAS_PARSE_DEPS, "pandas/pdfplumber 미설치")
class SampleFileTest(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"MOCK_AI": "1"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def _samples(self):
        return sorted(glob.glob(str(_ROOT / "samples" / "*내역*")))

    def test_sample_files_parse(self):
        from services.parse_service import parse_file

        found = self._samples()
        self.assertTrue(found, "samples/ 에 카드내역/계좌내역 예시 파일이 없음")
        for path in found:
            with self.subTest(file=Path(path).name):
                content = Path(path).read_bytes()
                r = parse_file(Path(path).name, content)
                self.assertGreater(len(r["items"]), 5)
                seen = {i["category"] for i in r["items"]}
                self.assertLessEqual(seen, set(CATEGORIES))
                # 편의점·배달 같은 흔한 카테고리는 잡혀야 한다
                self.assertIn("CONVENIENCE_STORE", seen)
                self.assertIn("DELIVERY_DINING", seen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
