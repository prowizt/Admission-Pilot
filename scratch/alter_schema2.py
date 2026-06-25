import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.main import get_mssql_connection

try:
    conn = get_mssql_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE Sys_TableCatalog ALTER COLUMN description NVARCHAR(MAX)")
        print("Altered Sys_TableCatalog")
        cursor.execute("ALTER TABLE Sys_ColumnCatalog ALTER COLUMN ai_description NVARCHAR(MAX)")
        print("Altered Sys_ColumnCatalog")
        cursor.execute("ALTER TABLE Sys_DocumentCatalog ALTER COLUMN description NVARCHAR(MAX)")
        print("Altered Sys_DocumentCatalog")
        conn.commit()
        conn.close()
        print("Done")
    else:
        print("Could not connect to DB")
except Exception as e:
    print(f"Error: {e}")
