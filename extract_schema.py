# ==========================================
# Admission-Pilot DB 스키마 완벽 추출기
# ==========================================

import pyodbc
import os

# ==========================================
# [설정] DB 접속 정보 (main.py와 동일하게 세팅)
# ==========================================
SERVER = '10.10.1.11'   
USER = 'admission_ai'   # AI 접속용 계정
PASSWORD = 'fjk12#$' 
DATABASE = 'DDU_ADMISSION' # 입시처 전용 DB
OUTPUT_FILE = 'db_schema_full.txt'
# ==========================================

def get_mssql_connection():
    """ODBC 드라이버를 자동 검색하여 연결합니다."""
    available_drivers = [d for d in pyodbc.drivers() if 'SQL Server' in d]
    if not available_drivers:
        print("❌ ODBC 드라이버가 없습니다.")
        return None
        
    driver_name = available_drivers[0]
    for pref in ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]:
        if pref in available_drivers:
            driver_name = pref
            break
            
    conn_str = (
        f"DRIVER={{{driver_name}}};"
        f"SERVER={SERVER},1433;"
        f"DATABASE={DATABASE};"
        f"UID={USER};"
        f"PWD={PASSWORD};"
        "TrustServerCertificate=yes;" # SSL 무시 (중요)
    )
    
    conn = pyodbc.connect(conn_str, autocommit=True)
    # 한글 깨짐 방지
    conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp949')
    conn.setdecoding(pyodbc.SQL_WCHAR, encoding='cp949')
    conn.setencoding(encoding='cp949')
    return conn

def get_schema():
    print(f"🔄 [{DATABASE}] DB 스키마 추출을 시작합니다...")
    conn = get_mssql_connection()
    if not conn:
        return
        
    cursor = conn.cursor()
    schema_text = ""
    
    # 1. 테이블 목록 조회
    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        # 테이블 설명 가져오기
        cursor.execute(f"""
            SELECT CAST(value AS NVARCHAR(500)) AS TableDesc 
            FROM sys.extended_properties 
            WHERE major_id = OBJECT_ID('{table}') AND minor_id = 0 AND name = 'MS_Description'
        """)
        tbl_desc_row = cursor.fetchone()
        tbl_desc = f" ({tbl_desc_row[0]})" if tbl_desc_row else ""

        schema_text += f"=========================================\n"
        schema_text += f"Table: {table}{tbl_desc}\n"
        schema_text += f"=========================================\n"
        
        # 2. 컬럼 정보 + 설명 + PK/FK
        query = f"""
        SELECT 
            c.name AS ColumnName,
            t.name AS DataType,
            c.max_length AS MaxLength,
            c.is_nullable AS IsNullable,
            ISNULL(CAST(ep.value AS NVARCHAR(500)), '') AS Description,
            (SELECT COUNT(*) FROM sys.index_columns ic 
             INNER JOIN sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
             WHERE ic.object_id = c.object_id AND ic.column_id = c.column_id AND i.is_primary_key = 1) AS IsPK,
            (SELECT TOP 1 OBJECT_NAME(fkc.referenced_object_id) 
             FROM sys.foreign_key_columns fkc 
             WHERE fkc.parent_object_id = c.object_id AND fkc.parent_column_id = c.column_id) AS RefTable
        FROM sys.columns c
        INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
        LEFT JOIN sys.extended_properties ep 
            ON ep.major_id = c.object_id 
            AND ep.minor_id = c.column_id 
            AND ep.name = 'MS_Description'
        WHERE c.object_id = OBJECT_ID('{table}')
        ORDER BY c.column_id
        """
        cursor.execute(query)
        columns = cursor.fetchall()
        
        schema_text += "Columns:\n"
        for col in columns:
            col_name, data_type, max_length, is_nullable, description, is_pk, ref_table = col
            
            nullable = "NULL" if is_nullable else "NOT NULL"
            length = f"({max_length})" if max_length != -1 else ""
            
            pk_label = "[PK] " if is_pk > 0 else ""
            fk_label = f"[FK: {ref_table}] " if ref_table else ""
            desc = f" -- {description}" if description else "" 
            
            schema_text += f" - {pk_label}{fk_label}{col_name} ({data_type}{length}) {nullable}{desc}\n"
            
        schema_text += "\n"

    conn.close()
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(schema_text)
    
    print(f"✅ 스키마 추출 완료! '{OUTPUT_FILE}' 파일을 확인해보세요.")

if __name__ == "__main__":
    get_schema()