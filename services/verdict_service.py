"""판결문 '이유(reasoning)' + '형량(sentence)' Bedrock 생성 — TASK-B012 (docs/05 §14)

- 모델: global.anthropic.claude-sonnet-5 (global. 접두사 필수)
- region_name 하드코딩 금지 (서버 환경변수 AWS_DEFAULT_REGION 사용)
- MOCK_AI=1이면 고정 문구 반환 (로컬 개발용)
- 호출 실패 시 judgment 템플릿(fallbackReasoning·sentence) 사용 (빈 응답 금지)

설계 (docs/05 §14 — 죄명·유형·주문은 룰, 이유·형량은 AI):
  1. system : 재판장 페르소나 + 문체·유머·안전·출력형식 규칙 (데이터 없음)
  2. few-shot : 놀림 톤 1건 + 칭찬 톤 1건 — 이상적 JSON 출력 형태 고정
  3. user : 이번 달 통계 '증거 표' + 죄명/유형/주문 + (있으면) N빵 정상참작
           → 모델은 이유 2문장 + 형량 1문장(창의적 형벌 문구)만 JSON으로 반환
반환은 '문장'이 아니라 화면에 그대로 박아 넣을 '문구' 수준으로 짧게.
"""

import json
import os
import re

MODEL_ID = "global.anthropic.claude-sonnet-5"

# 칭찬(무혐의) 톤 유형 — judgment_service 템플릿 톤과 일치
_PRAISE_TYPES = {"SMART_SOLO", "BALANCED"}

# ─── N빵 / 더치페이 감지 키워드 (plea 소문자 매칭) ───
_SPLIT_KEYWORDS = (
    "n빵", "엔빵", "n/빵", "1/n", "1/n씩", "더치", "더치페이", "갹출", "각출",
    "나눠", "나눔", "분담", "분할결제", "공동결제", "공동 결제", "회비", "반반", "쿼터",
    "정산", "쏘고 정산", "n분",
)
# plea에서 인원수 추출용: "5명", "4인", "3명이서", "N=6"
_HEADCOUNT_RE = re.compile(r"(\d+)\s*(?:명|인|사람|빵|분)")


# ═══════════════════════════════════════════════════════════════════════════════
# 프롬프트 재료
# ═══════════════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = (
    "당신은 '영수증 소비 재판소'의 재판장입니다. "
    "피고인(자취생)의 한 달 소비 내역을 근거로, 판결문의 '이유(理由)'와 '형량(刑量)'만 작성합니다. "
    "죄명·소비 유형·주문은 이미 확정되어 있으니 새로 만들지 마십시오.\n"
    "\n"
    "[문체와 태도]\n"
    "- 실제 법원 판결문의 문어체. 모든 문장의 종결어미를 '~다'로 고정한다. "
    "'~합니다'·'~하십시오'·'~됩니다' 같은 존댓말 종결은 절대 쓰지 않는다.\n"
    "- 허용 종결 예: '~한 것으로 판단된다.', '~라 아니할 수 없다.', '~함이 상당하다.', "
    "'~에 처한다.', '~을 명한다.', '본 재판부는 ~하였다.'\n"
    "- 근엄한 척하지만 한 방에 뼈를 때리는 유머가 핵심이다. 판결문 형식 안에서 피식 웃게 만든다.\n"
    "- 놀림의 대상은 오직 '소비 습관'이다. 외모·체형·건강·성격·소득 수준은 언급 금지.\n"
    "- 칭찬(무혐의) 톤 지시가 오면 비꼬지 말고 담백하게 인정하고 응원하되, 종결어미는 그대로 '~다'.\n"
    "\n"
    "[이유(reasoning)]\n"
    "- 정확히 2문장, 각 문장 45자 내외. 두 문장 모두 '~다'로 끝낸다.\n"
    "- 제공된 수치(총지출, 카테고리별 금액·비율·건수, 결제 건수, 소액 건수 등) 중 최소 1개를 그대로 인용.\n"
    "- 죄명이 왜 성립하는지를 그 수치로 뒷받침한다.\n"
    "- 피고인 이름이 제공되면 이유 안에서 한 번 이상 언급한다.\n"
    "- '정상참작' 항목이 제공되면 반드시 이유 안에서 유쾌하게 언급한다.\n"
    "- 제공되지 않은 수치·상호·사실을 지어내지 않는다.\n"
    "\n"
    "[형량(sentence)]\n"
    "- 1문장, 60자 내외. 이번 소비 패턴에 딱 맞춘 창의적이고 유쾌한 형벌 문구.\n"
    "- 반드시 '~을 명한다.' 또는 '~에 처한다.'로 끝낸다. '~하십시오'는 금지.\n"
    "- 실행 가능한 소소한 미션 형태가 좋다. (예: 배달앱 아이콘을 홈 화면 맨 뒷장으로 추방할 것을 명한다.)\n"
    "\n"
    "[출력 형식]\n"
    '- 아래 JSON 객체 하나만 출력. 마크다운 코드블록·설명·머리말 금지.\n'
    '- {"reasoning": "...", "sentence": "..."}\n'
)

_FEWSHOT: list[dict] = [
    {
        "role": "user",
        "content": (
            "소비 유형: 냉장고보다 배달앱형 (톤: 놀림)\n"
            "죄명: 냉장고 유기죄\n"
            "주문: 냉장고는 가구가 아닙니다.\n"
            "피고인 이름: 박진수\n"
            "이번 달 총지출: 432,000원 / 결제 42건 / 소액(5천 이하) 21건\n"
            "카테고리별 지출(많은 순):\n"
            "- 배달·외식: 184,000원 (42.6%, 12건)\n"
            "- 편의점: 96,000원 (22.2%, 15건)\n"
            "정상참작: 없음\n"
            "위 근거로 이유와 형량을 작성하세요."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "reasoning": (
                "피고인 박진수는 이번 달 배달·외식에 184,000원을 지출하여 전체 소비의 42.6%를 한곳에 몰아넣었다. "
                "12회에 이르는 배달 결제에 비추어 주방을 사용한 정황은 발견되지 아니한다."
            ),
            "sentence": "다음 달 배달앱 아이콘을 홈 화면 맨 뒷장으로 추방하고, 밥솥 가동 3회를 명한다.",
        }, ensure_ascii=False),
    },
    {
        "role": "user",
        "content": (
            "소비 유형: 야무진 자취생형 (톤: 칭찬·무혐의)\n"
            "죄명: 무혐의 — 자취 모범생\n"
            "주문: 자취생의 정석을 보여주고 있습니다.\n"
            "피고인 이름: 익명의 자취생\n"
            "이번 달 총지출: 388,000원 / 결제 24건 / 소액(5천 이하) 6건\n"
            "카테고리별 지출(많은 순):\n"
            "- 식재료·생필품: 152,000원 (39.2%, 9건)\n"
            "- 배달·외식: 61,000원 (15.7%, 4건)\n"
            "정상참작: 없음\n"
            "위 근거로 이유와 형량을 작성하세요."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "reasoning": (
                "피고인은 식재료·생필품에 152,000원, 전체의 39.2%를 배정하고 배달은 4건에 그친 점이 확인된다. "
                "직접 조리하는 계획적 생활 습관이 넉넉히 인정되는바, 본 재판부는 감동하였다."
            ),
            "sentence": "현재의 장바구니 습관을 그대로 유지할 것을 명하며, 본 재판부가 조용히 응원한다.",
        }, ensure_ascii=False),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════════════════════════

def _evidence_table(stats: dict) -> str:
    """categoryStats를 금액 많은 순 '증거 표' 문자열로 (지출 0 제외)."""
    rows = [s for s in stats.get("categoryStats", []) if s.get("amount", 0) > 0]
    rows.sort(key=lambda s: -s["amount"])
    if not rows:
        return "- (집계된 카테고리 지출 없음)"
    return "\n".join(
        f"- {s['label']}: {s['amount']:,}원 ({s['percentage']}%, {s['count']}건)"
        for s in rows
    )


def detect_split_bill(expenses: list[dict]) -> dict | None:
    """피고인 변론(plea)에서 N빵·더치페이 정황을 찾아 정상참작 정보를 만든다.

    Returns
    -------
    dict | None
        {"note": 화면·프롬프트용 문구, "matchedCount": int,
         "matchedTotal": int, "estimatedBurden": int, "headcount": int}
    """
    if not expenses:
        return None

    matched: list[dict] = []
    headcount = 2  # 기본값: 최소 2명
    for e in expenses:
        plea = str(e.get("plea", "")).lower()
        if not plea:
            continue
        if any(k in plea for k in _SPLIT_KEYWORDS):
            matched.append(e)
            m = _HEADCOUNT_RE.search(plea)
            if m:
                n = int(m.group(1))
                if 2 <= n <= 30:
                    headcount = max(headcount, n)

    if not matched:
        return None

    matched_total = sum(int(e.get("amount", 0)) for e in matched)
    burden = matched_total // headcount
    sample = matched[0].get("storeName", "해당 결제")
    extra = f" 외 {len(matched) - 1}건" if len(matched) > 1 else ""

    note = (
        f"{sample}{extra} 합계 {matched_total:,}원은 {headcount}명이 나눠 낸 정황이 있어, "
        f"피고인의 실제 부담은 약 {burden:,}원으로 정상참작함"
    )
    return {
        "note": note,
        "matchedCount": len(matched),
        "matchedTotal": matched_total,
        "estimatedBurden": burden,
        "headcount": headcount,
    }


def _build_user_message(stats: dict, consumer_type: dict, judgment: dict,
                        defendant: str, split: dict | None) -> str:
    tone = "칭찬·무혐의" if consumer_type["code"] in _PRAISE_TYPES else "놀림"
    total = stats.get("totalExpense", 0)
    count = stats.get("paymentCount", 0)
    small = stats.get("smallPaymentCount", 0)

    lines = [
        f"소비 유형: {consumer_type['label']} (톤: {tone})",
        f"죄명: {judgment['crime']}",
        f"주문: {judgment['verdict']}",
        f"피고인 이름: {defendant}",
        f"이번 달 총지출: {total:,}원 / 결제 {count}건 / 소액(5천 이하) {small}건",
    ]
    largest = stats.get("largestSingleExpense")
    if largest:
        lines.append(
            f"최대 단일 지출: {largest['storeName']} {largest['amount']:,}원 ({largest['date']})"
        )
    lines.append("카테고리별 지출(많은 순):")
    lines.append(_evidence_table(stats))
    lines.append(f"정상참작: {split['note'] if split else '없음'}")
    lines.append(
        "위 근거로 판결문 '이유'(2문장)와 '형량'(1문장)을 작성하세요. "
        "죄명이 왜 성립하는지 위 수치 중 하나 이상을 인용하고, "
        "형량은 이번 소비 패턴에 맞춘 창의적이고 유쾌한 형벌 문구로 쓰세요."
    )
    return "\n".join(lines)


def _sanitize(text: str) -> str:
    """머리말·따옴표·줄바꿈·코드블록 제거해 한 줄 문구로."""
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    text = re.sub(r"^(이유|형량|理由|주문)\s*[:：]\s*", "", text)
    if len(text) >= 2 and text[0] in "\"'“”「『" and text[-1] in "\"'“”」』":
        text = text[1:-1].strip()
    return re.sub(r"\s+", " ", text).strip()


def _parse_verdict(raw_text: str) -> dict:
    """모델 응답에서 {"reasoning","sentence"} 를 뽑는다. 형식 이탈 시 raise."""
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    obj = json.loads(match.group(0) if match else raw_text)

    reasoning = _sanitize(str(obj.get("reasoning", "")))
    sentence = _sanitize(str(obj.get("sentence", "")))

    if not reasoning or not sentence:
        raise ValueError("reasoning/sentence 누락")
    if len(reasoning) > 400 or len(sentence) > 200:
        raise ValueError(f"길이 초과 (reasoning={len(reasoning)}, sentence={len(sentence)})")
    return {"reasoning": reasoning, "sentence": sentence}


def _extract_text(result: dict) -> str:
    """Bedrock 응답 content 배열에서 type == 'text' 블록의 텍스트를 꺼낸다.

    Claude Sonnet 5는 content[0]에 thinking 블록을 넣을 수 있어
    result["content"][0]["text"]는 KeyError가 난다 (.kiro tech-constraints §1).
    """
    for block in result.get("content", []):
        if block.get("type") == "text" and block.get("text"):
            return block["text"]
    types = [b.get("type") for b in result.get("content", [])]
    raise ValueError(f"응답에 text 블록이 없습니다 (blocks={types}, stop={result.get('stop_reason')})")


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK
# ═══════════════════════════════════════════════════════════════════════════════

def _mock_verdict(stats: dict, consumer_type: dict, judgment: dict,
                  defendant: str, split: dict | None) -> dict:
    label = consumer_type["label"]
    evidence = judgment.get("evidence") or []
    head = evidence[0] if evidence else f"총지출 {stats.get('totalExpense', 0):,}원"
    mitig = f" 다만 {split['note']}." if split else ""

    if consumer_type["code"] in _PRAISE_TYPES:
        reasoning = (
            f"{head} 등에 비추어 피고인 {defendant}의 계획적이고 절제된 소비 습관이 인정된다. "
            f"이를 '{label}'으로 판단함이 상당하다.{mitig}"
        )
        sentence = "현재의 소비 습관을 그대로 유지할 것을 명하며, 본 재판부가 조용히 응원한다."
    else:
        reasoning = (
            f"{head} 등의 정황에 비추어 피고인 {defendant}는 특정 소비에 편중된 지출 습관이 뚜렷하다. "
            f"이를 '{label}'으로 판단함이 상당하다.{mitig}"
        )
        sentence = "다음 달 동일 카테고리 지출을 주 2회 이하로 제한하고, 무지출 데이 1회를 명한다."
    return {"reasoning": _sanitize(reasoning), "sentence": _sanitize(sentence)}


# ═══════════════════════════════════════════════════════════════════════════════
# Bedrock
# ═══════════════════════════════════════════════════════════════════════════════

def _call_bedrock(stats: dict, consumer_type: dict, judgment: dict,
                  defendant: str, split: dict | None) -> dict:
    """Bedrock Claude 호출 → {"reasoning","sentence"}. 실패 시 예외 raise."""
    import boto3

    client = boto3.client("bedrock-runtime")  # region_name 미지정 → AWS_DEFAULT_REGION
    messages = _FEWSHOT + [
        {"role": "user",
         "content": _build_user_message(stats, consumer_type, judgment, defendant, split)}
    ]
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        # temperature·top_p를 넣으면 안 된다.
        # global.anthropic.claude-sonnet-5는 두 파라미터를 거부한다
        # (ValidationException: `temperature` is deprecated for this model).
        # 실패하면 조용히 폴백 템플릿으로 떨어져 AI가 실종된 것처럼 보인다.
        "system": _SYSTEM_PROMPT,
        "messages": messages,
    })

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return _parse_verdict(_extract_text(result))


# ═══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ═══════════════════════════════════════════════════════════════════════════════

def generate_verdict(stats: dict, consumer_type: dict, judgment: dict,
                     defendant: str = "피고인",
                     expenses: list[dict] | None = None) -> dict:
    """판결문의 이유(reasoning)와 형량(sentence)을 생성한다.

    Parameters
    ----------
    stats : dict           calculate_monthly_stats() 반환값
    consumer_type : dict    {"code": str, "label": str}
    judgment : dict         build_judgment() 반환값 (fallback 포함)
    defendant : str         판결 대상 피고인 이름 (이유 문장에 언급)
    expenses : list[dict]   fetch_month_expenses() 반환값 (plea 정상참작용, 없으면 생략)

    Returns
    -------
    dict  {"reasoning": str, "sentence": str, "mitigation": dict | None}
          어떤 경우에도 예외를 밖으로 던지지 않는다.
    """
    split = detect_split_bill(expenses or [])

    if os.environ.get("MOCK_AI") == "1":
        out = _mock_verdict(stats, consumer_type, judgment, defendant, split)
        out["mitigation"] = split
        return out

    for attempt in range(2):
        try:
            out = _call_bedrock(stats, consumer_type, judgment, defendant, split)
            out["mitigation"] = split
            return out
        except Exception as e:
            print(f"[verdict] Bedrock 호출 실패({attempt + 1}차): {e}")
            if attempt == 0:
                continue
            break

    # 폴백: judgment 템플릿 문구 그대로
    return {
        "reasoning": judgment.get("reasoning", ""),
        "sentence": judgment.get("sentence", ""),
        "mitigation": split,
    }


def generate_reasoning(stats: dict, consumer_type: dict, judgment: dict,
                       defendant: str = "피고인") -> str:
    """하위 호환용 — 이유 문자열만 반환 (구 호출부 대비)."""
    return generate_verdict(stats, consumer_type, judgment, defendant).get("reasoning", "")
