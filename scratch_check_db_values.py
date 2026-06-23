import pyodbc
import json

conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=10.10.1.11,1433;"
    "DATABASE=DDU_ADMISSION;"
    "UID=admission_ai;"
    "PWD=fjk12#$;"
    "TrustServerCertificate=yes;"
)

try:
    conn = pyodbc.connect(conn_str, autocommit=True)
    conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp949')
    conn.setdecoding(pyodbc.SQL_WCHAR, encoding='cp949')
    conn.setencoding(encoding='cp949')
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT 모집학과명 FROM ADMISSIONQUOTA WHERE 입시년도 = '2026'")
    quota_depts = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT 지원학과명 FROM UI_IPSI_M_V WHERE 입시학년도 = '2026'")
    ipsi_depts = [row[0] for row in cursor.fetchall()]
    
    with open("scratch_db_depts.txt", "w", encoding="utf-8") as f:
        f.write("ADMISSIONQUOTA depts: " + json.dumps(quota_depts, ensure_ascii=False) + "\n")
        f.write("UI_IPSI_M_V depts: " + json.dumps(ipsi_depts, ensure_ascii=False) + "\n")
        
except Exception as e:
    print(f"Error: {e}")
