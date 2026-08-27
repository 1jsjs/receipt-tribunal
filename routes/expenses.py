"""expenses CRUD API — feat/crud 브랜치 담당 (TASK-B004~B008)

구현 기준: docs/05 §9(API)·§10(검증)·§4(필드명 계약 — camelCase 응답)
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

# TODO(feat/crud): POST /       — 저장 (검증 포함)
# TODO(feat/crud): GET  /?month=YYYY-MM — 월별 조회 (날짜 내림차순)
# TODO(feat/crud): GET  /{id}  — 단건 조회
# TODO(feat/crud): PUT  /{id}  — 수정
# TODO(feat/crud): DELETE /{id} — 삭제
