import pyodbc

conn_str = "Driver={ODBC Driver 18 for SQL Server};Server=127.0.0.1,59433;Database=DDU_ADMISSION;UID=sa;PWD=Ddu_admission!23;TrustServerCertificate=yes"
try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH, DATA_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME IN ('Sys_TableCatalog', 'Sys_ColumnCatalog', 'Sys_DocumentCatalog') 
          AND COLUMN_NAME IN ('description', 'ai_description')
    """)
    for row in cursor.fetchall():
        print(f"Table: {row[0]}, Column: {row[1]}, MaxLength: {row[2]}, DataType: {row[3]}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
