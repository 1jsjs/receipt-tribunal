---
inclusion: always
---

# 폴더 구조 · 작업 규칙

```
main.py              # FastAPI 엔드포인트 (한국어 주석)
static/index.html    # SPA 전체 (단일 파일)
core/parse.py        # 파일(PDF/xlsx/csv) → 원시 추출 → Bedrock LLM 정규화·분류 (주 파이프라인)
core/vision.py       # 스캔형 PDF 폴백 전용 (기존 analyze_receipt_image 패턴 재사용)
core/analyze.py      # 월간 집계
core/judge.py        # 판정 룰 (결정적 조건문)
core/verdict.py      # Bedrock 판결문 생성
db.py                # SQLite
data/seed.py         # 더미 시드 (8월, 닉네임 8개 — 각 죄명 임계값 충족 분포, 총 60건 내외)
samples/             # 데모용 합성 지출내역 엑셀·PDF 2종(제작 task) + 영수증 이미지 3종(폴백 테스트용)
tests/
```

작업 규칙:
- task 한 번에 하나, 완료마다 커밋 (메시지에 task 번호)
- .kiro/ 폴더는 항상 커밋에 포함
- 항상 실행 가능한 상태 유지, 스코프 확장 제안 금지
- 로컬 실행 확인은 MOCK_AI=1 (로컬엔 AWS 자격증명 없음 — Access Key 발급 시도 금지)
