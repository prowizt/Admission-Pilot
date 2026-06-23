import pyodbc

conn_str = 'DRIVER={ODBC Driver 18 for SQL Server};SERVER=10.10.1.11,1433;DATABASE=DDU_ADMISSION;UID=admission_ai;PWD=fjk12#$;TrustServerCertificate=yes;'
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()
cursor.execute("SELECT filename, is_public FROM Sys_DocumentCatalog WHERE filename LIKE '%2026%'")
for row in cursor.fetchall():
    print(row.filename, row.is_public)
