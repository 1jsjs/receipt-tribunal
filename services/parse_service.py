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
    # _needs_review()가 미분류 판정에 쓴다 (키워드 규칙은 category_rules.py로 이동했지만
    # OTHER 비교는 여기 남아 있으므로 import를 지우면 안 된다)
    CATEGORY_OTHER,
    TRANSACTION_TYPE_EXPENSE,
    TRANSACTION_TYPE_TRANSFER,
    TRANSACTION_TYPES,
)
from services.category_rules import classify_by_keyword, refine_categories

MODEL_ID = "global.anthropic.claude-sonnet-5"

# 한 번에 처리할 최대 행 수 (프롬프트 길이·비용 방어)
# Bedrock 호출은 40행씩 청크로 나눠 부르므로 이 상한은 토큰이 아니라 총량 제한용이다.
# 통장 내역은 이자·캐시백 등 노이즈 행이 많아 원시 행 수가 크게 잡히므로 넉넉히 둔다.
MAX_ROWS = 400

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


# 거래 '구분' 컬럼에 오는 표준 용어 (상호명이 아니다 — 적요에서 제거)
_TXN_KIND_WORDS = (
    "체크카드결제", "카드결제", "출금", "입금", "이자입금", "오픈뱅킹", "펌뱅킹출금",
    "펌뱅킹", "캐시백", "이체", "송금", "자동이체", "결제취소", "승인취소", "환불",
)


def _split_text_line(line: str) -> dict:
    """PDF 텍스트 한 줄을 날짜·적요(상호)·금액으로 쪼갠다.

    두 가지 레이아웃을 모두 다룬다:
      A) "2026.10.02 배달의민족 19,800 1,230,400"  (날짜 → 상호 → 금액 → 잔액)
      B) "2026-08-27 14:54:26 체크카드결제 -1,860 276,558 토스페이_TOSS"
         (날짜시각 → 구분 → 거래금액 → 잔액 → 상호)   ← 토스뱅크 등

    핵심 원칙:
    - 거래금액은 '날짜 뒤 첫 숫자'로 본다 (부호 포함). 그 뒤 숫자는 대개 잔액이다.
    - 상호명은 숫자열이 끝난 뒤의 텍스트를 우선 쓴다(레이아웃 B). 그게 없으면
      날짜와 첫 숫자 사이의 텍스트를 쓰되(레이아웃 A), 거래 '구분' 단어는 걷어낸다.
    """
    date_match = re.search(r"\d{2,4}[-./]\d{1,2}[-./]\d{1,2}", line)
    date = date_match.group(0) if date_match else ""
    # 날짜 뒤 시각(HH:MM:SS)이 붙어 있으면 함께 소비
    rest = line[date_match.end():] if date_match else line
    rest = re.sub(r"^\s*\d{1,2}:\d{2}(:\d{2})?", "", rest).strip()

    def _strip_kind(text: str) -> str:
        for w in _TXN_KIND_WORDS:
            text = text.replace(w, " ")
        return re.sub(r"\s+", " ", text).strip()

    # 앞머리의 거래 '구분' 단어를 먼저 걷어낸다 (레이아웃 B: 구분 → 금액 → 잔액 → 상호)
    head_removed = _strip_kind(rest)

    # '독립된 금액 토큰'만 잡는다: 양옆이 글자가 아닌 순수 숫자열(콤마 허용).
    # 이렇게 하면 "e마트24"의 24처럼 상호에 붙은 숫자는 금액으로 오인하지 않는다.
    money_re = re.compile(r"(?<![\d가-힣A-Za-z])(-?\d{1,3}(?:,\d{3})+|-?\d+)(?![\d가-힣A-Za-z])")
    tokens = [m for m in money_re.finditer(head_removed) if re.sub(r"[^\d]", "", m.group(0))]

    if not tokens:
        return {"거래일자": date, "적요": _strip_kind(rest), "금액": "", "_raw": rest}

    # 거래금액 = 첫 숫자. 잔액(둘째 숫자)까지 소비하고 그 뒤를 상호명으로 본다.
    first_amt = tokens[0].group(0)
    before = head_removed[:tokens[0].start()].strip()
    # 상호가 숫자 뒤에 오는 레이아웃(B): 잔액 토큰 뒤부터가 상호
    balance_idx = 1 if len(tokens) >= 2 else 0
    after = head_removed[tokens[balance_idx].end():].strip()

    # 상호명: 앞 텍스트(레이아웃 A)가 있으면 우선, 없으면 숫자 뒤 텍스트(레이아웃 B)
    store = before if re.search(r"[가-힣A-Za-z]", before) else after
    if not store:
        store = after or before

    # _raw: 구분어를 포함한 원본 줄. 이체/소비 판정에 쓴다(구분어가 상호에서 지워지므로).
    return {"거래일자": date, "적요": store.strip(), "금액": first_amt, "_raw": rest}


def _read_pdf(content: bytes) -> list[dict]:
    """PDF에서 표를 우선 추출하고, 표가 없으면 텍스트 줄을 그대로 넘긴다.

    스캔본(이미지 PDF)은 pdfplumber가 아무것도 못 뽑는다 → 빈 리스트를 반환하고
    호출 측에서 안내 메시지를 낸다. (비전 폴백은 이번 범위에서 제외)
    """
    import pdfplumber

    rows: list[dict] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            # 표/텍스트 판정은 반드시 "이 페이지" 기준으로 한다.
            # 전체 누적 rows로 판정하면, 앞 페이지에서 표가 한 번 잡힌 뒤로는
            # 이후 페이지가 표로 안 잡혀도 텍스트 폴백을 건너뛰어 통째로 누락된다.
            page_rows: list[dict] = []
            for table in (page.extract_tables() or []):
                if not table:
                    continue
                header = [str(c or "").strip() for c in table[0]]
                for raw in table[1:]:
                    cells = [str(c or "").strip() for c in raw]
                    if not any(cells):
                        continue
                    page_rows.append({header[i] if i < len(header) and header[i] else f"col{i}": cells[i]
                                      for i in range(len(cells))})
            if not page_rows:
                text = page.extract_text() or ""
                page_rows.extend(_parse_text_lines(text))
            rows.extend(page_rows)
    return rows


# 거래 줄 판정용
_LINE_DATE_RE = re.compile(r"\d{2,4}[-./]\d{1,2}[-./]\d{1,2}")
_LINE_NUM_RE = re.compile(r"\d{3,}")

# 거래가 아닌 안내/헤더/꼬리 줄 (상호 조각으로 오인하면 안 됨)
_NON_TX_HINTS = (
    "거래내역", "거래일자", "예금주", "계좌번호", "예금종류", "조회기간",
    "단위", "발급", "고객센터", "문서", "페이지", "은행", "bank",
)
# "11 // 77", "1 / 7" 같은 페이지 번호
_PAGE_NO_RE = re.compile(r"^\d+\s*/+\s*\d+$")


def _looks_like_store_fragment(line: str) -> bool:
    """날짜 없는 줄이 '쪼개진 상호 조각'으로 보이는지 판단한다.

    안내문·헤더·페이지번호는 조각이 아니다. 한글/영문이 있고 위 힌트에 안 걸리면 조각으로 본다.
    """
    if not line or not re.search(r"[가-힣A-Za-z]", line):
        return False
    if _PAGE_NO_RE.match(line):
        return False
    low = line.lower()
    return not any(h in low for h in _NON_TX_HINTS)


def _parse_text_lines(text: str) -> list[dict]:
    """PDF 텍스트를 거래 행으로 만든다. 긴 상호가 거래 줄 앞뒤로 쪼개진 경우 병합한다.

    토스뱅크 등은 긴 상호를 이렇게 나눈다:
        '커몬뮤직플렉스코인노래연'                        ← 머리 (날짜 없음)
        '2026-08-26 20:35:52 체크카드결제 -9,900 585,002'  ← 금액 줄 (상호 비어있음)
        '습장'                                           ← 꼬리 (날짜 없음)
    금액 줄에 상호가 비면 직전(머리)·직후(꼬리) 조각을 이어붙여 복원한다.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    is_tx = [bool(_LINE_DATE_RE.search(l) and _LINE_NUM_RE.search(l)) for l in lines]

    result: list[dict] = []
    for i, line in enumerate(lines):
        if not is_tx[i]:
            continue
        parsed = _split_text_line(line)
        store = parsed["적요"]

        # 상호가 비었으면 앞뒤의 날짜없는 조각을 이어붙인다
        if not re.search(r"[가-힣A-Za-z]", store):
            head = lines[i - 1] if i > 0 and not is_tx[i - 1] and _looks_like_store_fragment(lines[i - 1]) else ""
            tail = lines[i + 1] if i + 1 < len(lines) and not is_tx[i + 1] and _looks_like_store_fragment(lines[i + 1]) else ""
            merged = (head + tail).strip()
            if merged:
                store = merged
                parsed["적요"] = merged

        # 그래도 상호에 글자가 없으면 거래가 아니다 (안내문 등)
        if re.search(r"[가-힣A-Za-z]", store):
            result.append(parsed)
    return result


def extract_rows(filename: str, content: bytes) -> list[dict]:
    """확장자에 따라 원시 행을 추출한다."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _read_pdf(content)
    if lower.endswith((".xlsx", ".xls", ".csv")):
        return _read_tabular(filename, content)
    raise ValueError(f"지원하지 않는 형식입니다. {', '.join(SUPPORTED_EXTENSIONS)}만 가능합니다.")


# ─────────────────── 2단계: 규칙 기반 정규화 (폴백) ───────────────────

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
    """상호명 키워드 규칙 (services/category_rules.py 단일 출처)."""
    return classify_by_keyword(store_name)


def _guess_transaction_type(store_name: str, row_text: str) -> str:
    haystack = f"{store_name} {row_text}".lower()
    if any(k in haystack for k in _TRANSFER_KEYWORDS):
        return TRANSACTION_TYPE_TRANSFER
    return TRANSACTION_TYPE_EXPENSE


# 한국 성씨 (예금주 이름 판별용 — 흔한 것 위주)
_SURNAMES = (
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신",
    "권", "황", "안", "송", "전", "홍", "고", "문", "손", "양", "배", "백", "허", "유",
    "남", "심", "노", "하", "곽", "성", "차", "주", "우", "구", "민", "진", "지", "엄",
    "채", "원", "천", "방", "공", "현", "함", "변", "염", "여", "추", "도", "소", "석",
)

# 마스킹된 예금주 표기: 김OO, 김○○, 김*수, 홍길*
_MASKED_NAME_RE = re.compile(r"^[가-힣][O○o\*×\-_]{1,2}[가-힣]?$")


def _looks_like_person(name: str) -> bool:
    """상호명이 아니라 예금주 이름으로 보이는지 판단한다.

    통장 내역에는 가맹점 대신 "김OO", "홍길동" 같은 예금주명만 찍히는 경우가 많다.
    이런 건 카테고리를 기계가 정할 수 없으므로 사용자가 직접 채워야 한다.

    주의: 단독으로 쓰면 "이마트"(성씨 이 + 3글자), "김밥천국"이 사람으로 오인된다.
    그래서 호출부에서 카테고리가 OTHER로 떨어진 건에 대해서만 쓴다.
    """
    text = name.strip()
    if not text:
        return False
    if _MASKED_NAME_RE.match(text):
        return True
    # 성씨로 시작하는 순수 한글 3~4자 (2자는 상호와 구분이 안 돼 제외)
    if re.fullmatch(r"[가-힣]{3,4}", text) and text[0] in _SURNAMES:
        return True
    return False


def _needs_review(store_name: str, category: str, transaction_type: str) -> bool:
    """미분류로 표시할지 결정한다.

    - 이미 카테고리가 잡힌 건(아는 가맹점)은 대상 아님
    - 이체는 분석에서 제외되므로 대상 아님
    """
    if category != CATEGORY_OTHER or transaction_type != TRANSACTION_TYPE_EXPENSE:
        return False
    return _looks_like_person(store_name)


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

        category = _guess_category(store)
        transaction_type = _guess_transaction_type(store, row_text)
        items.append({
            "storeName": store,
            "date": date,
            "amount": amount,
            "category": category,
            "transactionType": transaction_type,
            "needsReview": _needs_review(store, category, transaction_type),
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
- needsReview: true 또는 false
    상호명 자리에 가맹점이 아니라 **사람 이름(예금주)**만 있어서 무엇을 샀는지
    알 수 없는 경우 true. (예: "김OO", "홍길동", "박○○")
    가맹점 이름이 분명하면 false.

규칙:
- 거래로 볼 수 없는 행(합계, 소계, 안내문, 빈 행)은 결과에서 제외하세요.
- 날짜나 금액을 알 수 없는 행도 제외하세요.
- 카테고리는 상호명을 보고 판단하세요. 애매하면 OTHER를 쓰세요.
- 결제대행(PG)사 명칭만 있고 실제 가맹점을 알 수 없으면(네이버페이, 카카오페이,
  토스페이, 이니시스, KCP, 나이스페이 등) category는 OTHER로 두세요.
- 상호명에 지점·법인 형태가 붙어도(㈜, (주), ~점) 핵심 브랜드명으로 판단하세요.
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
        # 모델이 needsReview를 빠뜨리거나 이상하게 주면 규칙으로 다시 판단한다
        needs_review = item.get("needsReview")
        if not isinstance(needs_review, bool):
            needs_review = _needs_review(store, category, transaction_type)
        cleaned.append({
            "storeName": store,
            "date": date,
            "amount": amount,
            "category": category,
            "transactionType": transaction_type,
            "needsReview": needs_review,
        })
    return cleaned


def _normalize_inner(rows: list[dict]) -> tuple[list[dict], str]:
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
        print(f"[parse] Bedrock 호출 실패 → 규칙 폴백: {e}")  # "Bedrock 호출 실패"로 grep됨 (verdict와 통일)

    return _rule_normalize(rows), "rules(fallback)"


def normalize(raw_rows: list[dict]) -> tuple[list[dict], str]:
    """원시 행 → 표준 거래 리스트. (결과, 사용한 방식) 을 돌려준다.

    MOCK_AI=1이거나 Bedrock이 실패하면 규칙 기반 폴백을 쓴다. 어떤 경우에도
    예외를 밖으로 던지지 않는다 (업로드가 통째로 실패하면 안 된다).

    정규화 방식과 무관하게, 마지막에 category_rules.refine_categories로
    OTHER·미지정 항목을 키워드+공공데이터로 한 번 더 보정한다.
    """
    if not raw_rows:
        return [], "empty"

    items, source = _normalize_inner(raw_rows[:MAX_ROWS])
    refine_categories(items)
    return items, source


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
