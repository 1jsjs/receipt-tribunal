"""SQLite 연결·초기화 (스켈레톤) — 스키마는 docs/05 §6 그대로"""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "database.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_name TEXT NOT NULL,
  date TEXT NOT NULL,
  amount INTEGER NOT NULL,
  category TEXT NOT NULL,
  transaction_type TEXT NOT NULL,
  memo TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _migrate(conn) -> None:
    """구버전 DB 호환: 누락 컬럼을 ALTER TABLE로 채운다 (기존 데이터 보존)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(expenses)")}
    if "memo" not in cols:
        conn.execute("ALTER TABLE expenses ADD COLUMN memo TEXT NOT NULL DEFAULT ''")


def get_connection() -> sqlite3.Connection:
    """커넥션 반환 — Row factory 적용 (컬럼명으로 접근 가능)"""
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """테이블 생성 (CREATE IF NOT EXISTS — 기존 데이터 보존)"""
    conn = get_connection()
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()
