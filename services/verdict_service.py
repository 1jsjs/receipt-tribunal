"""판결문 '이유(reasoning)' Bedrock 생성 — TASK-B012 (docs/05 §14)

- 모델: global.anthropic.claude-sonnet-5 (global. 접두사 필수)
- region_name 하드코딩 금지 (서버 환경변수 사용)
- MOCK_AI=1이면 고정 문장 반환 (로컬 개발용)
- 호출 실패 시 fallbackReasonings 템플릿 사용 (빈 응답 금지)
"""

import json
import os

MODEL_ID = "global.anthropic.claude-sonnet-5"


def _build_prompt(stats: dict, consumer_type: dict, judgment: dict) -> str:
    """Bedrock에 보낼 프롬프트를 조립한다."""
    label = consumer_type["label"]
    crime = judgment["crime"]
    verdict = judgment["verdict"]
    total_expense = stats.get("totalExpense", 0)
    payment_count = stats.get("paymentCount", 0)
    evidence_lines = "\n".join(f"- {e}" for e in judgment.get("evidence", []))

    return (
        "당신은 위트 있는 소비 재판소 판사입니다. "
        "아래 피고인의 소비 유형과 증거를 바탕으로, 판결 이유를 2~3문장으로 작성하세요.\n\n"
        "규칙:\n"
        "- 구체적 수치를 1개 이상 인용할 것\n"
        "- 존댓말 판사 어조\n"
        "- JSON·마크다운 없이 순수 텍스트만 출력\n"
        "- 2~3문장으로 간결하게\n\n"
        f"소비 유형: {label}\n"
        f"죄명: {crime}\n"
        f"판결: {verdict}\n"
        f"총지출: {total_expense:,}원\n"
        f"결제 건수: {payment_count}건\n"
        f"핵심 증거:\n{evidence_lines}\n\n"
        "위 정보를 바탕으로 판결 이유를 작성하세요."
    )


def _mock_reasoning(stats: dict, consumer_type: dict) -> str:
    """MOCK_AI=1일 때 반환하는 고정 문장."""
    label = consumer_type["label"]
    total = stats.get("totalExpense", 0)
    count = stats.get("paymentCount", 0)
    return (
        f"본 재판부는 피고인의 소비 내역을 면밀히 검토하였습니다. "
        f"총 {total:,}원, {count}건의 결제 기록을 분석한 결과, "
        f"'{label}' 유형에 해당하는 소비 패턴이 명확히 확인됩니다."
    )


def _call_bedrock(prompt: str) -> str:
    """Bedrock Claude를 호출해 reasoning 텍스트를 반환한다.

    region_name을 지정하지 않아 환경변수 AWS_DEFAULT_REGION을 사용한다.
    실패 시 예외를 그대로 raise (호출 측에서 처리).
    """
    import boto3

    # region_name 미지정 → 환경변수 AWS_DEFAULT_REGION 사용
    client = boto3.client("bedrock-runtime")

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    })

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())

    # Claude Sonnet 5는 content 배열의 첫 블록으로 thinking을 반환할 수 있다.
    # content[0]["text"]로 꺼내면 KeyError가 나므로 type이 "text"인 블록을 찾는다.
    for block in result.get("content", []):
        if block.get("type") == "text" and block.get("text"):
            return block["text"].strip()

    types = [b.get("type") for b in result.get("content", [])]
    raise ValueError(f"응답에 text 블록이 없습니다 (blocks={types}, stop={result.get('stop_reason')})")


def generate_reasoning(stats: dict, consumer_type: dict, judgment: dict) -> str:
    """판결문 이유(reasoning)를 생성한다.

    Parameters
    ----------
    stats : dict
        calculate_monthly_stats() 반환값
    consumer_type : dict
        {"code": str, "label": str}
    judgment : dict
        build_judgment() 반환값 (crime, evidence, verdict, reasoning, sentence)

    Returns
    -------
    str  2~3문장의 판결 이유. 어떤 경우에도 예외를 밖으로 던지지 않는다.
    """
    # MOCK_AI=1이면 고정 문장 반환 (로컬 개발용)
    if os.environ.get("MOCK_AI") == "1":
        return _mock_reasoning(stats, consumer_type)

    # 실호출 (1회 재시도)
    prompt = _build_prompt(stats, consumer_type, judgment)
    for attempt in range(2):
        try:
            return _call_bedrock(prompt)
        except Exception as e:
            print(f"[verdict] Bedrock 호출 실패({attempt+1}차): {e}")
            if attempt == 0:
                continue
            # 최종 실패 → 폴백
            break

    # 폴백: judgment에 이미 들어있는 fallback reasoning 사용
    return judgment.get("reasoning", "")
