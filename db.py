"""SQLite 데이터베이스 초기화 및 커넥션 관리 모듈"""

import sqlite3
from pathlib import Path

# DB 파일 경로 — db.py와 같은 디렉토리에 data.db 생성
DB_PATH = Path(__file__).parent / "data.db"

# 스키마 SQL — CREATE TABLE IF NOT EXISTS로 기존 데이터 보존
_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 사용자 테이블
CREATE TABLE IF NOT EXISTS users (
    nickname   TEXT PRIMARY KEY,
    age        INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 영수증 테이블
CREATE TABLE IF NOT EXISTS receipts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname     TEXT    NOT NULL REFERENCES users(nickname),
    store        TEXT    NOT NULL,
    date         TEXT    NOT NULL,
    amount       INTEGER NOT NULL,
    category     TEXT    NOT NULL CHECK (category IN (
                     '식비','카페·간식','쇼핑','교통·이동','여가·문화','기타'
                 )),
    subtype      TEXT    NOT NULL DEFAULT '일반' CHECK (subtype IN (
                     '배달앱','편의점','마트·장보기','카페','일반'
                 )),
    memo         TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0,
    s3_key       TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 판결문 테이블
CREATE TABLE IF NOT EXISTS verdicts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname         TEXT    NOT NULL REFERENCES users(nickname),
    month            TEXT    NOT NULL,
    case_number      TEXT    NOT NULL,
    charge           TEXT    NOT NULL,
    spending_type    TEXT    NOT NULL,
    article          TEXT    NOT NULL,
    evidence_json    TEXT    NOT NULL,
    ruling           TEXT    NOT NULL,
    reasoning        TEXT    NOT NULL,
    sentence         TEXT    NOT NULL,
    type_description TEXT    NOT NULL,
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
"""


def get_connection() -> sqlite3.Connection:
    """SQLite 커넥션을 반환한다 (WAL 모드, FK 활성화, Row factory 설정)"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """앱 시작 시 테이블·인덱스를 생성한다 (IF NOT EXISTS — 기존 데이터 보존)"""
    conn = get_connection()
    conn.executescript(_SCHEMA_SQL)
    conn.close()
