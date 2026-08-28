"""Bedrock 요청·응답 계약 회귀 테스트 — 실측으로 두 번 당한 사고 재발 방지.

로컬 MOCK_AI=1은 Bedrock을 아예 부르지 않으므로 요청 형식 오류를 못 잡는다
(.kiro/steering/tech-constraints.md §5). 여기서는 boto3.client를 가짜로 바꿔치기해
_call_bedrock이 **실제로 조립하는 요청 body**를 붙잡아 검사한다.

지키는 계약:
  1. temperature·top_p 를 넣지 않는다        (§2 — Sonnet 5가 거부 → 조용한 폴백)
  2. modelId 는 global. 접두사 포함             (§확정 스택)
  3. region_name 을 코드에서 지정하지 않는다   (환경변수 AWS_DEFAULT_REGION)
  4. 응답 content[0]이 thinking이어도 text 블록을 찾아낸다  (§1)

    python3 -m unittest tests.test_bedrock_contract -v
"""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from services import parse_service, verdict_service  # noqa: E402


class _FakeBody:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw


class _FakeBedrockClient:
    """invoke_model 호출을 기록하고, 미리 정한 응답을 돌려준다."""

    def __init__(self, response_payload: dict):
        self.calls: list[dict] = []
        self._response_payload = response_payload

    def invoke_model(self, **kwargs):
        body = json.loads(kwargs["body"])
        self.calls.append({"modelId": kwargs.get("modelId"), "body": body})
        return {"body": _FakeBody(self._response_payload)}


def _thinking_then_text(text: str) -> dict:
    """content[0]에 thinking, content[1]에 실제 text가 오는 Sonnet 5 응답 모양."""
    return {
        "content": [
            {"type": "thinking", "thinking": "음 이건 배달이 좀 많네..."},
            {"type": "text", "text": text},
        ],
        "stop_reason": "end_turn",
    }


_STATS = {
    "month": "2026-08", "totalExpense": 432000, "paymentCount": 42, "smallPaymentCount": 21,
    "largestSingleExpense": {"amount": 89000, "storeName": "무신사", "date": "2026-08-21",
                             "category": "SHOPPING_HOBBY"},
    "categoryStats": [
        {"category": "DELIVERY_DINING", "label": "배달·외식", "amount": 184000, "percentage": 42.6, "count": 12},
    ],
}
_CT = {"code": "DELIVERY_APP", "label": "냉장고보다 배달앱형"}
_JUDGMENT = {"crime": "냉장고 유기죄", "evidence": ["배달·외식 지출 184,000원"],
             "verdict": "냉장고는 가구가 아닙니다.", "reasoning": "폴백.", "sentence": "폴백 형량."}


def _assert_common_contract(tc: unittest.TestCase, call: dict, expect_system: bool):
    body = call["body"]
    # 1. 샘플링 파라미터 금지
    tc.assertNotIn("temperature", body, "temperature 를 넣으면 Sonnet 5가 요청을 거부한다")
    tc.assertNotIn("top_p", body, "top_p 를 넣으면 Sonnet 5가 요청을 거부한다")
    # 2. 모델 ID
    tc.assertEqual(call["modelId"], "global.anthropic.claude-sonnet-5")
    # 3. 필수 키
    tc.assertEqual(body.get("anthropic_version"), "bedrock-2023-05-31")
    tc.assertIsInstance(body.get("max_tokens"), int)
    tc.assertIn("messages", body)
    if expect_system:
        tc.assertIn("system", body)


class VerdictServiceContractTest(unittest.TestCase):
    def _run(self, response_payload):
        fake = _FakeBedrockClient(response_payload)
        with mock.patch.dict("os.environ", {"MOCK_AI": "0"}), \
             mock.patch("boto3.client", return_value=fake) as client_ctor:
            out = verdict_service.generate_verdict(_STATS, _CT, _JUDGMENT, "박진수", [])
        return out, fake, client_ctor

    def test_request_shape(self):
        payload = _thinking_then_text(json.dumps(
            {"reasoning": "배달 42.6% 편중이 확인된다. 주방 흔적이 없다.",
             "sentence": "배달앱 3일 삭제를 명한다."}, ensure_ascii=False))
        out, fake, client_ctor = self._run(payload)

        self.assertEqual(len(fake.calls), 1)
        _assert_common_contract(self, fake.calls[0], expect_system=True)
        # region_name 을 코드에서 넘기지 않는다 (환경변수 사용)
        _, kwargs = client_ctor.call_args
        self.assertNotIn("region_name", kwargs)

    def test_parses_text_block_after_thinking(self):
        payload = _thinking_then_text(json.dumps(
            {"reasoning": "배달·외식에 184,000원을 쏟았다. 주방은 방치되었다.",
             "sentence": "다음 달 배달 2회로 제한할 것을 명한다."}, ensure_ascii=False))
        out, _, _ = self._run(payload)
        self.assertIn("184,000원", out["reasoning"])
        self.assertTrue(out["sentence"].endswith("명한다."))

    def test_falls_back_when_only_thinking_block(self):
        # text 블록이 아예 없으면 예외 → 폴백 템플릿
        out, fake, _ = self._run({"content": [{"type": "thinking", "thinking": "..."}],
                                  "stop_reason": "max_tokens"})
        self.assertEqual(out["reasoning"], _JUDGMENT["reasoning"])
        self.assertEqual(out["sentence"], _JUDGMENT["sentence"])
        self.assertEqual(len(fake.calls), 2)  # 1회 재시도 후 폴백


class ParseServiceContractTest(unittest.TestCase):
    _RAW_ROWS = [
        {"거래일자": "2026-08-02", "적요": "배달의민족", "금액": "32,000"},
        {"거래일자": "2026-08-03", "적요": "스타벅스 역삼", "금액": "6,500"},
    ]

    def _run(self, response_payload):
        fake = _FakeBedrockClient(response_payload)
        with mock.patch.dict("os.environ", {"MOCK_AI": "0"}), \
             mock.patch("boto3.client", return_value=fake) as client_ctor:
            items, source = parse_service.normalize(self._RAW_ROWS)
        return items, source, fake, client_ctor

    def test_request_shape(self):
        arr = json.dumps([
            {"storeName": "배달의민족", "date": "2026-08-02", "amount": 32000,
             "category": "DELIVERY_DINING", "transactionType": "EXPENSE", "needsReview": False},
            {"storeName": "스타벅스 역삼", "date": "2026-08-03", "amount": 6500,
             "category": "CAFE_SNACK", "transactionType": "EXPENSE", "needsReview": False},
        ], ensure_ascii=False)
        items, source, fake, client_ctor = self._run(_thinking_then_text(arr))

        self.assertEqual(source, "bedrock")
        self.assertEqual(len(fake.calls), 1)
        _assert_common_contract(self, fake.calls[0], expect_system=False)
        _, kwargs = client_ctor.call_args
        self.assertNotIn("region_name", kwargs)

    def test_parses_json_array_after_thinking(self):
        arr = json.dumps([
            {"storeName": "배달의민족", "date": "2026-08-02", "amount": 32000,
             "category": "DELIVERY_DINING", "transactionType": "EXPENSE", "needsReview": False},
        ], ensure_ascii=False)
        items, source, _, _ = self._run(_thinking_then_text("```json\n" + arr + "\n```"))
        self.assertEqual(source, "bedrock")
        self.assertEqual(items[0]["storeName"], "배달의민족")
        self.assertEqual(items[0]["category"], "DELIVERY_DINING")

    def test_falls_back_to_rules_when_no_text_block(self):
        items, source, _, _ = self._run({"content": [{"type": "thinking", "thinking": "x"}]})
        # 규칙 폴백으로라도 결과가 나와야 한다 (업로드 통째 실패 금지)
        self.assertEqual(source, "rules(fallback)")
        self.assertTrue(items)
        self.assertEqual(items[0]["category"], "DELIVERY_DINING")  # 키워드 규칙


if __name__ == "__main__":
    unittest.main()
