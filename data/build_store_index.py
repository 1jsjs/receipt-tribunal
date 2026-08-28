"""공공데이터(소상공인 상가정보) ZIP → data/store_category.sqlite 색인 생성.

입력: 공공데이터포털 '소상공인시장진흥공단_상가(상권)정보' ZIP (시도별 CSV 17개).
출력: data/store_category.sqlite
  - store_exact(name, category, n)   : 정규화 상호명 → 최빈 카테고리 (n = 근거 점포 수)
  - store_prefix(prefix, category, n, total) : 정규화 상호명 접두사(3~8자) → 지배적 카테고리

실행:
    python3 data/build_store_index.py "~/Downloads/소상공인..._20260630.zip"

색인은 커밋하지 않는다 (.gitignore의 *.sqlite). 데모/배포 시 1회 생성.
소요: 약 2~4분 (전국 ~250만 행).
"""
import csv
import io
import sqlite3
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.industry_category_map import map_industry
from services.store_lookup import normalize_store_name

_OUT = Path(__file__).resolve().parent / "store_category.sqlite"

_PREFIX_MIN, _PREFIX_MAX = 4, 8
_EXACT_MIN_N = 1          # 상호명 1곳만 있어도 채택 (지역 소상공인 특성)
_PREFIX_MIN_TOTAL = 8     # 접두사는 최소 8개 점포가 근거일 때만 (오분류 방지)
_PREFIX_DOMINANCE = 0.85  # 그 중 한 카테고리가 85% 이상일 때만 접두사 채택

csv.field_size_limit(1 << 24)


def _iter_rows(zip_path: Path):
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        for i, name in enumerate(names, 1):
            print(f"  [{i}/{len(names)}] {name}")
            with zf.open(name) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))
                for row in reader:
                    yield row


def build(zip_path: Path) -> None:
    exact_counts: dict[str, Counter] = defaultdict(Counter)
    prefix_counts: dict[str, Counter] = defaultdict(Counter)

    n_rows = 0
    for row in _iter_rows(zip_path):
        n_rows += 1
        cat = map_industry(
            row.get("상권업종대분류명", ""),
            row.get("상권업종중분류명", ""),
            row.get("상권업종소분류명", ""),
        )
        norm = normalize_store_name(row.get("상호명", ""))
        if len(norm) < 2:
            continue
        exact_counts[norm][cat] += 1
        for k in range(_PREFIX_MIN, min(_PREFIX_MAX, len(norm)) + 1):
            prefix_counts[norm[:k]][cat] += 1

    print(f"행 {n_rows:,} / 상호명 {len(exact_counts):,} / 접두사 {len(prefix_counts):,}")

    _OUT.unlink(missing_ok=True)
    conn = sqlite3.connect(_OUT)
    conn.executescript(
        """
        CREATE TABLE store_exact  (name   TEXT PRIMARY KEY, category TEXT NOT NULL, n INTEGER NOT NULL);
        CREATE TABLE store_prefix (prefix TEXT PRIMARY KEY, category TEXT NOT NULL, n INTEGER NOT NULL, total INTEGER NOT NULL);
        """
    )

    exact_rows = []
    for norm, counter in exact_counts.items():
        cat, n = counter.most_common(1)[0]
        if n >= _EXACT_MIN_N:
            exact_rows.append((norm, cat, n))
    conn.executemany("INSERT INTO store_exact VALUES (?,?,?)", exact_rows)

    prefix_rows = []
    for pfx, counter in prefix_counts.items():
        total = sum(counter.values())
        cat, n = counter.most_common(1)[0]
        if total >= _PREFIX_MIN_TOTAL and n / total >= _PREFIX_DOMINANCE:
            prefix_rows.append((pfx, cat, n, total))
    conn.executemany("INSERT INTO store_prefix VALUES (?,?,?,?)", prefix_rows)

    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    size_mb = _OUT.stat().st_size / 1e6
    print(f"완료 → {_OUT}  (exact {len(exact_rows):,} / prefix {len(prefix_rows):,} / {size_mb:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python3 data/build_store_index.py <공공데이터 ZIP 경로>")
    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        sys.exit(f"파일 없음: {path}")
    build(path)
