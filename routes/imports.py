"""지출내역 파일 업로드 API — POST /api/import

엑셀·CSV·PDF를 올리면 거래를 뽑아 expenses 테이블에 저장한다.

경로를 /api/expenses/import 로 두지 않은 이유: routes/expenses.py의
GET /api/expenses/{id} 가 "import"를 id로 잡아먹기 때문이다.
"""
from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from db import get_connection, DEFAULT_DEFENDANT, DEFENDANT_MAX
from services.parse_service import SUPPORTED_EXTENSIONS, parse_file

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    """공통 에러 응답 (docs/05 §9) — expenses 라우터와 같은 형식"""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _save_all(items: list[dict], defendant: str) -> int:
    """파싱된 거래를 한 트랜잭션으로 저장하고 저장 건수를 돌려준다."""
    if not items:
        return 0
    conn = get_connection()
    try:
        conn.executemany(
            """INSERT INTO expenses
                 (store_name, date, amount, category, transaction_type,
                  defendant, memo, needs_review, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, '', ?, datetime('now'), datetime('now'))""",
            [
                (i["storeName"], i["date"], i["amount"], i["category"], i["transactionType"],
                 defendant, 1 if i.get("needsReview") else 0)
                for i in items
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return len(items)


@router.post("")
async def import_expenses(
    file: UploadFile = File(None),
    defendant: str = Form(None, description="피고인 이름 (10자 이내, 생략하면 기본 피고인)"),
    dryRun: str = Query("false", description="true면 파싱만 하고 저장하지 않는다"),
):
    """POST /api/import — 지출내역 파일을 파싱해 저장한다.

    응답 data: {imported, parsed, source, rawRowCount, items, warning}
      - source: bedrock | rules(fallback) | rules(mock) | empty
      - dryRun=true면 imported=0, items만 돌려준다 (프론트 미리보기용)
    """
    # File(...)로 필수 지정하면 FastAPI가 422를 낸다 → 공통 에러 형식(400)으로 통일
    if file is None:
        return _error("FILE_REQUIRED", "업로드할 파일이 없습니다.", 400)

    filename = file.filename or ""
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        return _error(
            "UNSUPPORTED_FILE",
            f"지원하지 않는 형식입니다. {', '.join(SUPPORTED_EXTENSIONS)}만 업로드할 수 있습니다.",
            400,
        )

    # 피고인 이름 — 사용자가 직접 입력. 말없이 자르지 않고 넘치면 알린다.
    if defendant is None or not str(defendant).strip():
        defendant = DEFAULT_DEFENDANT
    else:
        defendant = str(defendant).strip()
        if len(defendant) > DEFENDANT_MAX:
            return _error(
                "INVALID_DEFENDANT", f"피고인 이름은 최대 {DEFENDANT_MAX}자입니다.", 400
            )

    content = await file.read()
    if not content:
        return _error("EMPTY_FILE", "빈 파일입니다.", 400)
    if len(content) > MAX_FILE_BYTES:
        return _error("FILE_TOO_LARGE", "파일이 너무 큽니다. 10MB 이하만 올릴 수 있습니다.", 400)

    try:
        parsed = parse_file(filename, content)
    except Exception as e:
        # 파싱 자체가 깨져도 서버가 500으로 죽지 않게 한다
        return _error("PARSE_FAILED", f"파일을 읽지 못했습니다: {e}", 400)

    items = parsed["items"]
    is_dry_run = str(dryRun).lower() == "true"
    imported = 0 if is_dry_run else _save_all(items, defendant)

    return {
        "success": True,
        "data": {
            "imported": imported,
            "parsed": len(items),
            "defendant": defendant,
            # 상호명 대신 예금주 이름만 있어 사용자가 직접 정리해야 하는 건수
            "needsReviewCount": sum(1 for i in items if i.get("needsReview")),
            "source": parsed["source"],
            "rawRowCount": parsed["rawRowCount"],
            "items": items,
            "warning": parsed["warning"],
        },
    }
