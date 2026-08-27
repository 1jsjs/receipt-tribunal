"""분석 API — feat/analysis 브랜치 담당 (TASK-B014)

구현 기준: docs/05 §11(분석 규칙)·§12(응답 형식)·§13(판정)·§14(판결문)·§15(MZ)
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# TODO(feat/analysis): GET /?month=YYYY-MM — 통계+판정+판결문+MZ 통합 응답 (docs/05 §12)
