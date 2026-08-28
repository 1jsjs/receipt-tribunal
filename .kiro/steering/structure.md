---
inclusion: always
---

# 파일 구조 — 새 코드를 어디에 넣을지

```
main.py                    FastAPI 엔트리. 라우터 등록 후 static 마운트(반드시 맨 마지막)
db.py                      SQLite 연결·초기화·컬럼 마이그레이션. 길이 상수(MEMO_MAX 등)
constants.py               카테고리 6종·거래유형 2종 (단일 출처)

routes/
  expenses.py              CRUD 5종 + 입력 검증 + POST /skip-review
  analysis.py              GET /api/analysis — 통계+유형+판결문+MZ+benchmark+remark 통합
  imports.py               POST /api/import — 파일 업로드 파싱·저장

services/
  analysis_service.py      월간 통계 (EXPENSE만, TRANSFER 제외) + 피고인/미분류 집계
  judgment_service.py      소비 유형 판정 룰 7종 + 판결문 템플릿
  verdict_service.py       판결 이유·형량 Bedrock 생성 (+폴백). plea 정상참작
  parse_service.py         파일 원시추출 → Bedrock 정규화 (+규칙 폴백) + 미분류 판정
  category_rules.py        상호명 키워드 → 카테고리. OTHER면 공공데이터로 재보정
  store_lookup.py          공공데이터 색인 조회 (색인 없으면 조용히 비활성)
  benchmark_service.py     1인가구 평균 대비 비교
  remark_service.py        행방불명(기타) 비중 논평
  reaction_data.py         MZ 리액션 7유형 × 12개

data/
  seed.py                  데모 시드 77건 (2026-02~08, 월마다 다른 유형)
  benchmark_data.py        공공데이터 기준값·출처 (숫자 바꿀 때 SOURCE도 같이)
  industry_category_map.py 상권정보 업종분류 → 우리 6종 매핑 규칙
  build_store_index.py     상권정보 ZIP → store_category.sqlite 색인 생성 (2~4분)
  database.sqlite          로컬 DB (git 무시)
  store_category.sqlite    공공데이터 색인 129MB (git 무시 — 서버엔 scp로 올림)

static/                    프론트 — 지금은 index.html 스텁뿐. style.css·app.js는 새로 만든다
samples/                   데모용 합성 파일 (카드내역 xlsx · 계좌내역 pdf)
tests/                     pytest. 실행: python3 -m pytest tests/ -q
docs/                      설계 원본 00~06·99 — 코드보다 이게 기준이다
```

## 배치 규칙
- 새 API는 routes/ 아래 파일 하나 = 도메인 하나. main.py에 라우터 등록.
- 비즈니스 로직은 services/. routes/는 검증·응답 조립만 얇게.
- 상수는 constants.py. 카테고리 코드를 여기저기 문자열로 박지 말 것.
- **static 마운트는 main.py 맨 마지막.** 위로 올리면 /api 전체가 404가 된다.
- `*.sqlite`는 커밋하지 않는다. 색인은 서버에 직접 올린다.

## 브랜치
- `allnew` = 통합·배포 기준(기본 브랜치). 여기서 갈라져 나가고 여기로 합친다.
- 원격에 `master`(백지 기준점)·`spec-v1-backup`(v1 보존)도 있으나 작업 대상이 아니다.
- 작업 브랜치는 feat/*, 태스크 하나 끝날 때마다 커밋.
- PR 검토 시: ①브랜치 기반이 최신 allnew인지 ②Bedrock 호출부가 §1·§2 반영했는지
  ③GitHub가 MERGEABLE이라 해도 **의미 충돌**은 못 잡는다(import 삭제 등) — 로컬 머지 후
  pytest와 실서버 배포까지 확인할 것.
