import json
import re
import base64
from datetime import datetime

import boto3
import streamlit as st

# ------------------------------------------------------------
# 페이지 설정
# ------------------------------------------------------------
st.set_page_config(page_title="영수증 분석기", page_icon="🧾", layout="centered")

# S3 버킷 (이미 생성되어 있는 버킷 사용, region은 하드코딩하지 않음 — /etc/environment의
# AWS_DEFAULT_REGION 값을 boto3가 자동으로 사용)
BUCKET_NAME = "hackathon-e1-t07-docs"

# 이 계정에서 사용 가능한 서비스는 Bedrock, S3 뿐입니다 (DynamoDB/Lambda/Textract/Rekognition 전부 AccessDenied)


# ------------------------------------------------------------
# AWS 클라이언트
# ------------------------------------------------------------
@st.cache_resource
def get_aws_clients():
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client(service_name="bedrock-runtime")
    return s3_client, bedrock_client


s3_client, bedrock_client = get_aws_clients()


# ------------------------------------------------------------
# Bedrock Claude Sonnet 5 비전 호출 -> 영수증 구조화 JSON
# ------------------------------------------------------------
def analyze_receipt_image(image_bytes: bytes, media_type: str) -> dict:
    """업로드된 영수증 이미지를 Bedrock Claude Sonnet 5 비전에 보내 구조화된 JSON으로 반환합니다."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt_text = """당신은 영수증 이미지를 분석하는 어시스턴트입니다.
이 영수증 이미지를 보고 아래 JSON 형식으로만 정확히 응답하세요. 다른 설명이나 문장은 절대 추가하지 마세요.

{
  "가맹점": "",
  "결제일시": "",
  "총액": 0,
  "카테고리": "",
  "품목": [{"이름": "", "금액": 0}]
}

규칙:
- "총액"과 품목의 "금액"은 숫자(정수)로만 작성하세요. 문자열이나 통화기호를 넣지 마세요.
- "결제일시"는 영수증에 표기된 형식을 최대한 살려 문자열로 작성하세요. 알 수 없으면 빈 문자열로 두세요.
- "카테고리"는 편의점, 카페, 음식점, 마트/슈퍼, 배달, 주점, 기타 중 가장 적합한 것 하나를 선택하세요.
- 읽을 수 없는 값은 빈 문자열 또는 0으로 두세요.
- 응답은 JSON 객체 하나만 출력하세요. 마크다운 코드블록(```)도 사용하지 마세요.
"""

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        }
    )

    response = bedrock_client.invoke_model(
        modelId="global.anthropic.claude-sonnet-5",  # 지역 한정 프로필(us. 등) 대신 global. 사용 필수
        body=body,
    )
    response_body = json.loads(response.get("body").read())
    raw_text = "".join(
        block.get("text", "")
        for block in response_body.get("content", [])
        if block.get("type") == "text"
    ).strip()

    # 혹시 모델이 코드블록으로 감싸서 응답한 경우를 대비한 방어 처리
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    json_text = match.group(0) if match else raw_text

    return json.loads(json_text)


# ------------------------------------------------------------
# 소비 유형 판정 (JSON 근거로 Bedrock에게 유형명 + 한줄 코멘트 요청)
# ------------------------------------------------------------
def classify_spending_type(receipt_json: dict) -> dict:
    """영수증 분석 JSON을 바탕으로 소비 유형 이름과 한 줄 코멘트를 생성합니다."""
    prompt_text = f"""아래는 영수증 하나를 분석한 JSON 데이터입니다.

{json.dumps(receipt_json, ensure_ascii=False)}

이 데이터를 보고 재미있고 공감가는 "소비 유형"을 하나 지어내고, 그에 어울리는 한 줄 코멘트를 작성하세요.
예시: 유형 "새벽 편의점 야식형", 코멘트 "이번 주 편의점만 4번, 야식비가 식비를 이겼어요"

반드시 아래 JSON 형식으로만 응답하세요. 다른 설명은 추가하지 마세요.

{{"유형": "", "코멘트": ""}}
"""

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt_text}],
        }
    )

    response = bedrock_client.invoke_model(
        modelId="global.anthropic.claude-sonnet-5",
        body=body,
    )
    response_body = json.loads(response.get("body").read())
    raw_text = "".join(
        block.get("text", "")
        for block in response_body.get("content", [])
        if block.get("type") == "text"
    ).strip()

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    json_text = match.group(0) if match else raw_text

    return json.loads(json_text)


# ------------------------------------------------------------
# S3 저장 (원본 이미지 + 분석 JSON)
# ------------------------------------------------------------
def save_to_s3(image_bytes: bytes, receipt_json: dict, timestamp: str) -> tuple:
    image_key = f"receipts/{timestamp}.jpg"
    json_key = f"receipts/{timestamp}.json"

    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=image_key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=json_key,
        Body=json.dumps(receipt_json, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    return image_key, json_key


# ------------------------------------------------------------
# 세션 상태 초기화 (업로드한 영수증 누적)
# ------------------------------------------------------------
if "receipts" not in st.session_state:
    st.session_state.receipts = []  # 각 항목: {"file": UploadedFile, "receipt": dict, "spending_type": dict}


# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
st.title("🧾 영수증 분석기")
st.write("영수증 사진을 업로드하면 AI가 자동으로 분석하고, 소비 유형을 알려드려요.")

# 상단 총 지출액 표시
total_amount = sum(item["receipt"].get("총액", 0) or 0 for item in st.session_state.receipts)
st.metric("누적 총 지출액", f"{total_amount:,.0f}원", help=f"지금까지 업로드한 영수증 {len(st.session_state.receipts)}건 기준")

st.divider()

uploaded_file = st.file_uploader("영수증 사진을 업로드하세요", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="업로드한 영수증", use_container_width=True)

    if st.button("분석 시작", type="primary"):
        image_bytes = uploaded_file.getvalue()
        media_type = uploaded_file.type or "image/jpeg"

        with st.spinner("영수증을 분석하는 중입니다..."):
            try:
                receipt_json = analyze_receipt_image(image_bytes, media_type)
            except Exception as e:
                st.error(f"영수증 분석 중 오류가 발생했습니다: {e}")
                st.stop()

        with st.spinner("소비 유형을 판정하는 중입니다..."):
            try:
                spending_type = classify_spending_type(receipt_json)
            except Exception as e:
                st.error(f"소비 유형 판정 중 오류가 발생했습니다: {e}")
                st.stop()

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            image_key, json_key = save_to_s3(image_bytes, receipt_json, timestamp)
        except Exception as e:
            st.error(f"S3 저장 중 오류가 발생했습니다: {e}")
            st.stop()

        st.session_state.receipts.append(
            {
                "file": uploaded_file,
                "receipt": receipt_json,
                "spending_type": spending_type,
                "image_key": image_key,
                "json_key": json_key,
            }
        )

        st.success(f"분석 및 저장 완료! (S3: {image_key}, {json_key})")
        st.rerun()

st.divider()

# ------------------------------------------------------------
# 누적된 영수증 목록 표시
# ------------------------------------------------------------
st.subheader("분석 내역")

if not st.session_state.receipts:
    st.info("아직 업로드한 영수증이 없습니다.")
else:
    for item in reversed(st.session_state.receipts):
        receipt = item["receipt"]
        spending_type = item["spending_type"]

        with st.container(border=True):
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(item["file"], use_container_width=True)
            with col2:
                st.markdown(f"**{receipt.get('가맹점', '알 수 없음')}**")
                st.caption(receipt.get("결제일시", ""))
                st.write(f"총액: {receipt.get('총액', 0):,.0f}원")
                st.write(f"카테고리: {receipt.get('카테고리', '')}")

                품목 = receipt.get("품목", [])
                if 품목:
                    with st.expander("품목 보기"):
                        for p in 품목:
                            st.write(f"- {p.get('이름', '')}: {p.get('금액', 0):,.0f}원")

            # 소비 유형 카드
            st.markdown(
                f"""
<div style="background-color:#f0f2f6; border-radius:10px; padding:14px; margin-top:8px;">
  <div style="font-weight:700; font-size:16px; margin-bottom:4px;">🏷️ {spending_type.get('유형', '')}</div>
  <div style="color:#444;">{spending_type.get('코멘트', '')}</div>
</div>
""",
                unsafe_allow_html=True,
            )
