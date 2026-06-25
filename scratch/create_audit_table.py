import pyodbc
from backend.main import get_mssql_connection

def create_table():
    conn = get_mssql_connection()
    if not conn:
        print("DB Connection Failed")
        return

    cursor = conn.cursor()
    try:
        # Create Table
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Sys_AIAuditLog' AND xtype='U')
        BEGIN
            CREATE TABLE Sys_AIAuditLog (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_role VARCHAR(50),
                model_name VARCHAR(100),
                question NVARCHAR(MAX),
                scraped_context NVARCHAR(MAX),
                sql_query NVARCHAR(MAX),
                rag_query NVARCHAR(MAX),
                answer NVARCHAR(MAX),
                latency_ms INT,
                created_at DATETIME DEFAULT GETDATE()
            )
            print('Table created successfully.')
        END
        ELSE
        BEGIN
            print('Table already exists.')
        END
        """)

        # Add Extended Properties (한글 주석)
        properties = [
            ("TABLE", "Sys_AIAuditLog", None, "AI 챗봇 대화 및 모니터링 로그"),
            ("COLUMN", "Sys_AIAuditLog", "user_role", "사용자 직군(부서)"),
            ("COLUMN", "Sys_AIAuditLog", "model_name", "사용된 AI 모델명"),
            ("COLUMN", "Sys_AIAuditLog", "question", "사용자 실제 질문 원문"),
            ("COLUMN", "Sys_AIAuditLog", "scraped_context", "참고한 웹/스크랩 텍스트"),
            ("COLUMN", "Sys_AIAuditLog", "sql_query", "생성된 T-SQL 쿼리 (없으면 NONE)"),
            ("COLUMN", "Sys_AIAuditLog", "rag_query", "RAG 문서 검색 키워드"),
            ("COLUMN", "Sys_AIAuditLog", "answer", "AI가 응답한 최종 답변"),
            ("COLUMN", "Sys_AIAuditLog", "latency_ms", "응답 소요 시간(ms)"),
            ("COLUMN", "Sys_AIAuditLog", "created_at", "로그 생성 일시")
        ]

        for prop_type, table, column, desc in properties:
            try:
                if prop_type == "TABLE":
                    cursor.execute(f"""
                    IF NOT EXISTS (SELECT NULL FROM sys.extended_properties WHERE major_id = OBJECT_ID('{table}') AND name = 'MS_Description' AND minor_id = 0)
                    EXEC sp_addextendedproperty 'MS_Description', '{desc}', 'SCHEMA', 'dbo', 'TABLE', '{table}';
                    """)
                else:
                    cursor.execute(f"""
                    IF NOT EXISTS (SELECT NULL FROM sys.extended_properties WHERE major_id = OBJECT_ID('{table}') AND name = 'MS_Description' AND minor_id = (SELECT column_id FROM sys.columns WHERE object_id = OBJECT_ID('{table}') AND name = '{column}'))
                    EXEC sp_addextendedproperty 'MS_Description', '{desc}', 'SCHEMA', 'dbo', 'TABLE', '{table}', 'COLUMN', '{column}';
                    """)
            except Exception as pe:
                print(f"Property add error for {table}.{column}: {pe}")
        
        conn.commit()
        print("Extended properties added successfully.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    create_table()
