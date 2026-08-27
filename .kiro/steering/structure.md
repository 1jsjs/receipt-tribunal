---
inclusion: always
---

# 폴더 구조 · 작업 규칙

```
main.py              # FastAPI 엔드포인트 (한국어 주석)
static/index.html    # SPA 전체 (단일 파일)
core/vision.py       # 기존 receipt_app.py의 analyze_receipt_image 패턴 재사용 + subtype 분류
core/analyze.py      # 월간 집계
core/judge.py        # 판정 룰 (결정적 조건문)
core/verdict.py      # Bedrock 판결문 생성
db.py                # SQLite
data/seed.py         # 더미 시드 (8월, 닉네임 8개 — 각 죄명 임계값 충족 분포, 총 60건 내외)
samples/             # 합성 영수증 3종 (기존)
tests/
```

작업 규칙:
- task 한 번에 하나, 완료마다 커밋 (메시지에 task 번호)
- .kiro/ 폴더는 항상 커밋에 포함
- 항상 실행 가능한 상태 유지, 스코프 확장 제안 금지
- 로컬 실행 확인은 MOCK_AI=1 (로컬엔 AWS 자격증명 없음 — Access Key 발급 시도 금지)
