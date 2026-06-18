import pyodbc

def main():
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=10.10.1.11,1433;"
        "DATABASE=DDU_ADMISSION;"
        "UID=admission_ai;"
        "PWD=fjk12#$;"
        "TrustServerCertificate=yes;"
    )
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()
    
    cur.execute("SELECT 입시학년도, 모집구분명, 지원학과명, 전형명 FROM UI_IPSI_M_V WHERE 입시학년도='2026' AND 지원학과명 LIKE '%응급구조과%' AND 전형명 LIKE '%순수외국인%'")
    rows = cur.fetchall()
    print("UI_IPSI_M_V:", rows)

    cur.execute("SELECT 학년도, 학과, 전형구분 FROM ADMISSIONCAPACITY WHERE 학년도='2026' AND 학과 LIKE '%응급구조과%' AND 전형구분 LIKE '%순수외국인%'")
    rows2 = cur.fetchall()
    print("ADMISSIONCAPACITY:", rows2)

main()
