"""공공데이터(소상공인 상가정보) 기반 상호명 → 카테고리 조회.

LLM/키워드가 OTHER로 남긴 소비 내역을 보정하는 마지막 단계.
색인은 data/build_store_index.py로 미리 만들어 data/store_category.sqlite에 저장한다
(색인 파일이 없으면 이 모듈은 항상 None을 돌려주고 조용히 비활성화된다).

속도: 색인은 전부 인메모리 dict 2개로 로드(최초 1회, 보통 <0.3s). 조회는 dict 해시 O(1).
"""
import re
import sqlite3
import threading
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "store_category.sqlite"

# 가맹점명 뒤에 붙는 결제망(PG) 표기 — 이것만 잘라낸다 (그 뒤 '_택시' 같은 서비스명은 보존)
_PAY_TAIL = re.compile(
    r"[_/\s]?(toss|kcp|kicc|nice|나이스|이니시스|kg이니시스|스마트로|smartro|페이코|payco|"
    r"다우데이타|모빌리언스|kg모빌리언스|allat|ksnet|jtnet|헥토파이낸셜|세틀뱅크)\d*$",
    re.I,
)
_PAREN = re.compile(r"[(（【\[].*?[)）】\]]")
_CORP = re.compile(r"주식회사|유한회사|㈜|\(주\)|\(유\)")
_NONWORD = re.compile(r"[^0-9a-z가-힣]")
_BRANCH_SUFFIX = re.compile(r"(본점|직영점|[0-9a-z가-힣]{2,10}점)$")

_PREFIX_MIN = 4
_PREFIX_MAX = 8

_lock = threading.Lock()
_exact: dict[str, str] | None = None      # 정규화 상호명 → 카테고리
_prefix: dict[str, str] | None = None     # 정규화 상호명 접두사(3~8자) → 카테고리
_loaded = False


def normalize_store_name(name: str) -> str:
    """상호명 정규화 — 소문자, 결제망 접미사·괄호·법인표기·기호·공백 제거."""
    s = (name or "").lower().strip()
    s = _PAY_TAIL.sub("", s)
    s = _PAREN.sub("", s)
    s = _CORP.sub("", s)
    s = _NONWORD.sub("", s)
    return s


def _strip_branch(norm: str) -> str:
    """정규화된 이름에서 끝의 지점 표기('...점', '본점' 등) 1회 제거."""
    return _BRANCH_SUFFIX.sub("", norm)


def _load() -> None:
    global _exact, _prefix, _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        if not _DB_PATH.is_file():
            _exact, _prefix = {}, {}
            return
        conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        try:
            _exact = {n: c for n, c in conn.execute("SELECT name, category FROM store_exact")}
            _prefix = {p: c for p, c in conn.execute("SELECT prefix, category FROM store_prefix")}
        finally:
            conn.close()


def classify_by_public_data(store_name: str) -> str | None:
    """상호명을 공공데이터 색인에서 찾아 카테고리 코드를 돌려준다. 못 찾으면 None."""
    if _exact is None:
        _load()
    assert _exact is not None and _prefix is not None

    norm = normalize_store_name(store_name)
    if len(norm) < 2:
        return None

    hit = _exact.get(norm)
    if hit:
        return hit

    stripped = _strip_branch(norm)
    if stripped != norm and len(stripped) >= 2:
        hit = _exact.get(stripped)
        if hit:
            return hit

    # 접두사(브랜드) 매칭 — 긴 접두사부터
    for k in range(min(_PREFIX_MAX, len(norm)), _PREFIX_MIN - 1, -1):
        hit = _prefix.get(norm[:k])
        if hit:
            return hit
    return None
