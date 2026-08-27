import os
import boto3
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

def build_local_vector_db():
    # TODO: 팀 실습 시 본인 팀의 S3 버킷명으로 변경 (예: hackathon-{팀ID}-docs)
    bucket_name = "your-team-bucket-name-here"
    s3_file_key = "s3_test.txt"
    local_file_name = "downloaded_context.txt"
    
    # 1. S3에서 파일 다운로드
    print("1. Downloading raw file from S3...")
    s3 = boto3.client('s3')
    try:
        s3.download_file(bucket_name, s3_file_key, local_file_name)
        print(f"   Successfully downloaded '{s3_file_key}' to '{local_file_name}'")
    except Exception as e:
        print(f"   Error downloading from S3: {e}")
        print("   If downloading fails, checking for local 'rich_context.txt' as fallback...")
        if os.path.exists("rich_context.txt"):
            local_file_name = "rich_context.txt"
            print("   Using local 'rich_context.txt' fallback.")
        else:
            print("   No fallback file found. Indexing aborted.")
            return
    
    # 2. 파일 텍스트 로드 및 청킹 (Chunking)
    print("2. Splitting text into chunks...")
    with open(local_file_name, 'r', encoding='utf-8') as f:
        text = f.read()
        
    # 긴 문서를 의미 있는 단위로 분할 (청크 크기 500자, 중복 50자)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = text_splitter.create_documents([text])

    print(f"   Created {len(docs)} text chunks.")
    
    # 3. Bedrock Titan Embedding v2 모델 설정
    # 리전을 명시하지 마세요 — 팀 배정 리전 외엔 IAM이 전부 차단합니다.
    # 주의: Titan Embed v2는 싱가포르(ap-southeast-1)에는 없습니다. 배정 리전이 싱가포르인 팀은
    # 이 모델 대신 그 리전에서 되는 임베딩 모델(예: cohere.embed-multilingual-v3)로 바꿔야 합니다 —
    # Kiro에게 "이 리전에서 쓸 수 있는 Bedrock 임베딩 모델 확인하고 맞춰줘"라고 요청하세요.
    print("3. Initializing Bedrock Titan Text Embeddings...")
    bedrock_client = boto3.client(service_name='bedrock-runtime')
    embeddings = BedrockEmbeddings(
        client=bedrock_client,
        model_id="amazon.titan-embed-text-v2:0"
    )
    
    # 4. 로컬 FAISS 벡터 DB 구축 및 로컬 저장
    print("4. Generating vectors and saving to local FAISS index...")
    db = FAISS.from_documents(docs, embeddings)
    db.save_local("faiss_index")
    print("   Success! Vector DB saved locally as folder './faiss_index'\n")

if __name__ == "__main__":
    build_local_vector_db()
