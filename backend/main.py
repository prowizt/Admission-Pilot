# ==========================================
# 메인 서버 및 API 엔드포인트
# ==========================================
import os
import re
import io
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
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

# [CORS 설정] 크롬 사이드 패널 및 로컬 React 웹에서의 API 접근을 허용합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


from typing import List, Optional

class ChatRequest(BaseModel):
    question: str
    scraped_context: Optional[str] = "" # [NEW] 스크랩된 현재 화면 텍스트
    model_name: str = "gemini-2.5-flash"
    user_role: str = "staff" # 권한: "staff"(교직원) 또는 "student"(일반학생)

class ColumnUpdateItem(BaseModel):
    id: int
    ai_description: Optional[str] = "" # None 대신 빈 문자열 기본값 처리
    is_public: str

class ColumnUpdatePayload(BaseModel):
    columns: List[ColumnUpdateItem]

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
    Sys_TableCatalog, Sys_ColumnCatalog 및 Sys_DocumentCatalog를 모두 조회하여
    AI에게 데이터베이스와 비정형 문서 보유 현황을 통합 제공합니다.
    """
    if not conn: return "DB 연결 실패"
    try:
        cursor = conn.cursor()
        
        # 1. 정형 데이터 (테이블 & 컬럼 카탈로그)
        query = """
            SELECT c.table_name, t.description, c.column_name, c.ai_description 
            FROM Sys_ColumnCatalog c
            LEFT JOIN Sys_TableCatalog t ON c.table_name = t.table_name
        """
        if user_role == "student":
            query += " WHERE c.is_public = 'Y'"
            
        cursor.execute(query)
        schema_dict = {}
        table_desc_dict = {}
        for row in cursor.fetchall():
            t_name, t_desc, c_name, ai_desc = row
            if t_name not in schema_dict:
                schema_dict[t_name] = []
                table_desc_dict[t_name] = t_desc
            
            # AI를 위한 힌트 조합
            col_str = f"[{c_name}]"
            if ai_desc: col_str += f"(설명:{ai_desc})"
            schema_dict[t_name].append(col_str)
            
        schema_str = "[현재 AI가 접근 가능한 MS-SQL 테이블 구조]\n"
        for t_name, cols in schema_dict.items():
            t_desc = table_desc_dict.get(t_name)
            t_desc_str = f" (테이블 용도: {t_desc})" if t_desc else ""
            schema_str += f"- Table: [{t_name}]{t_desc_str} | Columns: {', '.join(cols)}\n"
            
        # 2. 비정형 데이터 (문서 카탈로그)
        doc_query = "SELECT doc_type, year, title, description FROM Sys_DocumentCatalog"
        if user_role == "student":
            doc_query += " WHERE is_public = 'Y'"
            
        cursor.execute(doc_query)
        docs = cursor.fetchall()
        if docs:
            schema_str += "\n[현재 AI가 접근 가능한 비정형 문서 목록 (ChromaDB에 저장됨)]\n"
            for doc in docs:
                d_type, d_year, d_title, d_desc = doc
                year_str = f"{d_year}학년도 " if d_year else ""
                desc_str = f" (문서 설명: {d_desc})" if d_desc else ""
                schema_str += f"- [{d_type}] {year_str}{d_title}{desc_str}\n"
                
        return schema_str
    except Exception as e:
        print(f"카탈로그 추출 에러: {e}")
        return "카탈로그 추출 오류"


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
    is_public: str = Form("Y"), # [NEW] 프론트엔드에서 보안 권한 수신
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
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, file.filename, doc_type, year, title, desc_val, is_public))
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


@app.get("/documents/{doc_type}/{doc_id}")
async def get_document_content(doc_type: str, doc_id: str):
    """관리자가 추출된 문서 본문을 미리보기 할 때 사용합니다."""
    if doc_type not in ["rule", "reference"]:
        raise HTTPException(status_code=400, detail="Invalid doc_type")
    
    target_db = rule_db if doc_type == "rule" else reference_db
    result = target_db.get(ids=[doc_id])
    
    if not result or not result.get("documents") or len(result["documents"]) == 0:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        
    return {"status": "success", "content": result["documents"][0]}


@app.put("/documents/{doc_id}")
async def update_document(
    doc_id: str,
    doc_type: str = Form(...),
    year: str = Form(...),
    title: str = Form(...),
    is_public: str = Form("Y"),
    description: str = Form(None)
):
    """비정형 문서 메타데이터 수정 (MS-SQL 및 ChromaDB 동기화)"""
    # 1. MS-SQL 업데이트
    conn = get_mssql_connection()
    if conn:
        try:
            cursor = conn.cursor()
            desc_val = description if description else ""
            cursor.execute("""
                UPDATE Sys_DocumentCatalog 
                SET year=?, title=?, description=?, is_public=? 
                WHERE doc_id=?
            """, (year, title, desc_val, is_public, doc_id))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"카탈로그 수정 에러: {e}")

    # 2. ChromaDB 메타데이터 업데이트
    target_db = rule_db if doc_type == "rule" else reference_db
    try:
        res = target_db.get(ids=[doc_id])
        if res and res.get("metadatas") and len(res["metadatas"]) > 0:
            meta = res["metadatas"][0]
            meta["year"] = year
            meta["title"] = title
            target_db.update(ids=[doc_id], metadatas=[meta])
    except Exception as e:
        print(f"ChromaDB 메타데이터 수정 에러: {e}")

    return {"status": "success", "message": "문서 정보가 성공적으로 수정되었습니다."}


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


@app.get("/available-views")
async def get_available_views():
    """MS-SQL에 존재하는 뷰(View) 중, 아직 연동되지 않은 목록만 조회합니다."""
    conn = get_mssql_connection()
    if not conn: raise HTTPException(status_code=500, detail="MS-SQL 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME NOT IN (SELECT table_name FROM Sys_TableCatalog)")
        views = [row[0] for row in cursor.fetchall()]
        return {"status": "success", "data": views}
    finally:
        cursor.close()
        conn.close()

@app.post("/upload-dynamic-statistics")
async def upload_dynamic_statistics(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    table_name_kr: str = Form(None),
    description: str = Form(None) # [NEW] 테이블 설명 추가
):
    """엑셀 데이터를 올리면서 데이터 카탈로그에 자동 등록합니다."""
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
            
        # [NEW] 테이블 카탈로그 등록 (한글명 및 설명 포함)
        kr_name = table_name_kr if table_name_kr else table_name
        desc_val = description if description else ""
        cursor.execute(f"IF NOT EXISTS (SELECT 1 FROM Sys_TableCatalog WHERE table_name = '{table_name}') INSERT INTO Sys_TableCatalog (table_name, table_name_kr, db_source, description) VALUES ('{table_name}', '{kr_name}', 'INTERNAL', '{desc_val}')")
        
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
        else:
            cursor.execute(f"UPDATE Sys_TableCatalog SET table_name_kr='{kr_name}', description='{desc_val}' WHERE table_name='{table_name}'")
        
        # 4. 컬럼 스마트 동기화 (신규 추가 및 삭제 반영)
        cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table_name}'")
        actual_cols = [row[0] for row in cursor.fetchall()]
        
        added_count = 0
        deleted_count = 0

        if actual_cols:
            # (A) 원본 뷰에서 삭제된 컬럼 장부에서 제거 및 카운트
            cols_format = ", ".join([f"'{c}'" for c in actual_cols])
            cursor.execute(f"SELECT COUNT(*) FROM Sys_ColumnCatalog WHERE table_name = '{table_name}' AND column_name NOT IN ({cols_format})")
            deleted_count = cursor.fetchone()[0]
            cursor.execute(f"DELETE FROM Sys_ColumnCatalog WHERE table_name = '{table_name}' AND column_name NOT IN ({cols_format})")
            
            # (B) 신규 컬럼 장부에 추가 (기본 비공개 'N')
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
            "message": f"'{table_name}' 뷰 동기화 완료\n(신규 추가: {added_count}개 / 삭제: {deleted_count}개)"
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
        # 스크랩된 내용이 있다면 질문과 앞부분 키워드를 조합하여 관련된 DB 통계를 찾을 수 있도록 유도
        sql_search_text = request.question
        if request.scraped_context:
            sql_search_text += " " + request.scraped_context[:300]

        import json
        
        sql_router_prompt = f"""
        너는 대동대학교 입시처의 수석 데이터 아키텍트야. 
        사용자의 [질문]에 답변하기 위해 아래의 [현재 데이터베이스 및 문서 카탈로그 현황]을 분석하고, 
        어떻게 데이터를 조회해야 할지 판단해 줘.

        [사전 지식 주입]
        1. [입시 학년도 정의]: 대학교 입시에서 'N학년도 전형(모집요강)'은 'N-1년도'에 모집을 실시하는 전형을 뜻합니다. (예: 2027학년도 모집요강 = 2026년 가을/겨울에 모집 실시). 사용자가 질문한 연도가 '실시 연도'인지 '입학 학년도'인지 문맥을 파악하여 SQL과 문서 검색 타겟을 정확히 일치시키세요.
        2. [일반 학년도 정의]: 학년도(예: 2026학년도)는 3월 1일부터 다음 해 2월 말일까지를 의미합니다. (예: 2026학년도 = 2026.03 ~ 2027.02).
        
        [가장 중요한 SQL 작성 규칙]
        1. 컬럼명이 한글일 수 있으므로 대괄호 []를 반드시 사용해.
        2. 문자열 조건은 무조건 `=` 대신 `LIKE`를 사용하되, 사용자의 단어에서 핵심 형태소만 짧게 잘라서 검색해! (예: "일반고" -> LIKE '%일반고%')
        3. 통계나 숫자를 물어보면 무조건 `COUNT()`, `SUM()` 같은 집계 함수를 사용해!
        4. 목록을 물어볼 때는 데이터 폭발 방지를 위해 `SELECT TOP 30 * FROM ...` 처럼 TOP 제한을 걸어!
        5. **[학년도 강제]** 질문에 특정 연도/학년도가 포함되어 있다면 반드시 `WHERE [입시학년도] = '2026'` 과 같이 학년도 조건을 추가해!

        {dynamic_schema}

        [질문]
        {sql_search_text}
        
        [출력 지침]
        너는 무조건 아래의 JSON 형식으로만 대답해야 해. 마크다운 기호(```json)나 다른 설명은 일절 쓰지 마.
        {{
            "sql_query": "정형 데이터 조회가 필요하면 T-SQL SELECT 문을, 필요 없으면 'NONE'을 입력",
            "need_rag": true 혹은 false (비정형 문서 목록에서 찾아봐야 할 정보가 있다면 true),
            "rag_search_query": "need_rag가 true일 경우, 문서를 검색할 핵심 키워드 문장 (예: '간호학부 모집인원')",
            "rag_year_filter": "특정 학년도(예: '2028')의 문서만 찾아야 할 경우 해당 4자리 숫자만 입력, 특정 학년도에 국한되지 않거나 모르면 'ALL' 입력"
        }}
        """
        # SQL 생성용은 빠르고 논리적인 모델 사용
        sql_model = genai.GenerativeModel("gemini-2.5-flash")
        sql_response = sql_model.generate_content(sql_router_prompt)
        
        # JSON 파싱
        try:
            response_text = sql_response.text.strip()
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()
                
            parsed_json = json.loads(response_text)
            sql_query = parsed_json.get("sql_query", "NONE")
            need_rag = parsed_json.get("need_rag", False)
            rag_query = parsed_json.get("rag_search_query", request.question)
            rag_year_filter = parsed_json.get("rag_year_filter", "ALL")
        except Exception as json_err:
            print(f"JSON 파싱 오류: {json_err} / 원본: {sql_response.text}")
            sql_query = "NONE"
            need_rag = True
            rag_query = request.question
            rag_year_filter = "ALL"
        
        print(f"=== [AI 라우팅 결과] ===\nSQL 쿼리: {sql_query}\n문서 검색 필요 여부(RAG): {need_rag}\nRAG 쿼리: {rag_query}\n메타데이터 필터(Year): {rag_year_filter}\n===========================")

        # =======================================================
        # [Step 2] 생성된 쿼리 실행
        # =======================================================
        sql_context = ""
        if sql_query.upper().startswith("SELECT") and conn:
            try:
                # [최적화] AI가 추출된 데이터의 출처와 필터링 조건을 확신할 수 있도록 사용된 쿼리 원문을 증거로 덧붙입니다.
                sql_context += f"[시스템이 데이터를 추출할 때 사용한 조건(쿼리)]: {sql_query}\n"
                
                cursor = conn.cursor()
                cursor.execute(sql_query)
                
                # [개선] 다중 결과셋(Multiple Result Sets)을 순회하며 모든 결과를 sql_context에 누적
                result_idx = 1
                while True:
                    if cursor.description:
                        rows = cursor.fetchall()
                        if rows:
                            columns = [column[0] for column in cursor.description]
                            for idx, row in enumerate(rows):
                                # [보안/안정성] 최대 50건까지만 컨텍스트에 포함시켜 토큰 폭발(429 에러) 완벽 차단
                                if idx >= 50:
                                    sql_context += f"- ... (데이터가 너무 많아 상위 50건만 AI에게 전달됩니다. 총 {len(rows)}건 검색됨)\n"
                                    break
                                row_dict = dict(zip(columns, row))
                                sql_context += f"- 시스템 DB 추출 데이터: {row_dict}\n"
                    
                    try:
                        # 다음 결과셋(두 번째 SELECT 쿼리 등의 결과)이 있는지 확인
                        more_results = cursor.nextset()
                    except Exception as nextset_err:
                        print(f"nextset() 호출 중 오류 또는 미지원: {nextset_err}")
                        break
                        
                    if not more_results:
                        break
                    result_idx += 1
                
                # [디버그 추가] MS-SQL에서 실제 가져온 데이터 확인용
                print(f"=== [SQL 실제 실행 결과] ===\n{sql_context if sql_context else '데이터 없음 (0건 검색됨)'}\n===========================")
                
            except Exception as db_err:
                print(f"SQL 실행 오류: {db_err}")
            finally:
                conn.close()
        elif conn:
            conn.close()

        # =======================================================
        # [Step 3] 비정형 DB (ChromaDB) 검색 (Rule + Ref 모두 탐색)
        # =======================================================
        chroma_context = ""
        results_metadatas = []

        # [AI 기반 스마트 라우팅 적용]
        # 스크랩 문서가 없고, AI가 카탈로그를 분석한 결과 문서 검색(RAG)이 불필요하다고 판단했다면 생략합니다.
        if not request.scraped_context and not need_rag:
            print("=== [스마트 라우팅] AI 판단 결과, 비정형 문서(RAG) 검색이 불필요하여 생략합니다 ===")
        else:
            # 스크랩 문맥이 있을 경우 앞부분의 문서 제목/내용 힌트(500자)를 쿼리에 덧붙입니다.
            chroma_query = rag_query
            if request.scraped_context:
                chroma_query += " " + request.scraped_context[:500]

            try:
                where_clause = {"year": rag_year_filter} if rag_year_filter and rag_year_filter != "ALL" else None
                
                rule_res = rule_db.query(query_texts=[chroma_query], n_results=2, where=where_clause)
                ref_res = reference_db.query(query_texts=[chroma_query], n_results=2, where=where_clause)
                
                if rule_res and rule_res.get("documents") and rule_res["documents"][0]:
                    chroma_context += "[규정/팩트 문서]\n" + "\n\n".join(rule_res["documents"][0]) + "\n\n"
                    if rule_res.get("metadatas"): results_metadatas.extend(rule_res["metadatas"][0])
                    
                if ref_res and ref_res.get("documents") and ref_res["documents"][0]:
                    chroma_context += "[참조/양식 문서]\n" + "\n\n".join(ref_res["documents"][0]) + "\n\n"
                    if ref_res.get("metadatas"): results_metadatas.extend(ref_res["metadatas"][0])
            except Exception as chroma_err:
                print(f"ChromaDB 검색 오류: {chroma_err}")

        # =======================================================
        # [Step 4] 최종 하이브리드 답변 생성
        # =======================================================
        final_model = genai.GenerativeModel(model_name=request.model_name, system_instruction=get_system_prompt(request.user_role))
        
        # [디버그] 프론트엔드에서 스크랩 컨텍스트가 분리되어 제대로 넘어왔는지 확인
        if request.scraped_context:
            print(f"=== [수신된 스크랩 컨텍스트 (미리보기)] ===\n{request.scraped_context[:200]}...\n===========================")
        else:
            print("=== [스크랩 컨텍스트 없음] ===")

        prompt = f"""
너는 대동대학교 입시처 행정 검토 전문 AI 아키텍트야.
아래의 XML 태그로 구분된 정보들을 읽고, <사용자 지시사항>에 따라 정확하고 명쾌한 답변을 제공해.

<검토 대상 문서 (선택)>
(사용자가 브라우저 화면에서 스크랩한 문서 원본입니다. 데이터가 존재한다면 문서를 검토하는 데 사용하세요.)
{request.scraped_context if request.scraped_context else "스크랩된 문서 없음 (단순 질의응답 모드로 동작하세요)"}
</검토 대상 문서 (선택)>

<판단 기준 1: 시스템 DB 최신 팩트>
(질문에 답변하기 위해 시스템에서 1순위로 추출한 실시간 DB 데이터입니다.)
{sql_context if sql_context else "관련 DB 데이터 없음"}
</판단 기준 1: 시스템 DB 최신 팩트>

<판단 기준 2: 사내 규정 및 과거 문서 (RAG)>
(규정 확인이나 과거 문서 참조가 필요할 때 사용하는 데이터입니다.)
{chroma_context if chroma_context else "관련 규정/참조 문서 없음"}
</판단 기준 2: 사내 규정 및 과거 문서 (RAG)>

<사용자 지시사항>
{request.question}
</사용자 지시사항>

[행동 지침]
1. "검토 대상 문서가 없다"며 답변을 회피하거나 사과하지 마. 문서가 없으면 <판단 기준 1>과 <판단 기준 2>의 데이터를 바탕으로 질문에 직접적으로 대답해.
2. <검토 대상 문서>가 존재할 경우에만 해당 문서 내 위반 사항이나 오류를 찾아내고 지적해.
3. <판단 기준 1: 시스템 DB 최신 팩트>에 사용자가 묻는 데이터(예: 사람, 숫자, 출신학교 등)가 포함되어 있다면 주저하지 말고 그 팩트를 기반으로 확신을 가지고 답변해.
4. <판단 기준 1>의 데이터는 시스템이 사용자의 질문 조건을 완벽히 필터링해서 가져온 맞춤형 정답입니다. 결과값에 연도나 수험번호가 보이지 않는다고 해서 "일치하는지 확인할 수 없다"는 식의 변명을 절대 하지 마세요.
5. **[데이터 크로스체크 및 결합 금지]:** <판단 기준 1: 시스템 DB>에서 추출된 데이터의 학년도(연도)와 <판단 기준 2: 사내 규정>에서 추출된 문서의 적용년도(학년도)를 반드시 대조하세요.
6. 만약 두 데이터의 기준 연도(학년도)가 다를 경우, 절대 데이터를 결합하여 경쟁률 등을 산출하지 마세요. 대신 "DB 데이터는 OOOO학년도 기준이며, 문서는 OOOO학년도 기준이라 두 수치를 직접 비교하거나 산출할 수 없습니다"라고 명확히 분리하여 경고하세요.
"""

        
        # 스크랩된 대량의 텍스트를 처리할 수 있도록 타임아웃을 60초로 넉넉하게 연장
        response = final_model.generate_content(prompt, request_options={"timeout": 60})
        return {
            "status": "success",
            "answer": response.text,
            "references": results_metadatas
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 답변 생성 중 오류 발생: {str(e)}")


@app.get("/catalog/tables")
async def get_table_catalog():
    """
    [대시보드 리스트용 API] 
    MS-SQL의 Sys_TableCatalog에서 연동된 정형 데이터(View/Table) 목록을 조회합니다.
    """
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
        
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name, db_source, description, 
                   CONVERT(VARCHAR(10), created_at, 120) AS created_at, 
                   table_name_kr 
            FROM Sys_TableCatalog
            ORDER BY created_at DESC
        """)
        
        columns = [column[0] for column in cursor.description]
        tables = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # 권한(is_public)은 컬럼 단위로 관리되지만 대시보드 표시를 위해 테이블 단위로 세분화 (Y: 전체공개, P: 부분공개, N: 직원전용)
        for t in tables:
            cursor.execute(f"SELECT COUNT(*) FROM Sys_ColumnCatalog WHERE table_name='{t['table_name']}'")
            total_cols = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(*) FROM Sys_ColumnCatalog WHERE table_name='{t['table_name']}' AND is_public='Y'")
            public_cols = cursor.fetchone()[0]
            
            if total_cols == 0:
                t['is_public'] = 'N'
            elif public_cols == total_cols:
                t['is_public'] = 'Y'
            elif public_cols == 0:
                t['is_public'] = 'N'
            else:
                t['is_public'] = 'P'
        
        return {
            "status": "success",
            "total_count": len(tables),
            "data": tables
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"테이블 카탈로그 목록 조회 에러: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/tables/{table_name}")
async def update_table(table_name: str, table_name_kr: str = Form(...), description: str = Form(None)):
    """정형 데이터(테이블/뷰) 메타데이터 수정"""
    conn = get_mssql_connection()
    if not conn: raise HTTPException(status_code=500, detail="MS-SQL 연결 실패")
    try:
        cursor = conn.cursor()
        desc_val = description if description else ""
        cursor.execute("UPDATE Sys_TableCatalog SET table_name_kr=?, description=? WHERE table_name=?", (table_name_kr, desc_val, table_name))
        conn.commit()
        return {"status": "success", "message": "데이터 카탈로그 정보가 수정되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.delete("/tables/{table_name}")
async def delete_table(table_name: str):
    """정형 데이터 카탈로그 영구 삭제 및 엑셀 데이터 Drop"""
    conn = get_mssql_connection()
    if not conn: raise HTTPException(status_code=500, detail="MS-SQL 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT db_source FROM Sys_TableCatalog WHERE table_name = ?", (table_name,))
        row = cursor.fetchone()
        db_source = row[0] if row else None
        
        # 메타데이터 장부 삭제
        cursor.execute("DELETE FROM Sys_ColumnCatalog WHERE table_name = ?", (table_name,))
        cursor.execute("DELETE FROM Sys_TableCatalog WHERE table_name = ?", (table_name,))
        
        # 엑셀 데이터일 경우 실제 물리 테이블도 Drop
        if db_source == 'INTERNAL':
            cursor.execute(f"IF OBJECT_ID('[{table_name}]', 'U') IS NOT NULL DROP TABLE [{table_name}]")
            
        conn.commit()
        return {"status": "success", "message": f"'{table_name}' 연동 해제 및 삭제 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/catalog/documents")
async def get_document_catalog():
    """
    [대시보드 리스트용 API] 
    ChromaDB가 아닌 MS-SQL의 Sys_DocumentCatalog에서 비정형 문서 메타데이터 목록만 빠르게 조회합니다.
    """
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
        
    try:
        cursor = conn.cursor()
        # 프론트엔드 UI에 맞게 날짜 포맷팅 및 최신순 정렬
        cursor.execute("""
            SELECT doc_id, filename, doc_type, year, title, is_public, 
                   CONVERT(VARCHAR(10), uploaded_at, 120) AS uploaded_at, 
                   description 
            FROM Sys_DocumentCatalog
            ORDER BY uploaded_at DESC
        """)
        
        columns = [column[0] for column in cursor.description]
        documents = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return {
            "status": "success",
            "total_count": len(documents),
            "data": documents
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"카탈로그 목록 조회 에러: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.get("/columns/{table_name}")
async def get_columns(table_name: str):
    """특정 테이블/뷰의 컬럼 카탈로그 정보를 반환합니다."""
    conn = get_mssql_connection()
    if not conn: raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, column_name, ai_description, is_public FROM Sys_ColumnCatalog WHERE table_name = '{table_name}' ORDER BY id ASC")
        columns = [column[0] for column in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"status": "success", "data": data}
    finally:
        cursor.close()
        conn.close()

@app.put("/columns/{table_name}")
async def update_columns(table_name: str, payload: ColumnUpdatePayload):
    """특정 테이블/뷰의 컬럼 카탈로그(AI 힌트, 공개 여부)를 일괄 수정합니다."""
    conn = get_mssql_connection()
    if not conn: raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
    try:
        cursor = conn.cursor()
        for col in payload.columns:
            desc = col.ai_description if col.ai_description else ""
            cursor.execute("UPDATE Sys_ColumnCatalog SET ai_description=?, is_public=? WHERE id=?", (desc, col.is_public, col.id))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import uvicorn
    # 코드 수정 시 자동 재시작(reload=True) 적용. 
    # 실제 배포 시에는 host="0.0.0.0", reload=False 로 구동.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)