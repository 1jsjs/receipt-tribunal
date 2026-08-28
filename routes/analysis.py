"""분석 API — feat/analysis 브랜치 담당 (TASK-B014)

구현 기준: docs/05 §11(분석 규칙)·§12(응답 형식)·§13(판정)·§14(판결문)·§15(MZ)
"""
import re

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from services.analysis_service import calculate_monthly_stats, fetch_month_expenses
from services.judgment_service import determine_consumer_type, build_judgment
from services.verdict_service import generate_verdict
from services.reaction_data import get_reaction

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# YYYY-MM 형식 검증 정규식
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("")
def get_analysis(month: str | None = Query(None, description="조회 월 (YYYY-MM)")):
    """GET /api/analysis?month=YYYY-MM — 월 분석 통합 응답 (docs/05 §12)"""

    # ─── month 형식 검증 ───
    # 필수(...)로 두면 FastAPI가 422를 내므로 직접 검증해 400으로 통일
    if not month or not _MONTH_RE.match(month):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_MONTH",
                    "message": "month는 YYYY-MM 형식이어야 합니다.",
                },
            },
        )

    try:
        # 1) 월간 통계
        stats = calculate_monthly_stats(month)

        # 2) 소비 유형 판정
        consumer_type = determine_consumer_type(stats)

        # 3) 판결문 조립 (reasoning·sentence는 일단 템플릿 폴백)
        judgment = build_judgment(stats, consumer_type)

        # 4) 이유(reasoning)·형량(sentence)을 Bedrock(또는 MOCK/폴백)으로 교체
        #    memo(N빵·더치페이)는 원본 거래행에서 읽어 정상참작에 반영
        expenses = fetch_month_expenses(month)
        verdict = generate_verdict(stats, consumer_type, judgment, expenses)
        judgment["reasoning"] = verdict["reasoning"]
        judgment["sentence"] = verdict["sentence"]
        if verdict.get("mitigation"):
            judgment["evidence"] = list(judgment["evidence"]) + [
                f"정상참작: {verdict['mitigation']['note']}"
            ]

        # 5) MZ 리액션
        reaction_message = get_reaction(consumer_type["code"])

        # ─── docs/05 §12 형식 응답 조립 ───
        data = {
            "month": stats["month"],
            "totalExpense": stats["totalExpense"],
            "paymentCount": stats["paymentCount"],
            "averagePaymentAmount": stats["averagePaymentAmount"],
            "smallPaymentCount": stats["smallPaymentCount"],
            "largestSingleExpense": stats["largestSingleExpense"],
            "topCategory": stats["topCategory"],
            "categoryStats": stats["categoryStats"],
            "consumerType": consumer_type,
            "judgment": judgment,
            "reactionMessage": reaction_message,
        }

        return {"success": True, "data": data}

    except Exception as e:
        # 예상 밖 예외 → 500 (빈 화면 금지)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": f"분석 처리 중 오류가 발생했습니다: {str(e)}",
                },
            },
        )
