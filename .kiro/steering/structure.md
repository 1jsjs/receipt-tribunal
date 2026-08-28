---
inclusion: always
---

# 파일 구조 — 새 코드를 어디에 넣을지

## 현재 구조
```
main.py                      FastAPI 엔트리. 라우터 등록 후 static 마운트(반드시 마지막)
db.py                        SQLite 연결·초기화. expenses 테이블 하나뿐
constants.py                 카테고리 6종·거래유형 2종 (단일 출처)
routes/
  expenses.py                CRUD 5종 (POST/GET월별/GET단건/PUT/DELETE) + 입력 검증
  analysis.py                GET /api/analysis — 통계+유형+판결문+MZ 통합 응답
  imports.py                 POST /api/import — 파일 업로드 파싱·저장
services/
  analysis_service.py        월간 통계 계산 (EXPENSE만, TRANSFER 제외)
  judgment_service.py        소비 유형 판정 룰 + 판결문 템플릿 조립
  verdict_service.py         판결 "이유" Bedrock 생성 (+폴백)
  parse_service.py           파일 원시추출 → Bedrock 정규화 (+규칙 폴백)
  reaction_data.py           MZ 리액션 7유형 × 12개
data/
  seed.py                    데모 시드 77건 (2026-02~08, 월마다 다른 유형)
  database.sqlite            로컬 DB (git 무시)
static/                      프론트 (index.html·style.css·app.js) — 여기가 남은 작업
samples/                     데모용 지출내역 파일 (xlsx·pdf)
docs/                        설계 원본 00~06, 99 — 코드보다 이게 기준이다
```

## 배치 규칙
- 새 API는 routes/ 아래 파일 하나 = 도메인 하나. main.py에 라우터 등록.
- 비즈니스 로직은 services/ 에. routes/는 검증·응답 조립만 얇게.
- 상수는 constants.py. 카테고리 코드를 여기저기 문자열로 박지 말 것.
- **static 마운트는 main.py 맨 마지막**이어야 한다. 위로 올리면 /api 전체가 404가 된다.

## 미사용 파일 (v1 잔재 — 건드리지도, 참고하지도 말 것)
app.py / receipt_app.py / bedrock_faiss_indexer.py / bedrock_faiss_rag_chatbot.py /
bedrock_simple_test.py / TEAM_GUIDE.html
v1(Streamlit·스타터)에서 남은 것들이다. 현재 서비스와 무관하며 수정 대상이 아니다.

## 브랜치
- `allnew` = 통합·배포 기준. 여기서 갈라져 나가고 여기로 합친다.
- 작업 브랜치는 feat/* 로 만들고, 태스크 하나 끝날 때마다 커밋한다.
