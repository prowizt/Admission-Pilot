
from backend.main import get_mssql_connection
conn = get_mssql_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM UI_IPSI_M_V WHERE 입시학년도=''2026'' AND 정원내외명=''정원외''')
print('Rows 2026 정원외:', cursor.fetchone()[0])
cursor.execute('SELECT TOP 5 전형명, 최종입시결과 FROM UI_IPSI_M_V WHERE 입시학년도=''2026'' AND 정원내외명=''정원외''')
print(cursor.fetchall())

