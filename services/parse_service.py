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

from constants import (
    CATEGORIES,
    CATEGORY_CAFE_SNACK,
    CATEGORY_CONVENIENCE_STORE,
    CATEGORY_DELIVERY_DINING,
    CATEGORY_GROCERIES,
    CATEGORY_OTHER,
    CATEGORY_SHOPPING_HOBBY,
    TRANSACTION_TYPE_EXPENSE,
    TRANSACTION_TYPE_TRANSFER,
    TRANSACTION_TYPES,
)

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


def _split_text_line(line: str) -> dict:
    """PDF 텍스트 한 줄을 날짜·적요·금액으로 쪼갠다.

    은행 거래내역은 "2026.10.02 배달의민족 19,800 1,230,400"처럼
    한 줄에 날짜·적요·출금액·잔액이 붙어 나온다. 통째로 두면 금액 추출이
    실패하므로(숫자가 섞여 float 변환이 깨진다) 여기서 미리 나눈다.

    금액이 여러 개면 첫 번째를 거래금액으로 본다 (뒤쪽은 대개 잔액).
    """
    date_match = re.search(r"\d{2,4}[-./]\d{1,2}[-./]\d{1,2}", line)
    date = date_match.group(0) if date_match else ""
    rest = line[date_match.end():] if date_match else line

    # 1,234 / 1234 형태의 금액 토큰 (3자리 이상)
    amounts = re.findall(r"[\d,]{3,}", rest)
    amounts = [a for a in amounts if re.sub(r"[^\d]", "", a)]

    # 적요 = 첫 금액 앞의 텍스트
    memo = rest
    if amounts:
        cut = rest.find(amounts[0])
        if cut > 0:
            memo = rest[:cut]

    return {
        "거래일자": date,
        "적요": memo.strip(),
        "금액": amounts[0] if amounts else "",
    }


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
                        parsed_line = _split_text_line(line)
                        # 상호명 자리에 글자가 없으면 거래가 아니다
                        # (예: "조회기간 2026.10.01 ~ 2026.10.31" → 적요가 "~"만 남음)
                        if re.search(r"[가-힣A-Za-z]", parsed_line["적요"]):
                            rows.append(parsed_line)
    return rows


def extract_rows(filename: str, content: bytes) -> list[dict]:
    """확장자에 따라 원시 행을 추출한다."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _read_pdf(content)
    if lower.endswith((".xlsx", ".xls", ".csv")):
        return _read_tabular(filename, content)
    raise ValueError(f"지원하지 않는 형식입니다. {', '.join(SUPPORTED_EXTENSIONS)}만 가능합니다.")


# ─────────────────── 2단계: 규칙 기반 정규화 (폴백) ───────────────────

# 상호명 키워드 → 카테고리. 위에서부터 먼저 걸리는 것을 채택한다.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (CATEGORY_DELIVERY_DINING, (
        "배달", "배민", "쿠팡이츠", "요기요", "땡겨요", "식당", "국밥", "김밥", "치킨", "피자",
        "분식", "음식", "마라", "버거", "맥도날드", "롯데리아", "서브웨이", "돈까스", "칼국수",
        "쌀국수", "초밥", "회집", "곱창", "삼겹", "떡볶이", "food",
    )),
    (CATEGORY_CONVENIENCE_STORE, (
        "gs25", "cu ", "씨유", "세븐일레븐", "7-eleven", "이마트24", "미니스톱", "편의점", "storyway",
    )),
    (CATEGORY_CAFE_SNACK, (
        "카페", "커피", "스타벅스", "starbucks", "투썸", "이디야", "메가커피", "컴포즈", "빽다방",
        "파리바게", "뚜레쥬르", "베이커리", "디저트", "아이스크림", "배스킨", "공차", "cafe",
    )),
    (CATEGORY_GROCERIES, (
        "마트", "이마트", "홈플러스", "롯데마트", "하나로", "농협", "정육", "청과", "수산",
        "슈퍼", "생협", "한살림", "식자재",
    )),
    (CATEGORY_SHOPPING_HOBBY, (
        "무신사", "쿠팡", "11번가", "지마켓", "옥션", "올리브영", "다이소", "교보문고", "알라딘",
        "cgv", "메가박스", "롯데시네마", "영화", "넷플릭스", "스팀", "steam", "게임", "문구",
        "화장품", "의류", "패션",
    )),
]

# 이체·송금으로 볼 키워드
_TRANSFER_KEYWORDS = (
    "이체", "송금", "atm", "출금", "입금", "계좌", "자동납부", "카드대금", "대출", "월세", "보증금",
)

# 헤더 이름에서 역할을 추정할 때 쓰는 키워드
_DATE_HEADERS = ("날짜", "일자", "거래일", "승인일", "이용일", "date", "거래일시")
_NAME_HEADERS = ("가맹점", "상호", "내용", "적요", "이용처", "사용처", "store", "merchant", "비고")
_AMOUNT_HEADERS = ("금액", "출금", "사용금액", "승인금액", "결제금액", "amount", "합계")


def _norm_date(value: str) -> str | None:
    """다양한 날짜 표기를 YYYY-MM-DD로 바꾼다. 실패하면 None."""
    text = str(value).strip()
    if not text:
        return None
    # 2026-08-15 14:30:00 같은 값에서 앞부분만
    match = re.search(r"(\d{4})[-./년\s]+(\d{1,2})[-./월\s]+(\d{1,2})", text)
    if match:
        y, m, d = match.groups()
    else:
        # 20260815
        match = re.search(r"\b(\d{4})(\d{2})(\d{2})\b", text)
        if not match:
            return None
        y, m, d = match.groups()
    try:
        return datetime(int(y), int(m), int(d)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _norm_amount(value: str) -> int | None:
    """1,200원 / -3500 / 3,500.00 → 정수. 실패하면 None."""
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^\d.\-]", "", text)
    if not text or text in ("-", ".", "-."):
        return None
    try:
        amount = int(round(abs(float(text))))
    except ValueError:
        return None
    return amount if amount >= 1 else None


def _guess_category(store_name: str) -> str:
    lowered = store_name.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(k in lowered for k in keywords):
            return category
    return CATEGORY_OTHER


def _guess_transaction_type(store_name: str, row_text: str) -> str:
    haystack = f"{store_name} {row_text}".lower()
    if any(k in haystack for k in _TRANSFER_KEYWORDS):
        return TRANSACTION_TYPE_TRANSFER
    return TRANSACTION_TYPE_EXPENSE


def _pick_by_header(row: dict, candidates: tuple[str, ...]) -> str | None:
    """헤더 이름에 키워드가 포함된 컬럼의 값을 돌려준다."""
    for key, value in row.items():
        lowered = str(key).lower()
        if any(c in lowered for c in candidates) and str(value).strip():
            return str(value)
    return None


def _rule_normalize(raw_rows: list[dict]) -> list[dict]:
    """헤더 키워드와 값 패턴으로 표준 스키마를 맞춘다 (Bedrock 실패 시 폴백)."""
    items: list[dict] = []
    for row in raw_rows:
        values = list(row.values())
        row_text = " ".join(str(v) for v in values)

        # 날짜: 헤더로 먼저, 없으면 아무 값에서나 날짜 패턴 탐색
        date = _norm_date(_pick_by_header(row, _DATE_HEADERS) or "")
        if not date:
            for v in values:
                date = _norm_date(v)
                if date:
                    break
        if not date:
            continue

        # 금액: 헤더로 먼저, 없으면 값 중 가장 큰 수
        amount = _norm_amount(_pick_by_header(row, _AMOUNT_HEADERS) or "")
        if not amount:
            candidates = [a for a in (_norm_amount(v) for v in values) if a]
            # 날짜에서 뽑힌 숫자(20260815 등)를 금액으로 오인하지 않도록 제외
            candidates = [a for a in candidates if a < 10_000_000]
            amount = max(candidates) if candidates else None
        if not amount:
            continue

        # 상호명: 헤더로 먼저, 없으면 한글·영문이 섞인 가장 긴 값
        store = _pick_by_header(row, _NAME_HEADERS)
        if not store:
            texts = [str(v).strip() for v in values if re.search(r"[가-힣A-Za-z]", str(v))]
            texts = [t for t in texts if not _norm_date(t)]
            store = max(texts, key=len) if texts else "미상"
        store = store.strip()[:100] or "미상"

        items.append({
            "storeName": store,
            "date": date,
            "amount": amount,
            "category": _guess_category(store),
            "transactionType": _guess_transaction_type(store, row_text),
        })
    return items


# ─────────────────── 3단계: Bedrock 정규화 ───────────────────

_NORMALIZE_INSTRUCTION = """당신은 한국 은행·카드사의 지출내역 데이터를 표준 형식으로 정리하는 도구입니다.

아래 원시 거래 행들을 표준 JSON 배열로 변환하세요.

각 원소는 정확히 이 5개 키를 가집니다:
- storeName: 상호명/가맹점명 (문자열, 최대 100자)
- date: "YYYY-MM-DD" (연도가 없으면 2026으로 가정)
- amount: 양의 정수 (원 단위, 콤마·원 표기 제거, 음수는 절댓값)
- category: 다음 6개 중 하나
    DELIVERY_DINING(배달·외식), CONVENIENCE_STORE(편의점), CAFE_SNACK(카페·간식),
    GROCERIES(식재료·생필품), SHOPPING_HOBBY(쇼핑·취미), OTHER(기타)
- transactionType: "EXPENSE" 또는 "TRANSFER"
    이체·송금·ATM출금·카드대금·월세처럼 실제 소비가 아닌 자금 이동은 TRANSFER,
    나머지 실제 소비는 EXPENSE

규칙:
- 거래로 볼 수 없는 행(합계, 소계, 안내문, 빈 행)은 결과에서 제외하세요.
- 날짜나 금액을 알 수 없는 행도 제외하세요.
- 카테고리는 상호명을 보고 판단하세요. 애매하면 OTHER를 쓰세요.
- 설명·주석·마크다운 없이 JSON 배열만 출력하세요. 배열 외의 텍스트를 쓰지 마세요."""


def _extract_json_array(text: str) -> list:
    """모델 응답에서 JSON 배열을 꺼낸다 (```json 펜스가 붙어도 처리)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON 배열을 찾지 못했습니다.")
    return json.loads(cleaned[start:end + 1])


def _call_bedrock(prompt: str) -> str:
    """Bedrock 호출 후 text 블록만 뽑는다.

    주의: Claude Sonnet 5는 content[0]에 thinking 블록을 반환할 수 있다.
    content[0]["text"]로 꺼내면 KeyError가 난다 (verdict_service에서 같은 버그를 겪었음).
    """
    import boto3

    client = boto3.client("bedrock-runtime")  # region은 환경변수 사용 (하드코딩 금지)
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = client.invoke_model(
        modelId=MODEL_ID, contentType="application/json", accept="application/json", body=body
    )
    result = json.loads(response["body"].read())

    for block in result.get("content", []):
        if block.get("type") == "text" and block.get("text"):
            return block["text"].strip()

    types = [b.get("type") for b in result.get("content", [])]
    raise ValueError(f"응답에 text 블록이 없습니다 (blocks={types}, stop={result.get('stop_reason')})")


def _sanitize(items: list) -> list[dict]:
    """모델이 준 결과를 계약(docs/05 §4)에 맞게 최종 검사·보정한다.

    모델을 믿지 않는다. 카테고리 오타·잘못된 날짜·음수 금액이 그대로 DB에 들어가면
    분석이 통째로 틀어지므로 여기서 전부 걸러낸다.
    """
    cleaned: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        store = str(item.get("storeName", "")).strip()[:100]
        date = _norm_date(item.get("date", ""))
        amount = _norm_amount(item.get("amount", ""))
        if not store or not date or not amount:
            continue
        category = item.get("category")
        if category not in CATEGORIES:
            category = _guess_category(store)
        transaction_type = item.get("transactionType")
        if transaction_type not in TRANSACTION_TYPES:
            transaction_type = _guess_transaction_type(store, store)
        cleaned.append({
            "storeName": store,
            "date": date,
            "amount": amount,
            "category": category,
            "transactionType": transaction_type,
        })
    return cleaned


def normalize(raw_rows: list[dict]) -> tuple[list[dict], str]:
    """원시 행 → 표준 거래 리스트. (결과, 사용한 방식) 을 돌려준다.

    MOCK_AI=1이거나 Bedrock이 실패하면 규칙 기반 폴백을 쓴다. 어떤 경우에도
    예외를 밖으로 던지지 않는다 (업로드가 통째로 실패하면 안 된다).
    """
    if not raw_rows:
        return [], "empty"

    rows = raw_rows[:MAX_ROWS]

    if os.environ.get("MOCK_AI") == "1":
        return _rule_normalize(rows), "rules(mock)"

    # 한 번에 다 보내면 토큰이 넘칠 수 있어 40행씩 나눠 호출한다
    collected: list[dict] = []
    try:
        for start in range(0, len(rows), 40):
            chunk = rows[start:start + 40]
            prompt = (
                f"{_NORMALIZE_INSTRUCTION}\n\n원시 거래 행:\n"
                f"{json.dumps(chunk, ensure_ascii=False)}"
            )
            collected.extend(_extract_json_array(_call_bedrock(prompt)))
        result = _sanitize(collected)
        if result:
            return result, "bedrock"
        print("[parse] Bedrock 결과가 비어 규칙 폴백으로 전환")
    except Exception as e:
        print(f"[parse] Bedrock 정규화 실패 → 규칙 폴백: {e}")

    return _rule_normalize(rows), "rules(fallback)"


def parse_file(filename: str, content: bytes) -> dict:
    """업로드 파일 하나를 표준 거래 리스트로 변환한다."""
    raw_rows = extract_rows(filename, content)
    if not raw_rows:
        return {
            "items": [], "source": "empty", "rawRowCount": 0,
            "warning": "파일에서 거래 내역을 찾지 못했습니다. "
                       "스캔한 이미지 PDF는 지원하지 않습니다 (텍스트 PDF·엑셀·CSV만 가능).",
        }
    items, source = normalize(raw_rows)
    return {"items": items, "source": source, "rawRowCount": len(raw_rows), "warning": None}
