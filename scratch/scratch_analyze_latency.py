import pyodbc
from dotenv import load_dotenv
import os

load_dotenv('d:/Admission-Pilot/backend/.env')

conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={os.getenv('DB_HOST')};"
    f"DATABASE={os.getenv('DB_NAME')};"
    f"UID={os.getenv('DB_USER')};"
    f"PWD={os.getenv('DB_PASSWORD')};"
    f"TrustServerCertificate=yes"
)

cursor = conn.cursor()
cursor.execute('''
    SELECT TOP 10 
        log_id, 
        created_at, 
        prompt_tokens, 
        completion_tokens, 
        latency_ms, 
        user_question, 
        ai_response, 
        scraped_context 
    FROM Sys_AIAuditLog 
    WHERE scraped_context IS NOT NULL
    ORDER BY created_at DESC
''')

rows = cursor.fetchall()

print("="*80)
print(f"{'ID':<5} | {'Date':<20} | {'Latency(ms)':<15} | {'P_Tok':<8} | {'C_Tok':<8} | {'Scraped Length':<15}")
print("-" * 80)
for r in rows:
    scraped_len = len(r.scraped_context) if r.scraped_context else 0
    print(f"{r.log_id:<5} | {str(r.created_at)[:19]:<20} | {r.latency_ms:<15} | {r.prompt_tokens:<8} | {r.completion_tokens:<8} | {scraped_len:<15}")

print("="*80)
