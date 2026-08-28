"""영수증 소비 재판소 — FastAPI 엔트리 (스켈레톤)

규칙: 모든 /api 라우터를 먼저 등록하고, static 마운트는 반드시 맨 마지막에 한다.
(순서가 바뀌면 /api 전체가 404가 된다 — docs/05 §3 참고)
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from db import init_db
from routes.expenses import router as expenses_router
from routes.analysis import router as analysis_router
from routes.imports import router as imports_router

app = FastAPI(title="영수증 소비 재판소")


@app.on_event("startup")
def _startup():
    """서버 시작 시 DB 테이블 생성 (기존 데이터 보존)"""
    init_db()


@app.get("/api/health")
def health():
    """서버 생존 확인용"""
    return {"success": True, "data": {"message": "server is running"}}


# ─── API 라우터 등록 (static 마운트보다 반드시 먼저) ───
app.include_router(expenses_router)   # feat/crud 담당
app.include_router(analysis_router)   # feat/analysis 담당
app.include_router(imports_router)    # 지출내역 파일 업로드

# ─── 정적 파일 서빙 — 반드시 파일 맨 마지막 ───
_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="static")
