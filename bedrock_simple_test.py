import json
import boto3

def test_bedrock():
    # 1. Bedrock Runtime Client initialization
    # Automatically picks up the EC2 IAM Instance Profile role AND the EC2's own region.
    # 리전을 명시하지 마세요 — 팀마다 배정된 리전이 다르고, IAM이 "본인 팀 리전 외 전부 차단"으로
    # 설정되어 있어서 다른 리전(예: us-east-1)을 하드코딩하면 무조건 AccessDenied가 납니다.
    bedrock_runtime = boto3.client(service_name='bedrock-runtime')

    # 2. Global Cross-Region Inference Profile ID for Claude Sonnet 5
    # "us."/"apac." 같은 지역 한정 프로필이 아니라 "global." 프로필을 써야 8개 리전 어디서든 동작합니다.
    # raw 모델 ID(예: anthropic.claude-sonnet-5)로 직접 호출하면
    # "on-demand throughput isn't supported" 에러가 납니다.
    model_id = "global.anthropic.claude-sonnet-5"
    
    # 3. Payload Construction
    prompt = "AWS EC2 인스턴스 프로파일을 통해 Amazon Bedrock Claude 5 연동에 최종 성공했습니다. 축하 메시지 한 줄 출력해줘."
    
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    })
    
    print("Sending prompt to Bedrock Claude...")
    try:
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=body
        )
        
        # 4. Response Parsing
        response_body = json.loads(response.get('body').read())
        answer = response_body['content'][0]['text']
        print("\n--- Claude Response ---")
        print(answer)
        print("-----------------------")
        
    except Exception as e:
        print(f"Error calling Bedrock: {e}")

if __name__ == "__main__":
    test_bedrock()
