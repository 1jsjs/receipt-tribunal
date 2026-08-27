import os
import json
import boto3
import streamlit as st
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Page Config
st.set_page_config(page_title="AI Hackathon Portal", page_icon="🤖", layout="centered")

# AWS 및 S3/Bedrock 설정
# TODO: 팀 실습 시 본인 팀의 S3 버킷명으로 변경 (예: hackathon-{팀ID}-docs)
BUCKET_NAME = "your-team-bucket-name-here"
S3_FILE_KEY = "s3_test.txt"  # 기본 RAG 참고용 파일 키

# 2. AWS Client Initialization
# boto3 클라이언트는 커넥션 풀을 관리하므로 캐싱 유지
@st.cache_resource
def get_aws_clients():
    s3_client = boto3.client('s3')
    # 리전을 명시하지 마세요 — 팀마다 배정된 리전이 다르고 IAM이 그 리전 외엔 전부 차단합니다.
    bedrock_client = boto3.client(service_name='bedrock-runtime')
    return s3_client, bedrock_client

s3_client, bedrock_client = get_aws_clients()

# 3. Bedrock Embeddings Config
def get_embeddings():
    return BedrockEmbeddings(
        client=bedrock_client,
        model_id="amazon.titan-embed-text-v2:0"
    )

# 4. Local FAISS DB Loader (동적 갱신 반영을 위해 캐싱 제거)
def load_vector_db():
    embeddings = get_embeddings()
    try:
        # 캐싱을 제거하여 파일이 갱신될 때마다 최신 인덱스를 디스크에서 로드합니다.
        db = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)
        return db
    except Exception as e:
        return None

# 5. Multi-Page Navigation (Sidebar)
st.sidebar.title("📌 메뉴 구성")
page = st.sidebar.radio("원하시는 페이지를 선택하세요:", ["💬 RAG 챗봇", "📁 S3 문서 업로드 & DB 갱신"])

# ==========================================
# PAGE 1: RAG Chatbot
# ==========================================
if page == "💬 RAG 챗봇":
    st.title("💬 RAG Q&A 챗봇 서비스")
    st.write("로컬 벡터 데이터베이스(FAISS)를 조회하여 팩트 기반의 답변을 실시간 스트리밍합니다.")
    
    # 디스크에서 실시간으로 인덱스 로드
    db = load_vector_db()
    
    if db is None:
        st.warning("로컬 FAISS 인덱스를 불러올 수 없습니다. '📁 S3 문서 업로드 & DB 갱신' 메뉴에서 인덱스를 먼저 빌드해 주세요.")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Stream Response Generator from Bedrock
    def stream_bedrock_response(prompt_text):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 800,
            "messages": [
                {"role": "user", "content": prompt_text}
            ]
        })
        try:
            response = bedrock_client.invoke_model_with_response_stream(
                modelId="global.anthropic.claude-sonnet-5",  # "us." 등 지역 한정 프로필 대신 "global." 사용
                body=body
            )
            for event in response.get('body'):
                chunk = json.loads(event.get('chunk').get('bytes').decode('utf-8'))
                if chunk.get('type') == 'content_block_delta':
                    yield chunk.get('delta', {}).get('text', '')
        except Exception as e:
            yield f"\n\n⚠️ Error calling Bedrock: {e}"

    # Chat logic
    if db is not None:
        if query := st.chat_input("질문을 입력해 주세요..."):
            with st.chat_message("user"):
                st.markdown(query)
            st.session_state.messages.append({"role": "user", "content": query})
            
            # FAISS similarity search (k=4)
            docs = db.similarity_search(query, k=4)
            context_text = "\n---\n".join([doc.page_content for doc in docs])

            
            # Augmented prompt
            augmented_prompt = f"""
당신은 친절한 안내원입니다. 아래 주어진 [참고문서]를 바탕으로 질문에 답하세요.
참고문서에 없는 질문은 모른다고 명확히 답해야 합니다.

[참고문서]
{context_text}

질문: {query}
답변:
"""
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""
                for chunk in stream_bedrock_response(augmented_prompt):
                    full_response += chunk
                    response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)
                
            st.session_state.messages.append({"role": "assistant", "content": full_response})

# ==========================================
# PAGE 2: Document Upload & Index Update
# ==========================================
elif page == "📁 S3 문서 업로드 & DB 갱신":
    st.title("📁 S3 문서 업로드 및 벡터 DB 갱신")
    st.write("로컬 PC의 문서를 S3 버킷으로 업로드하고, 실시간으로 벡터 데이터베이스(FAISS)를 갱신합니다.")
    
    st.info(f"현재 타겟 S3 버킷: `{BUCKET_NAME}`")
    
    # 1. File Uploader Form
    uploaded_file = st.file_uploader("업로드할 텍스트 파일(.txt)을 선택해 주세요", type=["txt"])
    
    if uploaded_file is not None:
        file_details = {"FileName": uploaded_file.name, "FileType": uploaded_file.type, "FileSize": f"{uploaded_file.size} Bytes"}
        st.write(file_details)
        
        # 원클릭 업로드 및 인덱스 갱신 통합 버튼
        if st.button("S3 업로드 및 벡터 DB 즉시 갱신 실행"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # 1단계: S3 업로드
                status_text.text("1/5 단계: S3 버킷으로 파일 업로드 중...")
                s3_client.upload_fileobj(uploaded_file, BUCKET_NAME, S3_FILE_KEY)
                progress_bar.progress(20)
                
                # 2단계: S3에서 최신 문서 다운로드 (동기화 검증)
                status_text.text("2/5 단계: S3에서 방금 업로드된 최신 문서 다운로드 중...")
                local_file_name = "downloaded_context.txt"
                s3_client.download_file(BUCKET_NAME, S3_FILE_KEY, local_file_name)
                progress_bar.progress(40)
                
                # 3단계: 텍스트 로드 및 청킹
                status_text.text("3/5 단계: 문서 데이터를 읽고 텍스트 청크 분할 중...")
                with open(local_file_name, 'r', encoding='utf-8') as f:
                    text = f.read()
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
                docs = text_splitter.create_documents([text])

                progress_bar.progress(60)
                
                # 4단계: 임베딩 및 인덱스 생성
                status_text.text("4/5 단계: Titan 임베딩 생성 및 벡터 DB 빌드 중...")
                embeddings = get_embeddings()
                db = FAISS.from_documents(docs, embeddings)
                progress_bar.progress(80)
                
                # 5단계: 로컬 저장
                status_text.text("5/5 단계: 로컬 디스크에 faiss_index 저장 완료 중...")
                db.save_local("faiss_index")
                progress_bar.progress(100)
                
                st.success(f"성공! 파일이 `s3://{BUCKET_NAME}/{S3_FILE_KEY}` 경로로 업로드되었으며, 벡터 DB 갱신이 최종 완료되었습니다. (총 {len(docs)}개의 청크 데이터베이스화 성공)")
                status_text.text("준비 완료! '💬 RAG 챗봇' 메뉴로 이동하여 질문해 보세요.")
                
                # 대화 기록 세션 초기화 (새 지식 로드 시 이전 대화 컨텍스트 비우기)
                st.session_state.messages = []
                
            except Exception as e:
                st.error(f"작업 도중 에러가 발생했습니다: {e}")
