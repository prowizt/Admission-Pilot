# ==========================================
# 메인 서버 및 API 엔드포인트
# ==========================================
import os
import re
import io
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from pydantic import BaseModel
import chromadb
import pyodbc
import pdfplumber
import openpyxl
import google.generativeai as genai

# 서버 초기화: 입시처 통합 AI 지식 관리 시스템 중앙 통제소
app = FastAPI(
    title="Admission-Pilot Backend", 
    description="대동대학교 입시처 AI 업무 헬퍼 및 챗봇 중앙 서버"
)

# ==========================================
# [0] AI 페르소나 및 시스템 프롬프트
# ==========================================
def get_system_prompt():
    """
    AI 챗봇의 역할(Persona)과 규칙을 정의하는 시스템 프롬프트 문자열을 반환합니다.
    이 문자열은 Gemini API 호출 시 'system_instruction'으로 전달되어 일관된 답변 톤을 유지합니다.
    """
    
    # 1. AI의 역할 정의 (Role Definition)
    role_definition = """
당신은 **대동대학교 입시처의 핵심 AI 업무 헬퍼(Sub-Assistant)**입니다.
주 사용자는 복잡한 행정 절차와 규정 사이에서 신속하고 정확한 사실 확인이 필요한 입시처 공무원입니다.
당신은 챗봇 인터페이스(프론트엔드)를 통해 이들에게 실시간으로 답변을 제공합니다.
당신의 목표는 사람을 대체하는 것이 아니라, 수작업 처리 시간을 획기적으로 줄여주는 **유능한 조수(Buddy)**가 되는 것입니다.
"""

    # 2. 답변 스타일 및 톤앤매너 (Tone & Manners)
    tone_definition = """
[답변 스타일 및 톤앤매너]
- **전문성(Professionalism):** 긍정적이고 적극적인 태도를 유지하되, 모든 정보는 사실에 기반해야 합니다.
- **공감 및 협업:** 사용자가 "바쁘다", "헷갈린다" 등의 감정을 표현할 때는 공감하는 리액션을 먼저 취하세요.
- **공식성(Formality):** '-습니다' 체를 사용하며, 문서는 항상 정확한 행정 용어와 격식을 갖춰 서술하십시오.
- **친절함:** 딱딱한 말투보다는 따뜻하고 배려심 있는 어조를 사용하세요.
"""

    # 3. 핵심 답변 규칙 (Response Rules)
    rules_definition = """
[핵심 답변 규칙]
1. **출처 제시 의무:** 
   - 답변의 근거가 된 문서나 데이터가 있다면 반드시 **출처(Source)**를 명시하세요.
   - 예: "2026학년도 정시모집요강 p.12에 따르면..." 또는 "2025학년도 데이터 기준..."
   - (기술적 참고) 이는 백엔드의 ChromaDB 메타데이터를 통해 제공되는 정보에 기반해야 합니다.

2. **단계적 처리 프로세스:**
   - 사용자의 질문이 복잡할 경우, 단일 문장으로 답하려 하지 마십시오.
   - **1단계(확인):** "해당 업무는 A 절차에 해당합니다."와 같이 분류하세요.
   - **2단계(세부사항):** "관련 규정은 다음과 같습니다."라며 관련 팩트를 나열하세요.
   - **3단계(가이드):** "따라서 순서는 [1->2->3]으로 진행하시면 됩니다."라며 행동 지침을 제시하세요.

3. **허용 불가 행동(Don'ts):**
   - **절대 추측하지 마십시오.** 불확실한 정보는 "확인해보겠습니다" 또는 "자료를 찾아보겠습니다"라고 답하세요.
   - **법규/규정 해석:** 법적 구속력이 있는 해석을 단정적으로 내리지 마세요. (단, 지침상 명확한 내용은 전달)
   - **과거/미래 정보 혼용:** 사용자가 연도를 지정하지 않았더라도, 현재 유효한 최신 정보(Current Year)를 기준으로 답하세요.
     - 단, 과거 자료를 참고해야 하는 맥락(예: "작년도와 비교하면?")에서는 명확히 연도를 구분하여 서술하세요.
"""

    # 4. 결론
    conclusion = """
위 규칙을 모두 준수하여, 사용자가 신뢰할 수 있고 효율적으로 업무를 처리할 수 있도록 최선을 다해 지원하십시오.
"""

    # 전체 프롬프트 조합
    full_prompt = f"{role_definition}\n{tone_definition}\n{rules_definition}\n{conclusion}"
    
    return full_prompt


class ChatRequest(BaseModel):
    question: str
    model_name: str = "gemini-2.5-flash"  # 기본값 설정

# ==========================================
# [1] 하이브리드 DB 세팅 (Vector DB)
# ==========================================
# 로컬 환경 및 Windows Server 2022에서 데이터가 영구 보존되도록 PersistentClient 사용
CHROMA_DB_PATH = "./db"
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# [핵심 라우팅 분리] 
# 목적이 섞이지 않도록 컬렉션을 명확히 2개로 분리하여 생성/로드합니다.

# 1-1. Rule DB: 교육부 공문, 입시요강 등 팩트 체크 및 질의응답 전용
rule_db = chroma_client.get_or_create_collection(name="rule_db")

# 1-2. Reference DB: 과거 기안문, 행사 계획서 등 톤앤매너 및 양식 참고용
reference_db = chroma_client.get_or_create_collection(name="reference_db")


# ==========================================
# [2] 하이브리드 DB 세팅 (정형 DB)
# ==========================================
def mask_personal_info(text: str) -> str:
    """
    텍스트 내의 민감한 개인정보(주민등록번호, 휴대전화번호)를 정규식으로 찾아 마스킹 처리합니다.
    """
    if not text:
        return text
    # 주민등록번호 마스킹 (ex: 900101-1234567 -> 900101-*******)
    masked_text = re.sub(r'(\d{6})[-]\d{7}', r'\1-*******', text)
    # 휴대전화번호 마스킹 (ex: 010-1234-5678 -> 010-****-****)
    masked_text = re.sub(r'(01\d)-(\d{3,4})-(\d{4})', r'\1-****-****', masked_text)
    
    return masked_text


def table_to_markdown(table):
    """
    pdfplumber가 추출한 2D 리스트(표) 데이터를 Markdown 테이블 형식으로 변환합니다.
    """
    if not table:
        return ""
    
    md_table = "\n"
    for row in table:
        # 각 셀의 줄바꿈 제거 및 None 처리
        cleaned_row = [str(cell).replace("\n", " ").strip() if cell else "" for cell in row]
        md_table += "| " + " | ".join(cleaned_row) + " |\n"
        
        # 첫 번째 행(헤더) 다음에 구분선 추가
        if row == table[0] and len(table) > 1:
            md_table += "| " + " | ".join(["---"] * len(row)) + " |\n"
            
    return md_table + "\n"


def get_mssql_connection():
    """
    MS-SQL 데이터베이스 연결 객체를 반환합니다.
    실제 운영 서버(10.10.1.11) 설정 및 한글 인코딩(CP949)이 적용되어 있습니다.
    """
    try:
        conn_str = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=10.10.1.11,1433;"
            "DATABASE=DDU_ADMISSION;"
            "UID=admission_ai;"
            "PWD=fjk12#$;"
        )
        conn = pyodbc.connect(conn_str, autocommit=True)
        conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp949')
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding='cp949')
        conn.setencoding(encoding='cp949')
        return conn
    except Exception as e:
        print(f"MS-SQL 연결 에러 발생: {e}")
        return None


# ==========================================
# [3] 핵심 API 엔드포인트
# ==========================================
@app.get("/health")
async def health_check():
    """
    크롬 확장 프로그램이나 Watchdog이 서버와 정상 통신 가능한지 확인하는 엔드포인트.
    각 DB에 데이터가 몇 개 들어있는지 카운트도 함께 반환합니다.
    """
    return {
        "status": "online",
        "rule_db_document_count": rule_db.count(),
        "reference_db_document_count": reference_db.count()
    }


@app.post("/upload-knowledge")
async def upload_knowledge(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    year: str = Form(...),
    title: str = Form(...)
):
    """
    PDF 등 문서를 업로드 받아 텍스트를 추출, 개인정보를 마스킹한 후 지정된 벡터 DB에 저장합니다.
    doc_type: 'rule' (팩트체크용) 또는 'reference' (기안문 양식 참고용)
    """
    if doc_type not in ["rule", "reference"]:
        raise HTTPException(status_code=400, detail="doc_type은 'rule' 또는 'reference'여야 합니다.")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="현재는 PDF 파일만 지원합니다.")

    # 1. PDF 텍스트 및 표 추출 (Try-Except 방어 로직)
    try:
        content = await file.read()
        extracted_text = ""
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                # 일반 텍스트 추출
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
                
                # 표 데이터 추출 및 마크다운 변환
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        extracted_text += table_to_markdown(table)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 파싱 중 오류가 발생했습니다: {str(e)}")

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="문서에서 텍스트를 추출할 수 없습니다. (이미지 기반 PDF일 수 있음)")

    # 2. 개인정보 마스킹 (Security First)
    safe_text = mask_personal_info(extracted_text)

    # 3. DB 라우팅 및 저장
    doc_id = str(uuid.uuid4())
    metadata = {"year": year, "title": title, "doc_type": doc_type, "filename": file.filename}

    try:
        if doc_type == "rule":
            rule_db.add(documents=[safe_text], metadatas=[metadata], ids=[doc_id])
        else:
            reference_db.add(documents=[safe_text], metadatas=[metadata], ids=[doc_id])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"벡터 DB 저장 중 오류가 발생했습니다: {str(e)}")

    return {
        "status": "success",
        "message": f"'{title}' 문서가 {doc_type} DB에 성공적으로 저장되었습니다.",
        "doc_id": doc_id,
        "extracted_preview": safe_text[:100] + "..." # 테스트 확인용 미리보기
    }


@app.get("/documents/{doc_type}")
async def get_documents(doc_type: str):
    """
    지정된 벡터 DB(rule 또는 reference)에 저장된 모든 문서의 목록과 내용을 조회합니다.
    (관리자 검증 및 테스트 용도)
    """
    if doc_type not in ["rule", "reference"]:
        raise HTTPException(status_code=400, detail="doc_type은 'rule' 또는 'reference'여야 합니다.")

    try:
        # 지정된 DB에서 데이터 가져오기
        target_db = rule_db if doc_type == "rule" else reference_db
        
        # get() 메서드는 저장된 id, metadata, document를 반환합니다.
        result = target_db.get()
        
        # 응답하기 좋게 리스트 형태로 가공
        documents_list = []
        if result and result.get("ids"):
            for i in range(len(result["ids"])):
                documents_list.append({
                    "id": result["ids"][i],
                    "metadata": result["metadatas"][i] if result.get("metadatas") else {},
                    "content": result["documents"][i] if result.get("documents") else ""
                })
                
        return {
            "status": "success",
            "total_count": len(documents_list),
            "documents": documents_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 조회 중 오류가 발생했습니다: {str(e)}")


@app.delete("/documents/{doc_type}/{doc_id}")
async def delete_document(doc_type: str, doc_id: str):
    """
    지정된 벡터 DB(rule 또는 reference)에서 특정 문서(doc_id)를 삭제합니다.
    오래된 규정이나 잘못 업로드된 지식을 정리할 때 사용합니다.
    """
    if doc_type not in ["rule", "reference"]:
        raise HTTPException(status_code=400, detail="doc_type은 'rule' 또는 'reference'여야 합니다.")

    try:
        # 1. DB 라우팅
        target_db = rule_db if doc_type == "rule" else reference_db
        
        # 2. 문서 존재 여부 확인 및 삭제
        # ChromaDB는 없는 ID를 삭제하려 해도 에러를 뱉지 않으므로 바로 delete 호출
        target_db.delete(ids=[doc_id])
        
        return {
            "status": "success",
            "message": f"{doc_type} DB에서 문서({doc_id})가 성공적으로 삭제되었습니다."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 삭제 중 오류가 발생했습니다: {str(e)}")


@app.post("/upload-statistics")
async def upload_statistics(file: UploadFile = File(...)):
    """
    [A열: 적용년도, B열: 모집구분, C열: 학과, D열: 전형명, E열: 모집정원] 형태의 
    엑셀 파일을 읽어 MS-SQL 정형 DB(AdmissionStats 테이블)에 저장합니다.
    """
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx, .xls)만 업로드 가능합니다.")
        
    try:
        content = await file.read()
        # data_only=True로 수식 대신 결과값 추출
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheet = wb.active
        
        conn = get_mssql_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="MS-SQL 서버에 연결할 수 없습니다. IP 및 계정 설정을 확인하세요.")
            
        cursor = conn.cursor()
        
        inserted_count = 0
        # 첫 번째 행(1)은 헤더이므로 두 번째 행(2)부터 읽음
        for row in sheet.iter_rows(min_row=2, values_only=True):
            # A열(적용년도)이 없으면 데이터의 끝으로 간주하고 중단
            if not row[0]: 
                continue
                
            apply_year = str(row[0]).strip()
            admission_term = str(row[1]).strip() if row[1] else ""
            department = str(row[2]).strip() if row[2] else ""
            admission_type = str(row[3]).strip() if row[3] else ""
            quota = int(row[4]) if row[4] else 0
            
            # DB 삽입
            cursor.execute("""
                INSERT INTO AdmissionStats (apply_year, admission_term, department, admission_type, quota)
                VALUES (?, ?, ?, ?, ?)
            """, (apply_year, admission_term, department, admission_type, quota))
            inserted_count += 1
            
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "status": "success", 
            "message": f"총 {inserted_count}건의 모집정원 데이터가 MS-SQL에 성공적으로 저장되었습니다."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"엑셀 데이터 업로드 중 오류 발생: {str(e)}")


@app.post("/chat")
async def chat_with_ai(
    request: ChatRequest,
    x_gemini_key: str = Header(None)
):
    """
    사용자의 질문에 대해 Rule DB의 지식을 검색하고, Gemini를 통해 답변을 생성합니다.
    디버깅 로그 출력, 엄격한 프롬프트 규칙 및 동적 모델 선택이 적용됩니다.
    """
    if not x_gemini_key:
        raise HTTPException(status_code=401, detail="Gemini API Key가 필요합니다. (Header: x-gemini-key)")

    try:
        # 1. Rule DB에서 관련 지식 검색 (Top 3)
        results = rule_db.query(
            query_texts=[request.question],
            n_results=3
        )
        
        # 검색된 문서들을 하나의 컨텍스트로 결합
        context = ""
        if results and results.get("documents"):
            context = "\n\n".join(results["documents"][0])

        # [디버깅 로그 추가] 서버 관리자가 참조 텍스트를 확인할 수 있도록 터미널에 출력
        print(f"=== [디버그] AI가 참조할 텍스트 ===\n{context}\n===========================")

        if not context.strip():
            return {
                "status": "success",
                "answer": "현재 등록된 규정 데이터가 없어 답변을 드릴 수 없습니다. 먼저 지식 문서를 업로드해 주세요.",
                "references": []
            }

        # 2. Gemini 설정 및 답변 생성
        genai.configure(api_key=x_gemini_key)
        # 프론트엔드에서 요청한 모델명(또는 기본값)으로 초기화
        model = genai.GenerativeModel(request.model_name)
        
        # [프롬프트 고도화] 더 엄격한 답변 규칙 적용
        prompt = f"""
    너는 대동대학교 입시처의 전문 AI 상담원이야.
    [규칙 1] 반드시 아래 제공된 [참조 문서]의 내용만 바탕으로 답변해.
    [규칙 2] 제공된 문서에 질문과 관련된 단어나 숫자가 아예 없다면, 절대 지어내지 말고 "제공된 문서에서는 해당 내용을 찾을 수 없습니다."라고만 답변해.
    [규칙 3] 표(Table)가 텍스트로 변환되면서 행과 열이 섞여 있을 수 있어. 학과명과 숫자를 매칭할 때 문맥을 극도로 주의해서 읽어.

    [참조 문서]
    {context}

    [사용자 질문]
    {request.question}
    """
        
        # [타임아웃 및 재시도(Retry) 로직]
        max_retries = 2
        response = None
        
        for attempt in range(max_retries + 1):
            try:
                # 타임아웃 15초 설정 및 답변 생성
                response = model.generate_content(
                    prompt,
                    request_options={"timeout": 15}
                )
                break  # 성공 시 루프 탈출
            except Exception as ai_err:
                print(f"Gemini API 호출 시도 {attempt + 1} 실패: {ai_err}")
                if attempt == max_retries:
                    raise HTTPException(status_code=500, detail="AI API 통신 지연 또는 오류가 반복적으로 발생했습니다.")
        
        return {
            "status": "success",
            "answer": response.text,
            "references": results.get("metadatas")[0] if results.get("metadatas") else []
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 답변 생성 중 오류가 발생했습니다: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    # 코드 수정 시 자동 재시작(reload=True) 적용. 
    # 실제 배포 시에는 host="0.0.0.0", reload=False 로 구동.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
