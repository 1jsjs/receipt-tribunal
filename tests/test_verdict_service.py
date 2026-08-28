"""verdict_service 테스트 — 이유·형량 생성 + N빵 정상참작.

실행: python3 -m unittest discover -s tests -q

MOCK_AI=1 경로, Bedrock 경로(_call_bedrock 몽키패치), 폴백, 정상참작 감지, 응답
파싱(thinking 블록 포함)을 모두 검증한다.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import verdict_service as vs

_STATS = {
    "month": "2026-08",
    "totalExpense": 432000,
    "paymentCount": 42,
    "smallPaymentCount": 21,
    "largestSingleExpense": {
        "amount": 89000, "storeName": "무신사", "date": "2026-08-21",
        "category": "SHOPPING_HOBBY",
    },
    "categoryStats": [
        {"category": "DELIVERY_DINING", "label": "배달·외식", "amount": 184000, "percentage": 42.6, "count": 12},
        {"category": "CONVENIENCE_STORE", "label": "편의점", "amount": 96000, "percentage": 22.2, "count": 15},
        {"category": "GROCERIES", "label": "식재료·생필품", "amount": 0, "percentage": 0.0, "count": 0},
    ],
}
_CT = {"code": "DELIVERY_APP", "label": "냉장고보다 배달앱형"}
_JUDGMENT = {
    "crime": "냉장고 유기죄",
    "evidence": ["배달·외식 지출 184,000원", "배달·외식 결제 12회"],
    "verdict": "냉장고는 가구가 아닙니다.",
    "reasoning": "폴백 이유 문장.",
    "sentence": "폴백 형량 문장.",
}
_DEFENDANT = "박진수"


class TestDetectSplitBill(unittest.TestCase):
    def test_none_when_no_plea(self):
        self.assertIsNone(vs.detect_split_bill([]))
        self.assertIsNone(vs.detect_split_bill([{"storeName": "배민", "amount": 30000, "plea": ""}]))

    def test_detects_dutch_pay(self):
        exp = [{"storeName": "쿠팡이츠", "amount": 45000, "plea": "친구 4명 더치페이"}]
        out = vs.detect_split_bill(exp)
        self.assertIsNotNone(out)
        self.assertEqual(out["matchedCount"], 1)
        self.assertEqual(out["matchedTotal"], 45000)
        self.assertEqual(out["headcount"], 4)
        self.assertEqual(out["estimatedBurden"], 45000 // 4)
        self.assertIn("정상참작", out["note"])

    def test_default_headcount_two(self):
        exp = [{"storeName": "포차", "amount": 50000, "plea": "n빵함"}]
        out = vs.detect_split_bill(exp)
        self.assertEqual(out["headcount"], 2)
        self.assertEqual(out["estimatedBurden"], 25000)

    def test_multiple_matches_sum(self):
        exp = [
            {"storeName": "A", "amount": 30000, "plea": "3명 갹출"},
            {"storeName": "B", "amount": 20000, "plea": "회비"},
            {"storeName": "C", "amount": 99999, "plea": "그냥 혼밥"},
        ]
        out = vs.detect_split_bill(exp)
        self.assertEqual(out["matchedCount"], 2)
        self.assertEqual(out["matchedTotal"], 50000)
        self.assertEqual(out["headcount"], 3)


class TestMockPath(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"MOCK_AI": "1"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_returns_reasoning_and_sentence(self):
        out = vs.generate_verdict(_STATS, _CT, _JUDGMENT, _DEFENDANT, [])
        self.assertTrue(out["reasoning"])
        self.assertTrue(out["sentence"])
        self.assertIsNone(out["mitigation"])
        # 수치 인용 확인 (evidence 첫 항목이 들어감)
        self.assertIn("184,000원", out["reasoning"])
        # 피고인 이름 언급 확인
        self.assertIn(_DEFENDANT, out["reasoning"])

    def test_mock_reflects_mitigation(self):
        exp = [{"storeName": "쿠팡이츠", "amount": 45000, "plea": "친구 4명 더치페이"}]
        out = vs.generate_verdict(_STATS, _CT, _JUDGMENT, _DEFENDANT, exp)
        self.assertIsNotNone(out["mitigation"])
        self.assertIn("정상참작", out["reasoning"])

    def test_praise_tone(self):
        ct = {"code": "SMART_SOLO", "label": "야무진 자취생형"}
        out = vs.generate_verdict(_STATS, ct, _JUDGMENT, _DEFENDANT, [])
        self.assertIn("응원", out["sentence"])

    def test_backcompat_generate_reasoning(self):
        self.assertTrue(vs.generate_reasoning(_STATS, _CT, _JUDGMENT, _DEFENDANT))


class TestParseVerdict(unittest.TestCase):
    def test_plain_json(self):
        out = vs._parse_verdict('{"reasoning": "이유다.", "sentence": "형량이다."}')
        self.assertEqual(out, {"reasoning": "이유다.", "sentence": "형량이다."})

    def test_code_fenced(self):
        raw = "```json\n{\"reasoning\": \"이유다.\", \"sentence\": \"형량이다.\"}\n```"
        out = vs._parse_verdict(raw)
        self.assertEqual(out["sentence"], "형량이다.")

    def test_missing_field_raises(self):
        with self.assertRaises(Exception):
            vs._parse_verdict('{"reasoning": "이유만 있음"}')

    def test_too_long_raises(self):
        with self.assertRaises(Exception):
            vs._parse_verdict(json.dumps({"reasoning": "가" * 401, "sentence": "짧음"}))


class TestExtractText(unittest.TestCase):
    def test_skips_thinking_block(self):
        # Claude Sonnet 5: content[0]은 thinking, text는 뒤 블록
        result = {
            "content": [
                {"type": "thinking", "thinking": "흠 배달이 많군"},
                {"type": "text", "text": '{"reasoning": "a.", "sentence": "b."}'},
            ],
            "stop_reason": "end_turn",
        }
        self.assertEqual(vs._extract_text(result), '{"reasoning": "a.", "sentence": "b."}')

    def test_raises_when_no_text_block(self):
        with self.assertRaises(ValueError):
            vs._extract_text({"content": [{"type": "thinking", "thinking": "..."}]})


class TestBedrockPath(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"MOCK_AI": "0"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_uses_bedrock_output(self):
        fake = {"reasoning": "배달 42.6% 편중이 확인된다. 주방 사용 흔적이 없다.",
                "sentence": "배달앱 3일 삭제를 명한다."}
        with mock.patch.object(vs, "_call_bedrock", return_value=fake):
            out = vs.generate_verdict(_STATS, _CT, _JUDGMENT, _DEFENDANT, [])
        self.assertEqual(out["reasoning"], fake["reasoning"])
        self.assertEqual(out["sentence"], fake["sentence"])

    def test_falls_back_to_template_on_error(self):
        with mock.patch.object(vs, "_call_bedrock", side_effect=RuntimeError("bedrock down")):
            out = vs.generate_verdict(_STATS, _CT, _JUDGMENT, _DEFENDANT, [])
        self.assertEqual(out["reasoning"], _JUDGMENT["reasoning"])
        self.assertEqual(out["sentence"], _JUDGMENT["sentence"])

    def test_mitigation_passed_through_on_fallback(self):
        exp = [{"storeName": "포차", "amount": 60000, "plea": "5명 n빵"}]
        with mock.patch.object(vs, "_call_bedrock", side_effect=RuntimeError("x")):
            out = vs.generate_verdict(_STATS, _CT, _JUDGMENT, _DEFENDANT, exp)
        self.assertIsNotNone(out["mitigation"])
        self.assertEqual(out["mitigation"]["headcount"], 5)


if __name__ == "__main__":
    unittest.main()
