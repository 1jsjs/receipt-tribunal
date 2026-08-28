"""GET /api/analysis 통합 — 격리된 임시 DB에 소량 데이터를 넣고 응답 전체를 검증.

실제 시드(data/database.sqlite 77건)는 건드리지 않는다. db.DB_PATH를 tmp로 갈아끼운다.
MOCK_AI=1 이므로 판결문 이유·형량은 템플릿/모의값이다 (Bedrock 미호출).

확인 대상: 응답 계약(키 15개), benchmark 방향·출처, remark 발화 조건,
           judgment.sentence 채워짐, 정상참작(plea) evidence 반영.

    MOCK_AI=1 python3 -m unittest tests.test_analysis_integration -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("MOCK_AI", "1")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import db  # noqa: E402


def _insert(conn, rows):
    for r in rows:
        conn.execute(
            """INSERT INTO expenses
                 (store_name, date, amount, category, transaction_type,
                  defendant, memo, plea, needs_review, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))""",
            (r["store"], r["date"], r["amount"], r["category"], r.get("tx", "EXPENSE"),
             r.get("defendant", "익명의 자취생"), r.get("memo", ""), r.get("plea", ""),
             r.get("needs_review", 0)),
        )
    conn.commit()


class AnalysisIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="analysis_it_")
        cls._patchers = [
            mock.patch.object(db, "DATA_DIR", Path(cls._tmp)),
            mock.patch.object(db, "DB_PATH", Path(cls._tmp) / "test.sqlite"),
        ]
        for p in cls._patchers:
            p.start()
        db.init_db()

        conn = db.get_connection()
        # 2026-09: 배달 편중 + N빵 plea 1건
        _insert(conn, [
            {"store": "배달의민족", "date": "2026-09-02", "amount": 40000, "category": "DELIVERY_DINING"},
            {"store": "쿠팡이츠", "date": "2026-09-06", "amount": 60000, "category": "DELIVERY_DINING",
             "plea": "친구 5명이서 시켜서 n빵함"},
            {"store": "GS25", "date": "2026-09-09", "amount": 8000, "category": "CONVENIENCE_STORE"},
            {"store": "스타벅스", "date": "2026-09-11", "amount": 6000, "category": "CAFE_SNACK"},
            {"store": "김한생", "date": "2026-09-15", "amount": 300000, "category": "OTHER",
             "tx": "TRANSFER"},  # 정체불명 송금 → remark 유도
        ])
        conn.close()
        cls.client = _make_client()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patchers:
            p.stop()

    def _data(self, month="2026-09", **q):
        qs = "&".join(f"{k}={v}" for k, v in q.items())
        url = f"/api/analysis?month={month}" + (f"&{qs}" if qs else "")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["success"])
        return body["data"]

    def test_response_contract_keys(self):
        d = self._data()
        expected = {
            "month", "totalExpense", "paymentCount", "averagePaymentAmount",
            "smallPaymentCount", "largestSingleExpense", "topCategory", "categoryStats",
            "consumerType", "judgment", "reactionMessage", "defendant",
            "benchmark", "remark", "needsReviewCount",
        }
        self.assertEqual(set(d.keys()), expected)
        for k in ("crime", "evidence", "verdict", "reasoning", "sentence"):
            self.assertIn(k, d["judgment"])
        self.assertTrue(d["judgment"]["sentence"], "형량이 비어 있으면 안 된다")

    def test_transfer_excluded_from_totals(self):
        d = self._data()
        # 30만원 송금(TRANSFER)은 총지출에서 빠진다
        self.assertEqual(d["totalExpense"], 40000 + 60000 + 8000 + 6000)

    def test_benchmark_direction_and_source(self):
        d = self._data()
        b = d["benchmark"]
        self.assertIsNotNone(b)
        self.assertEqual(b["groupLabel"], "전국 1인가구 평균")
        self.assertIn("국가데이터처", b["source"])
        self.assertTrue(b["isEstimated"])
        # 배달 100,000 vs 기준 246,000 → 덜 씀
        self.assertEqual(b["category"], "DELIVERY_DINING")
        self.assertEqual(b["direction"], "under")
        self.assertIn("적게 썼습니다", b["headline"])

    def test_remark_fires_on_unknown_transfer(self):
        d = self._data()
        r = d["remark"]
        self.assertIsNotNone(r, "정체불명 송금 30만원이 전체의 대부분 → remark 발화해야 함")
        self.assertGreaterEqual(r["ratio"], 50.0)
        self.assertEqual(r["level"], "severe")
        self.assertEqual(r["amount"], 300000)
        self.assertIn("정체 불명", r["message"])

    def test_plea_split_bill_reflected_in_evidence(self):
        d = self._data()
        joined = " ".join(d["judgment"]["evidence"])
        self.assertIn("정상참작", joined)
        self.assertIn("5명", joined)

    def test_empty_month_has_null_benchmark_and_remark(self):
        d = self._data(month="2026-01")
        self.assertIsNone(d["benchmark"])
        self.assertIsNone(d["remark"])
        self.assertEqual(d["consumerType"]["code"], "BALANCED")

    def test_invalid_month_is_400_common_format(self):
        res = self.client.get("/api/analysis?month=2026-13")
        self.assertEqual(res.status_code, 400)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "INVALID_MONTH")


def _make_client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


if __name__ == "__main__":
    unittest.main()
