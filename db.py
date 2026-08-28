"""SQLite 연결·초기화 — 스키마는 docs/05 §6 + 피고인·미분류 확장"""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "database.sqlite"

# 피고인 이름을 안 보냈을 때 쓰는 기본값.
# 이 값 덕분에 defendant를 모르는 기존 호출도 그대로 동작한다(시드 데이터도 이 이름).
DEFAULT_DEFENDANT = "익명의 자취생"

MEMO_MAX = 10       # 미분류 내역에 붙이는 메모 길이 제한
DEFENDANT_MAX = 10  # 피고인 이름 길이 제한 (사용자가 직접 입력)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_name TEXT NOT NULL,
  date TEXT NOT NULL,
  amount INTEGER NOT NULL,
  category TEXT NOT NULL,
  transaction_type TEXT NOT NULL,
  defendant TEXT NOT NULL DEFAULT '',
  memo TEXT NOT NULL DEFAULT '',
  needs_review INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""

# 이미 만들어진 DB(배포 서버 포함)에 나중에 추가된 컬럼을 채워 넣기 위한 목록.
# SQLite는 ADD COLUMN만 지원하므로 기존 데이터는 보존된다.
_ADDED_COLUMNS = [
    ("defendant", f"TEXT NOT NULL DEFAULT '{DEFAULT_DEFENDANT}'"),
    ("memo", "TEXT NOT NULL DEFAULT ''"),
    ("needs_review", "INTEGER NOT NULL DEFAULT 0"),
]


def get_connection() -> sqlite3.Connection:
    """커넥션 반환 — Row factory 적용 (컬럼명으로 접근 가능)"""
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """없는 컬럼만 추가한다 (이미 운영 중인 DB를 안 지우고 확장하기 위함)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(expenses)")}
    for name, ddl in _ADDED_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE expenses ADD COLUMN {name} {ddl}")
            print(f"[db] 컬럼 추가: {name}")

    # 기존 행의 빈 피고인은 기본 피고인으로 채운다 (조회 필터에서 누락되지 않게)
    conn.execute(
        "UPDATE expenses SET defendant = ? WHERE defendant IS NULL OR defendant = ''",
        (DEFAULT_DEFENDANT,),
    )


def init_db():
    """테이블 생성 + 컬럼 마이그레이션 (기존 데이터 보존)"""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
