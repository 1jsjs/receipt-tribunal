"""지출내역 파일 파싱 — 엑셀/CSV/PDF → 표준 거래 JSON

흐름: 파일에서 원시 행 추출(pandas·pdfplumber) → Bedrock으로 정규화·분류 → 표준 JSON

설계 원칙
- 은행·카드사별 전용 파서를 만들지 않는다. 컬럼명이 제각각이므로 원시 추출만 하고
  표준 스키마로 맞추는 일은 Bedrock에 맡긴다.
- Bedrock이 실패해도 빈 화면이 되면 안 된다 → 규칙 기반 폴백으로 최대한 살린다.
- MOCK_AI=1이면 Bedrock을 부르지 않고 폴백 로직만 쓴다 (로컬은 자격증명이 없다).
"""

import io
import json
import os
import re
from datetime import datetime

from constants import CATEGORIES, CATEGORY_OTHER, TRANSACTION_TYPE_EXPENSE, TRANSACTION_TYPE_TRANSFER

MODEL_ID = "global.anthropic.claude-sonnet-5"

# 한 번에 처리할 최대 행 수 (프롬프트 길이·비용 방어)
MAX_ROWS = 120

# 업로드 허용 확장자
SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".csv", ".pdf")


# ─────────────────────── 1단계: 원시 추출 ───────────────────────

def _read_tabular(filename: str, content: bytes) -> list[dict]:
    """엑셀·CSV에서 원시 행을 뽑는다. 컬럼명은 파일마다 다르므로 그대로 둔다."""
    import pandas as pd

    lower = filename.lower()
    if lower.endswith(".csv"):
        # 한국 은행 CSV는 cp949(euc-kr)인 경우가 많다
        for encoding in ("utf-8-sig", "cp949", "utf-8"):
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            raise ValueError("CSV 인코딩을 인식할 수 없습니다 (utf-8·cp949 시도함).")
    else:
        df = pd.read_excel(io.BytesIO(content))

    # 헤더가 위쪽 안내문 아래에 있는 경우가 흔하다.
    # 컬럼명이 'Unnamed'투성이면 실제 헤더 행을 찾아 다시 읽는다.
    unnamed = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
    if unnamed >= max(2, len(df.columns) // 2):
        header_row = _guess_header_row(df)
        if header_row is not None:
            df.columns = df.iloc[header_row]
            df = df.iloc[header_row + 1:].reset_index(drop=True)

    df = df.dropna(how="all")
    return [
        {str(k): ("" if _is_blank(v) else str(v)) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _is_blank(value) -> bool:
    """NaN·None·빈 문자열 판정 (pandas import 없이 쓰기 위해 문자열로 비교)."""
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in ("", "nan", "nat", "none")


def _guess_header_row(df) -> int | None:
    """날짜·금액 같은 헤더 키워드가 가장 많이 등장하는 행을 헤더로 추정한다."""
    keywords = ("날짜", "일자", "거래", "금액", "가맹점", "내용", "적요", "상호", "사용")
    best_row, best_hits = None, 0
    for i in range(min(10, len(df))):
        cells = [str(c) for c in df.iloc[i].tolist()]
        hits = sum(1 for c in cells for k in keywords if k in c)
        if hits > best_hits:
            best_row, best_hits = i, hits
    return best_row if best_hits >= 2 else None


def _read_pdf(content: bytes) -> list[dict]:
    """PDF에서 표를 우선 추출하고, 표가 없으면 텍스트 줄을 그대로 넘긴다.

    스캔본(이미지 PDF)은 pdfplumber가 아무것도 못 뽑는다 → 빈 리스트를 반환하고
    호출 측에서 안내 메시지를 낸다. (비전 폴백은 이번 범위에서 제외)
    """
    import pdfplumber

    rows: list[dict] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                if not table:
                    continue
                header = [str(c or "").strip() for c in table[0]]
                for raw in table[1:]:
                    cells = [str(c or "").strip() for c in raw]
                    if not any(cells):
                        continue
                    rows.append({header[i] if i < len(header) and header[i] else f"col{i}": cells[i]
                                 for i in range(len(cells))})
            if not rows:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    line = line.strip()
                    # 날짜와 숫자가 같이 있는 줄만 거래로 취급
                    if line and re.search(r"\d{2,4}[-./]\d{1,2}[-./]\d{1,2}", line) and re.search(r"\d{3,}", line):
                        rows.append({"line": line})
    return rows


def extract_rows(filename: str, content: bytes) -> list[dict]:
    """확장자에 따라 원시 행을 추출한다."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _read_pdf(content)
    if lower.endswith((".xlsx", ".xls", ".csv")):
        return _read_tabular(filename, content)
    raise ValueError(f"지원하지 않는 형식입니다. {', '.join(SUPPORTED_EXTENSIONS)}만 가능합니다.")
