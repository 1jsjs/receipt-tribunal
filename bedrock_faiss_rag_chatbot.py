import json
import boto3
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS

def run_faiss_rag_chatbot():
    # 1. 임베딩 모델 및 로컬 FAISS DB 로드
    # 리전을 명시하지 마세요 — 팀 배정 리전 외엔 IAM이 전부 차단합니다.
    bedrock_client = boto3.client(service_name='bedrock-runtime')
    embeddings = BedrockEmbeddings(
        client=bedrock_client,
        model_id="amazon.titan-embed-text-v2:0"
    )
    
    print("Loading local FAISS database...")
    try:
        # 로컬 faiss_index 폴더 로드
        db = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)
    except Exception as e:
        print(f"Error loading local FAISS index: {e}")
        print("Please run bedrock_faiss_indexer.py first to create the index.")
        return

    print("==================================================")
    print(" FAISS RAG Chatbot is running! (Type 'exit' to quit)")
    print("==================================================")
    
    while True:
        query = input("\nQ: ")
        if query.strip().lower() == 'exit':
            print("Chatbot shutdown.")
            break
            
        # 2. 로컬 FAISS DB에서 질문과 가장 유사한 조각 검색 (k=4)
        docs = db.similarity_search(query, k=4)

        
        # 검색된 텍스트 조각 병합
        context_text = "\n---\n".join([doc.page_content for doc in docs])
        
        # 3. 프롬프트 생성
        augmented_prompt = f"""
당신은 친절한 안내원입니다. 아래 주어진 [참고문서]를 바탕으로 질문에 답하세요.
참고문서에 없는 질문은 모른다고 명확히 답해야 합니다.

[참고문서]
{context_text}

질문: {query}
답변:
"""

        # 4. Bedrock Claude 5 호출 (추론 프로필 활용)
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [
                {"role": "user", "content": augmented_prompt}
            ]
        })
        
        try:
            response = bedrock_client.invoke_model(
                modelId="global.anthropic.claude-sonnet-5",  # "us." 등 지역 한정 프로필 대신 "global." 사용
                body=body
            )
            response_body = json.loads(response.get('body').read())
            answer = response_body['content'][0]['text']
            print(f"\nA: {answer}")
            
        except Exception as e:
            print(f"Error calling Bedrock: {e}")

if __name__ == "__main__":
    run_faiss_rag_chatbot()
