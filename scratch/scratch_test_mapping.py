import os
import requests
import json

API_KEY = "AIzaSyC_StkUWAe9PL5FBuKnWdQ3UyX5-Lte5aE"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

sql_context = """
[
  {"학과명": "간호학부", "재외국민_모집인원": 0, "재외국민_지원인원": 0, "대학졸업자_지원인원": 253},
  {"학과명": "토탈미용과", "재외국민_모집인원": 0, "대학졸업자_지원인원": 18}
]
"""
empty_cells_info = [
    {"row": 2, "A_입시학년도": 2026, "C_지원학과명": "간호학부", "E_전형명": "대학졸업자", "F_모집인원": "[]", "G_지원인원": "[]"},
    {"row": 3, "A_입시학년도": 2026, "C_지원학과명": "토탈미용과", "E_전형명": "대학졸업자", "F_모집인원": "[]", "G_지원인원": "[]"},
]

prompt = f"""
[사용자 질문]
2026학년도 DB에서 매핑시켜 채워줘. 모집인원의 경우 제한없음인경우 0 으로 채워줘, 우리대학교는 야간이 없으므로 0 으로 모두 채우면돼

[1. 정형 DB 추출 통계 데이터]
{sql_context}

[2. 비정형 PDF 추출 규정 문서 참조 내용]
검색된 비정형 문서가 없습니다.

[엑셀 빈 셀 구조]
{json.dumps(empty_cells_info, ensure_ascii=False)}

[주의 사항 (환각 방지 및 병합된 셀 처리)]
- 사용자가 데이터 추출을 요청한 대상 연도는 '2026'학년도입니다. 
- 만약 [비정형 PDF 추출 규정 문서]에 '2026'학년도에 해당하는 데이터가 부족하거나 없다면, 절대로 다른 연도(예: 2027년도)의 데이터를 상상해서 지어내거나 억지로 채워 넣지 마십시오. (데이터가 없으면 0으로 처리하십시오).

[출력 지침]
- 출력은 무조건 JSON 형식
"""

payload = {
    "contents": [{"parts": [{"text": prompt}]}]
}

try:
    response = requests.post(URL, json=payload, timeout=30)
    data = response.json()
    print(data['candidates'][0]['content']['parts'][0]['text'])
except Exception as e:
    print(f"Error: {e}")
