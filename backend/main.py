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
1. **출처 및 우선순위 절대 규칙 (0순위):** - [시스템 DB 추출 데이터]와 [PDF 규정 문서]의 수치/내용이 충돌할 경우, **무조건 [시스템 DB 추출 데이터]가 최신 정답**입니다. PDF 숫자는 과거 자료이므로 완전히 무시하십시오.
   - DB에서 수치를 가져왔다면 답변에 반드시 "최신 시스템 DB 확인 결과..." 라고 명시하십시오.

2. **단계적 처리 프로세스:**
   - **1단계(확인):** "해당 업무는 A 절차에 해당합니다."와 같이 분류하세요.
   - **2단계(세부사항):** "관련 규정/데이터는 다음과 같습니다."라며 팩트를 나열하세요.

3. **허용 불가 행동(Don'ts):**
   - 절대 추측하지 마십시오. 데이터가 없으면 없다고 하세요.
   - 법적 구속력이 있는 해석을 단정적으로 내리지 마세요.
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
    IM002 에러 방지를 위해 OS에 설치된 ODBC 드라이버를 자동 검색하여 연결합니다.
    """
    try:
        # 1. 시스템에 설치된 SQL Server 관련 드라이버 검색
        available_drivers = [d for d in pyodbc.drivers() if 'SQL Server' in d]
        
        if not available_drivers:
            print("❌ 오류: 시스템에 설치된 SQL Server ODBC 드라이버가 없습니다.")
            return None
            
        # 2. 드라이버 우선순위 선택 (17 -> 18 -> 11 -> 기본 SQL Server)
        driver_name = available_drivers[0] # 기본값으로 첫 번째 발견된 드라이버 사용
        preferred_drivers = ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
        
        for pref in preferred_drivers:
            if pref in available_drivers:
                driver_name = pref
                break
                
        print(f"✅ 선택된 MS-SQL 드라이버: {driver_name}")

        # 3. 동적 드라이버 연결 문자열 구성 (ODBC 18 SSL 검증 에러 우회)
        conn_str = (
            f"DRIVER={{{driver_name}}};"
            "SERVER=10.10.1.11,1433;"
            "DATABASE=DDU_ADMISSION;"
            "UID=admission_ai;"
            "PWD=fjk12#$;"
            "TrustServerCertificate=yes;"
        )
        
        conn = pyodbc.connect(conn_str, autocommit=True)
        # cp949 인코딩으로 한글 깨짐 방지
        conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp949')
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding='cp949')
        conn.setencoding(encoding='cp949')
        return conn
        
    except Exception as e:
        print(f"MS-SQL 연결 에러 발생: {e}")
        return None


def get_dynamic_db_schema(conn):
    """
    MS-SQL의 INFORMATION_SCHEMA와 함께 '실제 샘플 데이터 1건'을 조회하여 반환합니다.
    (AI가 각 컬럼에 어떤 종류의 값이 들어가는지 완벽히 파악하도록 돕는 핵심 역할)
    """
    if not conn:
        return "DB 연결 실패"
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = 'dbo'
        """)
        schema_dict = {}
        for row in cursor.fetchall():
            t_name, c_name = row
            if t_name not in schema_dict:
                schema_dict[t_name] = []
            schema_dict[t_name].append(c_name)
            
        schema_str = "[현재 MS-SQL 실시간 테이블 및 컬럼 구조 (데이터 샘플 포함)]\n"
        for t_name, cols in schema_dict.items():
            cols_bracket = [f"[{c}]" for c in cols]
            schema_str += f"- Table: [{t_name}] | Columns: {', '.join(cols_bracket)}\n"
            
            # [신규 로직] AI의 문맥 이해를 돕기 위해 데이터 샘플 1건 추출
            try:
                safe_cols = ", ".join(cols_bracket)
                cursor.execute(f"SELECT TOP 1 {safe_cols} FROM [{t_name}]")
                sample_row = cursor.fetchone()
                if sample_row:
                    sample_dict = dict(zip(cols, sample_row))
                    schema_str += f"  * 💡 데이터 샘플 힌트: {sample_dict}\n"
            except Exception as sample_err:
                pass # 샘플 추출에 실패해도 메인 스키마 로딩은 계속 진행
                
        return schema_str
    except Exception as e:
        print(f"스키마 추출 에러: {e}")
        return "스키마 추출 오류"


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


@app.post("/upload-dynamic-statistics")
async def upload_dynamic_statistics(
    file: UploadFile = File(...),
    table_name: str = Form(...) # 프론트엔드에서 테이블명(영문 권장)을 입력받음
):
    """
    [지능형 범용 엑셀 업로더] 
    엑셀의 첫 행(한글/영문 헤더)을 읽어, MS-SQL에 테이블이 없으면 
    즉석에서 생성(CREATE)하고 데이터를 동적으로 매핑하여 INSERT 합니다.
    """
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="엑셀 파일만 업로드 가능합니다.")
        
    if not re.match(r"^[a-zA-Z0-9_]+$", table_name):
        raise HTTPException(status_code=400, detail="테이블 이름은 영문, 숫자, 언더바(_)만 허용됩니다.")

    try:
        content = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheet = wb.active
        
        conn = get_mssql_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="MS-SQL 서버 연결 실패")
            
        cursor = conn.cursor()
        
        # 1. 엑셀 1행에서 헤더 추출
        headers = [str(cell.value).strip() for cell in sheet[1] if cell.value is not None]
        if not headers:
            raise HTTPException(status_code=400, detail="엑셀 파일에 헤더(컬럼명)가 없습니다.")

        # 2. 테이블 존재 여부 확인 및 자동 생성 (Auto DDL)
        cursor.execute(f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{table_name}'")
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            # 대괄호 []를 사용하여 한글 컬럼명 안전하게 생성
            cols_def = ", ".join([f"[{h}] NVARCHAR(255)" for h in headers])
            create_query = f"CREATE TABLE [{table_name}] (id INT IDENTITY(1,1) PRIMARY KEY, {cols_def}, created_at DATETIME DEFAULT GETDATE())"
            cursor.execute(create_query)
            conn.commit()
            print(f"✅ 신규 테이블 [{table_name}] 자동 생성 완료")

        # 3. 데이터 INSERT 쿼리 조립
        columns_str = ", ".join([f"[{h}]" for h in headers])
        placeholders = ", ".join(["?"] * len(headers))
        insert_query = f"INSERT INTO [{table_name}] ({columns_str}) VALUES ({placeholders})"
        
        inserted_count = 0
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            row_data = tuple(row[i] if i < len(row) else None for i in range(len(headers)))
            cursor.execute(insert_query, row_data)
            inserted_count += 1
            
        conn.commit()
        cursor.close()
        conn.close()
        
        msg = f"[{table_name}] 테이블에 {inserted_count}건 저장 완료."
        if not table_exists:
            msg += " (신규 테이블 자동생성됨)"
        return {"status": "success", "message": msg}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 중 오류 발생: {str(e)}")


@app.post("/chat")
async def chat_with_ai(request: ChatRequest, x_gemini_key: str = Header(None)):
    if not x_gemini_key:
        raise HTTPException(status_code=401, detail="Gemini API Key가 필요합니다.")

    try:
        genai.configure(api_key=x_gemini_key)
        
        # 1. MS-SQL 실시간 구조 파악 (데이터 사전 자동 생성)
        conn = get_mssql_connection()
        dynamic_schema = get_dynamic_db_schema(conn) if conn else "DB 연결 불가"
        
        # =======================================================
        # [Step 1] NL2SQL: 사용자 질문 -> T-SQL 생성
        # =======================================================
        sql_router_prompt = f"""
        너는 대동대학교 입시처의 DB 아키텍트야. 
        사용자의 [질문]에 답변하기 위해 정형 데이터(숫자/통계) 조회가 필요하다면, 
        아래 [현재 MS-SQL 테이블 구조]를 보고 MS SQL Server용 T-SQL SELECT 쿼리를 작성해.

        [가장 중요한 SQL 작성 규칙]
        1. 컬럼명이 한글일 수 있으므로 대괄호 []를 반드시 사용해.
        2. 문자열 조건은 무조건 `=` 대신 `LIKE`를 사용하되, **사용자의 단어에서 핵심 형태소만 아주 짧게 잘라서 검색해!**
           - (예시) "대학교 전형" -> `LIKE '%대학%'`
           - (예시) "일반고 전형" -> `LIKE '%일반고%'`
        3. **[핵심] 최종 AI가 어떤 데이터인지 정확히 문맥을 파악할 수 있도록, 특정 컬럼 하나만 조회하지 말고 무조건 `SELECT * FROM [테이블명]` 형태로 모든 컬럼을 추출해!**
           - (나쁜 예: SELECT [모집정원] FROM ...)
           - (좋은 예: SELECT * FROM ...)
        4. 정형 데이터 조회가 전혀 필요 없는 질문이면 오직 "NONE" 이라고만 출력해.
        5. 마크다운 기호(```sql)나 설명은 절대 쓰지 마. 오직 SELECT 쿼리문만 출력해.

        {dynamic_schema}

        [질문]
        {request.question}
        """
        # SQL 생성용은 빠르고 논리적인 모델 사용
        sql_model = genai.GenerativeModel("gemini-2.5-flash")
        sql_response = sql_model.generate_content(sql_router_prompt)
        sql_query = sql_response.text.strip().replace("```sql", "").replace("```", "").strip()
        
        print(f"=== [NL2SQL 자동 생성 쿼리] ===\n{sql_query}\n===========================")

        # =======================================================
        # [Step 2] 생성된 쿼리 실행
        # =======================================================
        sql_context = ""
        if sql_query.upper().startswith("SELECT") and conn:
            try:
                cursor = conn.cursor()
                cursor.execute(sql_query)
                rows = cursor.fetchall()
                if rows:
                    columns = [column[0] for column in cursor.description]
                    for row in rows:
                        row_dict = dict(zip(columns, row))
                        sql_context += f"- 시스템 DB 추출 데이터: {row_dict}\n"
                
                # [디버그 추가] MS-SQL에서 실제 가져온 데이터 확인용
                print(f"=== [SQL 실제 실행 결과] ===\n{sql_context if sql_context else '데이터 없음 (0건 검색됨)'}\n===========================")
                
            except Exception as db_err:
                print(f"SQL 실행 오류: {db_err}")
            finally:
                conn.close()
        elif conn:
            conn.close()

        # =======================================================
        # [Step 3] 비정형 DB (ChromaDB) 검색
        # =======================================================
        results = rule_db.query(query_texts=[request.question], n_results=3)
        chroma_context = "\n\n".join(results["documents"][0]) if results.get("documents") else ""

        # =======================================================
        # [Step 4] 최종 하이브리드 답변 생성
        # =======================================================
        final_model = genai.GenerativeModel(model_name=request.model_name, system_instruction=get_system_prompt())
        
        prompt = f"""
        너는 대동대학교 입시처 전문 AI 상담원이야.

        [🚨 0순위 절대 규칙 🚨]
        1. 아래 [시스템 DB 데이터]와 [PDF 규정 문서]의 수치(정원, 인원, 금액 등)가 서로 다를 경우, 무조건!!! [시스템 DB 데이터]의 수치가 100% 정답이야. 
        2. PDF의 수치는 변경되기 전의 '과거 자료'이므로 절대 답변에 사용하지 마.
        3. 답변할 때 반드시 "최신 시스템 DB 확인 결과, 변경된 모집정원은 OO명입니다." 라는 식으로 강조해서 답변해.

        [시스템 DB 데이터 (최신 팩트 - 무조건 이 숫자를 사용할 것)]
        {sql_context if sql_context else "관련 DB 데이터 없음"}

        [PDF 규정 문서 (참고용 - DB와 숫자가 다르면 이 문서의 숫자는 무시할 것)]
        {chroma_context}

        [사용자 질문]
        {request.question}
        """
        
        response = final_model.generate_content(prompt, request_options={"timeout": 15})
        return {
            "status": "success",
            "answer": response.text,
            "references": results.get("metadatas")[0] if results.get("metadatas") else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 답변 생성 중 오류 발생: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    # 코드 수정 시 자동 재시작(reload=True) 적용. 
    # 실제 배포 시에는 host="0.0.0.0", reload=False 로 구동.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
