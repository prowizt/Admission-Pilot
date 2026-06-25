import pyodbc

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
    cursor.execute("SELECT column_name FROM Sys_ColumnCatalog")
    cols = [row[0] for row in cursor.fetchall()]
    with open("catalog_cols.txt", "w", encoding="utf-8") as f:
        for c in cols:
            f.write(c + "\n")
except Exception as e:
    print(f"Error: {e}")
