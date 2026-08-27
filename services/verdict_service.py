"""판결문 '이유(reasoning)' Bedrock 생성 — TASK-B012 (docs/05 §14)

- 모델: global.anthropic.claude-sonnet-5 (global. 접두사 필수)
- region_name 하드코딩 금지 (서버 환경변수 사용)
- MOCK_AI=1이면 고정 문장 반환 (로컬 개발용)
- 호출 실패 시 fallbackReasonings 템플릿 사용 (빈 응답 금지)
"""
# TODO(feat/analysis)
