# Design Document

## Overview

영수증 소비 재판소는 한 달치 지출내역을 업로드하면 결정적 룰 엔진으로 "죄명"을 판정하고, Bedrock LLM으로 위트있는 판결문을 생성하는 SPA 기반 서비스이다. FastAPI 백엔드 + 순수 HTML/CSS/JS 프런트엔드 + SQLite 저장소 구성이며, 파일 파싱(PDF/엑셀/CSV)부터 판결문 열람까지 전 흐름을 닉네임 하나로 인증 없이 이용할 수 있다.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client (Browser)                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  static/index.html — 순수 HTML/CSS/JS SPA                │  │
│  │  max-width: 480px 중앙 컨테이너 (모바일 세로 기준)        │  │
│  │  하단 탭: 홈 | 등록 | 내역 | 판결                        │  │
│  └──────────────────────────┬────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────┘
                              │ HTTP (fetch API)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FastAPI (main.py, 포트 8501)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ /api/    │  │ /api/    │  │ /api/    │  │ /api/upload   │   │
│  │ users    │  │ receipts │  │ verdict  │  │ (multipart)   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬────────┘   │
│       │              │              │               │            │
│       ▼              ▼              ▼               ▼            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Core Modules                          │    │
│  │  core/parse.py   — 파일 파싱 + Bedrock 정규화           │    │
│  │  core/vision.py  — 스캔형 PDF 비전 폴백                 │    │
│  │  core/analyze.py — 월간 집계·통계                       │    │
│  │  core/judge.py   — 결정적 판정 룰 엔진                  │    │
│  │  core/verdict.py — Bedrock 판결문 산문 생성             │    │
│  └────┬──────────────────┬──────────────────┬──────────────┘    │
│       │                  │                  │                    │
└───────┼──────────────────┼──────────────────┼────────────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────┐      ┌───────────┐      ┌───────────────┐
   │ SQLite  │      │ S3 Bucket │      │ Bedrock       │
   │ data.db │      │ hackathon │      │ Claude Sonnet │
   │         │      │ -e1-t07-  │      │ 5 (global.)   │
   │ - users │      │ docs      │      │               │
   │ - rcpts │      │ evidence/ │      │ - 텍스트 정규화│
   │ - vrdct │      │           │      │ - 비전 폴백   │
   └─────────┘      └───────────┘      │ - 판결문 생성 │
                                        └───────────────┘
```

### 핵심 플로우

**플로우 A — 파일 업로드 → 파싱 → 저장**
1. SPA에서 multipart/form-data로 파일 업로드 (POST /api/upload)
2. `core/parse.py`가 파일 형식 판별 (xlsx/csv → pandas, PDF → pdfplumber)
3. 추출된 텍스트를 Bedrock 텍스트 호출로 정규화 → 표준 JSON 배열 반환
4. (스캔형 PDF 폴백) pdfplumber 텍스트 없음 → pypdfium2 렌더 → `core/vision.py` 비전 호출
5. 원본 파일은 S3 `evidence/` 경로에 보관
6. SPA에서 결과 확인 후 POST /api/receipts로 최종 저장

**플로우 B — 판결문 생성**
1. SPA에서 POST /api/verdict/{nickname}?month=YYYY-MM 호출
2. `core/judge.py`가 월간 영수증 집계 후 결정적 룰 평가 → charge + type 확정
3. `core/verdict.py`가 judge 결과 + 통계 + 메모를 Bedrock에 전달 → 판결문 산문 생성
4. 생성된 판결문을 SQLite verdicts 테이블에 저장 후 SPA에 반환

---

## Components and Interfaces

| 모듈 | 역할 |
|------|------|
| `main.py` | FastAPI 엔드포인트 정의, 에러 핸들러, 정적 파일 마운트 |
| `static/index.html` | 순수 HTML/CSS/JS SPA (7개 화면, 탭 전환) |
| `core/parse.py` | 파일(PDF/xlsx/csv) 원시 추출 → Bedrock LLM 정규화·분류 |
| `core/vision.py` | 스캔형 PDF 폴백 — pypdfium2 렌더 → Bedrock 비전 호출 |
| `core/analyze.py` | 월간 집계 통계 (카테고리별, 서브타입별, 일평균 등) |
| `core/judge.py` | 결정적 판정 룰 엔진 + 증거 선정 로직 |
| `core/verdict.py` | Bedrock 판결문 산문 생성 (프롬프트 조립 + 필드 검증) |
| `core/bedrock.py` | Bedrock 공통 래퍼 (재시도·Mock 분기·JSON 추출) |
| `db.py` | SQLite 초기화·커넥션 관리 (WAL 모드, FK 활성화) |

모듈 간 의존 관계는 위 Architecture 다이어그램 참조. `main.py`가 진입점이며, 각 API 엔드포인트에서 `core/*` 모듈을 호출하고, `core/parse.py`와 `core/verdict.py`는 `core/bedrock.py` 래퍼를 통해 Bedrock에 접근한다.

---

## Data Models

### SQLite 스키마 (db.py 초기화)

```sql
-- 연결 시 설정
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 사용자 테이블
CREATE TABLE IF NOT EXISTS users (
    nickname   TEXT PRIMARY KEY,
    age        INTEGER,                          -- nullable, 1~120
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 영수증 테이블
CREATE TABLE IF NOT EXISTS receipts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname     TEXT    NOT NULL REFERENCES users(nickname),
    store        TEXT    NOT NULL,
    date         TEXT    NOT NULL,               -- YYYY-MM-DD
    amount       INTEGER NOT NULL,               -- 양의 정수, 원 단위
    category     TEXT    NOT NULL CHECK (category IN (
                     '식비','카페·간식','쇼핑','교통·이동','여가·문화','기타'
                 )),
    subtype      TEXT    NOT NULL DEFAULT '일반' CHECK (subtype IN (
                     '배달앱','편의점','마트·장보기','카페','일반'
                 )),
    memo         TEXT,                           -- nullable, 최대 100자
    needs_review INTEGER NOT NULL DEFAULT 0,     -- 0=확정, 1=검토필요
    s3_key       TEXT,                           -- nullable, S3 원본 파일 경로
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 판결문 테이블
CREATE TABLE IF NOT EXISTS verdicts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname         TEXT    NOT NULL REFERENCES users(nickname),
    month            TEXT    NOT NULL,           -- YYYY-MM
    case_number      TEXT    NOT NULL,           -- 예: "0847"
    charge           TEXT    NOT NULL,           -- 죄명
    spending_type    TEXT    NOT NULL,           -- 소비 유형
    article          TEXT    NOT NULL,           -- 조문 부제
    evidence_json    TEXT    NOT NULL,           -- 증거 01~04 JSON
    ruling           TEXT    NOT NULL,           -- 주문 (한 줄)
    reasoning        TEXT    NOT NULL,           -- 이유 (2~3문장)
    sentence         TEXT    NOT NULL,           -- 형량 (2~3줄)
    type_description TEXT    NOT NULL,           -- 유형 설명 (2~3문장)
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(nickname, month)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_receipts_nickname_date
    ON receipts(nickname, date);
CREATE INDEX IF NOT EXISTS idx_receipts_nickname_month
    ON receipts(nickname, substr(date, 1, 7));
CREATE INDEX IF NOT EXISTS idx_verdicts_nickname
    ON verdicts(nickname);
```

### db.py 초기화 패턴

```python
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"

def get_connection() -> sqlite3.Connection:
    """SQLite 커넥션 반환 (WAL 모드, FK 활성화)"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """앱 시작 시 테이블 생성 (기존 데이터 보존)"""
    conn = get_connection()
    conn.executescript(_SCHEMA_SQL)
    conn.close()
```

---

## 3. API Design

### 3.1 POST /api/users/{nickname}

사용자 생성 또는 기존 사용자 반환 (멱등)

**Request**
```
POST /api/users/홍길동
Content-Type: application/json (optional body)

{
  "age": 27          // optional, 1~120 정수
}
```

**Response 200**
```json
{
  "nickname": "홍길동",
  "age": 27,
  "created_at": "2026-08-01T12:00:00"
}
```

**Error 422** — 닉네임 빈 문자열 또는 12자 초과

---

### 3.2 POST /api/receipts

영수증 일괄 저장 (수동 입력 + 파싱 결과 모두 이 엔드포인트 사용)

**Request**
```json
{
  "nickname": "홍길동",
  "items": [
    {
      "store": "배달의민족-맛있는족발",
      "date": "2026-08-05",
      "amount": 32000,
      "category": "식비",
      "subtype": "배달앱",
      "memo": "야식 참지 못함"
    }
  ]
}
```

**필드 제약**
| 필드 | 타입 | 필수 | 제약 |
|------|------|------|------|
| store | string | ✓ | 1~50자 |
| date | string | ✓ | YYYY-MM-DD, 미래 날짜 불가 |
| amount | integer | ✓ | 1 ~ 999,999,999 |
| category | string | ✓ | 6종 중 하나 |
| subtype | string | — | 5종 중 하나, 기본값 "일반" |
| memo | string | — | 최대 100자 |

**Response 200**
```json
{
  "stored_count": 1
}
```

**Error 422** — 필수 필드 누락, amount ≤ 0, 유효하지 않은 category 등

---

### 3.3 GET /api/receipts/{nickname}

월별 영수증 조회

**Query Parameters**
- `month` (required): YYYY-MM 형식

**Response 200**
```json
[
  {
    "id": 1,
    "store": "배달의민족-맛있는족발",
    "date": "2026-08-05",
    "amount": 32000,
    "category": "식비",
    "subtype": "배달앱",
    "memo": "야식 참지 못함"
  }
]
```
- 날짜 내림차순 정렬
- 닉네임 미존재 시 빈 배열 반환 (에러 아님)

---

### 3.4 GET /api/summary/{nickname}

월간 집계 통계

**Query Parameters**
- `month` (required): YYYY-MM 형식

**Response 200**
```json
{
  "total_amount": 1250000,
  "count": 42,
  "daily_average": 40323,
  "categories": {
    "식비": {"amount": 520000, "count": 18},
    "카페·간식": {"amount": 180000, "count": 12},
    "쇼핑": {"amount": 300000, "count": 5},
    "교통·이동": {"amount": 100000, "count": 4},
    "여가·문화": {"amount": 50000, "count": 2},
    "기타": {"amount": 100000, "count": 1}
  },
  "top_category": {
    "name": "식비",
    "percentage": 41.6
  },
  "largest_transaction": {
    "store": "나이키 온라인스토어",
    "amount": 189000,
    "date": "2026-08-12"
  }
}
```

- `daily_average` = total_amount ÷ 해당 월 달력 일수
- `top_category`: 금액 동률 시 count 높은 것, count도 동률이면 고정 카테고리 순서 우선
- 닉네임 미존재 시 모든 값 0/빈 객체 반환

---

### 3.5 POST /api/verdict/{nickname}

판정 + 판결문 생성

**Query Parameters**
- `month` (required): YYYY-MM 형식
- `force` (optional): true/false, 기본 false

**Response 200**
```json
{
  "case_number": "0847",
  "charge": "냉장고 유기죄",
  "spending_type": "냉장고보다 배달앱형",
  "article": "소비보호법 제4조 (냉장고의 존엄)",
  "evidence": [
    {"label": "배달·외식 지출액", "value": "520,000원"},
    {"label": "배달앱 결제 횟수", "value": "18회"},
    {"label": "전체 중 배달 비중", "value": "41.6%"},
    {"label": "최다 결제 요일", "value": "금요일"}
  ],
  "ruling": "피고인을 배달앱 7일 금지에 처한다",
  "reasoning": "피고인은 한 달간 냉장고를 장식품으로 전락시킨 혐의가 명백하다...",
  "sentence": "1. 이번 주 3회 이상 자취 요리 실행\n2. 배달앱 알림 OFF\n3. 냉장고에 사과문 부착",
  "type_description": "냉장고는 전기세만 먹는 가전이 된 지 오래...",
  "created_at": "2026-08-31T23:59:00"
}
```

- `force=false`이고 이미 verdict 존재 → 저장된 것 반환 (재생성 안 함)
- `force=true` → 기존 verdict 삭제 후 재생성

**Error 422** — 월 형식 오류
**Error 500** (재시도 실패) — `{"detail": "판결문 생성에 실패했습니다. 잠시 후 다시 시도해주세요."}`

---

### 3.6 GET /api/history/{nickname}

과거 판결문 전체 목록 (최신순)

**Response 200**
```json
[
  {
    "month": "2026-08",
    "case_number": "0847",
    "charge": "냉장고 유기죄",
    "spending_type": "냉장고보다 배달앱형",
    "created_at": "2026-08-31T23:59:00"
  }
]
```

---

### 3.7 POST /api/upload

파일 업로드 → 파싱 → 정규화된 트랜잭션 반환

**Request**
```
POST /api/upload
Content-Type: multipart/form-data

file: (binary, max 10MB)
nickname: "홍길동"
```

**Response 200**
```json
{
  "transactions": [
    {
      "date": "2026-08-05",
      "store": "배달의민족-맛있는족발",
      "amount": 32000,
      "category": "식비",
      "subtype": "배달앱",
      "needs_review": false
    }
  ],
  "s3_key": "evidence/20260805-143022-a1b2c3.xlsx",
  "total_count": 28,
  "filtered_count": 3
}
```

- `total_count`: 파싱된 전체 행 수
- `filtered_count`: 제외된 비지출 행 수 (입금, 취소, 카드대금)
- 파싱 실패 시 1회 재시도 → 최종 실패 시 에러 응답 + 사유

**Error 413** — 파일 10MB 초과
**Error 422** — 지원하지 않는 파일 형식
**Error 500** — `{"detail": "파일 파싱에 실패했습니다. 수동 입력을 이용해주세요.", "fallback": true}`

---

### 3.8 정적 파일 서빙

> ⚠️ **WARNING: 마운트 순서 필수**
> `app.mount("/", StaticFiles(...))` 는 반드시 모든 `/api/*` 라우트 등록 **이후 마지막 줄**에 위치해야 한다.
> StaticFiles가 `"/"` 경로에 마운트되면 이후 모든 요청을 가로채므로, 만약 API 라우트보다 먼저 선언하면 `/api/*` 경로가 전부 404를 반환한다.

```python
# main.py — FastAPI 마운트 (반드시 모든 @app.route 등록 후 마지막에 배치)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

루트(`/`) 접근 시 `static/index.html` 반환.

---

## 4. Judgment Engine (core/judge.py)

### 설계 원칙

- **결정적**: 동일 입력 → 항상 동일 결과 (LLM 호출 없음)
- **우선순위 기반**: 룰 0~8 순서대로 평가, 첫 매칭 룰 선택
- **가드 룰**: 5건 미만이면 무조건 "증거 불충분" (division-by-zero 방지)

### 룰 정의 데이터 구조

```python
"""판정 룰 엔진 — 결정적 조건문 기반 (core/judge.py)"""

from dataclasses import dataclass
from typing import Callable

# 카테고리·서브타입 상수
CATEGORIES = ["식비", "카페·간식", "쇼핑", "교통·이동", "여가·문화", "기타"]
SUBTYPES = ["배달앱", "편의점", "마트·장보기", "카페", "일반"]


@dataclass
class JudgmentRule:
    """판정 룰 하나를 표현하는 데이터 클래스"""
    index: int              # 우선순위 (0부터)
    charge: str             # 죄명
    spending_type: str      # 소비 유형
    condition: Callable     # (stats) -> bool


def evaluate(receipts: list[dict]) -> dict:
    """
    월간 영수증 리스트를 받아 판정 결과를 반환한다.
    Returns: {"charge": str, "type": str, "stats": dict}
    """
    # 1. 가드 룰: 영수증 5건 미만
    if len(receipts) < 5:
        return {
            "charge": "증거 불충분",
            "type": "균형 잡힌 생존형",
            "stats": _compute_stats(receipts),
        }

    stats = _compute_stats(receipts)

    # 2. total이 0이면 폴백
    if stats["total_amount"] == 0:
        return {
            "charge": "증거 불충분",
            "type": "균형 잡힌 생존형",
            "stats": stats,
        }

    # 3. 룰 1~7 순서대로 평가
    for rule in RULES:
        if rule.condition(stats):
            return {
                "charge": rule.charge,
                "type": rule.spending_type,
                "stats": stats,
            }

    # 4. 폴백 룰 8: 아무것도 매칭 안 됨
    return {
        "charge": "증거 불충분",
        "type": "균형 잡힌 생존형",
        "stats": stats,
    }


def _compute_stats(receipts: list[dict]) -> dict:
    """판정에 필요한 집계 통계를 계산한다."""
    total_amount = sum(r["amount"] for r in receipts)
    total_count = len(receipts)

    # 서브타입별 집계
    subtype_amount = {s: 0 for s in SUBTYPES}
    subtype_count = {s: 0 for s in SUBTYPES}
    for r in receipts:
        st = r.get("subtype", "일반")
        if st not in SUBTYPES:
            st = "일반"  # 예상치 못한 subtype → "일반"으로 폴백 (KeyError 방지)
        subtype_amount[st] += r["amount"]
        subtype_count[st] += 1

    # 카테고리별 집계
    category_amount = {c: 0 for c in CATEGORIES}
    category_count = {c: 0 for c in CATEGORIES}
    for r in receipts:
        cat = r.get("category", "기타")
        if cat not in CATEGORIES:
            cat = "기타"  # 예상치 못한 category → "기타"로 폴백 (KeyError 방지)
        category_amount[cat] += r["amount"]
        category_count[cat] += 1

    # 월초(1~10일) 집계
    early_amount = sum(
        r["amount"] for r in receipts
        if 1 <= int(r["date"].split("-")[2]) <= 10
    )

    # 소액(≤1만원) 집계
    small_count = sum(1 for r in receipts if r["amount"] <= 10000)

    return {
        "total_amount": total_amount,
        "total_count": total_count,
        "subtype_amount": subtype_amount,
        "subtype_count": subtype_count,
        "category_amount": category_amount,
        "category_count": category_count,
        "early_month_amount": early_amount,
        "small_payment_count": small_count,
    }


# 룰 정의 (우선순위 순서)
RULES = [
    JudgmentRule(
        index=1,
        charge="냉장고 유기죄",
        spending_type="냉장고보다 배달앱형",
        condition=lambda s: s["subtype_amount"]["배달앱"] / s["total_amount"] >= 0.35,
    ),
    JudgmentRule(
        index=2,
        charge="편의점 상습 출석죄",
        spending_type="편의점이 내 부엌형",
        condition=lambda s: s["subtype_count"]["편의점"] >= 10,
    ),
    JudgmentRule(
        index=3,
        charge="카페인 정기후원죄",
        spending_type="소확행 충전형",
        condition=lambda s: s["category_amount"]["카페·간식"] / s["total_amount"] >= 0.25,
    ),
    JudgmentRule(
        index=4,
        charge="필요와 욕망 혼동죄",
        spending_type="취향에 진심형",
        condition=lambda s: s["category_amount"]["쇼핑"] / s["total_amount"] >= 0.30,
    ),
    JudgmentRule(
        index=5,
        charge="월초 재벌 행세죄",
        spending_type="월초 플렉스형",
        condition=lambda s: s["early_month_amount"] / s["total_amount"] >= 0.45,
    ),
    JudgmentRule(
        index=6,
        charge="잔액 조금씩 빼돌린 죄",
        spending_type="티끌 과소비형",
        condition=lambda s: s["small_payment_count"] >= 15,
    ),
    JudgmentRule(
        index=7,
        charge="무혐의",
        spending_type="야무진 자취생형",
        condition=lambda s: (
            s["subtype_amount"]["마트·장보기"] / s["total_amount"] >= 0.30
            and s["subtype_amount"]["배달앱"] / s["total_amount"] <= 0.15
        ),
    ),
]
```

### 평가 순서 요약

| 우선순위 | 죄명 | 조건 |
|---------|------|------|
| 0 (가드) | 증거 불충분 | 영수증 < 5건 또는 총액 = 0 |
| 1 | 냉장고 유기죄 | 배달앱 금액 ≥ 총액의 35% |
| 2 | 편의점 상습 출석죄 | 편의점 결제 횟수 ≥ 10회 |
| 3 | 카페인 정기후원죄 | 카페·간식 금액 ≥ 총액의 25% |
| 4 | 필요와 욕망 혼동죄 | 쇼핑 금액 ≥ 총액의 30% |
| 5 | 월초 재벌 행세죄 | 1~10일 금액 ≥ 총액의 45% |
| 6 | 잔액 조금씩 빼돌린 죄 | 1만원 이하 결제 ≥ 15건 |
| 7 | 무혐의 | 마트 ≥ 30% AND 배달 ≤ 15% |
| 8 (폴백) | 증거 불충분 | 위 룰 모두 불일치 |

---

## 5. 증거 01~04 선정 로직

판결문의 "증거" 섹션에 표시할 4개 통계를 죄명별로 다르게 산출한다.

### 증거 매핑 테이블

| 죄명 | 증거01 | 증거02 | 증거03 | 증거04 |
|------|--------|--------|--------|--------|
| 냉장고 유기죄 | 배달·외식 지출액 | 배달앱 결제 횟수 | 전체 중 배달 비중% | 최다 결제 요일 |
| 편의점 상습 출석죄 | 편의점 지출액 | 편의점 결제 횟수 | 전체 중 편의점 비중% | 최다 결제 요일 |
| 카페인 정기후원죄 | 카페·간식 지출액 | 카페 결제 횟수 | 전체 중 카페 비중% | 최다 방문 매장 |
| 필요와 욕망 혼동죄 | 쇼핑 지출액 | 쇼핑 결제 횟수 | 전체 중 쇼핑 비중% | 가장 큰 단일 쇼핑 |
| 월초 재벌 행세죄 | 1~10일 지출액 | 1~10일 결제 횟수 | 1~10일 비중% | 11~말일 일평균 |
| 잔액 조금씩 빼돌린 죄 | 1만원이하 결제 횟수 | 1만원이하 총액 | 소액 비율% | 최다 소액 카테고리 |
| 무혐의 | 마트·장보기 지출액 | 마트 결제 횟수 | 마트 비중% | 배달앱 비중% |
| 증거 불충분 | 총지출액 | 총 결제 횟수 | 카테고리 수 | 일평균 지출 |

### 증거 계산 구현

```python
"""증거 선정 로직 — core/judge.py 내 build_evidence 함수"""

import calendar
from collections import Counter


def build_evidence(charge: str, receipts: list[dict], stats: dict, month: str) -> list[dict]:
    """
    죄명에 맞는 증거 4건을 계산하여 반환한다.
    Returns: [{"label": str, "value": str}, ...]
    """
    # 공통 헬퍼
    def fmt_amount(n: int) -> str:
        return f"{n:,}원"

    def fmt_pct(part: int, whole: int) -> str:
        if whole == 0:
            return "0%"
        return f"{part / whole * 100:.1f}%"

    def most_frequent_weekday(subset: list[dict]) -> str:
        """최다 결제 요일 계산"""
        days = ["월", "화", "수", "목", "금", "토", "일"]
        from datetime import date as dt_date
        weekdays = []
        for r in subset:
            y, m, d = map(int, r["date"].split("-"))
            weekdays.append(dt_date(y, m, d).weekday())
        if not weekdays:
            return "-"
        most_common = Counter(weekdays).most_common(1)[0][0]
        return f"{days[most_common]}요일"

    def most_frequent_store(subset: list[dict]) -> str:
        """최다 방문 매장 계산"""
        if not subset:
            return "-"
        stores = [r["store"] for r in subset]
        return Counter(stores).most_common(1)[0][0]

    # 월의 총 일수
    year, mon = map(int, month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]

    # 서브셋 추출
    delivery_receipts = [r for r in receipts if r.get("subtype") == "배달앱"]
    cvs_receipts = [r for r in receipts if r.get("subtype") == "편의점"]
    cafe_receipts = [r for r in receipts if r["category"] == "카페·간식"]
    shopping_receipts = [r for r in receipts if r["category"] == "쇼핑"]
    early_receipts = [r for r in receipts if 1 <= int(r["date"].split("-")[2]) <= 10]
    late_receipts = [r for r in receipts if int(r["date"].split("-")[2]) > 10]
    small_receipts = [r for r in receipts if r["amount"] <= 10000]
    mart_receipts = [r for r in receipts if r.get("subtype") == "마트·장보기"]

    total = stats["total_amount"]

    # 죄명별 증거 매핑
    EVIDENCE_MAP = {
        "냉장고 유기죄": [
            {"label": "배달·외식 지출액", "value": fmt_amount(sum(r["amount"] for r in delivery_receipts))},
            {"label": "배달앱 결제 횟수", "value": f"{len(delivery_receipts)}회"},
            {"label": "전체 중 배달 비중", "value": fmt_pct(sum(r["amount"] for r in delivery_receipts), total)},
            {"label": "최다 결제 요일", "value": most_frequent_weekday(delivery_receipts)},
        ],
        "편의점 상습 출석죄": [
            {"label": "편의점 지출액", "value": fmt_amount(sum(r["amount"] for r in cvs_receipts))},
            {"label": "편의점 결제 횟수", "value": f"{len(cvs_receipts)}회"},
            {"label": "전체 중 편의점 비중", "value": fmt_pct(sum(r["amount"] for r in cvs_receipts), total)},
            {"label": "최다 결제 요일", "value": most_frequent_weekday(cvs_receipts)},
        ],
        "카페인 정기후원죄": [
            {"label": "카페·간식 지출액", "value": fmt_amount(sum(r["amount"] for r in cafe_receipts))},
            {"label": "카페 결제 횟수", "value": f"{len(cafe_receipts)}회"},
            {"label": "전체 중 카페 비중", "value": fmt_pct(sum(r["amount"] for r in cafe_receipts), total)},
            {"label": "최다 방문 매장", "value": most_frequent_store(cafe_receipts)},
        ],
        "필요와 욕망 혼동죄": [
            {"label": "쇼핑 지출액", "value": fmt_amount(sum(r["amount"] for r in shopping_receipts))},
            {"label": "쇼핑 결제 횟수", "value": f"{len(shopping_receipts)}회"},
            {"label": "전체 중 쇼핑 비중", "value": fmt_pct(sum(r["amount"] for r in shopping_receipts), total)},
            {"label": "가장 큰 단일 쇼핑", "value": fmt_amount(max((r["amount"] for r in shopping_receipts), default=0))},
        ],
        "월초 재벌 행세죄": [
            {"label": "1~10일 지출액", "value": fmt_amount(sum(r["amount"] for r in early_receipts))},
            {"label": "1~10일 결제 횟수", "value": f"{len(early_receipts)}회"},
            {"label": "1~10일 비중", "value": fmt_pct(sum(r["amount"] for r in early_receipts), total)},
            {"label": "11~말일 일평균", "value": fmt_amount(
                sum(r["amount"] for r in late_receipts) // max(days_in_month - 10, 1)
            )},
        ],
        "잔액 조금씩 빼돌린 죄": [
            {"label": "1만원이하 결제 횟수", "value": f"{len(small_receipts)}회"},
            {"label": "1만원이하 총액", "value": fmt_amount(sum(r["amount"] for r in small_receipts))},
            {"label": "소액 비율", "value": fmt_pct(len(small_receipts), len(receipts)) if receipts else "0%"},
            {"label": "최다 소액 카테고리", "value": (
                Counter(r["category"] for r in small_receipts).most_common(1)[0][0]
                if small_receipts else "-"
            )},
        ],
        "무혐의": [
            {"label": "마트·장보기 지출액", "value": fmt_amount(sum(r["amount"] for r in mart_receipts))},
            {"label": "마트 결제 횟수", "value": f"{len(mart_receipts)}회"},
            {"label": "마트 비중", "value": fmt_pct(sum(r["amount"] for r in mart_receipts), total)},
            {"label": "배달앱 비중", "value": fmt_pct(sum(r["amount"] for r in delivery_receipts), total)},
        ],
        "증거 불충분": [
            {"label": "총지출액", "value": fmt_amount(total)},
            {"label": "총 결제 횟수", "value": f"{len(receipts)}회"},
            {"label": "카테고리 수", "value": f"{len(set(r['category'] for r in receipts))}개"},
            {"label": "일평균 지출", "value": fmt_amount(total // max(days_in_month, 1))},
        ],
    }

    return EVIDENCE_MAP.get(charge, EVIDENCE_MAP["증거 불충분"])
```

---

## 6. 파싱 정규화 프롬프트 (core/parse.py)

### 설계 방침

- 은행/카드사별 포맷을 하드코딩하지 않는다 — 포맷 해석은 전적으로 LLM이 담당.
- 키워드 기반 subtype 매핑은 프롬프트에 명시하여 LLM이 일관 적용하도록 한다.
- JSON-only 응답을 강제하고, 파싱 실패 시 1회 재시도 후 에러 반환.

### Bedrock 정규화 프롬프트 전문

```python
"""지출내역 파일 파싱 및 정규화 모듈 (core/parse.py)"""

# Bedrock 텍스트 호출로 원시 추출 텍스트를 표준 JSON으로 정규화하는 프롬프트
NORMALIZATION_PROMPT = """당신은 한국 카드사/은행 지출내역 텍스트를 분석하는 전문가입니다.
아래 텍스트는 PDF 또는 엑셀에서 추출한 원시 지출내역입니다.

## 작업 지시

이 텍스트에서 **지출(결제) 건만** 추출하여 아래 JSON 배열로 변환하세요.

## 제외 대상 (반드시 필터링)
- 입금, 이체 입금
- 결제 취소, 승인 취소, 마이너스(-) 금액
- 카드 대금 자동이체, 카드론 상환
- 연회비, 이자, 수수료 (단, 실제 서비스 이용 수수료는 포함)
- 잔액, 누적 합계 행

## 금액 정리 규칙
- 콤마(,) 제거
- "원", "₩", "KRW" 등 통화 기호 제거
- 결과는 양의 정수(integer)로 변환
- 마이너스 금액은 지출이 아니므로 제외

## 카테고리 분류 (6종 중 하나 선택)
- **식비**: 음식점, 배달, 편의점 식품, 마트 식료품
- **카페·간식**: 카페, 빵집, 디저트, 아이스크림, 편의점 간식
- **쇼핑**: 의류, 전자제품, 온라인쇼핑, 생활용품 (식료품 제외)
- **교통·이동**: 택시, 대중교통, 주유, 주차, 톨게이트, 킥보드
- **여가·문화**: 영화, 공연, 도서, 게임, 구독서비스, 운동
- **기타**: 위 5개에 해당하지 않는 모든 지출

## 서브타입 분류 (키워드 기반)
아래 키워드가 가맹점명에 포함되면 해당 서브타입을 부여합니다:

- **배달앱**: 배달의민족, 요기요, 쿠팡이츠, 배민, 땡겨요, 위메프오
- **편의점**: GS25, CU, 세븐일레븐, 이마트24, 미니스톱, GS더프레시
- **마트·장보기**: 이마트, 홈플러스, 롯데마트, 하나로마트, 코스트코, 트레이더스, 마트
- **카페**: 스타벅스, 메가커피, 투썸, 이디야, 커피빈, 할리스, 카페, 커피, 빽다방, 컴포즈
- **일반**: 위 키워드에 해당하지 않는 경우

## needs_review 판정
다음 중 하나라도 해당하면 needs_review를 true로 설정:
- 가맹점명이 불분명하거나 의미를 파악하기 어려운 경우 (예: "카드결제", "PG결제")
- 카테고리 분류가 애매한 경우 (예: "다이소" → 쇼핑? 식비? 생활용품?)
- 금액이 비정상적으로 크거나 작은 경우 (100원 미만 또는 500만원 초과)
- 날짜를 특정하기 어려운 경우

## 개인정보 마스킹
- 카드번호: 앞 4자리와 뒤 4자리만 남기고 나머지는 *로 마스킹 (예: 1234-****-****-5678)
- 전화번호: 중간 자릿수를 *로 마스킹 (예: 010-****-1234)
- 가맹점명에 포함된 개인정보도 동일하게 마스킹

## 출력 형식 (JSON 배열만 출력, 다른 텍스트 금지)

```json
[
  {
    "date": "2026-08-05",
    "store": "배달의민족-맛있는족발",
    "amount": 32000,
    "category": "식비",
    "subtype": "배달앱",
    "needs_review": false
  }
]
```

## 규칙 요약
1. date는 YYYY-MM-DD 형식. 연도가 없으면 문맥에서 추론.
2. store는 원본 가맹점명 유지 (마스킹 적용 후).
3. amount는 양의 정수. 콤마·통화기호 제거.
4. category는 위 6종 중 정확히 하나.
5. subtype는 위 5종 중 정확히 하나.
6. needs_review는 boolean.
7. 제외 대상에 해당하는 행은 절대 포함하지 마세요.
8. 응답은 JSON 배열만 출력하세요. 설명·마크다운 코드블록(```) 없이 [ 로 시작하고 ] 로 끝나세요.

---
아래가 분석할 원시 텍스트입니다:

{raw_text}
"""
```

### 파싱 파이프라인 로직

```python
import os
import io
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber
import boto3

from core.vision import analyze_image_vision

# Mock 모드 확인
MOCK_AI = os.environ.get("MOCK_AI", "0") == "1"
BUCKET_NAME = "hackathon-e1-t07-docs"


def parse_file(file_bytes: bytes, filename: str, nickname: str) -> dict:
    """
    업로드된 파일을 파싱하여 정규화된 트랜잭션 리스트를 반환한다.
    Returns: {"transactions": [...], "s3_key": str, "total_count": int, "filtered_count": int}
    """
    if MOCK_AI:
        return _mock_response()

    # S3에 원본 저장
    s3_key = _upload_to_s3(file_bytes, filename)

    # 파일 확장자 판별
    ext = Path(filename).suffix.lower()

    if ext in (".xlsx", ".xls"):
        raw_text = _extract_excel(file_bytes)
    elif ext == ".csv":
        raw_text = _extract_csv(file_bytes)
    elif ext == ".pdf":
        raw_text = _extract_pdf(file_bytes)
        if not raw_text or len(raw_text.strip()) < 50:
            # 스캔형 PDF → 비전 폴백
            return _vision_fallback(file_bytes, s3_key)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")

    # Bedrock 정규화 호출 (invoke_bedrock 래퍼 사용, 실패 시 1회 재시도 내장)
    # → _normalize_single 또는 chunk_and_normalize (섹션 8 참조)
    transactions = _normalize_single(raw_text, target_month=None)

    return {
        "transactions": transactions,
        "s3_key": s3_key,
        "total_count": len(transactions),
        "filtered_count": 0,  # LLM이 이미 필터링 완료
    }


# ─── 참고: 정규화 경로 통합 ──────────────────────────────────────────
# 정규화는 반드시 core/bedrock.py의 invoke_bedrock 래퍼를 통해 수행한다.
# _normalize_single (50행 이하) 또는 chunk_and_normalize (50행 초과)가
# invoke_bedrock을 호출하며, 재시도·Mock 분기·JSON 추출을 일관 처리한다.
# boto3를 직접 호출하는 별도 정규화 함수(_normalize_with_bedrock)는 사용하지 않는다.
# ────────────────────────────────────────────────────────────────────


def _extract_excel(file_bytes: bytes) -> str:
    """엑셀 파일에서 원시 텍스트 추출 (pandas + openpyxl)"""
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl", header=None)
    return df.to_string(index=False)


def _extract_csv(file_bytes: bytes) -> str:
    """CSV 파일에서 원시 텍스트 추출"""
    # 인코딩 자동 감지: utf-8 → euc-kr 폴백
    for encoding in ["utf-8", "euc-kr", "cp949"]:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding, header=None)
            return df.to_string(index=False)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError("CSV 인코딩을 판별할 수 없습니다")


def _extract_pdf(file_bytes: bytes) -> str:
    """PDF에서 pdfplumber로 텍스트 추출"""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def _validate_transactions(transactions: list[dict]) -> tuple[list[dict], int]:
    """
    정규화 결과 필드 검증 — 가능한 많은 행을 살리는 관용적 처리.

    - category가 유효 6종에 없으면 → "기타"로 교정 + needs_review=true
    - subtype가 유효 5종에 없으면 → "일반"으로 교정 + needs_review=true
    - date가 YYYY-MM-DD 형식이 아니거나 파싱 불가 → 해당 행 DROP
    - amount가 정수가 아니거나 ≤0이거나 누락 → 해당 행 DROP
    - 전체 배치를 실패시키지 않는다.

    Returns:
        (valid_rows, dropped_count)
    """
    valid_categories = {"식비", "카페·간식", "쇼핑", "교통·이동", "여가·문화", "기타"}
    valid_subtypes = {"배달앱", "편의점", "마트·장보기", "카페", "일반"}

    valid_rows = []
    dropped_count = 0

    for t in transactions:
        # ─── DROP 조건: date 검증 ───
        date_val = t.get("date", "")
        if not isinstance(date_val, str) or not re.match(r"\d{4}-\d{2}-\d{2}$", date_val):
            dropped_count += 1
            continue
        # 날짜 파싱 가능 여부 확인
        try:
            year, month, day = map(int, date_val.split("-"))
            if month < 1 or month > 12 or day < 1 or day > 31:
                dropped_count += 1
                continue
        except (ValueError, TypeError):
            dropped_count += 1
            continue

        # ─── DROP 조건: amount 검증 ───
        amount_val = t.get("amount")
        if not isinstance(amount_val, int) or amount_val <= 0:
            dropped_count += 1
            continue

        # ─── DROP 조건: store 누락 ───
        if not t.get("store"):
            dropped_count += 1
            continue

        # ─── 교정: category ───
        if t.get("category") not in valid_categories:
            t["category"] = "기타"
            t["needs_review"] = True

        # ─── 교정: subtype ───
        if t.get("subtype", "일반") not in valid_subtypes:
            t["subtype"] = "일반"
            t["needs_review"] = True

        valid_rows.append(t)

    return valid_rows, dropped_count


def _upload_to_s3(file_bytes: bytes, filename: str) -> str:
    """원본 파일을 S3 evidence/ 경로에 업로드"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ext = Path(filename).suffix.lower()
    s3_key = f"evidence/{timestamp}-{filename}"

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=file_bytes,
    )
    return s3_key


def _vision_fallback(file_bytes: bytes, s3_key: str) -> dict:
    """스캔형 PDF → pypdfium2 렌더 → 비전 모듈 호출"""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(file_bytes)
    all_transactions = []

    for i in range(len(pdf)):
        page = pdf[i]
        bitmap = page.render(scale=2)  # 해상도 2배
        pil_image = bitmap.to_pil()

        # PIL → bytes
        img_buffer = io.BytesIO()
        pil_image.save(img_buffer, format="PNG")
        img_bytes = img_buffer.getvalue()

        # 비전 모듈 호출
        page_result = analyze_image_vision(img_bytes, "image/png")
        if isinstance(page_result, list):
            all_transactions.extend(page_result)

    return {
        "transactions": all_transactions,
        "s3_key": s3_key,
        "total_count": len(all_transactions),
        "filtered_count": 0,
    }


def _mock_response() -> dict:
    """Mock 모드: 고정 샘플 응답 반환"""
    return {
        "transactions": [
            {"date": "2026-08-01", "store": "배달의민족-교촌치킨", "amount": 25000, "category": "식비", "subtype": "배달앱", "needs_review": False},
            {"date": "2026-08-02", "store": "스타벅스 강남역점", "amount": 6500, "category": "카페·간식", "subtype": "카페", "needs_review": False},
            {"date": "2026-08-03", "store": "CU 서초점", "amount": 3200, "category": "식비", "subtype": "편의점", "needs_review": False},
            {"date": "2026-08-05", "store": "이마트 성수점", "amount": 67800, "category": "식비", "subtype": "마트·장보기", "needs_review": False},
            {"date": "2026-08-07", "store": "카카오택시", "amount": 12500, "category": "교통·이동", "subtype": "일반", "needs_review": False},
            {"date": "2026-08-10", "store": "무신사스토어", "amount": 89000, "category": "쇼핑", "subtype": "일반", "needs_review": False},
            {"date": "2026-08-12", "store": "CGV 왕십리", "amount": 15000, "category": "여가·문화", "subtype": "일반", "needs_review": False},
            {"date": "2026-08-15", "store": "PG결제-알수없음", "amount": 33000, "category": "기타", "subtype": "일반", "needs_review": True},
        ],
        "s3_key": "mock/placeholder.pdf",
        "total_count": 8,
        "filtered_count": 2,
    }
```

### 서브타입 키워드 매핑 (참조 테이블)

| 서브타입 | 키워드 목록 |
|---------|------------|
| 배달앱 | 배달의민족, 요기요, 쿠팡이츠, 배민, 땡겨요, 위메프오 |
| 편의점 | GS25, CU, 세븐일레븐, 이마트24, 미니스톱, GS더프레시 |
| 마트·장보기 | 이마트, 홈플러스, 롯데마트, 하나로마트, 코스트코, 트레이더스, 마트 |
| 카페 | 스타벅스, 메가커피, 투썸, 이디야, 커피빈, 할리스, 카페, 커피, 빽다방, 컴포즈 |
| 일반 | 위 키워드에 해당하지 않는 모든 가맹점 |


---

## 7. Bedrock 공통 래퍼 (core/bedrock.py)

### 설계 목적

parse.py와 verdict.py가 각각 Bedrock을 호출하는 대신, 공통 래퍼를 통해 일관된 에러 처리·재시도·Mock 분기를 적용한다.

### 구현

```python
"""Bedrock 공통 래퍼 — core/bedrock.py

parse.py와 verdict.py가 공유하는 Bedrock invoke 래퍼.
MOCK_AI=1 환경에서는 실제 호출 없이 고정 응답을 반환한다.
"""

import os
import json
import re
from typing import Any

import boto3

# ─── 환경 설정 ────────────────────────────────────────────────
MOCK_AI = os.environ.get("MOCK_AI", "0") == "1"
MODEL_ID = "global.anthropic.claude-sonnet-5"


class BedrockError(Exception):
    """Bedrock 호출 실패 시 사용하는 커스텀 예외"""

    def __init__(self, message: str, original: Exception | None = None):
        super().__init__(message)
        self.original = original


# ─── Mock 응답 저장소 ──────────────────────────────────────────
MOCK_RESPONSES: dict[str, Any] = {
    "parse": [
        {"date": "2026-08-01", "store": "배달의민족-교촌치킨", "amount": 25000, "category": "식비", "subtype": "배달앱", "needs_review": False},
        {"date": "2026-08-02", "store": "스타벅스 강남역점", "amount": 6500, "category": "카페·간식", "subtype": "카페", "needs_review": False},
        {"date": "2026-08-03", "store": "CU 서초점", "amount": 3200, "category": "식비", "subtype": "편의점", "needs_review": False},
        {"date": "2026-08-05", "store": "이마트 성수점", "amount": 67800, "category": "식비", "subtype": "마트·장보기", "needs_review": False},
        {"date": "2026-08-07", "store": "카카오택시", "amount": 12500, "category": "교통·이동", "subtype": "일반", "needs_review": False},
        {"date": "2026-08-10", "store": "무신사스토어", "amount": 89000, "category": "쇼핑", "subtype": "일반", "needs_review": False},
        {"date": "2026-08-12", "store": "CGV 왕십리", "amount": 15000, "category": "여가·문화", "subtype": "일반", "needs_review": False},
        {"date": "2026-08-15", "store": "PG결제-알수없음", "amount": 33000, "category": "기타", "subtype": "일반", "needs_review": True},
    ],
    "verdict": {
        "article": "소비보호법 제4조 (냉장고의 존엄)",
        "ruling": "피고인을 배달앱 7일 금지에 처한다",
        "reasoning": "피고인은 한 달간 냉장고를 장식품으로 전락시킨 혐의가 명백하다. 배달앱 결제 내역이 총 지출의 41.6%를 차지하며, 냉장고 안에는 유통기한 지난 소스만 잔뜩 발견되었다.",
        "sentence": "1. 이번 주 3회 이상 자취 요리 실행\n2. 배달앱 알림 OFF\n3. 냉장고에 사과문 부착",
        "type_description": "냉장고는 전기세만 먹는 가전이 된 지 오래. 당신의 주방은 배달 포장지 수거함이며, 요리 도구는 포장 뜯는 가위뿐이다. 하지만 걱정 마라, 냉장고도 언젠간 당신을 용서할 것이다.",
    },
}


def invoke_bedrock(
    operation: str,
    messages: list[dict],
    mock_key: str,
    max_tokens: int = 4096,
) -> Any:
    """
    Bedrock Claude Sonnet 5 호출 통합 래퍼.

    Args:
        operation: 호출 목적 설명 (로깅용, 예: "지출내역 정규화", "판결문 생성")
        messages: Bedrock Messages API 형식의 메시지 리스트
        mock_key: MOCK_AI=1일 때 MOCK_RESPONSES에서 참조할 키 ("parse" | "verdict")
        max_tokens: 최대 생성 토큰 수 (기본 4096)

    Returns:
        파싱된 JSON 객체 (list 또는 dict)

    Raises:
        BedrockError: 재시도 포함 최종 실패 시
    """
    # ─── Mock 모드: 즉시 고정 응답 반환 ───────────────────────
    if MOCK_AI:
        return MOCK_RESPONSES[mock_key]

    # ─── 실제 Bedrock 호출 ────────────────────────────────────
    return _call_with_retry(operation, messages, max_tokens)


def _call_with_retry(
    operation: str,
    messages: list[dict],
    max_tokens: int,
) -> Any:
    """1회 재시도를 포함한 Bedrock 호출 내부 함수"""
    last_error: Exception | None = None

    for attempt in range(2):  # 최대 2회 시도 (원본 + 1회 재시도)
        try:
            raw_text = _invoke_model(messages, max_tokens)
            parsed = _extract_json(raw_text)
            return parsed
        except Exception as e:
            last_error = e
            if attempt == 0:
                # 첫 번째 실패: 재시도
                continue
            # 두 번째 실패: 예외 발생
            break

    raise BedrockError(
        f"{operation} 실패: Bedrock 응답을 처리할 수 없습니다. 잠시 후 다시 시도해주세요.",
        original=last_error,
    )


def _invoke_model(messages: list[dict], max_tokens: int) -> str:
    """Bedrock invoke_model 호출 → 응답 텍스트 추출"""
    bedrock = boto3.client("bedrock-runtime")

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
    })

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=body,
    )

    response_body = json.loads(response["body"].read())
    # content 블록에서 텍스트만 결합
    text_parts = [
        block.get("text", "")
        for block in response_body.get("content", [])
        if block.get("type") == "text"
    ]
    raw_text = "".join(text_parts).strip()

    if not raw_text:
        raise ValueError("Bedrock 응답이 비어 있습니다")

    return raw_text


def _extract_json(raw_text: str) -> Any:
    """
    Bedrock 응답 텍스트에서 JSON 객체/배열을 추출한다.
    마크다운 코드블록 안에 있을 수도 있고, 순수 JSON일 수도 있다.
    """
    # 마크다운 코드블록 제거 (```json ... ``` 패턴)
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # JSON 배열 시도 (parse용)
    array_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    # JSON 객체 시도 (verdict용)
    obj_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    # 전체 텍스트를 직접 파싱 시도
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError(f"JSON 파싱 실패: 유효한 JSON을 찾을 수 없습니다. 원본 길이={len(raw_text)}")
```

### 호출 예시

```python
# core/parse.py에서 사용
from core.bedrock import invoke_bedrock, BedrockError

def normalize_text(raw_text: str) -> list[dict]:
    """원시 텍스트를 Bedrock으로 정규화하여 트랜잭션 리스트로 반환"""
    messages = [{"role": "user", "content": NORMALIZATION_PROMPT.replace("{raw_text}", raw_text)}]
    return invoke_bedrock(
        operation="지출내역 정규화",
        messages=messages,
        mock_key="parse",
        max_tokens=8192,
    )

# core/verdict.py에서 사용
from core.bedrock import invoke_bedrock, BedrockError

def generate_verdict_prose(prompt_text: str) -> dict:
    """판결문 산문을 Bedrock으로 생성"""
    messages = [{"role": "user", "content": prompt_text}]
    return invoke_bedrock(
        operation="판결문 생성",
        messages=messages,
        mock_key="verdict",
        max_tokens=2048,
    )
```

---

## 8. 대용량 파일 처리 (Chunking)

### 설계 배경

카드사 지출내역 파일은 3개월치 이상이 한 파일에 포함될 수 있다. Bedrock의 컨텍스트 한계와 응답 품질을 고려해 50행 단위로 분할 처리한다.

### 구현

```python
"""대용량 파일 청킹 모듈 — core/parse.py 내부 함수

50행 초과 시 분할하여 Bedrock 정규화를 여러 번 호출한 뒤 병합한다.
대상 월(target_month)이 지정되면 해당 월 행만 필터링한다.
"""

import re
from core.bedrock import invoke_bedrock, MOCK_AI

# 청크 사이즈: 한 번에 Bedrock에 보낼 최대 행 수
CHUNK_SIZE = 50


def chunk_and_normalize(raw_text: str, target_month: str) -> list[dict]:
    """
    원시 텍스트를 청킹하여 Bedrock 정규화를 수행한다.

    Args:
        raw_text: 파일에서 추출한 원시 텍스트 전체
        target_month: 대상 월 (YYYY-MM 형식, 예: "2026-08")

    Returns:
        정규화된 트랜잭션 리스트 (대상 월 건만 포함)
    """
    if MOCK_AI:
        from core.bedrock import MOCK_RESPONSES
        return MOCK_RESPONSES["parse"]

    # 1. 텍스트를 행 단위로 분리
    lines = raw_text.strip().split("\n")

    # 2. 헤더 행 식별 (첫 번째 행이 헤더일 가능성)
    #    헤더 판정: 숫자(금액)가 포함되지 않은 행
    header_line = ""
    data_lines = lines
    if lines and not re.search(r"\d{4,}", lines[0]):
        header_line = lines[0]
        data_lines = lines[1:]

    # 3. 대상 월 사전 필터링 (가능한 경우)
    #    날짜 패턴이 보이는 행만 필터 → 대상 월에 해당하는 행 추출
    #    날짜 패턴: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, MM-DD, MM/DD
    target_prefix = target_month  # "2026-08"
    target_patterns = [
        target_month,                                    # 2026-08
        target_month.replace("-", "."),                  # 2026.08
        target_month.replace("-", "/"),                  # 2026/08
        f"{int(target_month.split('-')[1]):02d}",       # 08 (월만)
    ]

    filtered_lines = []
    for line in data_lines:
        # 날짜 패턴이 행에 포함되는지 확인
        has_date = any(pat in line for pat in target_patterns)
        # 날짜 패턴을 찾을 수 없는 행도 포함 (LLM이 판단하도록)
        if has_date or not re.search(r"\d{4}[-./]\d{2}[-./]\d{2}", line):
            filtered_lines.append(line)

    # 필터링 결과가 너무 적으면 전체 사용 (LLM에게 월 필터링 위임)
    if len(filtered_lines) < 5:
        filtered_lines = data_lines

    # 4. 청킹: CHUNK_SIZE행 단위로 분할
    chunks = []
    for i in range(0, len(filtered_lines), CHUNK_SIZE):
        chunk_lines = filtered_lines[i:i + CHUNK_SIZE]
        # 헤더가 있으면 각 청크 앞에 붙임 (컬럼 맥락 유지)
        if header_line:
            chunk_text = header_line + "\n" + "\n".join(chunk_lines)
        else:
            chunk_text = "\n".join(chunk_lines)
        chunks.append(chunk_text)

    # 5. 각 청크를 Bedrock으로 정규화
    all_transactions: list[dict] = []

    for idx, chunk_text in enumerate(chunks):
        prompt = _build_normalization_prompt(chunk_text, target_month)
        messages = [{"role": "user", "content": prompt}]

        chunk_result = invoke_bedrock(
            operation=f"지출내역 정규화 (청크 {idx + 1}/{len(chunks)})",
            messages=messages,
            mock_key="parse",
            max_tokens=8192,
        )

        if isinstance(chunk_result, list):
            all_transactions.extend(chunk_result)

    # 6. 최종 대상 월 필터링 (LLM이 다른 월 데이터를 포함했을 수 있음)
    month_filtered = [
        t for t in all_transactions
        if t.get("date", "").startswith(target_month)
    ]

    # 대상 월 건이 0이면 전체 반환 (월 추론 실패 케이스)
    return month_filtered if month_filtered else all_transactions


def _build_normalization_prompt(chunk_text: str, target_month: str) -> str:
    """청크용 정규화 프롬프트 생성 (대상 월 명시)"""
    from core.parse import NORMALIZATION_PROMPT

    # 기본 프롬프트에 대상 월 힌트 추가
    month_hint = f"\n\n## 추가 지시\n- 대상 월은 {target_month}입니다. 이 월에 해당하는 지출만 추출하세요.\n- 다른 월의 거래는 제외하세요.\n\n---\n아래가 분석할 원시 텍스트입니다:\n\n{chunk_text}"

    # NORMALIZATION_PROMPT에서 {raw_text} 이후 부분을 교체
    base_prompt = NORMALIZATION_PROMPT.split("---\n아래가 분석할 원시 텍스트입니다:")[0]
    return base_prompt + month_hint
```

### parse_file 통합

```python
# core/parse.py의 parse_file 함수 내부에서 chunk_and_normalize 호출
def parse_file(file_bytes: bytes, filename: str, nickname: str, target_month: str = None) -> dict:
    """
    업로드된 파일을 파싱하여 정규화된 트랜잭션 리스트를 반환한다.
    target_month가 지정되면 해당 월 데이터만 추출한다.
    """
    if MOCK_AI:
        return _mock_response()

    s3_key = _upload_to_s3(file_bytes, filename)
    ext = Path(filename).suffix.lower()

    if ext in (".xlsx", ".xls"):
        raw_text = _extract_excel(file_bytes)
    elif ext == ".csv":
        raw_text = _extract_csv(file_bytes)
    elif ext == ".pdf":
        raw_text = _extract_pdf(file_bytes)
        if not raw_text or len(raw_text.strip()) < 50:
            return _vision_fallback(file_bytes, s3_key)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {ext}")

    # 대상 월이 없으면 현재 월 사용
    if not target_month:
        from datetime import datetime
        target_month = datetime.now().strftime("%Y-%m")

    # 행 수 판단 → 청킹 여부 결정
    lines = raw_text.strip().split("\n")
    if len(lines) > CHUNK_SIZE:
        transactions = chunk_and_normalize(raw_text, target_month)
    else:
        transactions = _normalize_single(raw_text, target_month)

    return {
        "transactions": transactions,
        "s3_key": s3_key,
        "total_count": len(transactions),
        "filtered_count": 0,
    }


def _normalize_single(raw_text: str, target_month: str) -> list[dict]:
    """50행 이하 소규모 텍스트의 단일 호출 정규화"""
    prompt = _build_normalization_prompt(raw_text, target_month)
    messages = [{"role": "user", "content": prompt}]

    result = invoke_bedrock(
        operation="지출내역 정규화",
        messages=messages,
        mock_key="parse",
        max_tokens=8192,
    )

    if isinstance(result, list):
        # 대상 월 필터
        filtered = [t for t in result if t.get("date", "").startswith(target_month)]
        return filtered if filtered else result
    return []
```

---

## 9. index.html 단일 파일 구조

### 설계 방침

- 순수 HTML/CSS/JS, 프레임워크 없음
- 모바일 세로 기준, 데스크톱에서 max-width: 480px 중앙 고정
- 7개 화면을 div 전환으로 처리 (SPA)
- 재판소 콘셉트의 다크 + 종이 텍스처 컬러 팔레트

### 완전한 HTML 스켈레톤

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>영수증 소비 재판소</title>
    <style>
        /* ─── CSS 변수 ─────────────────────────────────────── */
        :root {
            --bg-dark: #1a1a1a;
            --paper: #f5f0e8;
            --burgundy: #8b1a2b;
            --gold: #c4a04a;
            --text-light: #e8e0d4;
            --text-dark: #2c2c2c;
            --success: #2d8a4e;
            --error: #c0392b;
            --border: #3a3a3a;
            --tab-height: 60px;
        }

        /* ─── 리셋 및 기본 스타일 ─────────────────────────── */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-dark);
            color: var(--text-light);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* ─── 중앙 컨테이너 (480px 최대) ─────────────────── */
        #app-container {
            max-width: 480px;
            margin: 0 auto;
            min-height: 100vh;
            position: relative;
            background: var(--bg-dark);
        }

        /* ─── 화면 섹션 공통 ─────────────────────────────── */
        .screen {
            display: none;
            padding: 20px 16px;
            padding-bottom: calc(var(--tab-height) + 20px);
            min-height: 100vh;
            animation: fadeIn 0.2s ease-in;
        }

        .screen.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        /* ─── 종이 스타일 카드 ────────────────────────────── */
        .paper-card {
            background: var(--paper);
            color: var(--text-dark);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }

        /* ─── 버튼 스타일 ────────────────────────────────── */
        .btn-primary {
            width: 100%;
            padding: 14px;
            background: var(--burgundy);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }

        .btn-primary:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .btn-primary:active:not(:disabled) {
            opacity: 0.8;
        }

        .btn-secondary {
            width: 100%;
            padding: 14px;
            background: transparent;
            color: var(--gold);
            border: 1px solid var(--gold);
            border-radius: 8px;
            font-size: 14px;
            cursor: pointer;
        }

        /* ─── 입력 필드 ──────────────────────────────────── */
        .input-field {
            width: 100%;
            padding: 12px;
            background: #2a2a2a;
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-light);
            font-size: 15px;
            outline: none;
            transition: border-color 0.2s;
        }

        .input-field:focus {
            border-color: var(--gold);
        }

        .input-field.error {
            border-color: var(--error);
        }

        /* ─── 카테고리 칩 ────────────────────────────────── */
        .chip-group {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 12px 0;
        }

        .chip {
            padding: 8px 14px;
            border-radius: 20px;
            border: 1px solid var(--border);
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
            color: var(--text-light);
            background: transparent;
        }

        .chip.selected {
            background: var(--burgundy);
            border-color: var(--burgundy);
            color: white;
        }

        /* ─── 토스트 ─────────────────────────────────────── */
        #toast-container {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 9999;
            max-width: 440px;
            width: calc(100% - 40px);
        }

        .toast {
            background: var(--text-dark);
            color: var(--text-light);
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 14px;
            animation: toastIn 0.3s ease-out;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
        }

        .toast.fade-out {
            animation: toastOut 0.3s ease-in forwards;
        }

        @keyframes toastIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes toastOut {
            from { opacity: 1; }
            to { opacity: 0; }
        }

        /* ─── 로딩 인디케이터 ────────────────────────────── */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.6);
            z-index: 8888;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }

        .loading-overlay.active {
            display: flex;
        }

        .loading-spinner {
            width: 40px;
            height: 40px;
            border: 3px solid var(--border);
            border-top-color: var(--gold);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .loading-text {
            margin-top: 12px;
            color: var(--text-light);
            font-size: 14px;
        }

        /* ─── 하단 탭바 ──────────────────────────────────── */
        #tab-bar {
            display: none;
            position: fixed;
            bottom: 0;
            left: 50%;
            transform: translateX(-50%);
            max-width: 480px;
            width: 100%;
            height: var(--tab-height);
            background: #111;
            border-top: 1px solid var(--border);
            z-index: 7777;
        }

        #tab-bar.visible {
            display: flex;
            justify-content: space-around;
            align-items: center;
        }

        .tab-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            padding: 8px 0;
            cursor: pointer;
            opacity: 0.5;
            transition: opacity 0.2s;
            flex: 1;
        }

        .tab-item.active {
            opacity: 1;
            color: var(--gold);
        }

        .tab-icon {
            font-size: 20px;
        }

        .tab-label {
            font-size: 11px;
        }

        /* ─── 판결문 종이 스타일 ──────────────────────────── */
        .verdict-paper {
            background: var(--paper);
            color: var(--text-dark);
            border-radius: 4px;
            padding: 28px 20px;
            font-family: 'Nanum Myeongjo', serif, -apple-system, sans-serif;
            line-height: 1.8;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
        }

        .verdict-header {
            text-align: center;
            border-bottom: 2px solid var(--text-dark);
            padding-bottom: 16px;
            margin-bottom: 20px;
        }

        .verdict-charge {
            font-size: 22px;
            color: var(--burgundy);
            font-weight: 700;
            margin: 16px 0;
        }

        .verdict-stamp {
            width: 80px;
            height: 80px;
            border: 3px solid var(--burgundy);
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            margin: 20px auto;
            font-size: 11px;
            color: var(--burgundy);
            font-weight: 700;
            transform: rotate(-15deg);
        }

        .verdict-stamp.acquitted {
            border-color: var(--success);
            color: var(--success);
        }

        /* ─── 유형 카드 ──────────────────────────────────── */
        .type-card {
            background: linear-gradient(135deg, #2a1a1a, #1a1a2a);
            border: 1px solid var(--gold);
            border-radius: 12px;
            padding: 24px;
            text-align: center;
        }

        .type-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-top: 16px;
        }

        .type-grid-item {
            background: #2a2a2a;
            border-radius: 8px;
            padding: 10px 4px;
            font-size: 11px;
            text-align: center;
            position: relative;
        }

        .type-grid-item.current::after {
            content: '';
            position: absolute;
            top: 4px;
            right: 4px;
            width: 8px;
            height: 8px;
            background: var(--burgundy);
            border-radius: 50%;
        }

        /* ─── 반응형 ─────────────────────────────────────── */
        @media (max-width: 480px) {
            #app-container {
                max-width: 100%;
            }
        }
    </style>
</head>
<body>
    <!-- 토스트 컨테이너 -->
    <div id="toast-container"></div>

    <!-- 로딩 오버레이 -->
    <div class="loading-overlay" id="loading-overlay">
        <div class="loading-spinner"></div>
        <p class="loading-text" id="loading-text">처리 중...</p>
    </div>

    <!-- 앱 컨테이너 -->
    <div id="app-container">

        <!-- ════════════════════════════════════════════════ -->
        <!-- 01. 온보딩 화면 -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-onboarding" class="screen active">
            <div style="text-align: center; padding-top: 60px;">
                <h1 style="font-size: 28px; margin-bottom: 8px;">영수증<br>소비 재판소</h1>
                <p style="color: var(--gold); font-size: 14px; margin-bottom: 40px;">당신의 소비를 심판합니다</p>
            </div>

            <div style="margin-bottom: 16px;">
                <label style="font-size: 13px; margin-bottom: 6px; display: block;">닉네임 (최대 12자)</label>
                <input type="text" id="input-nickname" class="input-field" maxlength="12" placeholder="닉네임을 입력하세요">
                <p id="err-nickname" style="color: var(--error); font-size: 12px; margin-top: 4px; display: none;"></p>
            </div>

            <div style="margin-bottom: 24px;">
                <label style="font-size: 13px; margin-bottom: 6px; display: block;">나이 (선택)</label>
                <input type="number" id="input-age" class="input-field" min="1" max="120" placeholder="숫자만 입력">
                <p id="err-age" style="color: var(--error); font-size: 12px; margin-top: 4px; display: none;"></p>
            </div>

            <button class="btn-primary" id="btn-start" style="margin-bottom: 12px;">영수증 등록하고 시작하기</button>
            <button class="btn-secondary" id="btn-existing">이미 등록한 내역 보기</button>
        </div>

        <!-- ════════════════════════════════════════════════ -->
        <!-- 02. 홈 화면 -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-home" class="screen">
            <div class="paper-card">
                <p style="font-size: 13px; color: #666;">이번 달 총 지출</p>
                <p id="home-total" style="font-size: 32px; font-weight: 700; color: var(--text-dark);">0원</p>
                <p id="home-count" style="font-size: 13px; color: #888; margin-top: 4px;"></p>
                <span id="home-dday" style="display: inline-block; background: var(--burgundy); color: white; padding: 4px 10px; border-radius: 12px; font-size: 12px; margin-top: 8px;"></span>
            </div>

            <div id="home-chart" style="margin-bottom: 16px;"></div>

            <div id="home-recent" style="margin-bottom: 16px;"></div>

            <button class="btn-primary" id="btn-verdict-home"></button>

            <div id="home-empty" style="display: none; text-align: center; padding: 40px 0; color: #888;">
                <p style="font-size: 40px; margin-bottom: 12px;">📋</p>
                <p>아직 등록된 영수증이 없습니다</p>
                <p style="font-size: 13px; margin-top: 8px;">하단 '등록' 탭에서 영수증을 추가해보세요</p>
            </div>
        </div>

        <!-- ════════════════════════════════════════════════ -->
        <!-- 03. 등록 화면 -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-register" class="screen">
            <h2 style="font-size: 20px; margin-bottom: 20px;">영수증 등록</h2>

            <!-- 파일 업로드 영역 -->
            <div style="border: 1px dashed var(--border); border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 20px;">
                <p style="font-size: 14px; margin-bottom: 8px;">지출내역 파일 업로드</p>
                <p style="font-size: 12px; color: #888; margin-bottom: 12px;">PDF, Excel, CSV (최대 10MB)</p>
                <input type="file" id="input-file" accept=".pdf,.xlsx,.xls,.csv" style="display: none;">
                <button class="btn-secondary" id="btn-file-select" style="width: auto; padding: 10px 20px;">파일 선택</button>
            </div>

            <div style="text-align: center; margin-bottom: 20px; color: #666; font-size: 13px;">또는 직접 입력</div>

            <!-- 수동 입력 폼 -->
            <div id="manual-form">
                <div style="margin-bottom: 12px;">
                    <label style="font-size: 13px; margin-bottom: 6px; display: block;">가맹점명 *</label>
                    <input type="text" id="input-store" class="input-field" maxlength="50" placeholder="예: 배달의민족-맛있는족발">
                </div>

                <div style="display: flex; gap: 12px; margin-bottom: 12px;">
                    <div style="flex: 1;">
                        <label style="font-size: 13px; margin-bottom: 6px; display: block;">날짜 *</label>
                        <input type="date" id="input-date" class="input-field">
                    </div>
                    <div style="flex: 1;">
                        <label style="font-size: 13px; margin-bottom: 6px; display: block;">금액 *</label>
                        <input type="number" id="input-amount" class="input-field" min="1" placeholder="원">
                    </div>
                </div>

                <div style="margin-bottom: 12px;">
                    <label style="font-size: 13px; margin-bottom: 6px; display: block;">카테고리 *</label>
                    <div class="chip-group" id="category-chips">
                        <span class="chip" data-value="식비">식비</span>
                        <span class="chip" data-value="카페·간식">카페·간식</span>
                        <span class="chip" data-value="쇼핑">쇼핑</span>
                        <span class="chip" data-value="교통·이동">교통·이동</span>
                        <span class="chip" data-value="여가·문화">여가·문화</span>
                        <span class="chip" data-value="기타">기타</span>
                    </div>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="font-size: 13px; margin-bottom: 6px; display: block;">메모 (선택)</label>
                    <input type="text" id="input-memo" class="input-field" maxlength="100" placeholder="이 소비에 대한 한마디">
                </div>

                <button class="btn-primary" id="btn-submit-receipt" disabled>등록하기</button>
            </div>

            <!-- 파싱 결과 리뷰 영역 (파일 업로드 후 표시) -->
            <div id="parse-review" style="display: none;">
                <h3 style="font-size: 16px; margin-bottom: 12px;">파싱 결과 확인</h3>
                <div id="parse-results-list"></div>
                <button class="btn-secondary" id="btn-add-row" style="margin: 12px 0;">+ 수동 추가</button>
                <button class="btn-primary" id="btn-save-parsed">전체 저장하기</button>
            </div>
        </div>

        <!-- ════════════════════════════════════════════════ -->
        <!-- 04. 내역 화면 -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-history" class="screen">
            <h2 style="font-size: 20px; margin-bottom: 16px;">소비 내역</h2>

            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <select id="history-month" class="input-field" style="width: auto; flex: 0 0 auto;"></select>
            </div>

            <div class="chip-group" id="history-filter-chips" style="margin-bottom: 16px; overflow-x: auto; flex-wrap: nowrap;">
                <span class="chip selected" data-value="전체">전체</span>
                <span class="chip" data-value="식비">식비</span>
                <span class="chip" data-value="카페·간식">카페·간식</span>
                <span class="chip" data-value="쇼핑">쇼핑</span>
                <span class="chip" data-value="교통·이동">교통·이동</span>
                <span class="chip" data-value="여가·문화">여가·문화</span>
                <span class="chip" data-value="기타">기타</span>
            </div>

            <div id="history-summary" style="font-size: 13px; color: #aaa; margin-bottom: 12px;"></div>

            <div id="history-list"></div>

            <div id="history-empty" style="display: none; text-align: center; padding: 40px 0; color: #888;">
                <p>해당 기간의 지출 내역이 없습니다</p>
            </div>
        </div>

        <!-- ════════════════════════════════════════════════ -->
        <!-- 05. 분석 화면 (판결 탭) -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-analysis" class="screen">
            <h2 style="font-size: 20px; margin-bottom: 16px;">소비 분석</h2>

            <div class="paper-card" id="analysis-summary">
                <p id="analysis-total" style="font-size: 28px; font-weight: 700; color: var(--text-dark);"></p>
                <div style="display: flex; gap: 16px; margin-top: 8px;">
                    <span id="analysis-count" style="font-size: 13px; color: #666;"></span>
                    <span id="analysis-daily" style="font-size: 13px; color: #666;"></span>
                </div>
            </div>

            <div id="analysis-categories" style="margin-bottom: 16px;"></div>

            <div style="display: flex; gap: 12px; margin-bottom: 20px;">
                <div class="paper-card" style="flex: 1; margin-bottom: 0;">
                    <p style="font-size: 11px; color: #888;">최다 지출 카테고리</p>
                    <p id="analysis-top-cat" style="font-size: 15px; font-weight: 600; color: var(--text-dark);"></p>
                    <p id="analysis-top-pct" style="font-size: 12px; color: var(--burgundy);"></p>
                </div>
                <div class="paper-card" style="flex: 1; margin-bottom: 0;">
                    <p style="font-size: 11px; color: #888;">가장 큰 단일 지출</p>
                    <p id="analysis-max-store" style="font-size: 15px; font-weight: 600; color: var(--text-dark);"></p>
                    <p id="analysis-max-amount" style="font-size: 12px; color: var(--burgundy);"></p>
                </div>
            </div>

            <button class="btn-primary" id="btn-verdict-analysis">이 증거로 판결받기</button>

            <div id="analysis-empty" style="display: none; text-align: center; padding: 40px 0; color: #888;">
                <p>이번 달 소비 데이터가 없습니다</p>
            </div>
        </div>

        <!-- ════════════════════════════════════════════════ -->
        <!-- 06. 판결문 화면 -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-verdict" class="screen">
            <div class="verdict-paper" id="verdict-document">
                <!-- JS에서 동적 렌더링 -->
            </div>

            <div style="display: flex; gap: 12px; margin-top: 16px;">
                <button class="btn-secondary" style="flex: 1; opacity: 0.5;" disabled>이미지 저장</button>
                <button class="btn-secondary" style="flex: 1; opacity: 0.5;" disabled>공유하기</button>
            </div>

            <button class="btn-primary" id="btn-goto-type" style="margin-top: 12px;">내 소비 유형 확인하기 →</button>
        </div>

        <!-- ════════════════════════════════════════════════ -->
        <!-- 07. 소비 유형 화면 -->
        <!-- ════════════════════════════════════════════════ -->
        <div id="screen-type" class="screen">
            <p id="type-header" style="font-size: 13px; color: #888; text-align: center; margin-bottom: 4px;"></p>
            <p style="font-size: 14px; text-align: center; margin-bottom: 20px; color: var(--gold);">당신의 소비 유형</p>

            <div class="type-card" id="type-result-card">
                <!-- JS에서 동적 렌더링 -->
            </div>

            <div style="margin-top: 20px;">
                <p style="font-size: 13px; color: #888; margin-bottom: 4px;">다음 달의 형량</p>
                <div id="type-sentence" style="background: #2a2a2a; border-radius: 8px; padding: 14px; font-size: 14px; line-height: 1.6; cursor: pointer;"></div>
            </div>

            <div style="margin-top: 24px;">
                <p style="font-size: 14px; margin-bottom: 12px;">소비 유형 도감 <span id="type-collection" style="color: var(--gold);"></span></p>
                <div class="type-grid" id="type-grid">
                    <!-- JS에서 8종 유형 그리드 렌더링 -->
                </div>
            </div>

            <button class="btn-primary" id="btn-next-month" style="margin-top: 24px;">다음 달 재판 시작하기</button>
        </div>

    </div><!-- /app-container -->

    <!-- ════════════════════════════════════════════════════ -->
    <!-- 하단 탭바 -->
    <!-- ════════════════════════════════════════════════════ -->
    <div id="tab-bar">
        <div class="tab-item active" data-screen="home">
            <span class="tab-icon">🏠</span>
            <span class="tab-label">홈</span>
        </div>
        <div class="tab-item" data-screen="register">
            <span class="tab-icon">📝</span>
            <span class="tab-label">등록</span>
        </div>
        <div class="tab-item" data-screen="history">
            <span class="tab-icon">📋</span>
            <span class="tab-label">내역</span>
        </div>
        <div class="tab-item" data-screen="analysis">
            <span class="tab-icon">⚖️</span>
            <span class="tab-label">판결</span>
        </div>
    </div>

    <!-- ════════════════════════════════════════════════════ -->
    <!-- JavaScript -->
    <!-- ════════════════════════════════════════════════════ -->
    <script>
    (function() {
        'use strict';

        /* ─── 전역 상태 ───────────────────────────────── */
        const state = {
            nickname: '',
            age: null,
            currentScreen: 'onboarding',
            currentVerdict: null,
            dripIndex: {},  // 유형별 드립 메시지 인덱스 추적
        };

        /* ─── 드립 메시지 (유형별 3~4개) ──────────────── */
        const DRIP_MESSAGES = {
            '냉장고보다 배달앱형': [
                '냉장고가 당신에게 소송을 걸고 싶어합니다.',
                '배달앱 사장님이 당신을 VIP로 등록했습니다.',
                '당신의 냉장고 안: 소스 3개, 얼음, 유통기한 지난 우유.',
                '배달비만 모았으면 에어프라이어 샀다.',
            ],
            '편의점이 내 부엌형': [
                '편의점 점장님: "아, 오늘도 오셨군요."',
                '삼각김밥이 당신의 주식입니다. (주식이 아니라 주식)',
                '편의점 도시락 마일리지로 여행 가능.',
                'GS25 출석체크 30일 달성! 보상: 없음.',
            ],
            '소확행 충전형': [
                '아메리카노 한 잔의 여유... 가 한 달에 12만원.',
                '카페 Wi-Fi가 당신의 세컨드 오피스.',
                '바리스타가 주문 전에 "아아요?" 라고 물어봅니다.',
                '카페인 없이는 출근 불가. 이것은 의료비.',
            ],
            '취향에 진심형': [
                '장바구니 정리 = 국가대표급 결단력 필요.',
                '"이건 투자야" 라는 말, 올해만 47번 함.',
                '무신사 찜 목록이 이력서보다 깁니다.',
            ],
            '월초 플렉스형': [
                '월급날: 부자. 월급날+3일: 거지.',
                '통장 잔고 그래프가 롤러코스터.',
                '월초의 나 vs 월말의 나: 완전히 다른 인격.',
                '"이번 달은 아껴야지" → 월급일 당일 파기.',
            ],
            '티끌 과소비형': [
                '1,200원짜리가 15번이면... 계산기 두드려봐.',
                '소액이라 괜찮다고? 통장은 그렇게 안 봅니다.',
                '편의점 영수증 길이: 내 키만큼.',
            ],
            '야무진 자취생형': [
                '어머니가 보시면 뿌듯해하실 장보기 실력.',
                '마트 할인 요일을 외우고 있는 프로 자취러.',
                '당신의 냉장고: 정리정돈 교과서.',
                '밀키트 대신 직접 하는 갓생.',
            ],
            '균형 잡힌 생존형': [
                '판사도 뭐라 할 게 없어서 당황 중.',
                '특별히 혼날 건 없지만... 칭찬할 것도 없다.',
                '가장 무서운 판결: 무혐의 (할 말이 없음).',
            ],
        };

        /* ─── 화면 전환 ───────────────────────────────── */
        function navigateTo(screenId) {
            // 모든 화면 숨기기
            document.querySelectorAll('.screen').forEach(el => {
                el.classList.remove('active');
            });

            // 대상 화면 표시
            const target = document.getElementById('screen-' + screenId);
            if (target) {
                target.classList.add('active');
            }

            state.currentScreen = screenId;

            // 탭바 표시/숨김
            const tabBar = document.getElementById('tab-bar');
            if (screenId === 'onboarding') {
                tabBar.classList.remove('visible');
            } else {
                tabBar.classList.add('visible');
            }

            // 탭 활성 상태 업데이트
            document.querySelectorAll('.tab-item').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.screen === screenId);
            });

            // 화면별 데이터 로드
            if (screenId === 'home') loadHomeData();
            if (screenId === 'history') loadHistoryData();
            if (screenId === 'analysis') loadAnalysisData();
        }

        /* ─── 탭 전환 이벤트 ─────────────────────────── */
        document.querySelectorAll('.tab-item').forEach(tab => {
            tab.addEventListener('click', () => {
                navigateTo(tab.dataset.screen);
            });
        });

        /* ─── 토스트 표시 ────────────────────────────── */
        function showToast(message, duration = 3000) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.textContent = message;
            container.appendChild(toast);

            setTimeout(() => {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        /* ─── 드립 메시지 표시 (순환) ────────────────── */
        function showDrip(type) {
            const messages = DRIP_MESSAGES[type];
            if (!messages || messages.length === 0) return;

            // 인덱스 초기화 또는 순환
            if (!state.dripIndex[type]) state.dripIndex[type] = 0;
            const idx = state.dripIndex[type] % messages.length;
            state.dripIndex[type]++;

            showToast(messages[idx], 2500);
        }

        /* ─── 로딩 표시/숨김 ─────────────────────────── */
        let loadingTimer = null;

        function showLoading(text = '처리 중...') {
            const overlay = document.getElementById('loading-overlay');
            document.getElementById('loading-text').textContent = text;
            overlay.classList.add('active');

            // 30초 타임아웃 (판결문·파일 업로드 대응)
            loadingTimer = setTimeout(() => {
                hideLoading();
                showToast('요청 시간이 초과되었습니다. 다시 시도해주세요.', 4000);
            }, 30000);
        }

        function hideLoading() {
            document.getElementById('loading-overlay').classList.remove('active');
            if (loadingTimer) {
                clearTimeout(loadingTimer);
                loadingTimer = null;
            }
        }

        /* ─── API 호출 헬퍼 ──────────────────────────── */
        async function apiCall(url, options = {}) {
            const defaultOptions = {
                headers: { 'Content-Type': 'application/json' },
            };
            const merged = { ...defaultOptions, ...options };

            try {
                // 판결문·파일 업로드는 30초, 나머지는 10초 타임아웃
                const isLongRequest = url.includes('/api/verdict') || url.includes('/api/upload');
                const timeoutMs = isLongRequest ? 30000 : 10000;

                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), timeoutMs);
                merged.signal = controller.signal;

                const response = await fetch(url, merged);
                clearTimeout(timeout);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `HTTP ${response.status} 오류`);
                }

                return await response.json();
            } catch (error) {
                if (error.name === 'AbortError') {
                    throw new Error('요청 시간이 초과되었습니다.');
                }
                throw error;
            }
        }

        async function apiGet(url) {
            return apiCall(url, { method: 'GET' });
        }

        async function apiPost(url, body) {
            return apiCall(url, {
                method: 'POST',
                body: JSON.stringify(body),
            });
        }

        async function apiPostForm(url, formData) {
            try {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), 30000);

                const response = await fetch(url, {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal,
                });
                clearTimeout(timeout);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `HTTP ${response.status} 오류`);
                }

                return await response.json();
            } catch (error) {
                if (error.name === 'AbortError') {
                    throw new Error('파일 처리 시간이 초과되었습니다.');
                }
                throw error;
            }
        }

        /* ─── 숫자 포맷 ──────────────────────────────── */
        function formatAmount(n) {
            return n.toLocaleString('ko-KR') + '원';
        }

        function getCurrentMonth() {
            const now = new Date();
            return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        }

        /* ─── 화면별 데이터 로드 함수 (스텁) ─────────── */
        function loadHomeData() { /* 홈 화면 데이터 로드 */ }
        function loadHistoryData() { /* 내역 화면 데이터 로드 */ }
        function loadAnalysisData() { /* 분석 화면 데이터 로드 */ }

        /* ─── 온보딩 이벤트 ──────────────────────────── */
        document.getElementById('btn-start').addEventListener('click', async () => {
            const nickname = document.getElementById('input-nickname').value.trim();
            const ageStr = document.getElementById('input-age').value.trim();

            // 닉네임 검증
            if (!nickname || nickname.length > 12) {
                document.getElementById('err-nickname').textContent = '닉네임을 1~12자로 입력해주세요.';
                document.getElementById('err-nickname').style.display = 'block';
                return;
            }
            document.getElementById('err-nickname').style.display = 'none';

            // 나이 검증
            let age = null;
            if (ageStr) {
                age = parseInt(ageStr, 10);
                if (isNaN(age) || age < 1 || age > 120) {
                    document.getElementById('err-age').textContent = '나이는 1~120 사이 정수만 가능합니다.';
                    document.getElementById('err-age').style.display = 'block';
                    return;
                }
            }
            document.getElementById('err-age').style.display = 'none';

            try {
                showLoading('입장 중...');
                const body = age ? { age } : {};
                await apiCall(`/api/users/${encodeURIComponent(nickname)}`, {
                    method: 'POST',
                    body: JSON.stringify(body),
                });
                state.nickname = nickname;
                state.age = age;
                hideLoading();
                navigateTo('home');
            } catch (e) {
                hideLoading();
                showToast('서버 연결에 실패했습니다. 다시 시도해주세요.', 4000);
            }
        });

        document.getElementById('btn-existing').addEventListener('click', async () => {
            const nickname = document.getElementById('input-nickname').value.trim();
            if (!nickname) {
                document.getElementById('err-nickname').textContent = '닉네임을 입력해주세요.';
                document.getElementById('err-nickname').style.display = 'block';
                return;
            }
            document.getElementById('err-nickname').style.display = 'none';

            try {
                showLoading('내역 확인 중...');
                const receipts = await apiGet(`/api/receipts/${encodeURIComponent(nickname)}?month=${getCurrentMonth()}`);
                hideLoading();

                if (receipts.length === 0) {
                    document.getElementById('err-nickname').textContent = '해당 닉네임으로 등록된 내역이 없습니다.';
                    document.getElementById('err-nickname').style.display = 'block';
                    return;
                }

                state.nickname = nickname;
                navigateTo('home');
            } catch (e) {
                hideLoading();
                showToast('서버 연결에 실패했습니다.', 4000);
            }
        });

        /* ─── 카테고리 칩 선택 ───────────────────────── */
        document.querySelectorAll('#category-chips .chip').forEach(chip => {
            chip.addEventListener('click', () => {
                document.querySelectorAll('#category-chips .chip').forEach(c => c.classList.remove('selected'));
                chip.classList.add('selected');
                validateManualForm();
            });
        });

        /* ─── 수동 폼 검증 ──────────────────────────── */
        function validateManualForm() {
            const store = document.getElementById('input-store').value.trim();
            const date = document.getElementById('input-date').value;
            const amount = document.getElementById('input-amount').value;
            const category = document.querySelector('#category-chips .chip.selected');
            const btn = document.getElementById('btn-submit-receipt');
            btn.disabled = !(store && date && amount && parseInt(amount) > 0 && category);
        }

        ['input-store', 'input-date', 'input-amount'].forEach(id => {
            document.getElementById(id).addEventListener('input', validateManualForm);
        });

        /* ─── 파일 업로드 ────────────────────────────── */
        document.getElementById('btn-file-select').addEventListener('click', () => {
            document.getElementById('input-file').click();
        });

        document.getElementById('input-file').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            if (file.size > 10 * 1024 * 1024) {
                showToast('파일 크기가 10MB를 초과합니다.', 4000);
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('nickname', state.nickname);

            try {
                showLoading('파일 분석 중...');
                const result = await apiPostForm('/api/upload', formData);
                hideLoading();
                renderParseResults(result.transactions);
            } catch (err) {
                hideLoading();
                showToast(err.message || '파일 파싱에 실패했습니다. 수동 입력을 이용해주세요.', 4000);
            }
        });

        function renderParseResults(transactions) {
            document.getElementById('manual-form').style.display = 'none';
            document.getElementById('parse-review').style.display = 'block';
            // 파싱 결과 리스트 렌더링 (구현 시 상세 작성)
            const list = document.getElementById('parse-results-list');
            list.innerHTML = transactions.map((t, i) => `
                <div class="paper-card" style="padding: 12px; ${t.needs_review ? 'border-left: 3px solid var(--gold);' : ''}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <p style="font-size: 14px; font-weight: 500;">${t.store}</p>
                            <p style="font-size: 12px; color: #888;">${t.date} · ${t.category}</p>
                        </div>
                        <p style="font-size: 15px; font-weight: 600;">${formatAmount(t.amount)}</p>
                    </div>
                </div>
            `).join('');
        }

    })();
    </script>
</body>
</html>
```

---

## 10. Verdict Generator (core/verdict.py)

### 설계 방침

- judge.py가 결정한 charge/type을 그대로 사용 (변경 금지)
- Bedrock에는 판결문 산문 5개 필드만 생성 요청
- 사건번호는 서버 측에서 결정적으로 생성
- 프롬프트 톤: 재판소 콘셉트 + MBTI식 위트

### 사건번호 생성

```python
import random

def generate_case_number(month: str) -> str:
    """
    사건번호 생성: "{월 2자리}{랜덤 2자리}"
    예: month="2026-08" → "0847"
    """
    month_num = int(month.split("-")[1])
    rand_part = random.randint(1, 99)
    return f"{month_num:02d}{rand_part:02d}"
```

### Bedrock 프롬프트 템플릿

```python
"""판결문 산문 생성 모듈 — core/verdict.py"""

from core.bedrock import invoke_bedrock, BedrockError

# 판결문 생성 프롬프트 템플릿
VERDICT_PROMPT_TEMPLATE = """당신은 "대한민국 소비재판소"의 위트있는 판사입니다.
자취생의 한 달 소비 데이터를 근거로 재미있는 판결문을 작성합니다.

## 피고인 정보
- 닉네임: {nickname}
- 월: {month}

## 판정 결과 (변경 금지 — 아래 죄명과 유형을 그대로 사용)
- 죄명: {charge}
- 소비 유형: {spending_type}

## 소비 통계
- 총 지출: {total_amount:,}원
- 총 결제 횟수: {total_count}회
- 서브타입별 지출: {subtype_summary}
- 카테고리별 지출: {category_summary}

## 증거 (참고용)
{evidence_text}

## 피고인의 메모 (있을 경우 판결문에 인용 가능)
{memos_text}

## 작성 지시

아래 5개 필드를 JSON 객체로 작성하세요. JSON만 출력하고 다른 텍스트는 금지합니다.

1. **article** (조문 부제): "소비보호법 제N조 (부제)" 형식의 가상 조문. 죄명과 관련된 위트있는 부제를 만드세요.
   - 예: "소비보호법 제4조 (냉장고의 존엄)"
   - 예: "소비보호법 제7조 (카페인 중독 예방)"

2. **ruling** (주문): "피고인을 [형벌]에 처한다" 형식의 한 줄 선고문. 유머러스하게.
   - 예: "피고인을 배달앱 7일 금지에 처한다"
   - 예: "피고인을 편의점 출입 제한 5일에 처한다"

3. **reasoning** (이유): 2~3문장의 판결 이유. 실제 통계를 근거로 들며, 재판관의 위트있는 어조로 작성.
   피고인의 메모가 있으면 적절히 인용하여 더 재미있게 만드세요.
   - 반드시 구체적 수치(금액, 횟수, 비율)를 1개 이상 인용할 것

4. **sentence** (형량): 2~3줄의 구체적 행동 제안. 줄바꿈(\\n)으로 구분. 번호 매기기.
   현실적이면서도 재미있는 "처방"으로 작성.
   - 예: "1. 이번 주 3회 이상 자취 요리 실행\\n2. 배달앱 알림 OFF\\n3. 냉장고에 사과문 부착"

5. **type_description** (유형 설명): 2~3문장으로 이 소비 유형의 특징을 설명.
   MBTI 결과지처럼 "당신은 ~한 유형입니다" 스타일로 작성. 위트있되 너무 길지 않게.

## 톤 & 스타일 규칙
- 법원 문서체 + 인터넷 밈/드립 혼합
- 존댓말(합쇼체) 사용하되 판사의 권위적 어조 유지
- 죄명이 "무혐의"인 경우: 칭찬 톤으로 작성 (그래도 약간의 걱정 섞기)
- 죄명이 "증거 불충분"인 경우: 데이터 부족을 아쉬워하는 톤

## 출력 형식 (JSON만, 다른 텍스트 금지)

```json
{{
  "article": "소비보호법 제N조 (부제)",
  "ruling": "피고인을 ...에 처한다",
  "reasoning": "판결 이유 2~3문장",
  "sentence": "1. 행동1\\n2. 행동2\\n3. 행동3",
  "type_description": "유형 설명 2~3문장"
}}
```
"""


def generate_verdict(
    nickname: str,
    month: str,
    charge: str,
    spending_type: str,
    stats: dict,
    evidence: list[dict],
    memos: list[str],
) -> dict:
    """
    Bedrock으로 판결문 산문을 생성한다.

    Args:
        nickname: 피고인 닉네임
        month: 대상 월 (YYYY-MM)
        charge: 죄명 (judge.py에서 확정)
        spending_type: 소비 유형 (judge.py에서 확정)
        stats: judge.py의 _compute_stats 결과
        evidence: build_evidence 결과 리스트
        memos: 해당 월 영수증 메모 리스트 (빈 문자열 제외)

    Returns:
        {
            "article": str,
            "ruling": str,
            "reasoning": str,
            "sentence": str,
            "type_description": str,
        }

    Raises:
        BedrockError: 2회 시도 모두 실패 시
    """
    # 통계 요약 텍스트 구성
    subtype_summary = ", ".join(
        f"{k}: {v:,}원"
        for k, v in stats.get("subtype_amount", {}).items()
        if v > 0
    )
    category_summary = ", ".join(
        f"{k}: {v:,}원"
        for k, v in stats.get("category_amount", {}).items()
        if v > 0
    )

    # 증거 텍스트 구성
    evidence_text = "\n".join(
        f"- {e['label']}: {e['value']}"
        for e in evidence
    )

    # 메모 텍스트 구성
    memos_text = "\n".join(f'- "{m}"' for m in memos if m) if memos else "(메모 없음)"

    # 프롬프트 조립
    prompt = VERDICT_PROMPT_TEMPLATE.format(
        nickname=nickname,
        month=month,
        charge=charge,
        spending_type=spending_type,
        total_amount=stats.get("total_amount", 0),
        total_count=stats.get("total_count", 0),
        subtype_summary=subtype_summary or "(없음)",
        category_summary=category_summary or "(없음)",
        evidence_text=evidence_text,
        memos_text=memos_text,
    )

    # Bedrock 호출 (bedrock.py 래퍼 사용)
    messages = [{"role": "user", "content": prompt}]
    result = invoke_bedrock(
        operation="판결문 생성",
        messages=messages,
        mock_key="verdict",
        max_tokens=2048,
    )

    # 필수 필드 검증
    required_fields = ["article", "ruling", "reasoning", "sentence", "type_description"]
    for field in required_fields:
        if field not in result or not result[field]:
            raise BedrockError(f"판결문 생성 결과에 '{field}' 필드가 누락되었습니다.")

    return {
        "article": result["article"],
        "ruling": result["ruling"],
        "reasoning": result["reasoning"],
        "sentence": result["sentence"],
        "type_description": result["type_description"],
    }
```

### 전체 판결 흐름 (main.py에서의 호출)

```python
# main.py — POST /api/verdict/{nickname} 엔드포인트 내부 로직

import random
from core.judge import evaluate, build_evidence
from core.verdict import generate_verdict

async def create_verdict(nickname: str, month: str, force: bool = False):
    """판정 → 증거 수집 → 판결문 생성 → DB 저장"""

    # 1. 기존 판결문 확인 (force=false일 때)
    if not force:
        existing = db_get_verdict(nickname, month)
        if existing:
            return existing

    # 2. 해당 월 영수증 조회
    receipts = db_get_receipts(nickname, month)

    # 3. 판정 엔진 실행
    judgment = evaluate(receipts)

    # 4. 증거 수집
    evidence = build_evidence(judgment["charge"], receipts, judgment["stats"], month)

    # 5. 메모 수집
    memos = [r.get("memo", "") for r in receipts if r.get("memo")]

    # 6. 판결문 산문 생성 (Bedrock)
    prose = generate_verdict(
        nickname=nickname,
        month=month,
        charge=judgment["charge"],
        spending_type=judgment["type"],
        stats=judgment["stats"],
        evidence=evidence,
        memos=memos,
    )

    # 7. 사건번호 생성
    case_number = generate_case_number(month)

    # 8. DB 저장 (기존 것 있으면 덮어쓰기)
    verdict_record = {
        "nickname": nickname,
        "month": month,
        "case_number": case_number,
        "charge": judgment["charge"],
        "spending_type": judgment["type"],
        "article": prose["article"],
        "evidence_json": json.dumps(evidence, ensure_ascii=False),
        "ruling": prose["ruling"],
        "reasoning": prose["reasoning"],
        "sentence": prose["sentence"],
        "type_description": prose["type_description"],
    }

    db_upsert_verdict(verdict_record)
    return verdict_record
```

---

## 11. Mock Mode Design

### 설계 원칙

- `MOCK_AI=1` 환경변수 하나로 모든 외부 서비스(Bedrock, S3) 호출을 차단
- mock 응답은 전체 UI 흐름을 운동할 수 있을 만큼 현실적인 데이터 포함
- `core/bedrock.py`의 `invoke_bedrock` 함수 진입부에서 분기 → 개별 모듈은 mock 로직 불필요

### Mock 응답 구조 상세

```python
"""Mock 응답 상세 — core/bedrock.py 내 MOCK_RESPONSES

각 키는 invoke_bedrock의 mock_key 파라미터와 매핑된다.
"""

MOCK_RESPONSES = {
    # ─── 파싱 정규화 Mock ─────────────────────────────────
    "parse": [
        {
            "date": "2026-08-01",
            "store": "배달의민족-교촌치킨",
            "amount": 25000,
            "category": "식비",
            "subtype": "배달앱",
            "needs_review": False,
        },
        {
            "date": "2026-08-02",
            "store": "스타벅스 강남역점",
            "amount": 6500,
            "category": "카페·간식",
            "subtype": "카페",
            "needs_review": False,
        },
        {
            "date": "2026-08-03",
            "store": "CU 서초점",
            "amount": 3200,
            "category": "식비",
            "subtype": "편의점",
            "needs_review": False,
        },
        {
            "date": "2026-08-05",
            "store": "이마트 성수점",
            "amount": 67800,
            "category": "식비",
            "subtype": "마트·장보기",
            "needs_review": False,
        },
        {
            "date": "2026-08-07",
            "store": "카카오택시",
            "amount": 12500,
            "category": "교통·이동",
            "subtype": "일반",
            "needs_review": False,
        },
        {
            "date": "2026-08-10",
            "store": "무신사스토어",
            "amount": 89000,
            "category": "쇼핑",
            "subtype": "일반",
            "needs_review": False,
        },
        {
            "date": "2026-08-12",
            "store": "CGV 왕십리",
            "amount": 15000,
            "category": "여가·문화",
            "subtype": "일반",
            "needs_review": False,
        },
        {
            "date": "2026-08-15",
            "store": "PG결제-알수없음",
            "amount": 33000,
            "category": "기타",
            "subtype": "일반",
            "needs_review": True,
        },
    ],

    # ─── 판결문 생성 Mock ─────────────────────────────────
    "verdict": {
        "article": "소비보호법 제4조 (냉장고의 존엄)",
        "ruling": "피고인을 배달앱 7일 금지에 처한다",
        "reasoning": (
            "피고인은 한 달간 냉장고를 장식품으로 전락시킨 혐의가 명백하다. "
            "배달앱 결제 내역이 총 지출의 41.6%를 차지하며, "
            "냉장고 안에는 유통기한 지난 소스만 잔뜩 발견되었다."
        ),
        "sentence": (
            "1. 이번 주 3회 이상 자취 요리 실행\n"
            "2. 배달앱 알림 OFF\n"
            "3. 냉장고에 사과문 부착"
        ),
        "type_description": (
            "냉장고는 전기세만 먹는 가전이 된 지 오래. "
            "당신의 주방은 배달 포장지 수거함이며, 요리 도구는 포장 뜯는 가위뿐이다. "
            "하지만 걱정 마라, 냉장고도 언젠간 당신을 용서할 것이다."
        ),
    },
}
```

### Mock 모드 통합 흐름

```
┌─────────────────────────────────────────────────────────┐
│  환경변수 MOCK_AI=1 설정                                 │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  core/bedrock.py — invoke_bedrock() 진입                 │
│                                                          │
│  if MOCK_AI:                                             │
│      return MOCK_RESPONSES[mock_key]  ← 즉시 반환       │
│                                                          │
│  # 이하 실제 Bedrock 호출 (Mock일 때 도달하지 않음)      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  core/parse.py — parse_file() 진입                       │
│                                                          │
│  if MOCK_AI:                                             │
│      return _mock_response()  ← S3 업로드도 건너뜀       │
│      # s3_key = "mock/placeholder.pdf"                   │
└─────────────────────────────────────────────────────────┘
```

### S3 Mock 처리

```python
# core/parse.py 내 S3 업로드 Mock 분기
def _upload_to_s3(file_bytes: bytes, filename: str) -> str:
    """원본 파일을 S3에 업로드 (Mock 모드에서는 건너뜀)"""
    if MOCK_AI:
        return "mock/placeholder.pdf"

    # 실제 S3 업로드 로직
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    s3_key = f"evidence/{timestamp}-{filename}"
    s3 = boto3.client("s3")
    s3.put_object(Bucket=BUCKET_NAME, Key=s3_key, Body=file_bytes)
    return s3_key
```

### 로컬 개발 실행 명령

```bash
# 로컬 개발 시 (AWS 자격증명 불필요)
MOCK_AI=1 python -m uvicorn main:app --host 0.0.0.0 --port 8501 --reload
```

---

## 12. Deployment & Error Handling

### 배포 명령 시퀀스

```bash
# 1. 기존 프로세스 종료 (포트 8501 점유 중인 프로세스)
lsof -ti:8501 | xargs kill -SIGTERM 2>/dev/null || true

# 2. 포트 해제 대기 (최대 10초)
for i in $(seq 1 10); do
    if ! lsof -ti:8501 > /dev/null 2>&1; then
        echo "포트 8501 해제 완료"
        break
    fi
    sleep 1
done

# 3. FastAPI 앱 백그라운드 실행 (nohup + stdin 분리)
nohup appenv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8501 < /dev/null > app.log 2>&1 &

# 4. 시작 대기 (최대 30초)
for i in $(seq 1 30); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        echo "서비스 시작 성공 (HTTP 200)"
        break
    fi
    if [ "$i" = "30" ]; then
        echo "ERROR: 30초 내 시작 실패. app.log 확인 필요"
        tail -20 app.log
        exit 1
    fi
    sleep 1
done

# 5. 외부 접근 검증
EXTERNAL_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://18.135.105.80:8501)
if [ "$EXTERNAL_CODE" = "200" ]; then
    echo "외부 접근 확인 완료: http://18.135.105.80:8501"
else
    echo "WARNING: 외부 접근 실패 (HTTP $EXTERNAL_CODE). 방화벽 확인 필요"
fi
```

## Error Handling

#### API 서버 측 (main.py)

```python
"""에러 처리 패턴 — main.py"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from core.bedrock import BedrockError

app = FastAPI()


@app.exception_handler(BedrockError)
async def bedrock_error_handler(request, exc: BedrockError):
    """Bedrock 호출 실패 시 사용자 친화적 에러 응답"""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "retryable": True},
    )


@app.exception_handler(ValueError)
async def validation_error_handler(request, exc: ValueError):
    """입력값 검증 실패"""
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc)},
    )


# 파일 업로드 에러 처리 패턴
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), nickname: str = Form(...)):
    """파일 업로드 → 파싱 → 정규화된 트랜잭션 반환"""
    # 파일 크기 검증 (10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기가 10MB를 초과합니다.")

    # 확장자 검증
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("pdf", "xlsx", "xls", "csv"):
        raise HTTPException(status_code=422, detail=f"지원하지 않는 파일 형식입니다: .{ext}")

    try:
        from core.parse import parse_file
        result = parse_file(contents, file.filename, nickname)
        return result
    except BedrockError as e:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "파일 파싱에 실패했습니다. 수동 입력을 이용해주세요.",
                "fallback": True,
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "파일 파싱에 실패했습니다. 수동 입력을 이용해주세요.",
                "fallback": True,
            },
        )
```

#### SPA 측 에러 처리 (index.html JS)

```javascript
/* ─── API 에러 처리 패턴 ─────────────────────────────── */

/**
 * API 호출 래퍼 — 통합 에러 처리 + 로딩 + 타임아웃
 *
 * @param {string} url - API 엔드포인트
 * @param {object} options - fetch 옵션
 * @param {string} loadingText - 로딩 중 표시할 텍스트
 * @param {string} errorText - 에러 시 토스트 메시지 (null이면 서버 메시지 사용)
 * @returns {Promise<object>} 응답 JSON
 */
async function apiCallWithUI(url, options, loadingText, errorText) {
    showLoading(loadingText);

    try {
        const result = await apiCall(url, options);
        hideLoading();
        return result;
    } catch (error) {
        hideLoading();

        // 에러 토스트 표시 (빈 화면 방지)
        const message = errorText || error.message || '요청에 실패했습니다. 다시 시도해주세요.';
        showToast(message, 4000);

        throw error;  // 호출부에서 추가 처리 가능
    }
}

/* ─── 판결문 생성 호출 예시 ───────────────────────────── */
async function requestVerdict(force = false) {
    const month = getCurrentMonth();
    const url = `/api/verdict/${encodeURIComponent(state.nickname)}?month=${month}&force=${force}`;

    try {
        const verdict = await apiCallWithUI(
            url,
            { method: 'POST' },
            '판결문을 작성 중입니다…',
            null  // 서버 에러 메시지 사용
        );

        state.currentVerdict = verdict;
        renderVerdict(verdict);
        navigateTo('verdict');
    } catch (error) {
        // 에러 토스트는 apiCallWithUI에서 이미 표시됨
        // 현재 화면 유지 (빈 화면 방지)
    }
}
```

### 재시도 패턴 요약

```
┌─────────────────────────────────────────────────────────────┐
│                      재시도 플로우                           │
│                                                             │
│  1차 시도 ──→ 성공? ──→ 결과 반환                           │
│     │                                                       │
│     ▼ 실패                                                  │
│  2차 시도 ──→ 성공? ──→ 결과 반환                           │
│     │                                                       │
│     ▼ 실패                                                  │
│  에러 응답:                                                  │
│  - HTTP 500 + detail 메시지                                 │
│  - SPA에서 토스트 4초 표시                                   │
│  - 현재 화면 유지 (빈 화면 금지)                             │
│  - "다시 시도해주세요" 안내                                   │
└─────────────────────────────────────────────────────────────┘
```

### 로딩 상태 타이밍

| 이벤트 | 동작 |
|--------|------|
| API 호출 시작 | 300ms 이내 로딩 오버레이 표시 |
| 응답 수신 (성공) | 로딩 즉시 해제 + 결과 렌더링 |
| 응답 수신 (에러) | 로딩 해제 + 토스트 4초 |
| 10초 타임아웃 (일반 API: GET /api/receipts, GET /api/summary 등) | 로딩 해제 + 타임아웃 토스트 |
| 30초 타임아웃 (판결문 생성: POST /api/verdict) | 로딩 해제 + 타임아웃 토스트 |
| 30초 타임아웃 (파일 업로드: POST /api/upload) | fetch abort + 에러 토스트 |


---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Judgment Determinism

*For any* set of receipt records (same nickname, same month), invoking `evaluate(receipts)` multiple times SHALL always return the identical `{charge, type}` result — no randomness in rule evaluation.

**Validates: Requirements 7.1**

### Property 2: Guard Rule Precedence

*For any* list of receipts with fewer than 5 elements, `evaluate(receipts)` SHALL return `charge="증거 불충분"` and `type="균형 잡힌 생존형"`, regardless of the amounts, categories, or subtypes present.

**Validates: Requirements 7.2, 7.3**

### Property 3: Rule Priority Order

*For any* receipt set that satisfies the conditions of two or more rules simultaneously, `evaluate(receipts)` SHALL return the result of the rule with the lowest index (first-match wins).

**Validates: Requirements 7.4–7.11**

### Property 4: Receipt Storage Round-Trip

*For any* valid receipt data (store 1–50 chars, date YYYY-MM-DD not future, amount 1–999999999, category in 6 defined, subtype in 5 defined), storing via POST /api/receipts then retrieving via GET /api/receipts/{nickname}?month=YYYY-MM SHALL return a record with all fields equivalent to the original input.

**Validates: Requirements 14.2, 14.3, 15.1**

### Property 5: User Creation Idempotence

*For any* nickname string (1–12 characters), calling POST /api/users/{nickname} two or more times SHALL return the same user record (same nickname, same age, same created_at) without creating duplicate entries.

**Validates: Requirements 14.1, 1.2**

### Property 6: Verdict Idempotence (no force)

*For any* nickname+month combination where a verdict already exists, calling POST /api/verdict/{nickname}?month=YYYY-MM&force=false SHALL return the stored verdict without regeneration — the response SHALL be byte-for-byte identical across calls.

**Validates: Requirements 8.3**

### Property 7: Category Filter Subset

*For any* month and category value, the receipt set returned by GET /api/receipts/{nickname}?month=M filtered by that category SHALL be a strict subset of the unfiltered receipt set for the same month and nickname.

**Validates: Requirements 5.2, 14.3**

### Property 8: Transaction Validation Rejects Invalid Data

*For any* receipt object where category is not in the 6 defined values, OR subtype is not in the 5 defined values, OR amount ≤ 0, OR date does not match YYYY-MM-DD format, `_validate_transactions()` SHALL raise an exception.

**Validates: Requirements 3.1, 15.1**

### Property 9: Top Category Tie-Breaking Determinism

*For any* monthly receipt set where two or more categories share the highest expenditure amount, `GET /api/summary/{nickname}?month=M` SHALL select as top_category the one with the higher payment count; if counts are also equal, the one appearing first in the fixed category order.

**Validates: Requirements 6.7**

### Property 10: Stamp Type Correctness

*For any* verdict with charge value, the SPA SHALL display "무죄 ACQUITTED" stamp if and only if charge is "무혐의" or "증거 불충분"; otherwise "유죄 CONVICTED" stamp. This is a pure function of the charge string.

**Validates: Requirements 9.2**

---

## Testing Strategy

### PBT 라이브러리 선정

- **Python**: [Hypothesis](https://hypothesis.readthedocs.io/) — FastAPI 백엔드 테스트
- **JavaScript**: 프런트엔드 로직이 단일 HTML 파일 내 인라인이므로 PBT 적용 생략. 프런트엔드는 수동 E2E + 예시 기반 테스트로 대체.

### Unit Tests (예시 기반)

| 대상 | 테스트 내용 |
|------|------------|
| core/judge.py | 각 룰별 경계값 테스트 (정확히 35% 배달 → 유죄, 34.9% → 무죄) |
| core/judge.py | build_evidence 각 죄명별 증거 4건 정확한 계산 검증 |
| core/parse.py | _validate_transactions 유효/무효 케이스 |
| core/verdict.py | generate_case_number 형식 검증 (4자리, 앞 2자리=월) |
| db.py | init_db 테이블 생성 + 기존 데이터 보존 |
| main.py | 각 API 엔드포인트 정상/에러 응답 코드 확인 |

### Property Tests (Hypothesis)

각 테스트는 최소 100회 반복 실행.

```python
# tests/test_judge_properties.py — 예시 구조

from hypothesis import given, settings, assume
from hypothesis.strategies import (
    lists, fixed_dictionaries, sampled_from, integers, text, dates
)
from core.judge import evaluate, CATEGORIES, SUBTYPES

# 유효한 영수증 생성 전략
receipt_strategy = fixed_dictionaries({
    "store": text(min_size=1, max_size=50),
    "date": dates().map(lambda d: d.strftime("%Y-%m-%d")),
    "amount": integers(min_value=1, max_value=999_999_999),
    "category": sampled_from(CATEGORIES),
    "subtype": sampled_from(SUBTYPES),
})


# Feature: receipt-tribunal, Property 1: Judgment Determinism
@given(receipts=lists(receipt_strategy, min_size=0, max_size=30))
@settings(max_examples=200)
def test_judgment_determinism(receipts):
    """동일 입력에 항상 동일 결과를 반환한다"""
    result1 = evaluate(receipts)
    result2 = evaluate(receipts)
    assert result1["charge"] == result2["charge"]
    assert result1["type"] == result2["type"]


# Feature: receipt-tribunal, Property 2: Guard Rule Precedence
@given(receipts=lists(receipt_strategy, min_size=0, max_size=4))
@settings(max_examples=200)
def test_guard_rule_under_5(receipts):
    """5건 미만이면 항상 증거 불충분"""
    result = evaluate(receipts)
    assert result["charge"] == "증거 불충분"
    assert result["type"] == "균형 잡힌 생존형"


# Feature: receipt-tribunal, Property 3: Rule Priority Order
@given(receipts=lists(receipt_strategy, min_size=5, max_size=30))
@settings(max_examples=200)
def test_priority_order(receipts):
    """다중 룰 매칭 시 우선순위 낮은 룰이 선택된다"""
    result = evaluate(receipts)
    # 결과가 반환되면 해당 룰 조건 이전의 모든 상위 룰은 불일치해야 함
    assert "charge" in result
    assert "type" in result
```

### Integration Tests

| 시나리오 | 방법 |
|---------|------|
| 파일 업로드 → 파싱 → 저장 → 판결문 | 서버 배포 후 samples/ 파일로 E2E 검증 |
| Mock 모드 전체 흐름 | MOCK_AI=1로 로컬 기동 후 curl 시나리오 |
| 시드 데이터 8종 죄명 재현 | seed.py 실행 후 8개 닉네임 각각 verdict 호출 |

### 테스트 실행 명령

```bash
# 로컬 단위 테스트 (Mock 모드)
MOCK_AI=1 appenv/bin/python -m pytest tests/ -v

# Property 테스트만 실행
MOCK_AI=1 appenv/bin/python -m pytest tests/test_judge_properties.py -v

# 서버 통합 테스트 (배포 후)
curl -X POST http://18.135.105.80:8501/api/users/테스트유저
curl -X POST http://18.135.105.80:8501/api/receipts -H "Content-Type: application/json" -d '...'
curl http://18.135.105.80:8501/api/summary/테스트유저?month=2026-08
```
