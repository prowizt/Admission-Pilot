import io
import json
import re
import os
import time
import base64
import urllib.parse
import openpyxl
import asyncio
import re
from decimal import Decimal
from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Form
import google.generativeai as genai

router = APIRouter()

def extract_excel_structure(ws):
    """
    빈 셀의 좌표와 해당 셀이 위치한 행/열의 문맥(헤더) 정보를 추출합니다.
    """
    empty_cells = []
    max_row = min(ws.max_row, 50)
    max_col = min(ws.max_column, 50)
    
    headers = {}
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            val = ws.cell(row=r, column=c).value
            if val is not None and str(val).strip() != "":
                headers[(r, c)] = str(val).strip()

    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            if cell.value is None or str(cell.value).strip() == "":
                left_headers = [headers[(r, i)] for i in range(1, c) if (r, i) in headers]
                top_headers = [headers[(i, c)] for i in range(1, r) if (i, c) in headers]
                
                # 좌측 헤더나 상단 헤더 중 하나라도 있으면 유효한 빈 셀로 간주 (유연성 확보)
                if left_headers or top_headers:
                    empty_cells.append({
                        "coord": cell.coordinate,
                        "row_headers": " > ".join(left_headers),
                        "col_headers": " > ".join(top_headers)
                    })
    # 기존에 입력된 데이터(주로 헤더) 정보를 문자열로 요약
    existing_data_summary = []
    for (r, c), val in headers.items():
        existing_data_summary.append(f"셀({ws.cell(row=r, column=c).coordinate}): {val}")
        
    return empty_cells, "\n".join(existing_data_summary)

@router.post("/chat-excel-autofill")
async def chat_excel_autofill(
    file: UploadFile = File(...), 
    question: str = Form(...),
    user_role: str = Form("staff"),
    model_name: str = Form("gemini-2.5-flash"),
    history: str = Form("[]"),
    scraped_context: str = Form(None),
    scraped_file_name: str = Form(None),
    x_gemini_key: str = Header(None)
):
    # 순환 참조 방지를 위해 함수 내부에서 import
    from main import get_mssql_connection, get_dynamic_db_schema, format_sql_query, mask_pii

    start_time = time.time()
    print(f"\n[EXCEL-AUTOFILL] 🚀 하이브리드 채팅 엑셀 자동 채우기 요청 수신 (질문: {question})")
    
    if question:
        question = mask_pii(question)
        
    if not x_gemini_key:
        raise HTTPException(status_code=401, detail="Gemini API Key가 필요합니다.")
        
    try:
        genai.configure(api_key=x_gemini_key)
        conn = get_mssql_connection()
        dynamic_schema = get_dynamic_db_schema(conn, user_role) if conn else "DB 연결 불가"
        
        pre_supplemental_text = ""
        if conn:
            try:
                pre_cursor = conn.cursor()
                pre_cursor.execute("SELECT category, content FROM Sys_SupplementalKnowledge WHERE is_active = 'Y' ORDER BY category ASC, id ASC")
                for r in pre_cursor.fetchall():
                    pre_supplemental_text += f"- [{r[0]}] {r[1]}\n"
            except Exception as e:
                print(f"사전지식 선행 조회 오류: {e}")
        
        # 1. 엑셀 파싱
        file_bytes = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        empty_cells_info, existing_data_context = extract_excel_structure(ws)
        print(f"[EXCEL-AUTOFILL] 📊 1단계: 엑셀 파악 완료 (빈 셀 {len(empty_cells_info)}개, 기존 데이터 {len(existing_data_context.split(chr(10))) if existing_data_context else 0}개 감지)")
        
        # 2. Text-to-SQL (라우터) 구동
        print("[EXCEL-AUTOFILL] 🧠 2단계: AI 통계 SQL 쿼리 설계 중...")
        sql_router_prompt = f"""
        너는 대동대학교 입시처의 [엑셀 매핑 전문 데이터 아키텍트]야.
        사용자가 첨부한 엑셀 파일의 빈 칸을 채우기 위해 필요한 통계 데이터를 DB에서 추출하는 T-SQL 쿼리를 하나 작성해야 해.

        [관리자 등록 최상위 사전지식]
        {pre_supplemental_text if pre_supplemental_text else "등록된 사전지식 없음"}
        - 위 [관리자 등록 최상위 사전지식]에 명시된 규칙은 질문의 의도 파악과 SQL 쿼리 설계 시 절대적으로 준수해야 하는 1순위 예외 규칙입니다.
        
        [기본 사전 지식 주입]
        1. [입시 학년도 정의]: 대학교 입시에서 'N학년도 전형(모집요강)'은 'N-1년도'에 모집을 실시하는 전형을 뜻합니다. (예: 2027학년도 모집요강 = 2026년 가을/겨울에 모집 실시). 사용자가 질문한 연도가 '실시 연도'인지 '입학 학년도'인지 문맥을 파악하여 SQL을 정확히 일치시키세요.
        2. [일반 학년도 정의]: 학년도(예: 2026학년도)는 3월 1일부터 다음 해 2월 말일까지를 의미합니다. (예: 2026학년도 = 2026.03 ~ 2027.02).
        3. [신입/편입 구분]: 대학 입학 결과에는 신입생 뿐만 아니라 '편입생'도 존재합니다. 사용자가 특정 전형만 지정하지 않고 종합 검토를 요청하는 경우, '신입'과 '편입' 데이터를 구분하여 각각 조회하거나 한꺼번에 수집하도록 T-SQL을 구성하세요.
        4. [정원내 및 정원외 전형 구분 규칙]: 대학 학칙상 명시된 '입학정원'은 오직 정원내 전형에만 적용됩니다. 정원외 전형은 정원 제한을 받지 않으므로, DB 데이터와 입학정원을 대조/통계 낼 때는 반드시 정원내와 정원외 전형을 명확하게 분리(GROUP BY 또는 CASE WHEN)하여 집계하십시오.
        5. [지역명 약어 자동 변환 규칙]: 사용자가 질문에 '부울경'이라고 입력하면 반드시 `[출신고교시도] LIKE '%부산%' OR [출신고교시도] LIKE '%울산%' OR [출신고교시도] LIKE '%경상남도%'` 형태로 검색하십시오. '경남' 등은 '경상남도'로 정식 명칭 변환하십시오.

        [가장 중요한 SQL 작성 규칙]
        1. 컬럼명이 한글일 수 있으므로 대괄호 []를 반드시 사용해.
        2. **[띄어쓰기 절대 금지]** 대괄호 `[]` 내부의 테이블명과 컬럼명에는 절대로 공백이나 띄어쓰기를 임의로 넣지 마세요. 카탈로그에 표시된 문자열 철자를 공백 없이 100% 동일하게 따라야 합니다. (예: `[입시학 년도]`가 아닌 `[입시학년도]`, `[전형 명]`이 아닌 `[전형명]`)
        3. **[별칭(Alias) 공백 금지 및 대괄호 필수]** `AS [일 반전형_모집인원]` 처럼 별칭 대괄호 안에 띄어쓰기가 들어가면 T-SQL 문법 오류가 발생하여 시스템이 붕괴됩니다. 무조건 띄어쓰기를 제거하세요. (정상 예: `AS [일반전형_모집인원]`)
        4. **[문자열 비교 공백 엄수]** 조건절에서 문자열을 비교할 때 카탈로그나 DB 원본에 정의된 문자열 구조를 임의로 띄어쓰지 마세요. 무조건 원본(`'최종등록자(최종합격자)'`)과 토씨 하나 틀리지 않게 동일하게 작성하세요.
        5. **[신입/편입 구분 및 정원내/외 조건]** 통계를 낼 때 신입생과 편입생, 정원내/외를 명확하게 분리(CASE WHEN 등)하세요.
        6. **[LIKE 검색어 공백 절대 금지]** 문자열 조건은 무조건 `=` 대신 `LIKE`를 사용하되, **LIKE '%...%' 구문 안에 절대로 띄어쓰기나 공백을 자의적으로 넣지 마세요.** (예: `LIKE '%수능 전형%'` 절대 불가, `LIKE '%수능전형%'` 정상)
        8. **[학년도 자동 추출 강제]** 사용자가 명시적으로 학년도를 말하지 않더라도, [첨부 엑셀 파일명]이나 [질문]에 기재된 연도(예: 2026학년도)를 찾아내어 반드시 `WHERE [입시학년도] = '2026'` 과 같이 학년도 조건을 쿼리에 강제 삽입하세요.
        9. **[DB에 없는 모집인원 등 억지 계산 금지]** 엑셀 표에 전형별 '모집인원'이나 '계획인원' 빈칸이 있더라도, `UI_IPSI_M_V` 등 지원자 원천 DB에는 전형별 모집 정원 데이터가 없습니다. 절대 `[합격구분명] LIKE '%합격%'` 등을 '모집인원'으로 억지로 둔갑시켜 계산하지 마십시오. (합격자 수와 모집인원은 완전히 다른 개념입니다). 알 수 없는 데이터는 무리해서 구하지 말고, 확실한 '지원인원', '최종등록인원', `ADMISSIONCAPACITY`의 '전체 입학정원'만 조회하십시오.
        10. **[순수 통계 목적 외 UNION ALL 남용 금지]** 아래 엑셀 빈 셀 구조는 단지 "어떤 지표들을 찾아야 하는지" 알려주는 힌트일 뿐입니다. 엑셀 모양과 동일하게 만들기 위해 야간 학과나 0으로 채워진 더미(dummy) 행, 합계 행을 억지로 UNION ALL로 만들지 마십시오. DB에 실존하는 데이터만 단순 GROUP BY로 가볍게 뽑아주면, 매핑은 2단계 AI가 알아서 합니다.
        11. **[지역 필터링 주의]** 엑셀 구조에 '지역(예: 부산)' 칸이 있더라도 이는 단순 학교 소재지입니다. 사용자가 질문에서 명시적으로 "부산 출신 학생만 찾아줘"라고 요구하지 않는 한, 절대로 `WHERE [출신고교시도] LIKE '%부산%'` 조건을 억지로 추가하여 데이터를 축소시키지 마십시오. (전국 모든 지원자를 대상으로 해야 합니다).
        12. **[ORDER BY 절대 사용 금지 (8127 에러 원천 차단)]** MS-SQL에서는 가공된 GROUP BY와 ORDER BY의 컬럼이 조금만 달라도 8127 구문 오류가 발생하여 시스템이 마비됩니다. 어차피 데이터 매핑은 2단계 AI가 알아서 매칭하므로 사람이 보기 좋게 정렬할 필요가 전혀 없습니다. **어떠한 경우에도 쿼리 마지막에 `ORDER BY` 절을 작성하지 마십시오!**

        [데이터베이스 스키마 및 힌트]
        (아래 스키마의 ai_description에 적힌 값(힌트)들을 꼼꼼히 확인하고 쿼리를 작성하세요)
        {dynamic_schema}

        [첨부 엑셀 파일명 (기준 학년도/학기 유추에 활용)]
        {file.filename}

        [엑셀 빈 셀 구조 (이 셀들을 채우기 위한 데이터가 필요함)]
        {json.dumps(empty_cells_info, ensure_ascii=False)}

        [사용자 질문/지시]
        {question}

        [출력 지침]
        오직 순수 JSON 형식으로만 응답해. 마크다운 기호 금지.
        {{
            "sql_query": "엑셀의 빈칸을 모두 채울 수 있는 포괄적인 T-SQL SELECT 문 (반드시 위 규칙들을 엄수한 무결결점 SQL)"
        }}
        """
        
        router_api_key = os.getenv("ROUTER_API_KEY", "")
        router_model_name = os.getenv("ROUTER_MODEL", "gemini-2.5-flash")
        
        if router_api_key and router_api_key != "여기에_새로운_API키를_입력하세요":
            genai.configure(api_key=router_api_key)
            sql_model = genai.GenerativeModel(router_model_name)
        else:
            sql_model = genai.GenerativeModel(model_name)
            
        sql_response = await sql_model.generate_content_async(sql_router_prompt)
        
        if router_api_key and router_api_key != "여기에_새로운_API키를_입력하세요":
            genai.configure(api_key=x_gemini_key)
            
        # JSON 파싱
        try:
            response_text = sql_response.text.strip()
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()
                
            parsed_json = json.loads(response_text)
            sql_query = parsed_json.get("sql_query", "NONE")
            
            # [2차 절대 방어선] 정규식을 이용해 대괄호 [ ] 내부의 모든 종류의 공백(띄어쓰기, 줄바꿈, 탭 등) 강제 삭제
            # 예: [수험 번호] 또는 [수험\n번호] -> [수험번호]
            if sql_query and sql_query != "NONE":
                sql_query = re.sub(r'\[([^\]]+)\]', lambda m: '[' + re.sub(r'\s+', '', m.group(1)) + ']', sql_query)
                
        except Exception as e:
            print(f"[EXCEL-AUTOFILL] SQL JSON 파싱 오류: {e}")
            sql_query = "NONE"
            
        sql_query = format_sql_query(sql_query)
        original_sql_query = sql_query
        
        # 8127 구문 에러 원천 차단을 위해 ORDER BY 절 강제 제거 (매핑 AI는 정렬 불필요)
        sql_query = re.sub(r'(?i)\s*ORDER\s+BY\s+.*', '', sql_query).strip()
        if not sql_query.endswith(';'):
            sql_query += ';'

        print(f"[EXCEL-AUTOFILL] [QUERY] AI 원본 쿼리문:")
        print("--- T-SQL START ---")
        print(original_sql_query)
        print("--- T-SQL END ---")
        
        print(f"[EXCEL-AUTOFILL] [QUERY] 파이썬 보정 후 실제 실행 쿼리문:")
        print("--- T-SQL START ---")
        print(sql_query)
        print("--- T-SQL END ---")
        
        # 3. 쿼리 실행
        sql_context = "추출된 DB 데이터 없음"
        if sql_query.upper().startswith("SELECT") and conn:
            try:
                print("[EXCEL-AUTOFILL] 🔍 3단계: 통계 DB 데이터 획득 중...")
                cursor = conn.cursor()
                cursor.execute(sql_query)
                cols = [column[0] for column in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                
                for r in rows:
                    for k, v in r.items():
                        if hasattr(v, 'isoformat'):
                            r[k] = v.isoformat()
                        elif isinstance(v, Decimal):
                            r[k] = float(v)
                sql_context = json.dumps(rows, ensure_ascii=False)
            except Exception as e:
                # DB 에러 발생 시 2단계 AI로 넘어가면 가짜(환각) 데이터를 생성하므로 즉시 에러를 던져 중단합니다.
                error_msg = f"DB 쿼리 실행 중 오류가 발생했습니다: {str(e)}\n\n[AI 원본 쿼리]\n{original_sql_query}\n\n[실제 실행 쿼리]\n{sql_query}"
                print(f"[EXCEL-AUTOFILL] DB 에러 (즉시 중단): {e}")
                raise HTTPException(status_code=500, detail=error_msg)
            finally:
                conn.close()

        # [NEW] 3.5단계: 비정형 DB(ChromaDB)에서 모집요강만 한정하여 RAG 검색
        print("[EXCEL-AUTOFILL] 📚 3.5단계: 비정형 DB에서 모집요강 '모집인원' 문서 검색 중...")
        chroma_context = "검색된 모집요강 문서가 없습니다."
        try:
            from main import rule_db, reference_db
            # 파일명에서 학년도 자동 추출, 없으면 질문에서 추출
            year_match = re.search(r'(202\d)', file.filename)
            if not year_match:
                year_match = re.search(r'(202\d)', question)
            target_year = year_match.group(1) if year_match else "ALL"
            
            # 파일명 한글 깨짐(Mojibake) 버그를 우회하기 위해 filename 필터 전면 삭제.
            # 오직 의미론적 유사도(Semantic Search)로만 문서 탐색
            query_texts = ["학과별 전형별 입학 정원 모집인원 계획"]
            
            if target_year != "ALL":
                where_clause = {"year": {"$in": [target_year, "ALL"]}}
                res_rule = rule_db.query(query_texts=query_texts, n_results=100, where=where_clause)
                res_ref = reference_db.query(query_texts=query_texts, n_results=100, where=where_clause)
            else:
                res_rule = rule_db.query(query_texts=query_texts, n_results=100)
                res_ref = reference_db.query(query_texts=query_texts, n_results=100)
            
            doc_texts = []
            for res in [res_rule, res_ref]:
                if res and res.get("documents") and res["documents"][0]:
                    for i, doc_text in enumerate(res["documents"][0]):
                        meta = res["metadatas"][0][i] if res.get("metadatas") else {}
                        fname = meta.get("filename", "이름없음")
                        doc_texts.append(f"[{fname}]\n{doc_text}")
                
            if doc_texts:
                # 100개 이상의 청크(전체 PDF 분량)를 그대로 결합하여 테이블 누락 방지!
                chroma_context = "\n\n".join(doc_texts[:200])
                print(f"[EXCEL-AUTOFILL] 📚 검색 성공: {len(doc_texts)}개의 모집요강 문단(전체) 참조 (rule+reference)")
            else:
                print("[EXCEL-AUTOFILL] 📚 검색된 모집요강 문단이 없습니다.")
        except Exception as e:
            print(f"[EXCEL-AUTOFILL] ⚠️ ChromaDB 모집요강 검색 오류 (무시됨): {e}")

        # 4. 최종 매핑 AI 구동
        print("[EXCEL-AUTOFILL] 🧠 4단계: 최종 엑셀 매핑 및 답변 생성 중...")
        final_prompt = f"""
        너는 대동대학교 입시처의 [엑셀 데이터 매핑 AI]야.

        [사용자 질문]
        {question}

        [관리자 등록 최상위 사전지식]
        {pre_supplemental_text if pre_supplemental_text else "등록된 사전지식 없음"}
        - 위 사전지식은 엑셀에 데이터를 매핑할 때 반드시 준수해야 하는 행정 룰입니다.

        [🚨 사용자 특별 지시사항 (최우선 적용 규칙) 🚨]
        - 사용자의 [사용자 질문] 내에 엑셀 값 입력과 관련된 명시적인 조건이나 제약(예: "제한없음은 제한없음으로 써라", "하이픈(-)은 제외하라", "쿼리나 DB를 보지 말고 요강만 보아라" 등)이 있다면, **아래의 모든 기본 출력 지침보다 사용자의 이 지시를 최우선으로, 그리고 완벽하게 따르십시오!**

        [주의 사항 (환각 방지 및 병합된 셀 처리)]
        - 사용자가 데이터 추출을 요청한 대상 연도는 '{target_year}'학년도입니다. 
        - 만약 [비정형 PDF 추출 규정 문서]에 '{target_year}'학년도에 해당하는 데이터가 부족하거나 없다면, 절대로 다른 연도(예: 2027년도)의 데이터를 상상해서 지어내거나 억지로 채워 넣지 마십시오. (데이터가 없으면 0으로 처리하십시오).
        - 💡 **[PDF 표 병합(Merge) 데이터 추론 규칙]**: 한국어 PDF 모집요강 문서의 표(Table) 특성상, 인접한 두 학과의 모집인원이 동일할 경우 셀이 병합되어 텍스트 추출 시 **첫 번째 학과에만 값이 적히고 그 아래 학과는 값이 누락된 것(빈칸)처럼 보일 수 있습니다.** (예: 치위생과 순수외국인 '제한없음', 그 바로 밑줄에 응급구조과 순수외국인 '빈칸'). 만약 특정 학과 전형의 모집인원 값이 비어있다면, **반드시 바로 위(또는 근처) 학과의 동일 전형 값을 확인하고, 병합된 셀이라고 판단되면 그 값을 똑같이 상속(복사)하여 채워 넣으십시오.**

        [데이터베이스 스키마 및 힌트]
        (각 테이블과 컬럼의 의미(ai_description)를 참고하여 아래 추출된 통계 데이터의 맥락을 이해하세요.)
        {dynamic_schema}

        [1. 정형 DB 추출 통계 데이터 (지원자/등록자 수)]
        {sql_context}
        
        [2. 비정형 PDF 추출 규정 문서 (학과별/전형별 모집인원 등)]
        {chroma_context}
        
        [첨부 엑셀 파일명]
        {file.filename}

        [현재 엑셀 파일에 존재하는 데이터(헤더 및 기존 값)]
        {existing_data_context if existing_data_context else "없음"}

        [엑셀 빈 셀 구조]
        (아래 빈 셀 좌표가 주어졌다면 해당 좌표에 맞게 채우고, 만약 비어있다면([]) 위 헤더 구조를 보고 AI가 스스로 적절한 행(예: 2행, 3행...)을 새롭게 무한대로 추가해가며 표를 완성해서 좌표를 생성하세요.)
        {json.dumps(empty_cells_info, ensure_ascii=False)}
        
        [출력 지침]
        정형 DB 통계 데이터와 비정형 모집요강 문서 텍스트를 종합적으로 분석하여 엑셀 셀 좌표를 추론하고 매핑해.
        (지원인원이나 최종등록인원은 정형 DB에서 찾고, 계획된 모집인원은 비정형 모집요강 문서에서 찾아서 융합하세요.)
        
        출력은 반드시 안내 텍스트로 시작하되, 
        안내 텍스트는 **무조건 3줄 이내로 극도로 짧게 핵심만 요약**해. (절대 학과별로 길게 나열하지 마십시오! 최대 출력 한도에 걸립니다.)
        
        그 다음, 엑셀에 주입할 실제 데이터는 **반드시 마지막에 순수한 JSON 배열 형식으로만** 작성해.
        - 기본 규칙 (단, 위 '사용자 특별 지시사항'과 충돌 시 사용자 지시를 100% 우선함): 데이터 값이 숫자일 경우 가급적 정수형(`int`)으로 입력.
        - 만약 사용자가 "제한없음" 문자열이나 "하이픈(-)", 빈칸을 유지하라고 지시했다면, 강제로 0으로 변환하지 말고 사용자의 요구대로 문자열을 매핑하거나 해당 셀 매핑을 과감히 생략하십시오.
        - 치명적 오류 방지: JSON 딕셔너리 구조는 무조건 `{{"cell": "좌표", "value": 값}}` 형태를 엄격히 지켜야 합니다. 키 이름(`"value"`)을 절대로 빼먹지 마십시오! (잘못된 예: `{{"cell": "E2", 174}}` -> 올바른 예: `{{"cell": "E2", "value": 174}}`)
        ```json
        [
          {{"cell": "A2", "value": "간호학부"}},
          {{"cell": "B2", "value": 150}}
        ]
        ```
        """
        
        final_model = genai.GenerativeModel(model_name)
        final_response = await final_model.generate_content_async(final_prompt)
        final_text = final_response.text
        
        # 5. 매핑 추출 및 엑셀 주입
        mapping_result = {}
        answer_text = final_text
        
        # 새로운 JSON 포맷 파싱 시도 (JSON 배열)
        json_match = re.search(r'```json\s*(\[.*?\])\s*```', final_text, re.DOTALL)
        if json_match:
            try:
                data_list = json.loads(json_match.group(1))
                answer_text = final_text.replace(json_match.group(0), "").strip()
            except Exception as e:
                print(f"[EXCEL-AUTOFILL] 신규 JSON 포맷 파싱 실패(정규식 폴백 시도): {e}")
                data_list = []
                answer_text = final_text
                # 정규식을 이용해 깨진 JSON에서 안전하게 데이터 추출 (Fallback)
                pattern = r'\{\s*"cell"\s*:\s*"([a-zA-Z]+[0-9]+)"\s*,\s*(?:"value"\s*:\s*)?([0-9\.]+|"[^"]+")\s*\}'
                for coord, val_str in re.findall(pattern, json_match.group(1)):
                    if val_str.startswith('"') and val_str.endswith('"'):
                        val = val_str[1:-1]
                    elif '.' in val_str:
                        val = float(val_str)
                    else:
                        val = int(val_str)
                    data_list.append({"cell": coord, "value": val})

            for item in data_list:
                if "cell" in item and "value" in item:
                    mapping_result[item["cell"].upper()] = item["value"]

        # 기존 방식 fallback
        if not mapping_result:
            map_match = re.search(r'\[EXCEL_MAP_START\](.*?)\[EXCEL_MAP_END\]', final_text, re.DOTALL)
            if map_match:
                json_str = map_match.group(1).strip()
                answer_text = final_text.replace(map_match.group(0), "").strip()
                pattern = r'"([a-zA-Z]+[0-9]+)"\s*:\s*([0-9\.]+)'
                matches = re.findall(pattern, json_str)
                for k, v in matches:
                    mapping_result[k.upper()] = float(v) if '.' in v else int(v)

        filled_count = 0
        for coord, val in mapping_result.items():
            try:
                ws[coord].value = val
                filled_count += 1
            except Exception as e:
                print(f"[EXCEL-AUTOFILL] 셀 {coord} 쓰기 실패: {e}")
                
        if filled_count > 0:
            print(f"[EXCEL-AUTOFILL] ✅ 5단계: AI 매핑 완료 (총 {filled_count}개 셀 주입 성공)")
        else:
            print("[EXCEL-AUTOFILL] ⚠️ 매핑된 데이터가 없습니다.")
            
        # [디버깅용] 로컬 temp 폴더에 원본 파일 강제 저장
        try:
            temp_dir = os.path.join(os.getcwd(), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            debug_file_path = os.path.join(temp_dir, f"DEBUG_Autofill_{file.filename}")
            wb.save(debug_file_path)
            print(f"[EXCEL-AUTOFILL] 💾 서버 저장 원본 엑셀 경로: {debug_file_path}")
        except Exception as e:
            print(f"[EXCEL-AUTOFILL] ⚠️ 임시 파일 저장 실패: {e}")
            
        # 6. Base64 인코딩 및 반환
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        excel_base64 = base64.b64encode(output.read()).decode('utf-8')
        
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[EXCEL-AUTOFILL] 🎉 하이브리드 엑셀 채우기 성공! ({latency_ms}ms)\n")
        
        return {
            "status": "success",
            "answer": answer_text,
            "log_id": -1, # 로그 저장은 생략하거나 필요 시 추가
            "latency_ms": latency_ms,
            "excel_base64": excel_base64,
            "excel_filename": f"AutoFilled_{file.filename}"
        }
        
    except asyncio.CancelledError:
        print(f"[EXCEL-AUTOFILL] 🛑 사용자에 의해 요청이 취소되었습니다.")
        raise
    except Exception as e:
        print(f"[EXCEL-AUTOFILL] ❌ 에러 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
