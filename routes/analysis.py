"""분석 API — feat/analysis 브랜치 담당 (TASK-B014)

구현 기준: docs/05 §11(분석 규칙)·§12(응답 형식)·§13(판정)·§14(판결문)·§15(MZ)
"""
import re

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from services.analysis_service import calculate_monthly_stats, get_month_context
from services.judgment_service import determine_consumer_type, build_judgment
from services.verdict_service import generate_reasoning
from services.reaction_data import get_reaction

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# YYYY-MM 형식 검증 정규식
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("")
def get_analysis(
    month: str = Query(None, description="조회 월 (YYYY-MM)"),
    defendant: str = Query(None, description="피고인 이름 (생략하면 그 달 기록에서 자동 결정)"),
):
    """GET /api/analysis?month=YYYY-MM — 월 분석 통합 응답 (docs/05 §12)"""

    # ─── month 형식 검증 ───
    if not isinstance(month, str) or not _MONTH_RE.match(month):
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

        # 2-1) 피고인 이름 — 쿼리로 받은 값 우선, 없으면 그 달 기록에서 결정
        context = get_month_context(month)
        defendant_name = (defendant or "").strip() or context["defendant"]

        # 3) 판결문 조립 (reasoning은 일단 폴백)
        judgment = build_judgment(stats, consumer_type)

        # 4) reasoning을 Bedrock(또는 MOCK/폴백)으로 교체
        judgment["reasoning"] = generate_reasoning(
            stats, consumer_type, judgment, defendant_name
        )

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
            "defendant": defendant_name,
            # 상호명 대신 예금주 이름만 있어 사용자가 정리해야 하는 건수
            "needsReviewCount": context["needsReviewCount"],
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
