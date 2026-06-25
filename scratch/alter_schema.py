import pyodbc

conn_str = "Driver={ODBC Driver 18 for SQL Server};Server=127.0.0.1,59433;Database=DDU_ADMISSION;UID=sa;PWD=Ddu_admission!23;TrustServerCertificate=yes"
try:
    conn = pyodbc.connect(conn_str, autocommit=True)
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE Sys_TableCatalog ALTER COLUMN description NVARCHAR(MAX)")
    print("Altered Sys_TableCatalog")
    cursor.execute("ALTER TABLE Sys_ColumnCatalog ALTER COLUMN ai_description NVARCHAR(MAX)")
    print("Altered Sys_ColumnCatalog")
    cursor.execute("ALTER TABLE Sys_DocumentCatalog ALTER COLUMN description NVARCHAR(MAX)")
    print("Altered Sys_DocumentCatalog")
    conn.close()
    print("Done")
except Exception as e:
    print(f"Error: {e}")
