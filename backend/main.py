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
def get_system_prompt(user_role: str = "staff"):
    """권한(role)에 따라 AI의 보안 수준과 페르소나를 통제합니다."""
    if user_role == "student":
        return """
        당신은 **대동대학교 입시 홍보처의 친절한 AI 입시 상담원**입니다.
        주 사용자는 우리 대학에 지원하려는 수험생 및 학부모입니다.
        [🚨 엄격한 보안 규칙]
        1. 내부 행정 지침, 예산, 교직원 연락처 등 민감한 정보는 절대 유출하지 마십시오.
        2. 제공된 데이터가 없다면, 지어내지 말고 "해당 정보는 확인이 어렵습니다. 입시처로 문의해주세요."라고 방어하십시오.
        3. [시스템 DB 추출 데이터]가 있다면 반드시 그 수치를 우선적으로 대답하세요.
        """
    else:
        return """
        당신은 **대동대학교 입시처의 핵심 AI 업무 헬퍼(Sub-Assistant)**입니다.
        주 사용자는 교직원입니다.
        [🚨 핵심 보안 및 답변 규칙]
        1. [시스템 DB 추출 데이터]와 [PDF 규정 문서]의 수치가 충돌할 경우, 무조건 [시스템 DB 추출 데이터]가 최신 정답입니다.
        2. DB에서 수치를 가져왔다면 반드시 "최신 시스템 DB 확인 결과..." 라고 명시하십시오.
        3. 절대 추측하지 마십시오. 데이터가 없으면 없다고 하세요.
        """


class ChatRequest(BaseModel):
    question: str
    model_name: str = "gemini-2.5-flash"
    user_role: str = "staff" # 권한: "staff"(교직원) 또는 "student"(일반학생)

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


def get_dynamic_db_schema(conn, user_role="staff"):
    """
    [데이터 카탈로그 기반 스키마 추출] 
    사용자의 권한(user_role)을 확인하여, 학생일 경우 is_public='Y'인 컬럼만 추출하고, 
    AI 이해를 돕기 위한 ai_description 힌트를 덧붙여 반환합니다.
    """
    if not conn: return "DB 연결 실패"
    try:
        cursor = conn.cursor()
        query = "SELECT table_name, column_name, ai_description FROM Sys_ColumnCatalog"
        if user_role == "student":
            query += " WHERE is_public = 'Y'" # 보안: 학생은 비공개 컬럼의 존재 자체를 모르게 차단
            
        cursor.execute(query)
        schema_dict = {}
        for row in cursor.fetchall():
            t_name, c_name, ai_desc = row
            if t_name not in schema_dict:
                schema_dict[t_name] = []
            
            # AI를 위한 힌트 조합 (예: [학번](설명: 학생 고유 식별번호))
            col_str = f"[{c_name}]"
            if ai_desc: col_str += f"(설명:{ai_desc})"
            schema_dict[t_name].append(col_str)
            
        schema_str = "[현재 AI가 접근 가능한 MS-SQL 테이블 구조]\n"
        for t_name, cols in schema_dict.items():
            schema_str += f"- Table: [{t_name}] | Columns: {', '.join(cols)}\n"
            try:
                # 샘플 조회를 위해 (설명:~) 부분 제거
                clean_cols = [c.split('(')[0] for c in cols]
                cursor.execute(f"SELECT TOP 1 {', '.join(clean_cols)} FROM [{t_name}]")
                sample_row = cursor.fetchone()
                if sample_row:
                    clean_col_names = [c.replace('[','').replace(']','') for c in clean_cols]
                    sample_dict = dict(zip(clean_col_names, sample_row))
                    schema_str += f"  * 💡 데이터 샘플 힌트: {sample_dict}\n"
            except Exception:
                pass
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
    title: str = Form(...),
    description: str = Form(None) # [NEW] 문서에 대한 관리자/AI 설명
):
    """
    PDF 등 문서를 업로드 받아 벡터 DB(ChromaDB)에 저장하고, 
    동시에 거버넌스 통제를 위해 MS-SQL 카탈로그에 메타데이터를 기록합니다.
    """
    if doc_type not in ["rule", "reference"]:
        raise HTTPException(status_code=400, detail="doc_type은 'rule' 또는 'reference'여야 합니다.")
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="현재는 PDF 파일만 지원합니다.")

    # 1. PDF 텍스트 및 표 추출
    try:
        content = await file.read()
        extracted_text = ""
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text: extracted_text += page_text + "\n"
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        extracted_text += table_to_markdown(table)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 파싱 오류: {str(e)}")

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="텍스트 추출 불가 (이미지 PDF 등)")

    safe_text = mask_personal_info(extracted_text)
    doc_id = str(uuid.uuid4())
    metadata = {"year": year, "title": title, "doc_type": doc_type, "filename": file.filename}

    # 2. Vector DB (ChromaDB) 저장
    try:
        if doc_type == "rule":
            rule_db.add(documents=[safe_text], metadatas=[metadata], ids=[doc_id])
        else:
            reference_db.add(documents=[safe_text], metadatas=[metadata], ids=[doc_id])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"벡터 DB 저장 오류: {str(e)}")

    # 3. [NEW] 정형 DB (MS-SQL Sys_DocumentCatalog) 메타데이터 기록
    conn = get_mssql_connection()
    if conn:
        try:
            cursor = conn.cursor()
            desc_val = description if description else ""
            cursor.execute("""
                INSERT INTO Sys_DocumentCatalog (doc_id, filename, doc_type, year, title, description, is_public)
                VALUES (?, ?, ?, ?, ?, ?, 'Y')
            """, (doc_id, file.filename, doc_type, year, title, desc_val))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as catalog_err:
            print(f"문서 카탈로그 등록 에러 (ChromaDB엔 저장됨): {catalog_err}")

    return {
        "status": "success",
        "message": f"'{title}' 문서가 DB 및 카탈로그에 성공적으로 저장되었습니다.",
        "doc_id": doc_id,
        "extracted_preview": safe_text[:100] + "..."
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
    """지정된 벡터 DB와 MS-SQL 문서 카탈로그에서 문서를 동기화하여 완벽히 삭제합니다."""
    if doc_type not in ["rule", "reference"]:
        raise HTTPException(status_code=400, detail="doc_type은 'rule' 또는 'reference'여야 합니다.")

    try:
        # 1. Vector DB (ChromaDB) 삭제
        target_db = rule_db if doc_type == "rule" else reference_db
        target_db.delete(ids=[doc_id])
        
        # 2. 정형 DB (MS-SQL Sys_DocumentCatalog) 동기화 삭제
        conn = get_mssql_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM Sys_DocumentCatalog WHERE doc_id = ?", (doc_id,))
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as catalog_err:
                print(f"문서 카탈로그 삭제 에러: {catalog_err}")

        return {
            "status": "success",
            "message": f"{doc_type} DB 및 카탈로그에서 문서({doc_id})가 성공적으로 삭제되었습니다."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 삭제 중 오류 발생: {str(e)}")


@app.post("/upload-dynamic-statistics")
async def upload_dynamic_statistics(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    table_name_kr: str = Form(None) # [NEW] 대시보드 표시용 한글 테이블명
):
    """엑셀 데이터를 올리면서 데이터 카탈로그에 한글 테이블명과 함께 자동 등록합니다."""
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="엑셀 파일만 업로드 가능합니다.")
    if not re.match(r"^[a-zA-Z0-9_]+$", table_name):
        raise HTTPException(status_code=400, detail="테이블 이름 오류")

    try:
        content = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheet = wb.active
        conn = get_mssql_connection()
        if not conn: raise HTTPException(status_code=500, detail="DB 연결 실패")
        cursor = conn.cursor()
        
        headers = [str(cell.value).strip() for cell in sheet[1] if cell.value is not None]
        if not headers: raise HTTPException(status_code=400, detail="헤더 없음")

        # 1. 실제 테이블 DDL 및 카탈로그 등록
        cursor.execute(f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{table_name}'")
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            cols_def = ", ".join([f"[{h}] NVARCHAR(255)" for h in headers])
            cursor.execute(f"CREATE TABLE [{table_name}] (id INT IDENTITY(1,1) PRIMARY KEY, {cols_def}, created_at DATETIME DEFAULT GETDATE())")
            print(f"✅ 테이블 [{table_name}] 생성 완료")
            
        # [NEW] 테이블 카탈로그 등록 (한글명 포함)
        kr_name = table_name_kr if table_name_kr else table_name
        cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM Sys_TableCatalog WHERE table_name = '{table_name}') INSERT INTO Sys_TableCatalog (table_name, table_name_kr, db_source) VALUES ('{table_name}', '{kr_name}', 'INTERNAL')")
        
        # [NEW] 컬럼 카탈로그 등록
        for h in headers:
            cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM Sys_ColumnCatalog WHERE table_name = '{table_name}' AND column_name = '{h}') INSERT INTO Sys_ColumnCatalog (table_name, column_name, is_public) VALUES ('{table_name}', '{h}', 'Y')")

        # 2. 데이터 INSERT
        columns_str = ", ".join([f"[{h}]" for h in headers])
        placeholders = ", ".join(["?"] * len(headers))
        insert_query = f"INSERT INTO [{table_name}] ({columns_str}) VALUES ({placeholders})"
        
        inserted_count = 0
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if all(cell is None or str(cell).strip() == "" for cell in row): continue
            row_data = tuple(row[i] if i < len(row) else None for i in range(len(headers)))
            cursor.execute(insert_query, row_data)
            inserted_count += 1
            
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "message": f"[{table_name}] 테이블에 {inserted_count}건 저장 및 카탈로그 등록 완료."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업로드 중 오류: {str(e)}")


@app.post("/sync-external-table")
async def sync_external_table(
    table_name: str = Form(...), 
    table_name_kr: str = Form(None), 
    description: str = Form(None)
):
    """
    [외부 연동 DB 스마트 동기화]
    실제 뷰(View)의 삭제/컬럼 변경을 감지하여 메타데이터 카탈로그를 자동 동기화합니다.
    - 뷰가 삭제되었으면 카탈로그에서 자동 제거
    - 신규 컬럼은 '비공개(N)'로 추가, 삭제된 컬럼은 제거
    """
    if not re.match(r"^[a-zA-Z0-9_]+$", table_name):
        raise HTTPException(status_code=400, detail="테이블 이름 오류")

    conn = get_mssql_connection()
    if not conn: raise HTTPException(status_code=500, detail="MS-SQL 연결 실패")

    try:
        cursor = conn.cursor()
        
        # 1. 실제 테이블/뷰 존재 여부 확인
        cursor.execute(f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{table_name}'")
        exists = cursor.fetchone()[0] > 0
        
        # 2. 뷰가 삭제되었으면 카탈로그 장부에서도 모두 영구 제거 (동기화)
        if not exists:
            cursor.execute(f"DELETE FROM Sys_ColumnCatalog WHERE table_name = '{table_name}'")
            cursor.execute(f"DELETE FROM Sys_TableCatalog WHERE table_name = '{table_name}'")
            conn.commit()
            cursor.close()
            conn.close()
            return {"status": "success", "message": f"'{table_name}' 뷰가 원본에서 삭제되어 카탈로그에서도 영구 제거되었습니다."}

        # 3. 뷰가 존재하면 테이블 카탈로그 등록/업데이트
        kr_name = table_name_kr if table_name_kr else table_name
        desc_val = description if description else ""
        
        cursor.execute(f"SELECT COUNT(*) FROM Sys_TableCatalog WHERE table_name = '{table_name}'")
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"INSERT INTO Sys_TableCatalog (table_name, table_name_kr, db_source, description) VALUES ('{table_name}', '{kr_name}', 'EXTERNAL', '{desc_val}')")
        
        # 4. 컬럼 스마트 동기화 (신규 추가 및 삭제 반영)
        cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table_name}'")
        actual_cols = [row[0] for row in cursor.fetchall()]
        
        if actual_cols:
            # (A) 원본 뷰에서 삭제된 컬럼 장부에서 제거
            cols_format = ", ".join([f"'{c}'" for c in actual_cols])
            cursor.execute(f"DELETE FROM Sys_ColumnCatalog WHERE table_name = '{table_name}' AND column_name NOT IN ({cols_format})")
            
            # (B) 신규 컬럼 장부에 추가 (기본 비공개 'N')
            added_count = 0
            for c_name in actual_cols:
                cursor.execute(f"SELECT COUNT(*) FROM Sys_ColumnCatalog WHERE table_name = '{table_name}' AND column_name = '{c_name}'")
                if cursor.fetchone()[0] == 0:
                    cursor.execute(f"INSERT INTO Sys_ColumnCatalog (table_name, column_name, is_public) VALUES ('{table_name}', '{c_name}', 'N')")
                    added_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "success", 
            "message": f"'{table_name}' 뷰 동기화 완료. (신규 발견 컬럼: {added_count}개 안전 등록)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"동기화 중 오류 발생: {str(e)}")


@app.post("/chat")
async def chat_with_ai(request: ChatRequest, x_gemini_key: str = Header(None)):
    if not x_gemini_key:
        raise HTTPException(status_code=401, detail="Gemini API Key가 필요합니다.")

    try:
        genai.configure(api_key=x_gemini_key)
        
        # 1. MS-SQL 실시간 구조 파악 (데이터 사전 자동 생성)
        conn = get_mssql_connection()
        dynamic_schema = get_dynamic_db_schema(conn, request.user_role) if conn else "DB 연결 불가"
        
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
        final_model = genai.GenerativeModel(model_name=request.model_name, system_instruction=get_system_prompt(request.user_role))
        
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
