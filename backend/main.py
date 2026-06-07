# ==========================================
# 메인 서버 및 API 엔드포인트
# ==========================================
import os
import re
import io
import uuid
import time
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import chromadb
import pyodbc
import pdfplumber
import openpyxl
import google.generativeai as genai
from fastapi.staticfiles import StaticFiles

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

# [정적 파일 배포] 크롬 확장 프로그램 소스(HTML/JS)를 웹 대시보드에서 이중개발 없이 그대로 재사용할 수 있도록 호스팅합니다.
app.mount("/extension", StaticFiles(directory="../extension"), name="extension")

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
    scraped_file_name: Optional[str] = "" # [NEW] 첨부 파일명
    model_name: str = "gemini-2.5-flash"
    user_role: str = "staff" # 권한: "staff"(교직원) 또는 "student"(일반학생)
    history: Optional[List[dict]] = []

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


def format_sql_query(sql: str) -> str:
    """SQL 쿼리 문자열을 예약어 및 SELECT 컬럼 기준으로 줄바꿈 처리하여 터미널 가독성을 높입니다."""
    if not sql or sql.upper() == "NONE":
        return sql
    
    # 1. 예약어 앞에 줄바꿈(\n  ) 추가
    keywords = ["SELECT ", "FROM ", "WHERE ", "GROUP BY ", "ORDER BY ", "HAVING ", "LEFT JOIN ", "INNER JOIN ", "JOIN "]
    formatted = sql
    
    for kw in keywords:
        pattern = re.compile(rf"\b{kw.strip()}\b", re.IGNORECASE)
        formatted = pattern.sub(f"\n  {kw.strip()}", formatted)
        
    # 2. SELECT 절의 최상위 컬럼들(쉼표 기준) 줄바꿈 처리
    lines = formatted.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("SELECT"):
            # SELECT 키워드와 컬럼들을 분리
            select_idx = line.upper().find("SELECT")
            select_keyword = line[:select_idx + 6]
            columns_part = line[select_idx + 6:]
            
            # 괄호 깊이를 추적하며 최상위 쉼표 분리
            new_columns = []
            current_col = []
            paren_depth = 0
            for char in columns_part:
                if char == '(':
                    paren_depth += 1
                    current_col.append(char)
                elif char == ')':
                    paren_depth -= 1
                    current_col.append(char)
                elif char == ',' and paren_depth == 0:
                    new_columns.append("".join(current_col).strip())
                    current_col = []
                else:
                    current_col.append(char)
            if current_col:
                new_columns.append("".join(current_col).strip())
                
            # 컬럼들을 줄바꿈 및 정렬하여 합침
            indent = " " * len(select_keyword)
            joined_cols = f",\n{indent} ".join(new_columns)
            new_lines.append(f"{select_keyword} {joined_cols}")
        else:
            new_lines.append(line)
            
    return "\n".join(new_lines).strip()


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
            print("[ERROR] 오류: 시스템에 설치된 SQL Server ODBC 드라이버가 없습니다.")
            return None
            
        # 2. 드라이버 우선순위 선택 (17 -> 18 -> 11 -> 기본 SQL Server)
        driver_name = available_drivers[0] # 기본값으로 첫 번째 발견된 드라이버 사용
        preferred_drivers = ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
        
        for pref in preferred_drivers:
            if pref in available_drivers:
                driver_name = pref
                break
                
        print(f"[OK] 선택된 MS-SQL 드라이버: {driver_name}")

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

    # [중복 방지] 기존에 동일한 파일명이나 제목을 가진 문서가 있다면 선 제거 조치
    conn = get_mssql_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT doc_id, doc_type FROM Sys_DocumentCatalog WHERE filename = ? OR title = ?",
                (file.filename, title)
            )
            existing_docs = cursor.fetchall()
            for old_id, old_type in existing_docs:
                print(f"[중복 제거] 기존 동일 파일/제목 감지하여 삭제 진행: ID {old_id}")
                # 1. ChromaDB 삭제
                try:
                    target_db = rule_db if old_type == "rule" else reference_db
                    target_db.delete(ids=[old_id])
                except Exception as e:
                    print(f"ChromaDB 이전 데이터 삭제 실패: {e}")
                
                # 2. MS-SQL 삭제
                cursor.execute("DELETE FROM Sys_DocumentCatalog WHERE doc_id = ?", (old_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as err:
            print(f"기존 중복 확인 과정 에러: {err}")

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

@app.post("/parse-file")
async def parse_file(file: UploadFile = File(...)):
    """
    [챗봇 첨부파일 파싱 전용 API]
    업로드된 파일(PDF, TXT, CSV)에서 텍스트와 표(마크다운 변환)를 추출하여 즉시 반환합니다.
    (ChromaDB나 SQL에 저장하지 않고 순수 파싱 용도로만 사용됨)
    """
    filename = file.filename.lower()
    if not (filename.endswith('.pdf') or filename.endswith('.txt') or filename.endswith('.csv')):
        raise HTTPException(status_code=400, detail="현재는 PDF, TXT, CSV 파일만 지원합니다.")

    try:
        content = await file.read()
        extracted_text = ""

        if filename.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += page_text + "\n"
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            extracted_text += table_to_markdown(table)
        else:
            # TXT, CSV 등 순수 텍스트 파일 처리
            # csv도 일반 텍스트 읽기로 처리 (단순 RAG용이므로)
            try:
                extracted_text = content.decode('utf-8')
            except UnicodeDecodeError:
                extracted_text = content.decode('euc-kr', errors='replace')
                
        if not extracted_text.strip():
            raise ValueError("추출된 텍스트가 없습니다.")
            
        safe_text = mask_personal_info(extracted_text)
        
        return {
            "status": "success",
            "filename": file.filename,
            "text": safe_text
        }
    except Exception as e:
        print(f"[파싱 오류] {str(e)}")
        raise HTTPException(status_code=500, detail=f"파일 파싱 오류: {str(e)}")


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
            print(f"[OK] 테이블 [{table_name}] 생성 완료")
            
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
    start_time = time.time()
    if not x_gemini_key:
        raise HTTPException(status_code=401, detail="Gemini API Key가 필요합니다.")

    try:
        genai.configure(api_key=x_gemini_key)
        
        # 1. MS-SQL 실시간 구조 파악 (데이터 사전 자동 생성)
        conn = get_mssql_connection()
        dynamic_schema = get_dynamic_db_schema(conn, request.user_role) if conn else "DB 연결 불가"
        
        # =======================================================
        # [Step 1-0] 스크랩 데이터 클렌징 (그룹웨어 메뉴, 결재선 등 불필요한 텍스트 제거)
        # =======================================================
        if request.scraped_context:
            def clean_scraped_context(text: str) -> str:
                if not text: return ""
                lines = text.split('\n')
                cleaned = []
                junk_keywords = {
                    "메일", "전자결재", "일정", "공지사항", "자료실", "공유자원", "더보기",
                    "완결문서", "회람지정", "인쇄", "COPY기안", "추가기능", "이전", "다음", "목록",
                    "기안작성", "미결문서", "진행문서", "임시저장문서", "문서옵션", "대면결재", 
                    "문서공개", "전체 다운로드", "전체다운로드(ZIP)", "선택파일 다운로드",
                    "결재[대기]", "기안자[승인]" # UI 요소만 제거, 실제 이름과 직급은 보존
                }
                for line in lines:
                    s = line.strip()
                    if not s: continue
                    if s in junk_keywords: continue
                    
                    if len(s) < 20:
                        if "회람문서 (" in s or "완결문서 (" in s: continue
                    if s.startswith("var uTop") or s.startswith("var uLeft") or s.startswith("var idx"): continue
                    
                    cleaned.append(s)
                return "\n".join(cleaned)
            
            request.scraped_context = clean_scraped_context(request.scraped_context)

        # =======================================================
        # [Step 1] NL2SQL: 사용자 질문 -> T-SQL 생성
        # =======================================================
        # 스크랩된 내용이 있다면 질문과 앞부분 키워드를 조합하여 관련된 DB 통계를 찾을 수 있도록 유도
        sql_search_text = request.question
        if request.scraped_context:
            sql_search_text += " " + request.scraped_context[:300]

        import json
        
        sql_router_prompt = f"""
        너는 대동대학교 입시처의 수석 데이터 아키텍트이자 실시간 입시 사전지식 관리자야. 
        사용자의 [질문]에 답변하기 위해 아래의 [현재 데이터베이스 및 문서 카탈로그 현황]을 분석하고, 
        어떻게 데이터를 조회 및 반영해야 할지 판단해 줘.

        [인사/조직 및 결재라인 변경 등의 지식 추가/삭제 판단 규칙]
        - 사용자의 [질문]이 "인사 정보 변경사항, 구성원 퇴사/입사 사실, 특정 결재라인 규정, 대학 행정 예외 정책" 등 AI가 향후 검토 시 상시 참고해야 할 새로운 규칙/정보를 **등록(저장/추가/기억) 또는 삭제(지우기/제거)**하려는 의도인 경우, 이를 감지하여 `knowledge_action`을 빌드하십시오.
        - 단순 질문(예: "~를 확인해줘", "~가 누구야?", "다른점이 있을까?")은 조회 목적이므로 `knowledge_action`의 `action`은 `"NONE"`입니다.
        - 등록 예시: "사전지식 등록해줘: 4월에 ooo 과장 퇴사했고, 5월에 ooo 주임 신규 입사" -> action: "INSERT", category: "인사/조직", content: "4월에 ooo 과장 퇴사했고, 5월에 ooo 주임 신규 입사"
        - 삭제 예시: "ooo 과장 이력 삭제해줘" -> action: "DELETE", category: "인사/조직", content: "ooo 과장" (삭제하려는 대상을 특정하는 키워드 또는 요약)

        [사전 지식 주입]
        1. [입시 학년도 정의]: 대학교 입시에서 'N학년도 전형(모집요강)'은 'N-1년도'에 모집을 실시하는 전형을 뜻합니다. (예: 2027학년도 모집요강 = 2026년 가을/겨울에 모집 실시). 사용자가 질문한 연도가 '실시 연도'인지 '입학 학년도'인지 문맥을 파악하여 SQL과 문서 검색 타겟을 정확히 일치시키세요.
        2. [일반 학년도 정의]: 학년도(예: 2026학년도)는 3월 1일부터 다음 해 2월 말일까지를 의미합니다. (예: 2026학년도 = 2026.03 ~ 2027.02).
        3. [신입/편입 구분]: 대학 입학 결과에는 신입생 뿐만 아니라 '편입생'도 존재합니다. 사용자가 특정 전형만 지정하지 않고 '최종 모집 결과' 등 종합 검토를 요청하는 경우, `[신입편입구분]` 조건에 '신입'만 걸어 조회하지 말고, '신입'과 '편입' 데이터를 구분하여 각각 조회하거나 한꺼번에 수집하도록 T-SQL을 구성하세요.
        4. [정원내 및 정원외 전형 구분 규칙]: 
           - 대학 학칙상 명시된 '입학정원'은 오직 **정원내 전형**에만 적용됩니다.
           - 전문대졸이상자, 기회균형 등 **'정원외 전형'**은 관계법령 및 학칙에 따라 입학정원 제한을 받지 않고 초과등록이 법적으로 허용됩니다.
           - 따라서 DB 최종등록자 수와 학칙상 입학정원을 비교·대조할 때는 반드시 `[정원내외명] = '정원내'`(혹은 `LIKE '%정원내%'`) 조건의 등록자 수만 직접 대조해야 합니다.
           - 정원외 등록자는 입학정원 대비 초과/미달 판단에서 제외하고 별도의 단독 수치(예: '정원외 등록자 O명')로만 나타내어야 하므로, 이를 분석할 수 있도록 T-SQL 작성 시 `[정원내외명]`을 GROUP BY 하거나 SELECT 절에서 조건별 분리 집계(CASE WHEN 등) 및 조건절로 구분하여 조회하게 만드십시오.
        
        [가장 중요한 SQL 작성 규칙]
        1. 컬럼명이 한글일 수 있으므로 대괄호 []를 반드시 사용해.
        2. **[띄어쓰기 절대 금지]** 대괄호 `[]` 내부의 테이블명과 컬럼명에는 절대로 공백이나 띄어쓰기를 임의로 넣지 마세요. 카탈로그에 표시된 문자열 철자를 공백 없이 100% 동일하게 따라야 합니다. (예: `[입시학 년도]`가 아닌 `[입시학년도]`, `[전형 명]`이 아닌 `[전형명]`)
        3. **[ai_description 준수]** 컬럼 설명(`ai_description`)에 가능한 코드값이나 텍스트 형태(예: '합격자(최종아님),최종등록자(최종합격자)')가 콤마로 나열되어 있다면, 이를 실제 DB에 저장된 데이터 명칭으로 인지하십시오. 문자열 비교 조건절(WHERE)을 작성할 때 텍스트를 자의적으로 단축하거나 가공(예: 괄호 제거 등)하지 말고 카탈로그에 명시된 문자열 그대로(예: `[최종입시결과] = '최종등록자(최종합격자)'`, `[정원내외명] = '정원외'`) 매칭하여 쿼리를 작성하십시오.
        4. 문자열 조건은 무조건 `=` 대신 `LIKE`를 사용하되, 사용자의 단어에서 핵심 형태소만 짧게 잘라서 검색해! (단, 3번 규칙에 따라 콤마로 나열된 고유값이 확실하고 정밀 비교가 필요한 경우는 `=`로 완전히 일치시키세요. 또한 띄어쓰기에 유의하여 공백 없이 검색해야 합니다. 예: `'%정원외%'`)
        5. 통계나 숫자를 물어보면 무조건 `COUNT()`, `SUM()` 같은 집계 함수를 사용해!
        6. 목록을 물어볼 때는 데이터 폭발 방지를 위해 `SELECT TOP 30 * FROM ...` 처럼 TOP 제한을 걸어!
        7. **[학년도 강제]** 질문에 특정 연도/학년도가 포함되어 있다면 반드시 `WHERE [입시학년도] = '2026'` 과 같이 학년도 조건을 추가해!
        8. **[스크랩/첨부 문서 데이터 구조 분석 및 쿼리 매핑 규칙]**:
           - 사용자가 제시한 `[질문]` 하단에는 스크랩되거나 첨부된 문서의 표 내용(예: 학과명, 지원인원, 최종등록자수, 정원내외구분, 신입편입여부 등)이 포함되어 있습니다.
           - 너는 이 문서 내용의 데이터 레이아웃과 구체적인 표 구조를 자세히 파악해야 해.
           - 만약 표에 **학과별 지원 수치 및 등록 수치**, **신입생/편입생 구분**, **정원내/외 구분** 등이 있다면, DB에서 이 수치들과 1:1로 직접 교차 검토(대조)가 가능하도록, **`[지원학과명]`, `[신입편입구분]`, `[정원내외명]`을 GROUP BY 절과 SELECT 절에 반드시 누락 없이 반영하여 학과별/전형구분별 세부 데이터(지원인원 수 및 등록자 수)를 집계하는 T-SQL 쿼리**를 영리하게 빌드해 내야 합니다. 단순히 전체 합계만 조회하는 쿼리로 퉁치지 말고, 서류의 표 구조와 1:1 매칭되는 상세 통계 쿼리를 작성하세요.
        9. **[구매/예산/계약 문서 감지 및 RAG 쿼리 확장 규칙]**:
           - 사용자의 [질문]이나 스크랩된 문서 내용(제목 등)에 '원인기안', '제작 계획', '구입', '품의', '지출', '계약' 등의 실무 행정/예산 집행 키워드가 감지될 경우, 명시적으로 '구매'나 '예산'이라는 단어가 없더라도 이는 100% 구매 및 예산 관련 기안문으로 간주해야 합니다.
           - 이 경우 AI는 행정 결재선뿐만 아니라 금액 및 예산 한도의 적정성을 필수적으로 검토해야 하므로, **반드시 `rag_search_query`에 '구매예산규정, 재무회계규정' 등 사내 예산/구매 관련 핵심 규정 문서 명칭을 강제로 추가**하여 RAG 검색 풀에 포함시키십시오.


        {dynamic_schema}

        [질문]
        {sql_search_text}
        
        [출력 지침]
        너는 무조건 아래의 JSON 형식으로만 대답해야 해. 마크다운 기호(```json)나 다른 설명은 일절 쓰지 마.
        {{
            "sql_query": "정형 데이터 조회가 필요하면 T-SQL SELECT 문을, 필요 없으면 'NONE'을 입력",
            "need_rag": true 혹은 false (비정형 문서 목록에서 찾아봐야 할 정보가 있다면 true),
            "rag_search_query": "need_rag가 true일 경우, 문서를 검색할 핵심 키워드. 만약 검토해야 할 연관된 여러 개의 규정/문서가 있을 경우, 각 키워드나 문서명을 쉼표(,)로 연결하여 모두 나열하십시오. (예: '구매 규정, 법인카드 사용 규정, 예산 회계 규정, 위임전결 규정')",
            "rag_year_filter": "특정 학년도의 문서만 찾아야 할 경우 해당 4자리 숫자 입력. 단, 학칙 등 상시 적용되는 문서를 찾아야 하거나 연도를 모르면 'ALL' 입력",
            "knowledge_action": {{
                "action": "INSERT" 또는 "DELETE" 또는 "NONE",
                "category": "인사/조직" 또는 "결재라인" 또는 "예외규정" 또는 "기타",
                "content": "등록 시에는 저장할 사전지식 요약 팩트 문장, 삭제 시에는 삭제를 식별할 수 있는 키워드나 요약 내용 (해당사항 없으면 빈 문자열)"
            }}
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
            
            # [실시간 지식 보완 액션 추출]
            k_action_data = parsed_json.get("knowledge_action", {})
            k_action = k_action_data.get("action", "NONE")
            k_category = k_action_data.get("category", "기타")
            k_content = k_action_data.get("content", "")
            
            # [연도 자동 보정] 사용자 질문이나 스크랩된 문서에서 4자리 연도를 감지하여 RAG 필터에 자동 적용합니다.
            if rag_year_filter == "ALL" or not rag_year_filter:
                all_text = (request.question or "") + " " + (request.scraped_context or "")
                years = re.findall(r"\b(202\d)\b", all_text)
                if years:
                    rag_year_filter = years[0]
                    print(f"[연도 보정] 질문/스크랩 내에서 {rag_year_filter}학년도를 감지하여 필터를 적용합니다.")
        except Exception as json_err:
            print(f"JSON 파싱 오류: {json_err} / 원본: {sql_response.text}")
            sql_query = "NONE"
            need_rag = True
            rag_query = request.question
            rag_year_filter = "ALL"
            k_action = "NONE"
            k_category = "기타"
            k_content = ""
            
            # [연도 자동 보정]
            all_text = (request.question or "") + " " + (request.scraped_context or "")
            years = re.findall(r"\b(202\d)\b", all_text)
            if years:
                rag_year_filter = years[0]
        
        # =======================================================
        # [Step 1-2] 실시간 보완 지식 (Supplemental Knowledge) DB 반영 및 수집
        # =======================================================
        k_feedback_msg = ""
        supplemental_context = ""
        
        if conn:
            try:
                cursor = conn.cursor()
                
                # A. 지식 실시간 저장/삭제 반영
                if k_action == "INSERT" and k_content:
                    # 중복 저장 방지 체크
                    cursor.execute(
                        "SELECT COUNT(*) FROM Sys_SupplementalKnowledge WHERE category = ? AND content = ? AND is_active = 'Y'",
                        (k_category, k_content)
                    )
                    if cursor.fetchone()[0] == 0:
                        cursor.execute(
                            "INSERT INTO Sys_SupplementalKnowledge (category, content, is_active, author) VALUES (?, ?, 'Y', ?)",
                            (k_category, k_content, request.user_role)
                        )
                        k_feedback_msg = f"[알림] 실시간 보완 지식({k_category})이 시스템에 성공적으로 등록되었습니다: '{k_content}'"
                        print(f"[지식 저장 성공] {k_feedback_msg}")
                    else:
                        k_feedback_msg = f"[알림] 이미 등록되어 활성화되어 있는 보완 지식입니다: '{k_content}'"
                        print(f"[지식 저장 중복] {k_feedback_msg}")
                        
                elif k_action == "DELETE" and k_content:
                    like_pattern = f"%{k_content}%"
                    cursor.execute(
                        "SELECT COUNT(*) FROM Sys_SupplementalKnowledge WHERE is_active = 'Y' AND (content LIKE ? OR category LIKE ?)",
                        (like_pattern, like_pattern)
                    )
                    del_count = cursor.fetchone()[0]
                    if del_count > 0:
                        cursor.execute(
                            "UPDATE Sys_SupplementalKnowledge SET is_active = 'N' WHERE is_active = 'Y' AND (content LIKE ? OR category LIKE ?)",
                            (like_pattern, like_pattern)
                        )
                        k_feedback_msg = f"[알림] 조건 '{k_content}'에 부합하는 실시간 보완 지식 총 {del_count}건이 삭제(비활성화) 처리되었습니다."
                        print(f"[지식 삭제 성공] {k_feedback_msg}")
                    else:
                        k_feedback_msg = f"[알림] 삭제 요청 조건('{k_content}')에 맞는 활성화된 사전지식을 찾지 못했습니다."
                        print(f"[지식 삭제 실패] {k_feedback_msg}")
                
                conn.commit()
                
                # B. 현재 활성화된 모든 사전지식 수집
                cursor.execute(
                    "SELECT category, content, CONVERT(VARCHAR(10), created_at, 120) FROM Sys_SupplementalKnowledge WHERE is_active = 'Y' ORDER BY category ASC, id ASC"
                )
                rows = cursor.fetchall()
                if rows:
                    for r in rows:
                        cat, cnt, r_date = r
                        supplemental_context += f"- [{cat}] {cnt} (등록일: {r_date})\n"
                else:
                    supplemental_context = "등록된 실시간 보완 지식 없음"
                    
            except Exception as k_db_err:
                print(f"보완 지식 트랜잭션 에러: {k_db_err}")
                supplemental_context = "보완 지식 데이터 로딩 오류"
        
        formatted_sql = format_sql_query(sql_query)
        print(f"=== [AI 라우팅 결과] ===")
        print(f"※ 설명: 사용자의 자연어 질문을 바탕으로 AI가 데이터 사전 카탈로그를 분석하여 자동으로 설계한 T-SQL 쿼리문입니다.")
        print(f"SQL 쿼리:")
        print("--- T-SQL START ---")
        print(formatted_sql)
        print("--- T-SQL END ---")
        print(f"문서 검색 필요 여부(RAG): {need_rag}")
        print(f"RAG 쿼리: {rag_query}")
        print(f"메타데이터 필터(Year): {rag_year_filter}")
        print(f"===========================")

        # =======================================================
        # [Step 2] 생성된 쿼리 실행
        # =======================================================
        sql_context = ""
        if sql_query.upper().startswith("SELECT") and conn:
            try:
                # [최적화] AI가 추출된 데이터의 출처와 필터링 조건을 확신할 수 있도록 사용된 쿼리 원문을 증거로 덧붙입니다.
                sql_context += f"[시스템이 데이터를 추출할 때 사용한 조건(쿼리)]:\n{formatted_sql}\n"
                
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
                print(f"=== [SQL 실제 실행 결과] ===")
                print(f"※ 설명: 위에서 AI가 설계한 T-SQL 쿼리를 실제 MS-SQL DB(입시마스타)에 전달하여 실시간으로 실행 및 수집해온 데이터 팩트입니다.")
                print("--- T-SQL START ---")
                print(formatted_sql)
                print("--- T-SQL END ---")
                
                print(f"\n[수집된 DB 레코드]")
                data_lines = [line for line in sql_context.split('\n') if "추출 데이터" in line or "데이터가 너무 많아" in line]
                print("\n".join(data_lines) if data_lines else "데이터 없음 (0건 검색됨)")
                print(f"===========================")
                
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
            # [최적화] CSV 등 텍스트 더미가 쿼리에 섞여 코사인 유사도를 망치지 않도록,
            # RAG 임베딩 검색 시에는 scraped_context를 생략하고 오직 자연어 질문(rag_query)만 쿼리로 사용합니다.
            chroma_query = rag_query
            
            # [스마트 RAG 키워드 확장]
            # 사용자 질문에 없더라도, 스크랩/첨부된 문서(scraped_context) 내에 규정 검토에 핵심적인 키워드가 발견되면
            # ChromaDB 검색 시 관련 규정 문서가 확실히 끌려오도록 검색 쿼리를 콤마로 결합해 확장합니다.
            if request.scraped_context:
                extra_keywords = []
                scraped_lower = request.scraped_context.lower()
                
                # 핵심 검토 도메인 키워드 매핑 (오매칭 및 토큰 낭비 방지를 위해 검색 필터 정교화)
                keyword_mappings = {
                    "학교폭력": ["학교폭력", "학폭"],  # '감점', '퇴학', '전학', '조치사항' 등 다른 문서에서도 흔한 단어는 오매칭 방지를 위해 제외
                    "위임전결": ["위임전결", "결재권", "전결"],  # '결재선' 등 흔한 일반 단어 제외
                    "문서보존": ["보존기한", "보존기간", "문서보존"],  # '문서보관', '보존기 간' 등 모호한 단어 제외
                    "예산": ["예산계획", "기안 금액", "부서 운영 계획"]  # 단독 '예산', '계획서'는 너무 흔한 일반 단어이므로 복합어로 정교화
                }
                
                for key_query, synonyms in keyword_mappings.items():
                    if any(syn in scraped_lower for syn in synonyms):
                        extra_keywords.append(key_query)
                        
                if extra_keywords:
                    chroma_query += "," + ",".join(extra_keywords)
                    print(f"[RAG 스마트 확장] 스크랩 문서 내 핵심 키워드가 발견되어 쿼리를 확장합니다: {extra_keywords}")

            try:
                # 쉼표(,)를 기준으로 쿼리 분할
                queries = [q.strip() for q in chroma_query.split(",") if q.strip()]
                if not queries:
                    queries = [chroma_query]

                rule_docs_map = {}
                ref_docs_map = {}

                # [상시 적용 문서 지원] 특정 연도(예: 2028)를 필터링하더라도, year가 'ALL'인 상시 적용 규정(학칙 등)도 함께 검색되도록 $in 연산자를 사용합니다.
                where_clause = {"year": {"$in": [rag_year_filter, "ALL"]}} if rag_year_filter and rag_year_filter != "ALL" else None
                
                # [개선] 영어 임베딩 모델의 한글 매칭 한계를 메우기 위해, 후보군을 넓게(60개) 가져온 후 파일명 매칭 보정을 적용합니다.
                n_results_per_query = 60

                for q in queries:
                    try:
                        rule_res = rule_db.query(query_texts=[q], n_results=n_results_per_query, where=where_clause)
                        if rule_res and rule_res.get("documents") and rule_res["documents"][0]:
                            for i, doc_text in enumerate(rule_res["documents"][0]):
                                meta = rule_res["metadatas"][0][i] if rule_res.get("metadatas") else {}
                                dist = rule_res["distances"][0][i] if rule_res.get("distances") else 1.0
                                fname = meta.get("filename", "이름없음")
                                
                                # [보정 알고리즘] 쿼리 텍스트와 파일명 키워드 매칭 보너스 부여
                                fname_clean = re.sub(r'[^a-zA-Z0-9가-힣]', '', fname.replace(".pdf", "")).lower()
                                q_clean = re.sub(r'[^a-zA-Z0-9가-힣]', '', q).lower()
                                if q_clean and fname_clean:
                                    if q_clean in fname_clean or fname_clean in q_clean:
                                        dist = min(dist, 0.1)
                                
                                # 중복 제거 시 최소 distance 유지
                                if fname not in rule_docs_map or dist < rule_docs_map[fname]["distance"]:
                                    rule_docs_map[fname] = {"doc_text": doc_text, "meta": meta, "distance": dist}
                    except Exception as q_err:
                        print(f"Rule DB query error for '{q}': {q_err}")

                    try:
                        ref_res = reference_db.query(query_texts=[q], n_results=n_results_per_query, where=where_clause)
                        if ref_res and ref_res.get("documents") and ref_res["documents"][0]:
                            for i, doc_text in enumerate(ref_res["documents"][0]):
                                meta = ref_res["metadatas"][0][i] if ref_res.get("metadatas") else {}
                                dist = ref_res["distances"][0][i] if ref_res.get("distances") else 1.0
                                fname = meta.get("filename", "이름없음")
                                
                                # [보정 알고리즘] 쿼리 텍스트와 파일명 키워드 매칭 보너스 부여
                                fname_clean = re.sub(r'[^a-zA-Z0-9가-힣]', '', fname.replace(".pdf", "")).lower()
                                q_clean = re.sub(r'[^a-zA-Z0-9가-힣]', '', q).lower()
                                if q_clean and fname_clean:
                                    if q_clean in fname_clean or fname_clean in q_clean:
                                        dist = min(dist, 0.1)

                                if fname not in ref_docs_map or dist < ref_docs_map[fname]["distance"]:
                                    ref_docs_map[fname] = {"doc_text": doc_text, "meta": meta, "distance": dist}
                    except Exception as q_err:
                        print(f"Reference DB query error for '{q}': {q_err}")

                # distance 기준 오름차순 통합 정렬 후 상위 최대 6개 추출 (Safe Limit)
                sorted_rules = sorted(rule_docs_map.values(), key=lambda x: x["distance"])
                sorted_refs = sorted(ref_docs_map.values(), key=lambda x: x["distance"])

                final_rules = sorted_rules[:6]
                final_refs = sorted_refs[:6]


                # [터미널 검색 현황 출력 - cp949 인코딩 에러 방지를 위해 이모지 제거]
                matched_rule_files = [d["meta"].get("filename", "이름없음") for d in final_rules]
                matched_ref_files = [d["meta"].get("filename", "이름없음") for d in final_refs]
                print(f"[RAG 검색 성공] Rule DB 매칭 문서: {matched_rule_files}")
                print(f"[RAG 검색 성공] Reference DB 매칭 문서: {matched_ref_files}")

                if final_rules:
                    formatted_docs = []
                    for d in final_rules:
                        meta_title = d["meta"].get("title", "출처 불명")
                        formatted_docs.append(f"◆ [출처 문서: {meta_title}]\n{d['doc_text']}")
                    chroma_context += "[규정/팩트 문서]\n" + "\n\n".join(formatted_docs) + "\n\n"
                    results_metadatas.extend([d["meta"] for d in final_rules])
                    
                if final_refs:
                    formatted_refs = []
                    for d in final_refs:
                        meta_title = d["meta"].get("title", "출처 불명")
                        formatted_refs.append(f"◆ [참조/양식 문서: {meta_title}]\n{d['doc_text']}")
                    chroma_context += "[참조/양식 문서]\n" + "\n\n".join(formatted_refs) + "\n\n"
                    results_metadatas.extend([d["meta"] for d in final_refs])

            except Exception as chroma_err:
                print(f"ChromaDB 검색 오류: {chroma_err}")


        # =======================================================
        # [Step 4] 최종 하이브리드 답변 생성
        # =======================================================
        final_model = genai.GenerativeModel(model_name=request.model_name, system_instruction=get_system_prompt(request.user_role))
        
        # [디버그] 프론트엔드에서 스크랩 컨텍스트가 분리되어 제대로 넘어왔는지 확인
        if request.scraped_context:
            if request.scraped_file_name:
                print(f"[BACKEND] === [수신된 스크랩 컨텍스트 (미리보기: {request.scraped_file_name})] ===")
            else:
                print(f"[BACKEND] === [수신된 스크랩 컨텍스트 (미리보기)] ===")
            
            # 빈 줄을 제외하고 유효한 텍스트 라인만 추출
            valid_lines = [line.strip() for line in request.scraped_context.split('\n') if line.strip()]
            
            # 처음 15줄 (제목/결재선 등)
            for line in valid_lines[:15]:
                print(f"[BACKEND] {line}")
                
            if len(valid_lines) > 30:
                print("[BACKEND] ... [중간 생략] ...")
                # 정중앙 부근의 15줄 (실제 본문/알맹이가 위치할 확률이 높음)
                mid = len(valid_lines) // 2
                for line in valid_lines[mid:mid+15]:
                    print(f"[BACKEND] {line}")
                print("[BACKEND] ... [하단 생략] ...")
            else:
                for line in valid_lines[15:]:
                    print(f"[BACKEND] {line}")
                    
            print(f"[BACKEND] (총 {len(request.scraped_context)}자, 유효 텍스트 {len(valid_lines)}줄 정상 수신됨)")
            print("[BACKEND] ===========================")
        else:
            print("[BACKEND] === [스크랩 컨텍스트 없음] ===")

        # [NEW] 이전 대화 기록 가공
        history_context = ""
        if request.history:
            for msg in request.history:
                role = "사용자" if msg.get("isUser", False) else "AI"
                history_context += f"{role}: {msg.get('text', '')}\n"
        else:
            history_context = "이전 대화 내역 없음"

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

<판단 기준 3: 실시간 보완 지식 (최신 인사 정보 및 행정 예외 정책)>
(과거 규정/조직 문서(판단 기준 2)에 기재된 정보보다 우선하여 적용할 실시간 변경 팩트 및 예외 규정입니다. 대조 대상 문서 내 인명이나 결재선 정보가 아래 팩트와 상충할 경우, 반드시 아래 팩트를 기준으로 최종 정합성을 판단하세요.)
{supplemental_context if supplemental_context else "등록된 실시간 보완 지식 없음"}
</판단 기준 3: 실시간 보완 지식 (최신 인사 정보 및 행정 예외 정책)>

<이전 대화 기록>
(사용자와 주고받은 최근 대화 맥락입니다. 질문의 대명사나 지칭 대상이 모호할 경우 이 맥락을 바탕으로 이해하세요.)
{history_context}
</이전 대화 기록>

<사용자 지시사항>
{request.question}
</사용자 지시사항>

[행동 지침]
1. "검토 대상 문서가 없다"며 답변을 회피하거나 사과하지 마. 문서가 없으면 <판단 기준 1>과 <판단 기준 2>의 데이터를 바탕으로 질문에 직접적으로 대답해.
2. <검토 대상 문서>가 존재할 경우에만 해당 문서 내 위반 사항이나 오류를 찾아내고 지적해.
3. <판단 기준 1: SYSTEM DB 최신 팩트>에 사용자가 묻는 데이터(예: 사람, 숫자, 출신학교 등)가 포함되어 있다면 주저하지 말고 그 팩트를 기반으로 확신을 가지고 답변해.
4. <판단 기준 1>의 데이터는 시스템이 사용자의 질문 조건을 완벽히 필터링해서 가져온 맞춤형 정답입니다. 결과값에 연도나 수험번호가 보이지 않는다고 해서 "일치하는지 확인할 수 없다"는 식의 변명을 절대 하지 마세요.
5. **[데이터 크로스체크 및 결합 금지]:** <판단 기준 1: 시스템 DB>에서 추출된 데이터의 학년도(연도)와 <판단 기준 2: 사내 규정>에서 추출된 문서의 적용년도(학년도)를 반드시 대조하세요.
6. 만약 두 데이터의 기준 연도(학년도)가 다를 경우, 절대 데이터를 결합하여 경쟁률 등을 산출하지 마세요. 대신 "DB 데이터는 OOOO학년도 기준이며, 문서는 OOOO학년도 기준이라 두 수치를 직접 비교하거나 산출할 수 없습니다"라고 명확히 분리하여 경고하세요.
7. **[근거 규정 출처 표기 필수]:** <판단 기준 2: 사내 규정 및 과거 문서 (RAG)>에서 제공된 정보 및 규정을 인용하거나 행정적 검토 의견을 제시할 때, 지적 사항 및 의견 끝 또는 자연스러운 문맥 위치에 반드시 근거 규정이 실린 문서의 명칭을 명시하세요. (예: "(근거 문서: 2027학년도 모집요강)", "(근거 문서: 2027학년도 전문대학 입학전형 기본사항)")
8. **[정원내/외 비교 및 정합성 검토 원칙]:**
   - 시스템 DB 최종등록자 수와 학칙상 입학정원을 대조하여 정합성을 판별할 때, **정원내 전형 최종등록자만 입학정원과 비교**해야 합니다.
   - 전문대졸이상자, 기회균형 등 **정원외 전형**은 정원에 구애받지 않고 초과등록이 가능하므로, 정원외 최종등록자를 정원에 포함해 "입학정원 초과 학칙 위반"이라고 오판하지 마십시오.
   - 문서를 대조할 때는 **[정원내 최종등록자 수]**와 **[정원외 최종등록자 수]**를 명확하게 구분하여 각각 기재하고 분석에 반영해야 합니다.
9. **[신입생 및 편입생 동시 분석]:**
   - 사용자가 전형 결과 보고 등의 문서 대조를 요구할 때, 신입생 모집 결과 뿐만 아니라 **편입생 모집 결과**도 동일하게 정형 DB의 편입생 데이터(`[신입편입구분] = '편입'`)를 참고하여 양쪽 모두 정합성을 분석하고 누락 없이 보고하십시오.
10. **[답변 구성 최우선순위 지침 (통계 대조 최우선화)]**:
   - 사용자가 "통계수치가 틀리지 않는지 대조/비교/검토/점검해줘"라고 요청한 경우, **서류(스크랩/첨부된 문서) 속의 표에 기재된 통계와 실제 DB(입시마스타) 데이터가 일치하는지 여부 판별 결과를 가장 먼저(답변의 최상단에) 상세히 노출**해야 합니다.
   - 서류 데이터와 DB 데이터를 1:1로 직접 대조한 결과를 보여준 뒤, 그 다음 순서로 규정(학칙, 예산 등)과의 연계 검토 의견을 서술하십시오.
   - 단, 사용자 질문의 주 핵심이 통계 대조보다 서류의 규정(Rule) 검토인 경우에는 규정 검토를 가장 처음에 답변하십시오.
11. **[학과별 1:1 대조 및 일치여부 표시 지침 (엄격 적용)]**:
   - 사용자가 통계 대조를 원할 때, 학과별 최종 모집 통계(지원인원 및 최종등록자 등)에 대해 단순히 DB 수치만 나열하지 마십시오.
   - **학과별로 각각 `[일치]` 혹은 `[불일치 - 서류: O명, DB: O명]`, 또는 서류에 해당 수치가 누락된 경우 `[불일치 - 서류 미기재]` 와 같이 일치 여부 상태를 개별 라인마다 반드시 1:1로 아주 정밀하게 명시**하십시오.
   - 대조 결과가 일치하는 경우와 일치하지 않는 경우, 그리고 대조군(서류)이 미기재된 경우 모두를 구분하여 각각의 학과 우측에 명확히 표기하여 교직원이 정밀 대조 현황을 즉각 판별하도록 하십시오.
12. **[서류 내 표 데이터 누락 시 안내문 노출 최소화 지침]**:
   - 만약 사용자가 '서류 표와 대조해달라'고 요청했으나, 스크랩된 문서에 학과별 세부 인원 표 데이터가 식별되지 않는 경우에도 **최상단에 경고성 안내사항을 반복해서 띄워 사용자를 불편하게 하지 마십시오.**
   - 사용자가 이미 드래그 등을 통해 시도했음에도 수집 한계로 누락되었을 수 있으므로, 안내사항은 최상단에 크게 띄우지 말고 답변 최하단에 참고용 노트(`> [!NOTE]`) 등으로 간략하게 배치하거나, 아예 생략하십시오.
   - 대신에 학과별 1:1 대조 결과 리스트/표를 작성할 때 서류 데이터가 존재하지 않는 학과는 상태 마크에 `[불일치 - 서류 미기재(DB 기준: O명)]` 등으로 표시하여, 안내문구에 의존하지 않고 대조 결과의 완성된 형태를 즉시 보여주십시오.
13. **[LaTeX 수학 기호 사용 절대 금지 및 유니코드 화살표 기호 사용]**:
   - 답변 내에 LaTeX 수학 기호(예: `\rightarrow`, `\implies`, `\times` 등)를 절대로 사용하지 마십시오. 마크다운 환경에서 렌더링되지 않고 텍스트 그대로 노출되어 가독성을 저해합니다.
   - 대신 반드시 일반 유니코드 화살표 기호(예: `→`, `⇒`, `×` 등)를 사용해 가독성 있게 작성하십시오. (예: `622명 → 623명`)
 14. **[🚨 실시간 보완 지식 한정 변호/해명 서술 금지 및 일반 RAG 규정/예산 대조 성공 팩트 노출 허용]**:
     - <판단 기준 3: 실시간 보완 지식>에 등재된 최신 인사정보 및 행정 예외 정책에 의하여 정상(무죄) 참작된 건에 대해서만 "인사 발령이므로 적법하다", "전결권 예외 정책에 부합한다" 등의 구구절절한 변호, 해명, 적정성 해설 문구를 최종 답변 본문의 어떤 영역에서도 절대 서술하지 말고 침묵(생략)하십시오.
 15. **[상세/빠짐없는 분석 요청 시 동적 분량 조절]**:
     - 사용자가 질문에서 "빠짐없이", "상세히", "길게", "모두 다" 등 전체를 심층 분석해 달라는 명시적 지시를 한 경우, 기본 요약 방식을 해제하고 문서를 처음부터 끝까지 샅샅이 뒤져 발견된 모든 규정 위반, 예산 문제, 팩트 오류를 생략 없이 최대한 구체적이고 길게 리포트 형식으로 작성하십시오.
     - 그러나 <판단 기준 2: 사내 규정 및 과거 문서 (RAG)>에 있는 예산서나 부서 운영 계획서 등의 수치와 대조하여 기안 금액이 적정 범위 내에 있음이 확인된 일반 팩트 검증 사항은 **"예산 한도 대조 결과: 부서 계획서상 예산 범위(4,000,000원) 내 적정 집행 확인"**과 같이 객관적인 교차 검증 성공 사실을 답변 본문에 포함하여 보고할 수 있습니다.
     - 즉, 예외 지식(판단 기준 3)으로 인하여 면죄부를 받은 항목에 한해서만 변호하지 말고 감춰야 하며, 일반 사내 규정(판단 기준 2)에 부합하는 일반적인 팩트 검증 성공 사항은 답변에 간결하게 반영하십시오.
 15. **[사용자 질문 의도 파악 및 우선순위 구성 지침]**:
   - 사용자가 질문을 던졌을 때, 단순 기계적으로 미리 정해진 고정된 포맷만 따르지 마십시오.
   - **사용자가 무엇을 가장 먼저 보고 싶어 하는지(의도)를 먼저 면밀히 파악**하십시오. 
   - 예를 들어, 서류와 DB의 정합성 대조가 주 목적이라면 대조 결과 리스트(일치/불일치)를 최상단에 바로 배치하고, 학칙/규정 준수 여부 검토가 핵심이라면 검토 의견 및 규정 근거를 최상단에 배치하여 답변의 순서와 구성을 질문 의도에 완벽히 정렬하십시오.
16. **[실시간 지식 업데이트 성공 시 피드백 알림 강제]**:
   - 만약 아래 <지식 업데이트 반영 내역>에 저장 성공 또는 삭제 완료와 관련된 알림 메시지(예: `[알림] ...`)가 포함되어 있다면, **해당 알림 메시지를 답변의 가장 최상단 첫 줄에 마크다운 굵은 글씨 또는 인용구 형태로 100% 원문 그대로 노출**하고 한 줄 띄운 다음 본 답변을 작성하십시오.
17. **[RAG 검색 한계 인지 및 오판 방지 지침 (엄격 적용)]**:
    - AI 모델은 RAG(<판단 기준 2: 사내 규정 및 과거 문서 (RAG)>)로 인출된 텍스트 조각들이 해당 규정/문서 전체를 완벽히 대변하지 않음을 명확히 인지해야 합니다.
    - RAG로 인출된 문서 본문 조각에 특정 수치(예: 학교폭력 9호 퇴학 감점 조항 등)가 명시적으로 보이지 않더라도, "사내 규정이나 모집요강에 해당 조항이 누락되었다"거나 "정량평가 표의 항목이 일치하지 않는다"고 성급하게 오판하여 사용자의 서류(스크랩/첨부 문서)에 기재된 정상적인 항목을 누락 및 오류로 지적하지 마십시오.
    - 본인이 RAG로 인출한 텍스트 조각 중 1~8호 등의 일부만 식별되어 9호 조치가 실제 규정에 존재하는지 확신할 수 없을 경우, 이를 누락 오류로 지적하는 대신 "모집요강 본문 규정 확인이 필요합니다" 또는 "관련 규정의 전체 표를 재확인해야 합니다"와 같이 유보적으로 답변하거나, 아예 지적하지 마십시오. (참고: 대동대학교 2027학년도 모집요강 43페이지에는 1호부터 9호 감점 기준이 실재합니다.)


<지식 업데이트 반영 내역>
{k_feedback_msg if k_feedback_msg else "수행된 업데이트 내역 없음"}
</지식 업데이트 반영 내역>
"""

        
        # 스크랩된 대량의 텍스트를 처리할 수 있도록 타임아웃을 60초로 넉넉하게 연장
        response = final_model.generate_content(prompt, request_options={"timeout": 60})
        
        # [NEW] Audit Log 기록
        latency_ms = int((time.time() - start_time) * 1000)
        try:
            audit_conn = get_mssql_connection()
            if audit_conn:
                cursor = audit_conn.cursor()
                
                # cp949 인코딩 에러 방지를 위해 호환되지 않는 특수문자/이모지 제거
                def safe_str(txt):
                    if not txt: return ""
                    return str(txt).encode('cp949', errors='ignore').decode('cp949')

                cursor.execute("""
                    INSERT INTO Sys_AIAuditLog (
                        user_role, model_name, question, scraped_context, 
                        sql_query, rag_query, answer, latency_ms
                    ) 
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    safe_str(request.user_role), safe_str(request.model_name), safe_str(request.question), safe_str(request.scraped_context),
                    safe_str(sql_query), safe_str(rag_query), safe_str(response.text), latency_ms
                ))
                inserted_row = cursor.fetchone()
                log_id = inserted_row[0] if inserted_row else None
                audit_conn.commit()
                cursor.close()
                audit_conn.close()
        except Exception as audit_err:
            print(f"Audit Log 기록 오류: {audit_err}")

        return {
            "status": "success",
            "log_id": log_id,
            "answer": response.text,
            "references": results_metadatas
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 답변 생성 중 오류 발생: {str(e)}")


class AnalyticsRequest(BaseModel):
    questions: List[str]

@app.get("/logs/audit")
async def get_audit_logs():
    """최근 대화 모니터링 로그 100건 조회"""
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 100 id, user_role, model_name, question, scraped_context, 
                   sql_query, rag_query, answer, latency_ms, user_feedback,
                   CONVERT(VARCHAR(19), created_at, 120) AS created_at
            FROM Sys_AIAuditLog
            ORDER BY id DESC
        """)
        columns = [column[0] for column in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"status": "success", "data": logs}
    except Exception as e:
        print(f"Audit Log 조회 오류: {e}")
        return {"status": "error", "data": []}
    finally:
        if conn:
            conn.close()

class FeedbackRequest(BaseModel):
    feedback: str = None  # 'UP', 'DOWN', or None

@app.put("/logs/audit/{log_id}/feedback")
async def update_log_feedback(log_id: int, req: FeedbackRequest):
    """사용자/관리자 피드백 반영"""
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL 연결 실패")
    try:
        cursor = conn.cursor()
        if req.feedback not in ['UP', 'DOWN']:
            cursor.execute("UPDATE Sys_AIAuditLog SET user_feedback = NULL WHERE id = ?", (log_id,))
        else:
            cursor.execute("UPDATE Sys_AIAuditLog SET user_feedback = ? WHERE id = ?", (req.feedback, log_id))
        conn.commit()
        return {"status": "success", "message": "피드백이 반영되었습니다."}
    except Exception as e:
        print(f"피드백 반영 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/logs/analytics")
async def analyze_audit_logs(req: AnalyticsRequest, x_gemini_key: str = Header(None)):
    """최근 로그 기반 핵심 키워드 및 개선점 AI 추출"""
    if not x_gemini_key:
        raise HTTPException(status_code=401, detail="Gemini API Key가 필요합니다.")
    try:
        genai.configure(api_key=x_gemini_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        prompt = f"""
        너는 대학교 입시처의 데이터 분석가야.
        교직원들이 입시 챗봇에 최근 질문한 아래 {len(req.questions)}개의 질의 내역을 분석해서, 
        어떤 규정이나 정보가 더 보완되어야 할지, 어떤 주제가 핫한지 인사이트를 도출해줘.
        
        출력 형식(반드시 마크다운 기호 없이 순수 JSON만 출력해):
        {{
            "keywords": ["핫키워드1", "핫키워드2", "핫키워드3", "핫키워드4", "핫키워드5"],
            "weak_points": [
                {{"topic": "취약 주제 1", "reason": "이 질문 패턴이 많아서 RAG 보완 필요"}},
                {{"topic": "취약 주제 2", "reason": "이런 세부 수치 비교 요청이 늘고 있음"}}
            ]
        }}
        
        질문 리스트:
        {req.questions}
        """
        resp = model.generate_content(prompt)
        text = resp.text.strip().replace("```json", "").replace("```", "")
        import json
        return {"status": "success", "data": json.loads(text)}
    except Exception as e:
        print(f"Analytics 오류: {e}")
        return {"status": "error", "message": str(e)}


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


class SupplementalKnowledgePayload(BaseModel):
    category: str
    content: str
    author: Optional[str] = "staff"


@app.get("/catalog/supplemental-knowledge")
async def get_supplemental_knowledge_catalog():
    """MS-SQL의 Sys_SupplementalKnowledge에서 활성화된 보완 지식 목록을 조회합니다."""
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, category, content, is_active, 
                   CONVERT(VARCHAR(10), created_at, 120) AS created_at, 
                   author 
            FROM Sys_SupplementalKnowledge
            WHERE is_active = 'Y'
            ORDER BY id DESC
        """)
        columns = [column[0] for column in cursor.description]
        data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {
            "status": "success",
            "total_count": len(data),
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"보완 지식 조회 에러: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.post("/catalog/supplemental-knowledge")
async def add_supplemental_knowledge(payload: SupplementalKnowledgePayload):
    """신규 보완 지식을 수동 등록합니다."""
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Sys_SupplementalKnowledge (category, content, is_active, author)
            VALUES (?, ?, 'Y', ?)
        """, (payload.category, payload.content, payload.author))
        conn.commit()
        return {"status": "success", "message": "사전지식이 성공적으로 등록되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"보완 지식 등록 에러: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.put("/catalog/supplemental-knowledge/{knowledge_id}")
async def update_supplemental_knowledge(knowledge_id: int, payload: SupplementalKnowledgePayload):
    """기존 보완 지식을 수정합니다."""
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Sys_SupplementalKnowledge
            SET category = ?, content = ?
            WHERE id = ?
        """, (payload.category, payload.content, knowledge_id))
        conn.commit()
        return {"status": "success", "message": "사전지식이 성공적으로 수정되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"보완 지식 수정 에러: {str(e)}")
    finally:
        cursor.close()
        conn.close()


@app.delete("/catalog/supplemental-knowledge/{knowledge_id}")
async def delete_supplemental_knowledge(knowledge_id: int):
    """보완 지식을 삭제(비활성화) 처리합니다."""
    conn = get_mssql_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="MS-SQL DB 연결 실패")
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Sys_SupplementalKnowledge
            SET is_active = 'N'
            WHERE id = ?
        """, (knowledge_id,))
        conn.commit()
        return {"status": "success", "message": "사전지식이 성공적으로 삭제되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"보완 지식 삭제 에러: {str(e)}")
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
    # 코드 수정 시 자동 재시작(reload=True)을 켜서 개발 편의성을 극대화합니다.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)