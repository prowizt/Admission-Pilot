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

query = """
WITH QuotaCTE AS (
  SELECT [모집학과명] AS [학과명],
         SUM(CASE WHEN [전형명] = '재외국민및외국인' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [재외국민_모집인원],
         SUM(CASE WHEN [전형명] = '북한이탈주민' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [북한이탈주민_모집인원],
         SUM(CASE WHEN [전형명] = '순수외국인' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [순수외국인_모집인원],
         SUM(CASE WHEN [전형명] LIKE '%장애%' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [장애인_모집인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [대학졸업자_모집인원],
         SUM(CASE WHEN [전형명] = '만학도' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [만학도_모집인원],
         SUM(CASE WHEN [전형명] = '농어촌' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [농어촌_모집인원],
         SUM(CASE WHEN [전형명] LIKE '%재직자%' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [특성화고재직자_모집인원],
         SUM(CASE WHEN [전형명] = '기초생활수급자' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [기초생활수급자_모집인원],
         SUM(CASE WHEN [전형명] LIKE '%서해%' THEN CASE WHEN [모집인원] = '제한없음' THEN 0 ELSE CAST([모집인원] AS INT) END ELSE 0 END) AS [서해5도_모집인원]
  FROM [ADMISSIONQUOTA]
  WHERE [입시년도] = '2026' AND [정원내외구분] = '정원외'
  GROUP BY [모집학과명]), IpsiCTE AS (
  SELECT [지원학과명] AS [학과명],
         SUM(CASE WHEN [전형명] = '재외국민및외국인' THEN 1 ELSE 0 END) AS [재외국민_지원인원],
         SUM(CASE WHEN [전형명] = '재외국민및외국인' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [재외국민_등록인원],
         SUM(CASE WHEN [전형명] = '북한이탈주민' THEN 1 ELSE 0 END) AS [북한이탈주민_지원인원],
         SUM(CASE WHEN [전형명] = '북한이탈주민' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [북한이탈주민_등록인원],
         SUM(CASE WHEN [전형명] = '순수외국인' THEN 1 ELSE 0 END) AS [순수외국인_지원인원],
         SUM(CASE WHEN [전형명] = '순수외국인' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [순수외국인_등록인원],
         SUM(CASE WHEN [전형명] LIKE '%장애%' THEN 1 ELSE 0 END) AS [장애인_지원인원],
         SUM(CASE WHEN [전형명] LIKE '%장애%' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [장애인_등록인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' THEN 1 ELSE 0 END) AS [대학졸업자_지원인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [대학졸업자_등록인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND ([대학구분명] LIKE '%2%' OR [대학구분명] LIKE '%3%') THEN 1 ELSE 0 END) AS [대학졸업자_2년제_지원인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND ([대학구분명] LIKE '%2%' OR [대학구분명] LIKE '%3%') AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [대학졸업자_2년제_등록인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND [대학구분명] LIKE '%4%' AND [대학졸업구분명] = '수료' THEN 1 ELSE 0 END) AS [대학졸업자_4년제수료_지원인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND [대학구분명] LIKE '%4%' AND [대학졸업구분명] = '수료' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [대학졸업자_4년제수료_등록인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND [대학구분명] LIKE '%4%' AND [대학졸업구분명] IN ('졸업',' 졸업예정') THEN 1 ELSE 0 END) AS [대학졸업자_4년제졸업_지원인원],
         SUM(CASE WHEN [전형명] = '대학졸업자' AND [대학구분명] LIKE '%4%' AND [대학졸업구분명] IN ('졸업',' 졸업예정') AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [대학졸업자_4년제졸업_등록인원],
         SUM(CASE WHEN [전형명] = '만학도' THEN 1 ELSE 0 END) AS [만학도_지원인원],
         SUM(CASE WHEN [전형명] = '만학도' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [만학도_등록인원],
         SUM(CASE WHEN [전형명] = '농어촌' THEN 1 ELSE 0 END) AS [농어촌_지원인원],
         SUM(CASE WHEN [전형명] = '농어촌' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [농어촌_등록인원],
         SUM(CASE WHEN [전형명] LIKE '%재직자%' THEN 1 ELSE 0 END) AS [특성화고재직자_지원인원],
         SUM(CASE WHEN [전형명] LIKE '%재직자%' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [특성화고재직자_등록인원],
         SUM(CASE WHEN [전형명] = '기초생활수급자' THEN 1 ELSE 0 END) AS [기초생활수급자_지원인원],
         SUM(CASE WHEN [전형명] = '기초생활수급자' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [기초생활수급자_등록인원],
         SUM(CASE WHEN [전형명] LIKE '%서해%' THEN 1 ELSE 0 END) AS [서해5도_지원인원],
         SUM(CASE WHEN [전형명] LIKE '%서해%' AND [최종입시결과] = '최종등록자(최종합격자)' THEN 1 ELSE 0 END) AS [서해5도_등록인원]
  FROM [UI_IPSI_M_V]
  WHERE [입시학년도] = '2026' AND [신입편입구분] = '신입' AND [정원내외명] = '정원외'
  GROUP BY [지원학과명])
  SELECT COALESCE(q.[학과명], i.[학과명]) AS [학과명],
         COALESCE(q.[재외국민_모집인원], 0) AS [재외국민_모집인원],
         COALESCE(i.[재외국민_지원인원], 0) AS [재외국민_지원인원],
         COALESCE(i.[재외국민_등록인원], 0) AS [재외국민_등록인원],
         COALESCE(q.[북한이탈주민_모집인원], 0) AS [북한이탈주민_모집인원],
         COALESCE(i.[북한이탈주민_지원인원], 0) AS [북한이탈주민_지원인원],
         COALESCE(i.[북한이탈주민_등록인원], 0) AS [북한이탈주민_등록인원],
         COALESCE(q.[순수외국인_모집인원], 0) AS [순수외국인_모집인원],
         COALESCE(i.[순수외국인_지원인원], 0) AS [순수외국인_지원인원],
         COALESCE(i.[순수외국인_등록인원], 0) AS [순수외국인_등록인원],
         COALESCE(q.[장애인_모집인원], 0) AS [장애인_모집인원],
         COALESCE(i.[장애인_지원인원], 0) AS [장애인_지원인원],
         COALESCE(i.[장애인_등록인원], 0) AS [장애인_등록인원],
         COALESCE(q.[대학졸업자_모집인원], 0) AS [대학졸업자_모집인원],
         COALESCE(i.[대학졸업자_지원인원], 0) AS [대학졸업자_지원인원],
         COALESCE(i.[대학졸업자_등록인원], 0) AS [대학졸업자_등록인원],
         COALESCE(i.[대학졸업자_2년제_지원인원], 0) AS [대학졸업자_2년제_지원인원],
         COALESCE(i.[대학졸업자_2년제_등록인원], 0) AS [대학졸업자_2년제_등록인원],
         COALESCE(i.[대학졸업자_4년제수료_지원인원], 0) AS [대학졸업자_4년제수료_지원인원],
         COALESCE(i.[대학졸업자_4년제수료_등록인원], 0) AS [대학졸업자_4년제수료_등록인원],
         COALESCE(i.[대학졸업자_4년제졸업_지원인원], 0) AS [대학졸업자_4년제졸업_지원인원],
         COALESCE(i.[대학졸업자_4년제졸업_등록인원], 0) AS [대학졸업자_4년제졸업_등록인원],
         COALESCE(q.[만학도_모집인원], 0) AS [만학도_모집인원],
         COALESCE(i.[만학도_지원인원], 0) AS [만학도_지원인원],
         COALESCE(i.[만학도_등록인원], 0) AS [만학도_등록인원],
         COALESCE(q.[농어촌_모집인원], 0) AS [농어촌_모집인원],
         COALESCE(i.[농어촌_지원인원], 0) AS [농어촌_지원인원],
         COALESCE(i.[농어촌_등록인원], 0) AS [농어촌_등록인원],
         COALESCE(q.[특성화고재직자_모집인원], 0) AS [특성화고재직자_모집인원],
         COALESCE(i.[특성화고재직자_지원인원], 0) AS [특성화고재직자_지원인원],
         COALESCE(i.[특성화고재직자_등록인원], 0) AS [특성화고재직자_등록인원],
         COALESCE(q.[기초생활수급자_모집인원], 0) AS [기초생활수급자_모집인원],
         COALESCE(i.[기초생활수급자_지원인원], 0) AS [기초생활수급자_지원인원],
         COALESCE(i.[기초생활수급자_등록인원], 0) AS [기초생활수급자_등록인원],
         COALESCE(q.[서해5도_모집인원], 0) AS [서해5도_모집인원],
         COALESCE(i.[서해5도_지원인원], 0) AS [서해5도_지원인원],
         COALESCE(i.[서해5도_등록인원], 0) AS [서해5도_등록인원]
  FROM QuotaCTE q FULL OUTER
  JOIN IpsiCTE i ON q.[학과명] = i.[학과명];
"""

try:
    conn = pyodbc.connect(conn_str, autocommit=True)
    conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp949')
    conn.setdecoding(pyodbc.SQL_WCHAR, encoding='cp949')
    conn.setencoding(encoding='cp949')
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    
    with open("scratch_query_result.txt", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(str(row) + "\n")
            
except Exception as e:
    print(f"Error: {e}")
