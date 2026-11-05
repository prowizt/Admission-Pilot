import io
import json
import re
import os
import time
import base64
import uuid
import urllib.parse
import openpyxl
import asyncio
from decimal import Decimal
from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Form
import llm_client
import excel_grid
import metric_query
import db_access
import app_config

router = APIRouter()

def extract_excel_structure(ws):
    """
    빈 셀의 좌표와 해당 셀이 위치한 행/열의 문맥(헤더) 정보를 추출합니다.
    """
    empty_cells = []
    max_row = min(ws.max_row, 200)
    max_col = min(ws.max_column, 200)
    # 1. 병합된 셀(Merged Cells) 완벽 평탄화 (Flatten)
    merged_values = {}
    for merged_range in ws.merged_cells.ranges:
        min_col, min_row, max_col_idx, max_row_idx = merged_range.bounds
        top_left_val = ws.cell(row=min_row, column=min_col).value
        if top_left_val is not None and str(top_left_val).strip() != "":
            # 병합 영역 내의 모든 셀에 좌상단 값 할당 (평탄화)
            for r in range(min_row, max_row_idx + 1):
                for c in range(min_col, max_col_idx + 1):
                    merged_values[(r, c)] = str(top_left_val).strip()

    headers = {}
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            if (r, c) in merged_values:
                headers[(r, c)] = merged_values[(r, c)]
            else:
                val = ws.cell(row=r, column=c).value
                if val is not None and str(val).strip() != "":
                    headers[(r, c)] = str(val).strip()

    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            
            # 헤더로 판별된 셀은 빈 셀 목록에서 제외
            if (r, c) in headers:
                continue

            # 빈칸(입력칸)이 병합된 경우, 좌상단 1개만 수집하고 나머지 껍데기는 무시
            if type(cell).__name__ == 'MergedCell':
                continue
                
            if cell.value is None or str(cell.value).strip() == "":
                left_headers = []
                for i in range(1, c):
                    if (r, i) in headers:
                        h = headers[(r, i)]
                        # 연속된 동일 헤더 제거 (평탄화로 인한 중복 방지)
                        if not left_headers or left_headers[-1] != h:
                            left_headers.append(h)

                top_headers = []
                for i in range(1, r):
                    if (i, c) in headers:
                        h = headers[(i, c)]
                        if not top_headers or top_headers[-1] != h:
                            top_headers.append(h)
                
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


def sheet_to_log_table(ws, max_rows=300):
    """채우기가 끝난 시트 전체를 '| 행 | A | B | ...' 표 문자열로 만듭니다. (감사 로그에서 결과를 바로 검증하기 위함)"""
    from openpyxl.utils import get_column_letter
    max_col = min(ws.max_column, 200)
    last_row = min(ws.max_row, max_rows)
    lines = ["| 행 | " + " | ".join(get_column_letter(c) for c in range(1, max_col + 1)) + " |"]
    for r in range(1, last_row + 1):
        vals = []
        for c in range(1, max_col + 1):
            v = ws.cell(row=r, column=c).value
            vals.append("" if v is None else str(v).replace("|", "/").replace("\n", " "))
        lines.append(f"| {r} | " + " | ".join(vals) + " |")
    if ws.max_row > max_rows:
        lines.append(f"... (총 {ws.max_row}행 중 {max_rows}행까지만 기록)")
    return "\n".join(lines)


def build_direct_fill(ws, empty_cells, db_rows):
    """
    머리글만 있는 빈 양식(빈 셀 0개)이고 DB 결과 열 이름이 머리글과 모두 일치하면,
    매핑 AI 없이 DB 결과를 머리글 아래에 한 행씩 그대로 적을 좌표 매핑을 만듭니다. (행 누락·값 변형 방지)
    조건이 맞지 않으면 None 을 반환해 기존 AI 매핑을 사용합니다.
    """
    if empty_cells or not db_rows:
        return None
    filled = [(c.row, c.column_letter, str(c.value).strip()) for row in ws.iter_rows() for c in row
              if c.value is not None and str(c.value).strip() != ""]
    header_rows = {r for r, _, _ in filled}
    if len(header_rows) != 1:
        return None  # 머리글 한 줄짜리 양식만 대상
    header_row = header_rows.pop()

    def norm(s):
        return re.sub(r'\s+', '', str(s))

    db_cols = {norm(k): k for k in db_rows[0].keys()}
    col_map = {}
    for _, letter, name in filled:
        if norm(name) not in db_cols:
            print(f"[EXCEL-AUTOFILL] 직접 기록 불가: 머리글 '{name}' 이 DB 결과 열 {list(db_rows[0].keys())} 에 없음 → AI 매핑 사용")
            return None
        col_map[letter] = db_cols[norm(name)]

    def cell_value(v):
        # 앞자리 0 이 없는 정수 문자열만 숫자로 (그 외 '제한없음' 등 글자는 그대로)
        if isinstance(v, str) and re.fullmatch(r'-?[1-9]\d*|0', v.strip()):
            return int(v.strip())
        return v

    mapping = {}
    out_row = header_row
    for r in db_rows:
        if any(r.get(src) is None for src in col_map.values()):
            continue  # ROLLUP 합계 등 빈 값 행 제외
        out_row += 1
        for letter, src in col_map.items():
            mapping[f"{letter}{out_row}"] = cell_value(r[src])
    return mapping, out_row - header_row

async def ai_fix_sql(conn, question, existing_data_context, raw_sql_query, first_err, router_model_name, router_api_key):
    """
    [자가 교정 1회] DB 오류가 난 쿼리를 오류 메시지 + 실제 테이블 열 목록과 함께 AI 에 주고 한 번만 다시 쓰게 합니다.
    반환: (고친 쿼리(끝에 ;) 또는 "", 입력 토큰, 출력 토큰)
    """
    table_lines = []
    for t_name in dict.fromkeys(re.findall(r'(?i)\b(?:FROM|JOIN)\s+\[?(\w+)\]?', raw_sql_query)):
        try:
            t_cur = conn.cursor()
            t_cur.execute(f"SELECT TOP 0 * FROM [{t_name}]")
            col_desc = ", ".join(f"[{c[0]}]({'문자' if c[1] is str else '숫자' if c[1] in (int, float, Decimal) else c[1].__name__})" for c in t_cur.description)
            table_lines.append(f"- {t_name}: {col_desc}")
        except Exception:
            pass  # CTE 별칭 등 실제 테이블이 아닌 이름
    fix_prompt = f"""아래 T-SQL 쿼리가 MS-SQL 에서 오류가 났습니다. 오류를 고친 쿼리 하나만 다시 작성하십시오.

[사용자 질문/지시]
{question}

[엑셀 기존 내용 (머리글)]
{existing_data_context if existing_data_context else "없음"}

[오류가 난 쿼리]
{raw_sql_query}

[오류 메시지]
{first_err}

[쿼리에 사용된 테이블의 실제 열 목록 (열 이름은 반드시 이 목록에서 글자 그대로 사용)]
{chr(10).join(table_lines) if table_lines else "확인 불가"}

[규칙]
- 열 이름은 위 실제 열 목록에 있는 이름만 대괄호로 감싸 사용하십시오.
- 문자형 열을 숫자로 집계할 때는 SUM(CASE WHEN ISNUMERIC([열])=1 THEN CAST([열] AS INT) ELSE 0 END) 형태를 사용하십시오. 집계가 필요 없으면 원본 값을 그대로 조회하십시오.
- ORDER BY 는 쓰지 마십시오.
"""
    fix_schema = {
        "type": "object",
        "properties": {"sql_query": {"type": "string", "description": "고친 T-SQL 쿼리"}},
        "required": ["sql_query"],
        "additionalProperties": False,
    }
    fix_response = await asyncio.to_thread(
        llm_client.generate, router_model_name, router_api_key, fix_prompt,
        json_schema=fix_schema, effort="low", timeout=120, thinking_off=llm_client.ROUTER_THINKING_OFF
    )
    try:
        fixed_sql = json.loads(fix_response.text.strip().replace("```json", "").replace("```", "").strip()).get("sql_query", "")
    except Exception:
        fixed_sql = ""
    fixed_sql = re.sub(r'\[([^\]]+)\]', lambda m: '[' + re.sub(r'[\s​‌‍﻿　]+', '', m.group(1)) + ']', fixed_sql or "")
    fixed_sql = re.sub(r'(?i)\s*ORDER\s+BY\s+.*', '', fixed_sql).strip()
    if not fixed_sql.upper().startswith(("SELECT", "WITH")):
        return "", fix_response.in_tokens, fix_response.out_tokens
    return (fixed_sql if fixed_sql.endswith(';') else fixed_sql + ';'), fix_response.in_tokens, fix_response.out_tokens


async def ai_revise_sql(conn, question, router_json, choices, router_model_name, router_api_key, purpose="metric"):
    """
    [기준 선택 → SQL 정의만 수정] 지표 정의(예: 등록인원 = 최초합격자 중 등록)를 바꾼 경우,
    라우터를 처음부터 다시 부르지 않고 '실제로 실행했던 SQL'에서 해당 지표 열의 계산식만 고치게 합니다.
    (테이블·조건·GROUP BY·별칭을 유지해 엉뚱한 테이블로 바뀌는 것을 막음)
    반환: (고친 router_json 또는 None, 입력 토큰, 출력 토큰)
    """
    sqls = [router_json.get("sql_query", "")] + list(router_json.get("extra_sql_queries", []) or [])
    table_lines = []
    for t_name in dict.fromkeys(t for q in sqls for t in re.findall(r'(?i)\b(?:FROM|JOIN)\s+\[?(\w+)\]?', q or "")):
        try:
            t_cur = conn.cursor()
            t_cur.execute(f"SELECT TOP 0 * FROM [{t_name}]")
            table_lines.append(f"- {t_name}: " + ", ".join(f"[{c[0]}]" for c in t_cur.description))
        except Exception:
            pass
    if purpose == "grid_fix":
        # [쿼리-양식 불일치 보정] 양식의 칸(학과·전형 등)을 나눌 구분 열이 빠진 쿼리를 고침
        # 다른 테이블 쿼리를 추가할 수도 있으므로 활성 테이블 전체의 실제 열 목록을 줌
        try:
            from main import get_real_table_columns, get_dynamic_db_schema
            all_cols = get_real_table_columns(conn)
            if all_cols:
                table_lines = [f"- {t}: " + ", ".join(f"[{c}]" for c, _ in cols) for t, cols in all_cols.items()]
            # 열 설명에 적힌 값 목록 (조건 값 오타 보정용)
            table_lines.append("\n[DB 스키마 설명]\n" + get_dynamic_db_schema(conn, "staff").split("\n[현재 AI가 접근 가능한 비정형")[0])
        except Exception:
            pass
        head = "아래는 엑셀 격자 채우기에 사용한 T-SQL 쿼리입니다. 시스템 검사에서 쿼리가 엑셀 양식의 칸과 맞지 않는 문제가 발견되었으니 고쳐 주십시오."
        rules = """- 각 쿼리의 FROM 테이블, WHERE 조건, 이미 있는 지표(숫자) 열의 계산식과 별칭은 그대로 두십시오. 단 문제에 '조회 결과가 0행'이 나온 쿼리는 WHERE 조건 값의 오타·표기를 아래 [DB 스키마 설명]의 실제 값으로 고치십시오.
- 엑셀 양식의 행 이름 열·머리글 각 단(학과, 전형 등)에 해당하는 구분 열을 각 쿼리의 SELECT 와 GROUP BY 에 넣으십시오. 칸 이름 목록을 보고 실제 열 목록에서 같은 뜻의 열을 고르십시오. (예: 인문고·특성화·독자·비교과·대학… 은 고교 유형이 아니라 전형 구분)
- 양식에 칸이 없는 세분화 열(예: 고교구분)은 SELECT·GROUP BY 에서 빼십시오.
- 문제에 '숫자 아닌 값이 사라짐'으로 나온 지표 열은 SUM·CAST·ISNUMERIC 없이 원본 열 그대로 SELECT 하고, 그 쿼리는 GROUP BY 를 빼고 행 단위로 조회하십시오 (구분 열은 SELECT 에 그대로).
- 문제에 '필요한 열이 조회 결과에 없음'으로 나온 지표 열은 SELECT 에 추가하십시오. 그 지표가 지금 쿼리의 테이블에 없으면(예: 지원·합격·등록 인원은 입시마스타) 그 테이블을 조회하는 쿼리를 extra_sql_queries 에 추가하고, 같은 WHERE 조건(학년도·모집구분 등)을 그 테이블의 열 이름으로 넣으십시오.
- 그 외에는 쿼리 개수와 순서를 그대로 유지하십시오 (extra_sql_queries 가 비어 있으면 빈 배열).
- 열 이름은 실제 열 목록에 있는 이름만 대괄호로 감싸 사용하고, ORDER BY·ROLLUP 은 쓰지 마십시오."""
        choice_title = "시스템이 발견한 문제와 양식 구조"
    else:
        head = "아래는 엑셀 채우기에 실제로 사용한 T-SQL 쿼리입니다. 사용자가 일부 지표의 정의를 바꿨으니, 해당 지표 열의 계산식만 고쳐 주십시오."
        rules = """- FROM 테이블, WHERE 조건, GROUP BY, 다른 열과 모든 별칭(AS [...])은 그대로 두고, 바뀐 기준에 해당하는 지표 열의 계산식만 고치십시오.
- 쿼리 개수와 순서도 그대로 유지하십시오 (extra_sql_queries 가 비어 있으면 빈 배열).
- 열 이름은 실제 열 목록에 있는 이름만 대괄호로 감싸 사용하고, ORDER BY 는 쓰지 마십시오."""
        choice_title = "사용자가 바꾼 기준"
    prompt = f"""{head}

[사용자 질문]
{question}

[{choice_title}]
{chr(10).join(f"- {c['topic']}: {c['answer']}" for c in choices)}

[이전에 실행한 쿼리]
sql_query:
{sqls[0]}
extra_sql_queries:
{json.dumps(sqls[1:], ensure_ascii=False)}

[쿼리에 쓰인 테이블의 실제 열 목록]
{chr(10).join(table_lines) if table_lines else "확인 불가"}

[규칙]
{rules}
"""
    schema = {
        "type": "object",
        "properties": {
            "sql_query": {"type": "string"},
            "extra_sql_queries": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["sql_query", "extra_sql_queries"],
        "additionalProperties": False,
    }
    try:
        resp = await asyncio.to_thread(
            llm_client.generate, router_model_name, router_api_key, prompt,
            json_schema=schema, effort="low", timeout=120, thinking_off=llm_client.ROUTER_THINKING_OFF
        )
        fixed = json.loads(resp.text.strip().replace("```json", "").replace("```", "").strip())
        new_sql = (fixed.get("sql_query") or "").strip()
        if not new_sql.upper().startswith(("SELECT", "WITH")):
            return None, resp.in_tokens, resp.out_tokens
        revised = dict(router_json)
        revised["sql_query"] = new_sql
        revised["extra_sql_queries"] = [q for q in (fixed.get("extra_sql_queries") or []) if q and q.strip()]
        print(f"[EXCEL-AUTOFILL] ✏️ SQL 수정 ({purpose}):\n{new_sql}")
        return revised, resp.in_tokens, resp.out_tokens
    except Exception as e:
        print(f"[EXCEL-AUTOFILL] ⚠️ SQL 정의 수정 실패: {e}")
        return None, 0, 0


def save_default_criteria(conn, choices):
    """
    [통계 기본 기준] 사전지식 1건을 만들거나, 이미 있으면 같은 주제(topic)만 바꿔 저장합니다. (엑셀 채우기·쿼리 요청 공용)
    (기본값이 여러 건으로 늘어나 서로 충돌하지 않도록 항상 한 건만 유지)
    반환: 사전지식 id (실패 시 None)
    """
    title = excel_grid.DEFAULT_CRITERIA_TITLE
    try:
        cur = conn.cursor()
        row = None
        for t in (title,) + excel_grid.OLD_CRITERIA_TITLES:
            cur.execute("SELECT TOP 1 id, content FROM Sys_SupplementalKnowledge "
                        "WHERE is_active = 'Y' AND LEFT(content, ?) = ? ORDER BY id DESC", (len(t), t))
            row = cur.fetchone()
            if row:
                break
        items = {}
        if row:
            for line in (row[1] or "").splitlines():
                m = re.match(r"^- (.+?) = (.+)$", line.strip())
                if m:
                    items[m.group(1)] = m.group(2)
        for c in choices:
            if c.get("topic") and c.get("answer"):
                items[c["topic"]] = c["answer"]
        content = (title + "\n" + excel_grid.DEFAULT_CRITERIA_NOTE + "\n"
                   + "\n".join(f"- {k} = {v}" for k, v in items.items()))
        if row:
            cur.execute("UPDATE Sys_SupplementalKnowledge SET content = ? WHERE id = ?", (content, row[0]))
            kid = row[0]
        else:
            cur.execute("INSERT INTO Sys_SupplementalKnowledge (category, content, is_active, created_at, author, target_scope) "
                        "OUTPUT INSERTED.id VALUES (?, ?, 'Y', GETDATE(), ?, 'staff')",
                        ("03_엑셀매핑", content, "system(엑셀 기준 저장)"))
            kid = cur.fetchone()[0]
        conn.commit()
        print(f"[EXCEL-AUTOFILL] 💾 통계 기본 기준 저장 (사전지식 #{kid}): {list(items.keys())}")
        return kid
    except Exception as e:
        print(f"[EXCEL-AUTOFILL] ⚠️ 기본 기준 저장 실패: {e}")
        return None


def resolve_values(conn, sql, notes):
    """
    [이름 보정] SQL 조건 값을 실제 DB 값과 대조 (value_resolver). 엑셀 채우기는 중간에 묻지 않고
    후보 1개 → 교체, 후보 여러 개 → 모두 포함 + '확인 필요' 안내. 안내 문구는 notes 에 추가.
    """
    try:
        from main import get_value_dictionary
        from value_resolver import resolve_sql_values, ALL_CHOICE
        vd = get_value_dictionary(conn)
        new_sql, found, ask = resolve_sql_values(sql, vd)
        if ask:
            new_sql, more, _ = resolve_sql_values(new_sql, vd, {a["given"]: ALL_CHOICE for a in ask})
            found += [m + " · AI 판단 · 확인 필요 (다르면 질문에 정확한 값을 적어 다시 채우기)" for m in more]
        for n in found:
            if n not in notes:
                notes.append(n)
                print(f"[EXCEL-AUTOFILL] 🔎 이름 보정: {n}")
        return new_sql
    except Exception as e:
        print(f"[EXCEL-AUTOFILL] 이름 보정 생략: {e}")
        return sql


def _fetch_rows(conn, sql):
    # [DB 권한 분리] AI·조립 쿼리는 읽기 계정으로, 한 문장의 조회만 실행
    runner = db_access.QueryRunner(conn, "staff")
    try:
        cur = runner.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        runner.close()
    for r in rows:
        for k, v in r.items():
            if hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
            elif isinstance(v, Decimal):
                r[k] = float(v)
    return rows


async def run_grid_fill(conn, grid, question, supplemental, main_sql, db_rows, extra_sql_queries,
                        existing_data_context, model_name, chat_api_key, router_model_name, router_api_key, effort,
                        schema_text="", user_choices=None, hint_text="", value_notes=None, metric_plan=None, metric_catalog=None, reuse_mapping=None):
    """
    [격자 직접 기록] 추가 쿼리 실행 → 대응표 AI → 파이썬 값 넣기·합계·검산.
    반환 dict: ok, cells, warnings, notes, fail, mapping_text, sql_log, map_in/map_out(대응표 AI), fix_in/fix_out(쿼리 재작성), effort, sources
    """
    out = {"ok": False, "cells": {}, "warnings": [], "notes": [], "omitted": [], "fail": [], "mapping_text": "",
           "decisions": [], "criteria_text": "", "summed": [], "auto_conditions": [],
           "sql_log": "", "map_in": 0, "map_out": 0, "fix_in": 0, "fix_out": 0, "effort": "", "sources": []}
    sources = [{"name": "Q1", "sql": main_sql, "rows": db_rows}]
    sql_log = []
    for i, q in enumerate(extra_sql_queries, 2):
        q = re.sub(r'\[([^\]]+)\]', lambda m: '[' + re.sub(r'[\s​‌‍﻿　]+', '', m.group(1)) + ']', q)
        q = re.sub(r'(?i)\s*ORDER\s+BY\s+.*', '', q).strip()
        if not q.endswith(';'):
            q += ';'
        q = resolve_values(conn, q, value_notes if value_notes is not None else [])
        try:
            rows = _fetch_rows(conn, q)
            sql_log.append(f"-- [추가 쿼리 Q{i}]\n{q}")
        except Exception as e:
            print(f"[EXCEL-AUTOFILL] ⚠️ 추가 쿼리 Q{i} DB 에러 → AI 재작성 1회 시도: {e}")
            fixed, fi, fo = await ai_fix_sql(conn, question, existing_data_context, q, e, router_model_name, router_api_key)
            out["fix_in"] += fi
            out["fix_out"] += fo
            if not fixed:
                out["fail"].append(f"추가 쿼리 Q{i} 실행 실패: {e}")
                out["sql_log"] = "\n\n".join(sql_log)
                return out
            fixed = resolve_values(conn, fixed, value_notes if value_notes is not None else [])
            try:
                rows = _fetch_rows(conn, fixed)
            except Exception as e2:
                out["fail"].append(f"추가 쿼리 Q{i} 재작성 후에도 실패: {e2}")
                out["sql_log"] = "\n\n".join(sql_log)
                return out
            sql_log.append(f"-- [추가 쿼리 Q{i}] (DB 오류: {str(e)[:150]})\n-- [AI 재작성 후 실행]\n{fixed}")
            q = fixed
        print(f"[EXCEL-AUTOFILL] 🔍 추가 쿼리 Q{i}: {len(rows)}행")
        sources.append({"name": f"Q{i}", "sql": q, "rows": rows})
    out["sources"] = sources
    out["sql_log"] = "\n\n".join(sql_log)

    # 대응표는 이름 맞추기라 깊은 추론이 필요 없음 → 최종 답변 effort 와 별도로 고정 (기본 low, .env GRID_MAP_EFFORT)
    out["effort"] = app_config.get("GRID_MAP_EFFORT")

    async def call_mapping(prompt_text):
        resp = await asyncio.to_thread(
            llm_client.generate, model_name, chat_api_key, prompt_text,
            json_schema=excel_grid.MAPPING_SCHEMA, effort=out["effort"], timeout=300, max_tokens=32000
        )
        out["map_in"] += resp.in_tokens
        out["map_out"] += resp.out_tokens
        return json.loads(resp.text.strip().replace("```json", "").replace("```", "").strip())

    async def map_and_fill(srcs):
        """대응표 작성 → 채우기. 대응표 문제(쿼리 문제 제외)는 문제 목록을 주고 1회 재작성"""
        prompt = excel_grid.build_mapping_prompt(question, supplemental, grid, srcs, schema_text, user_choices)
        try:
            mapping = await call_mapping(prompt)
        except Exception as e:
            return {"ok": False, "fail": [f"대응표 AI 응답 오류: {e}"]}, {}
        res = excel_grid.fill_grid(grid, srcs, json.loads(json.dumps(mapping)), hint_text)
        problems = res.get("fail", [])
        if res.get("ok") or any(p.startswith("[쿼리]") for p in problems):
            return res, mapping
        print(f"[EXCEL-AUTOFILL] ⚠️ 대응표 문제 {len(problems)}건 → 대응표 AI 재작성 1회: {problems[:3]}")
        retry_prompt = (prompt + "\n\n[이전에 네가 작성한 대응표]\n" + json.dumps(mapping, ensure_ascii=False)
                        + "\n\n[시스템 검사에서 발견된 문제 (모두 고쳐서 전체 대응표를 다시 작성)]\n"
                        + "\n".join(f"- {p}" for p in problems))
        try:
            mapping = await call_mapping(retry_prompt)
        except Exception as e:
            res["fail"] = problems + [f"대응표 재작성 오류: {e}"]
            return res, mapping
        res2 = excel_grid.fill_grid(grid, srcs, json.loads(json.dumps(mapping)), hint_text)
        if not res2.get("ok"):
            res2["fail"] = [f"(1차) {p}" for p in problems] + [f"(재작성 후) {p}" for p in res2.get("fail", [])]
        return res2, mapping

    empty_srcs = [x["name"] for x in sources if not x["rows"]]
    if empty_srcs:
        # 조회 결과 0행: 대응표를 만들 수 없음 → 조건 값 오타 등 쿼리 문제로 보고 바로 쿼리 보정
        res, mapping = {"ok": False, "fail": [
            f"[쿼리] {n} 조회 결과가 0행 — WHERE 조건의 값이 실제 DB 값과 다를 수 있음 (오타·표기 차이). 조건 값을 실제 열 값으로 고칠 것"
            for n in empty_srcs]}, {}
    elif reuse_mapping:
        # [기준 바꿔 다시 채우기] 지표 정의만 바뀌었으면 이전 대응표의 열 이름만 바꿔 채움 (대응표 AI 호출 없음)
        prev_mapping, renames = reuse_mapping
        mapping = excel_grid.rename_fields(prev_mapping, renames)
        excel_grid.apply_choices(mapping, user_choices)
        res = excel_grid.fill_grid(grid, sources, json.loads(json.dumps(mapping)), hint_text)
        if res.get("ok"):
            print(f"[EXCEL-AUTOFILL] ♻️ 이전 대응표 재사용 (열 이름만 교체 {renames}, 대응표 AI 호출 없음)")
        else:
            print(f"[EXCEL-AUTOFILL] ♻️ 이전 대응표 재사용 실패 → 대응표 새로 작성: {res.get('fail', [])[:3]}")
            res, mapping = await map_and_fill(sources)
    else:
        res, mapping = await map_and_fill(sources)

    # [쿼리-양식 불일치] 쿼리가 양식의 칸(전형 등)을 나눌 열 없이 다른 열로 묶였으면, 문제를 알려 쿼리를 1회 고치고 다시 조회
    query_problems = [p for p in res.get("fail", []) if "[쿼리]" in p]
    if query_problems:
        print(f"[EXCEL-AUTOFILL] ⚠️ 쿼리가 양식과 맞지 않음 → 쿼리 보정 1회: {query_problems[:2]}")
        router_json = {"sql_query": sources[0]["sql"], "extra_sql_queries": [x["sql"] for x in sources[1:]]}
        fix_choices = [{"topic": "쿼리 보정 (양식 구분 열 누락)", "answer": p} for p in query_problems]
        fix_choices.append({"topic": "양식 구조", "answer": excel_grid.grid_summary_text(grid)})
        revised, fi, fo = await ai_revise_sql(conn, question, router_json, fix_choices, router_model_name, router_api_key,
                                              purpose="grid_fix")
        out["fix_in"] += fi
        out["fix_out"] += fo
        if revised:
            new_sources, ok = [], True
            for i, q in enumerate([revised["sql_query"]] + revised.get("extra_sql_queries", [])):
                q = resolve_values(conn, q.strip().rstrip(";") + ";", value_notes if value_notes is not None else [])
                try:
                    new_sources.append({"name": f"Q{i + 1}", "sql": q, "rows": _fetch_rows(conn, q)})
                except Exception as e:
                    out["fail"].append(f"보정한 쿼리 Q{i + 1} 실행 실패: {e}")
                    ok = False
                    break
            if ok and new_sources:
                sources = new_sources
                out["sources"] = sources
                out["sql_log"] = (out["sql_log"] + "\n\n" if out["sql_log"] else "") + "\n\n".join(
                    f"-- [양식 구분 열 보정 후 {x['name']}]\n{x['sql']}" for x in sources)
                print(f"[EXCEL-AUTOFILL] 🔧 쿼리 보정 후 다시 조회: {[len(x['rows']) for x in sources]}행")
                res2, mapping2 = await map_and_fill(sources)
                if not res2.get("ok"):
                    res2["fail"] = [f"(쿼리 보정 전) {p}" for p in query_problems] + [f"(쿼리 보정 후) {p}" for p in res2.get("fail", [])]
                res, mapping = res2, mapping2

    # [기준 출처 검증] AI 가 '저장된 기본값'·'사용자 선택'이라고 표시해도 실제로 근거가 없으면 'AI 판단'으로 고쳐 사용자에게 묻게 함
    if res.get("ok") and res.get("decisions"):
        title = excel_grid.DEFAULT_CRITERIA_TITLE
        default_block = supplemental[supplemental.find(title):] if title in (supplemental or "") else ""
        default_block = default_block.split("\n\n")[0]
        chosen = {excel_grid.norm(c.get("topic")) for c in (user_choices or [])}
        changed = False
        for d in res["decisions"]:
            t = excel_grid.norm(d.get("topic"))
            if d.get("basis") == "default" and not (default_block and t and t in excel_grid.norm(default_block)):
                d["basis"], changed = "ai", True
            elif d.get("basis") == "user" and t not in chosen:
                d["basis"], changed = "ai", True
        # [지표 사전] 설계도로 조립했으면 정의가 둘 이상인 지표의 선택지를 지표 사전의 지표명으로 (기준 변경 시 설계도만 바꿔 다시 조립)
        if metric_plan and metric_catalog and metric_query.align_decisions(res["decisions"], metric_plan, metric_catalog):
            changed = True
        if changed:
            res["criteria_text"] = excel_grid.criteria_text({"decisions": res["decisions"], "measures": mapping.get("measures", [])},
                                                            res.get("auto_conditions"))
    out.update({k: res.get(k, out[k]) for k in ("ok", "cells", "warnings", "notes", "omitted", "decisions", "criteria_text", "summed", "auto_conditions")})
    out["fail"] += res.get("fail", [])
    out["mapping_text"] = excel_grid.mapping_to_text(mapping) if mapping else ""
    out["mapping"] = mapping if res.get("ok") else None  # 기준 바꿔 다시 채우기에서 재사용
    return out


@router.post("/chat-excel-autofill")
async def chat_excel_autofill(
    file: UploadFile = File(...), 
    question: str = Form(...),
    user_role: str = Form("staff"),
    model_name: str = Form("gemini-2.5-flash"),
    history: str = Form("[]"),
    scraped_context: str = Form(None),
    scraped_file_name: str = Form(None),
    router_model_name: str = Form(None),
    pending_id: str = Form(None),          # [큰 문서 확인] 확인 응답에서 받은 ID (재요청 시 라우터 재호출 생략)
    large_doc_decision: str = Form(None),  # [큰 문서 확인] "include" 또는 "exclude"
    effort: str = Form(None),              # (예전 확장 호환용, 무시됨) 추론 강도는 환경 설정 STAFF_EFFORT
    excel_choice_id: str = Form(None),     # [채우기 기준 확인] 확인 응답에서 받은 ID (기준 선택 후 재요청)
    excel_choices: str = Form(None),       # [채우기 기준 확인] 사용자가 고른 기준 JSON [{"topic", "answer"}]
    save_default: str = Form(None),        # [채우기 기준 확인] "true" 면 고른 기준을 사전지식 기본값으로 저장
    x_gemini_key: str = Header(None)
):
    # 순환 참조 방지를 위해 함수 내부에서 import
    from main import get_mssql_connection, get_dynamic_db_schema, get_real_table_columns, format_sql_query, mask_pii, today_line
    from main import (PENDING_ROUTER, purge_pending_router, insert_interim_audit_log,
                      find_explicit_docs, detect_db_only_intent, norm_doc_name)

    start_time = time.time()
    print(f"\n[EXCEL-AUTOFILL] 🚀 하이브리드 채팅 엑셀 자동 채우기 요청 수신 (질문: {question})")
    
    if question:
        question = mask_pii(question)
        
    # [Gemini ↔ Claude 전환] 헤더 키는 공급자 공통 키 (Claude 모델 + 헤더 키 없음 → 서버 ANTHROPIC_API_KEY)
    _router_model = router_model_name or model_name
    chat_api_key = llm_client.resolve_api_key(model_name, x_gemini_key)
    router_api_key = llm_client.resolve_api_key(_router_model, x_gemini_key)
    if llm_client.is_claude(model_name) != llm_client.is_claude(_router_model) and x_gemini_key:
        # 라우터/최종 모델 공급자가 다르면 Claude 쪽은 서버 키 사용
        if llm_client.is_claude(model_name):
            chat_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        else:
            router_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not chat_api_key or not router_api_key:
        raise HTTPException(status_code=401, detail="API Key가 필요합니다. (Claude 모델은 확장 설정의 키 또는 서버 ANTHROPIC_API_KEY 필요)")

    try:
        conn = get_mssql_connection()
        dynamic_schema = get_dynamic_db_schema(conn, user_role) if conn else "DB 연결 불가"

        # [채우기 기준 확인 후 재요청] 고른 기준을 받아, 대응표만 바꾸면 되는 경우 라우터 판단을 재사용 (라우터 비용 없음)
        choice_state, user_choices, original_question = None, None, question
        reuse_mapping = None  # (이전 대응표, {이전 지표: 새 지표}) — 지표 정의만 바꿔 다시 채울 때
        revise_in = revise_out = 0  # SQL 정의 수정 AI 토큰 (라우터 비용으로 합산)
        if excel_choice_id:
            purge_pending_router()
            choice_state = PENDING_ROUTER.get(excel_choice_id)
            try:
                user_choices = [c for c in json.loads(excel_choices or "[]") if c.get("topic") and c.get("answer")]
            except Exception:
                user_choices = []
            if not choice_state and not user_choices:
                return {
                    "status": "cancelled",
                    "reason": "pending_expired",
                    "message": "⏱️ 확인 대기 시간(15분)이 지나 요청이 만료되었습니다. 같은 요청을 다시 보내 주세요."
                }
            if not choice_state:
                # [대기 만료] 보관한 판단이 없으면 고른 기준을 질문에 붙여 처음부터 다시 실행 (라우터 1회 재호출)
                choice_state = {"question": question, "decisions": [], "log_id": None}
                if save_default == "true" and conn:
                    save_default_criteria(conn, user_choices)
                question = original_question + "\n\n[사용자가 선택한 채우기 기준]\n" + "\n".join(f"- {c['topic']}: {c['answer']}" for c in user_choices)
                print(f"[EXCEL-AUTOFILL] 🔁 기준 선택 후 재요청: 확인 대기 만료 → 고른 기준으로 처음부터 다시 실행")
            else:
                original_question = choice_state["question"]
                question = original_question
                if save_default == "true" and conn and user_choices:
                    save_default_criteria(conn, user_choices)
                prev = {norm_doc_name(d.get("topic")): d for d in choice_state.get("decisions", [])}
                needs_query = any(prev.get(norm_doc_name(c["topic"]), {}).get("affects_query")
                                  and c["answer"] != prev.get(norm_doc_name(c["topic"]), {}).get("applied") for c in user_choices)
                revised_router = None
                if needs_query:
                    # 개수 지표 정의가 바뀌면: 실행했던 SQL 에서 그 지표 계산식만 수정 (라우터 재호출 없음)
                    changed = [c for c in user_choices if c["answer"] != prev.get(norm_doc_name(c["topic"]), {}).get("applied")]
                    # [지표 사전] 설계도로 조립했던 요청이면 설계도의 지표만 바꿔 다시 조립 (AI 호출 없음)
                    new_plan = None
                    if choice_state.get("metric_plan") and conn:
                        new_plan = metric_query.swap_metrics(choice_state["metric_plan"], changed, metric_query.load_catalog(conn))
                    if new_plan:
                        revised_router = dict(json.loads(choice_state["router_text"]), metric_plan=new_plan)
                        if choice_state.get("mapping"):
                            cat_now = metric_query.load_catalog(conn)
                            renames = {}
                            for c in changed:
                                members = metric_query.family(cat_now, c["topic"])
                                new = next((m for m in new_plan.get("metrics") or [] if m in members), None)
                                old = next((m for m in choice_state["metric_plan"].get("metrics") or [] if m in members and m != new), None)
                                if old and new:
                                    renames[old] = new
                            reuse_mapping = (choice_state["mapping"], renames)
                        print(f"[EXCEL-AUTOFILL] 🧮 기준 변경 → 지표 설계도만 교체 (AI 호출 없음): {new_plan.get('metrics')}")
                    else:
                        try:
                            revised_router, revise_in, revise_out = await ai_revise_sql(
                                conn, original_question, json.loads(choice_state["router_text"]), changed, router_model_name or model_name, router_api_key)
                        except Exception as e:
                            print(f"[EXCEL-AUTOFILL] ⚠️ SQL 정의 수정 오류: {e}")
                    if revised_router:
                        choice_state["router_text"] = json.dumps(revised_router, ensure_ascii=False)
                        if not new_plan:
                            print(f"[EXCEL-AUTOFILL] 🔁 기준 선택 후 재요청: 지표 정의 변경 → SQL 계산식만 수정 (라우터 재호출 없음)")
                    else:
                        # 수정 실패 시 예전 방식: 고른 기준을 질문에 붙여 라우터를 새로 호출
                        question = original_question + "\n\n[사용자가 선택한 채우기 기준]\n" + "\n".join(f"- {c['topic']}: {c['answer']}" for c in user_choices)
                        print(f"[EXCEL-AUTOFILL] 🔁 기준 선택 후 재요청: SQL 수정 실패 → 라우터 재호출")
                if not needs_query or revised_router:
                    pending_id = excel_choice_id
                    large_doc_decision = choice_state.get("large_doc_decision")
                    if not needs_query:
                        print(f"[EXCEL-AUTOFILL] 🔁 기준 선택 후 재요청: 대응표만 다시 작성 (라우터·SQL 판단 재사용)")

        pre_supplemental_text = ""
        if conn:
            try:
                pre_cursor = conn.cursor()
                from main import load_supplemental_knowledge
                pre_supplemental_text = load_supplemental_knowledge(pre_cursor, user_role)
            except Exception as e:
                print(f"사전지식 선행 조회 오류: {e}")
        
        # 1. 엑셀 파싱
        file_bytes = await file.read()
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        empty_cells_info, existing_data_context = extract_excel_structure(ws)
        # [격자 양식] 행 이름 × N단 머리글 구조로 읽히면 대응표 AI + 파이썬 직접 기록을 사용
        grid = excel_grid.analyze_grid(ws, empty_cells_info)
        if grid:
            print(f"[EXCEL-AUTOFILL] 🧩 격자 양식 감지: 채울 칸 {len(grid['cells'])}개, 머리글 {len(grid['header_rows'])}단, 행 이름 열 {len(grid['key_cols'])}개")
            excel_structure_text = excel_grid.grid_summary_text(grid)
            grid_router_rules = """
        [🧩 격자 양식 전용 규칙 (아래 규칙이 위 1·14번 규칙보다 우선)]
        - 이 양식은 시스템이 DB 결과를 직접 펼쳐 넣고 합계·비율도 직접 계산합니다. 따라서 CASE WHEN 으로 엑셀 이름처럼 바꾸지 말고 DB 원본 값 그대로 GROUP BY 하십시오. (1번 규칙의 이름 가공 금지)
        - WITH ROLLUP/CUBE 를 쓰지 마십시오. (14번 규칙 적용 안 함, 합계는 시스템이 계산)
        - 비율(등록율·충원율 등)은 계산하지 말고, 그 비율에 필요한 개수 값(예: 지원인원, 등록인원, 모집인원)만 조회하십시오.
        - SELECT 에는 엑셀의 행 이름·머리글이 가리키는 구분 열(학과, 전형, 모집구분 등)을 원본 열 이름 그대로 넣고, 숫자 열은 의미가 드러나는 별칭(예: AS [지원인원])을 붙이십시오.
        - 엑셀 행 이름 열과 머리글 각 단(예: 학과, 전형)에 해당하는 구분 열은 **모든 쿼리**(sql_query·extra_sql_queries 각각)의 SELECT 와 GROUP BY 에 빠짐없이 넣으십시오. 머리글 이름 하나가 다른 열 값처럼 보여도(예: '인문고' → 고교구분?) 그 단의 이름 전체(인문고·특성화·독자·비교과·대학…)를 보고 어느 열인지 판단하십시오.
        - 양식에 없는 구분 열(고교구분 등)은 GROUP BY 에 넣지 마십시오. (필요 없는 세분화)
        - 숫자 아닌 값이 섞인 열(예: 모집인원의 '제한없음')은 SUM·CAST·ISNUMERIC 으로 가공하지 말고 원본 열 그대로 SELECT 하십시오. 그 쿼리는 GROUP BY 없이 행 단위로 조회합니다. (14번 규칙 적용 안 함, 합산과 '제한없음' 처리는 시스템이 함)
        - 사용자 질문·첨부 파일명에 나온 조건(학년도, 모집구분 등)은 엑셀에 그 칸이 없더라도 반드시 WHERE 에 넣으십시오. (예: 파일명에 '수시1차'가 있으면 모집구분을 수시1차로 한정, 오타가 있어도 뜻으로 판단)
        - 필요한 숫자가 서로 다른 테이블에 있으면(예: 모집인원 테이블 + 지원·등록 테이블) JOIN 하지 말고 테이블마다 쿼리를 따로 작성해, 첫 번째는 "sql_query", 나머지는 "extra_sql_queries" 배열에 넣으십시오. 하나로 충분하면 "extra_sql_queries" 는 빈 배열입니다.
"""
            # [지표 사전] 등록된 지표로 채울 수 있으면 AI 는 설계도(metric_plan)만 내고 SQL 은 시스템이 정의대로 조립
            metric_catalog = metric_query.load_catalog(conn) if conn else {"metrics": [], "dims": []}
            if metric_catalog["metrics"]:
                grid_router_rules += f"""
        {metric_query.catalog_prompt_text(metric_catalog)}
        [🧮 지표 설계도 (metric_plan) 규칙]
        - 엑셀의 숫자가 모두 위 [지표 사전]의 지표로 채워지면 "metric_plan" 의 use 를 true 로 하고, 지표명·구분명은 위 목록의 이름을 글자 그대로 쓰십시오. 이때 SQL 은 시스템이 지표 정의대로 조립하므로 "sql_query" 는 "NONE", "extra_sql_queries" 는 빈 배열로 두십시오.
          · metrics: 필요한 지표 (비율은 지표가 아님 — 등록율이면 그 분자·분모 지표만. 합격·등록 인원의 정의는 질문·사전지식을 따르고, 지정이 없으면 설명에 '이라고만 하면 이 지표'라고 적힌 지표)
          · dimensions: 엑셀 행 이름 열과 머리글 각 단이 가리키는 구분 (양식에 없는 구분은 넣지 않음)
          · filters: 질문·파일명에 나온 조건 (학년도·모집구분 등, 엑셀에 칸이 없어도 반드시). 값은 질문에 쓴 말 그대로 적어도 됨 (시스템이 실제 값으로 맞춤)
        - 사전에 없는 숫자가 하나라도 필요하면 use 를 false 로 하고 지금까지처럼 SQL 을 직접 작성하십시오.
"""
        else:
            excel_structure_text = json.dumps(empty_cells_info, ensure_ascii=False)
            grid_router_rules = ""
            metric_catalog = {"metrics": [], "dims": []}

        # 라우터 추론 설정: 격자 양식은 여러 출처·구분 열을 맞춘 SQL 이 필요해 추론을 켬 (.env EXCEL_GRID_ROUTER_THINKING=off|low|medium)
        router_effort, router_thinking_off = "low", llm_client.ROUTER_THINKING_OFF
        if grid:
            grid_think = app_config.get("EXCEL_GRID_ROUTER_THINKING")
            if grid_think in ("low", "medium", "high"):
                router_effort, router_thinking_off = grid_think, False


        print(f"[EXCEL-AUTOFILL] 📊 1단계: 엑셀 파악 완료 (빈 셀 {len(empty_cells_info)}개, 기존 데이터 {len(existing_data_context.split(chr(10))) if existing_data_context else 0}개 감지)")
        
        # 2. Text-to-SQL (라우터) 구동
        router_model_name = router_model_name or model_name

        # [사용자 명시 지시] 질문에 문서명('OOO에서/만/기준/보고') 또는 정형DB·테이블명 한정이 있으면 라우터 판단보다 우선 적용
        explicit_docs, explicit_doc_only = find_explicit_docs(question)
        db_only_reason = detect_db_only_intent(question, conn)

        print(f"[EXCEL-AUTOFILL] 🧠 2단계: AI 통계 SQL 쿼리 설계 중... (사용 모델: {router_model_name})")
        metric_plan_json_hint = (
            ',\n            "metric_plan": {"use": true, "metrics": ["[지표 사전]의 지표명 (예: 지원인원)"], "dimensions": ["엑셀 행·머리글의 구분명 (예: 학과, 전형)"], '
            '"filters": [{"dimension": "학년도", "values": ["2026"]}, {"dimension": "모집구분", "values": ["질문·파일명의 값"]}]}  '
            '← 숫자가 모두 지표 사전에 있으면 반드시 이것을 채우고 sql_query 는 NONE'
        ) if grid and metric_catalog["metrics"] else ""
        sql_router_prompt = f"""
        너는 대동대학교 입시처의 [엑셀 매핑 전문 데이터 아키텍트]야.
        {today_line()}
        사용자가 첨부한 엑셀 파일의 빈 칸을 채우기 위해 필요한 통계 데이터를 DB에서 추출하는 T-SQL 쿼리를 하나 작성해야 해.

        [관리자 등록 최상위 사전지식]
        {pre_supplemental_text if pre_supplemental_text else "등록된 사전지식 없음"}
        - 위 [관리자 등록 최상위 사전지식]에 명시된 규칙은 질문의 의도 파악과 SQL 쿼리 설계 시 절대적으로 준수해야 하는 1순위 예외 규칙입니다.
        
        [가장 중요한 SQL 작성 규칙]
        1. 🚨 **[전처리(Pre-mapping) 장려 및 줄바꿈 절대 금지]** 제공된 [엑셀 빈 셀 구조]의 헤더 명칭(예: '대학졸업자_2년제졸업자')을 참고하여, DB의 원본 데이터를 `CASE WHEN` 등을 사용해 엑셀 키워드와 최대한 똑같이 맞춰서(가공해서) 출력해 주는 것을 적극 권장합니다. **단, 쿼리가 길어지더라도 따옴표('') 내부 문자열에 절대 줄바꿈(Enter/Newline)을 넣지 마십시오!** (문법 에러 발생 원인). 컬럼의 Alias(AS `[전형명]`)는 반드시 `Sys_ColumnCatalog` 스키마에 존재하는 원본 컬럼명만 사용해야 하며, 엑셀 구조를 흉내 내려고 가로로 PIVOT 하지 말고 세로(Row) 방향으로 추출하세요.
        2. 컬럼명이 한글일 수 있으므로 대괄호 []를 반드시 사용해.
        3. 🚨 **[띄어쓰기 절대 금지]** 대괄호 `[]` 내부에는 **어떤 이유로도 단 한 칸의 공백도 넣지 마세요!** (예: `[ 수험번호]`, `[전형 명]`, `[지원인 원]`처럼 공백이 하나라도 들어가면 치명적 에러가 발생합니다. 무조건 `[수험번호]` 처럼 공백을 완전히 붙이세요.)
        4. **[별칭(Alias) 공백 금지 및 대괄호 필수]** `AS [지원_인원]` 처럼 별칭 대괄호 안에도 띄어쓰기를 절대 금지합니다.
        5. **[문자열 비교 공백 엄수]** 조건절에서 문자열을 비교할 때 카탈로그에 정의된 문자열 구조를 임의로 띄어쓰지 마세요. 무조건 원본과 똑같이 붙여 쓰세요.
        6. **[LIKE 검색어 공백 절대 금지]** `LIKE` 검색 시 `LIKE '%수능 전형%'` 처럼 단어 사이에 공백을 임의로 넣지 마세요.
        7. **[학년도 자동 추출 강제]** 사용자가 명시적으로 학년도를 말하지 않더라도, 파일명이나 질문의 연도를 찾아 학년도 조건(`WHERE [학년도열] = '추출된연도'`)을 넣으세요. 학년도 열 이름은 테이블마다 다를 수 있으므로, 반드시 쿼리하는 테이블의 스키마에 적힌 학년도 열 이름을 SELECT·WHERE·GROUP BY 모두에서 글자 그대로 사용하십시오.
        8. 🚨 **[UNION ALL 더미 행 생성 절대 금지]** 엑셀의 빈 셀 구조를 똑같이 따라 하겠다고 0으로 채워진 야간 학과나 더미 행을 `UNION ALL`로 억지로 생성하지 마십시오! DB에 실재하는 학과의 데이터만 단순 `GROUP BY`로 뽑아주면 빈 셀(0값) 매핑은 파이썬이 알아서 완벽히 처리합니다. 
        9. **[ORDER BY 절대 사용 금지]** MS-SQL 오류 방지를 위해 쿼리 마지막에 `ORDER BY` 절을 절대로 작성하지 마십시오!
        10. 🚨 **[일대다 조인 뻥튀기 방지 및 원본 컬럼명 보존]** 기준 정보 테이블과 상세 내역 테이블을 JOIN할 때 1:N 관계로 인해 숫자가 중복(뻥튀기)되지 않도록 주의하십시오. 이를 방지하기 위해 그룹핑 과정에서 가상의 세부 명칭(예: `[세부분류]`)을 생성하여 쪼갰다면, 최종 SELECT 절에서 임의로 `[출력명칭]` 같은 가짜 별칭을 만들지 마십시오. 반드시 매핑 시스템이 인식할 수 있도록 **원래 스키마에 존재하던 원본 컬럼명(Alias)**을 그대로 사용하여 덮어씌워야 합니다. 가짜 컬럼명을 반환하면 매핑 시스템이 데이터를 찾지 못해 모두 0으로 처리됩니다. (올바른 예: `COALESCE([A].[세부분류], [Q].[기준컬럼]) AS [기준컬럼]`)
        11. 🚨 **[절대 PIVOT 금지 및 스키마 원본 컬럼 강제]** 제공된 [키워드]들을 토대로 쿼리의 SELECT 컬럼(Alias)으로 억지로 PIVOT을 만들면 파이썬 서버에서 즉각 500 에러가 터집니다! 가로로 펼치는(PIVOT) 쿼리나 스키마에 없는 이상한 파생 컬럼을 억지로 생성하는 것을 엄격히 금지합니다. 반드시 **Sys_ColumnCatalog에 정의된 원본 컬럼명**만을 사용하여 세로 방향(Row 단위)의 정규화된(Normalized) 기본 1차원 테이블 구조로만 결과를 출력해야 합니다.
        12. 🚨 **[GROUP BY 8120 오류 완벽 방지 (반복 금지)]** MS-SQL에서 `SELECT` 절에 긴 `CASE WHEN` 구문을 사용하고 `GROUP BY` 절에 그대로 복사해서 넣을 경우, 줄바꿈/띄어쓰기 불일치로 8120 에러가 폭발적으로 발생합니다. 이 치명적 오류를 원천 차단하기 위해, **`GROUP BY` 절 내부에 `CASE WHEN` 구문을 사용하는 것을 엄격히 금지**합니다! 반드시 CTE나 인라인 뷰(서브쿼리)를 사용하여 `CASE WHEN`으로 가공된 컬럼(예: `[가공된_컬럼명]`)을 먼저 정의한 뒤, 메인 쿼리에서는 단순히 `GROUP BY [기준컬럼1], [가공된_컬럼명]` 형태로 깔끔하게 묶으십시오.
        13. 🚨 **[문자열 숫자형 변환 필수 (SUM 에러 방지)]** 스키마에서 수치 데이터를 나타내는 컬럼이 `nvarchar` 타입일 경우, `SUM()` 집계 함수를 사용할 때 원본 그대로 쓰지 마십시오! 반드시 `SUM(CASE WHEN ISNUMERIC([문자형수치컬럼])=1 THEN CAST([문자형수치컬럼] AS INT) ELSE 0 END)` 형태로 안전하게 형변환(Casting)하여 8117 에러를 완벽히 차단하십시오.
        14. 🚨 **[합계(Total) 자동 산출 (ROLLUP 필수)]** [엑셀 빈 셀 구조]를 살펴봤을 때 '합계', '계', '소계', '전체' 등의 집계(Total) 칸이 존재한다면, 파이썬 단의 매핑 AI가 직접 계산하지 않도록 **쿼리의 `GROUP BY` 절에 반드시 `WITH ROLLUP` (또는 CUBE) 구문을 추가**하여 DB 단에서 완벽하게 계산된 합계 행(Row)을 함께 추출해 주십시오.

        [데이터베이스 스키마 및 힌트]
        (아래 스키마의 ai_description에 적힌 값(힌트)들을 꼼꼼히 확인하고 쿼리를 작성하세요)
        {dynamic_schema}

        [첨부 엑셀 파일명 (기준 학년도/학기 유추에 활용)]
        {file.filename}

        [엑셀 빈 셀 구조 (이 셀들을 채우기 위한 데이터가 필요함)]
        (아래 엑셀 구조를 참고하여 어떤 테이블과 컬럼이 필요한지 맥락을 파악하십시오. 단, 절대 1번 규칙[스키마 전용 쿼리]을 어기고 엑셀 모양대로 PIVOT하거나 데이터를 변형하지 마십시오.)
        {excel_structure_text}
        {grid_router_rules}
        [엑셀 기존 내용 (머리글 등 이미 입력된 셀)]
        {existing_data_context if existing_data_context else "없음"}
        - 위 [엑셀 빈 셀 구조]가 비어 있다면([]) 사용자가 머리글만 있는 빈 양식을 올린 것입니다. 이때는 이 머리글이 채워야 할 표의 열 구성이므로, 머리글과 의미가 일치하는 테이블·컬럼을 카탈로그에서 찾아 그 열들을 행 단위로 반환하는 쿼리를 작성하십시오. 이 경우 결과는 시스템이 그대로 엑셀에 적으므로 SELECT 의 각 열 별칭(AS)을 엑셀 머리글과 글자 그대로 같게 하고(예: AS [입시년도]), 집계가 필요 없으면 원본 값을 그대로 조회하며 ROLLUP 은 쓰지 마십시오.

        [사용자 질문/지시]
        {question}

        [출력 지침]
        1. 🚨 **[최우선 판별 규칙 - 지능형 카탈로그 매핑]** 사용자의 [사용자 질문/지시] 속에 포함된 명칭이나 조건어(예: "OOO만 보고", "XXX에서 찾아")를 위 [데이터베이스 스키마 및 힌트]에 제공된 실제 카탈로그 이름들과 대조하여 스스로 검색 모드("search_mode")를 결정하십시오.
           - 질문 속 단어가 **비정형 문서 목록 (ChromaDB에 저장됨)의 파일명이나 타이틀**과 의미상/텍스트상 일치한다면 (예: "2027학년도 모집요강만 보고" -> '2027학년도 모집요강.pdf' 존재 확인), 무조건 "DOC_ONLY"로 강제 설정하십시오.
           - 질문 속 단어가 **MS-SQL 테이블 구조의 테이블명이나 용도**와 의미상/텍스트상 일치한다면 (예: "입학정원만 보고" -> 'ADMISSIONQUOTA' 테이블 존재 확인), 무조건 "DB_ONLY"로 강제 설정하십시오.
           - 위와 같은 명시적 대조가 없거나 두 영역 모두 검색이 필요한 일반적인 경우: "HYBRID"
        2. 만약 "search_mode"가 "DOC_ONLY"라면 "sql_query"는 반드시 "NONE"으로 출력하십시오.
        3. 그 외 정형 통계(지원인원, 등록인원 등)가 필요하다면 엑셀의 빈칸을 모두 채울 수 있는 포괄적인 T-SQL SELECT 문을 작성하십시오.
        4. "search_mode"가 "DB_ONLY"가 아니라면, 엑셀 빈칸을 채우는 데 꼭 필요한 비정형 문서만 [데이터베이스 스키마 및 힌트]의 비정형 문서 목록에서 골라 "rag_documents"에 공식 파일명(제목)을 글자 그대로 나열하십시오. 시스템은 이 이름과 카탈로그 문서명을 대조해서만 문서를 찾으므로 카탈로그에 없는 설명형 문구는 쓰지 마십시오. 필요 없는 문서는 넣지 마십시오. (문서는 통째로 전달되어 비용이 크므로 최소한으로 선택)

        오직 순수 JSON 형식으로만 응답해. 마크다운 기호 금지.
        {{
            "search_mode": "DB_ONLY | DOC_ONLY | HYBRID",
            "sql_query": "엑셀의 빈칸을 모두 채울 수 있는 포괄적인 T-SQL SELECT 문 (DOC_ONLY인 경우 'NONE')",
            "extra_sql_queries": ["격자 양식에서 다른 테이블의 숫자가 더 필요할 때만 추가 쿼리 (그 외 빈 배열)"],
            "target_documents": ["사용자가 특정 문서를 지정한 경우 해당 파일명들"],
            "rag_documents": ["엑셀을 채우는 데 필요한 비정형 문서 파일명들 (DB_ONLY 이면 빈 배열)"]{metric_plan_json_hint}
        }}
        """
        
        # JSON 응답 강제화를 위한 스키마 (표준 JSON Schema: Claude 는 구조화 출력, Gemini 는 response_schema 로 자동 변환)
        router_schema = {
            "type": "object",
            "properties": {
                "search_mode": {"type": "string", "description": "DB_ONLY | DOC_ONLY | HYBRID"},
                "sql_query": {"type": "string", "description": "엑셀의 빈칸을 모두 채울 수 있는 포괄적인 T-SQL SELECT 문 (DOC_ONLY인 경우 'NONE')"},
                "target_documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "질문자가 특정 문서를 명시적으로 지정하여 검토를 요구한 경우 일치하는 공식 파일명 리스트. 지정 없으면 빈 배열"
                },
                "rag_documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "엑셀 빈칸을 채우는 데 꼭 필요한 비정형 문서 파일명 리스트. DB_ONLY 이면 빈 배열"
                },
                "extra_sql_queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "격자 양식에서 다른 테이블의 숫자가 더 필요할 때만 추가하는 T-SQL SELECT 문. 그 외에는 빈 배열"
                }
            },
            "required": ["search_mode", "sql_query", "target_documents", "rag_documents", "extra_sql_queries"],
            "additionalProperties": False
        }
        if grid and metric_catalog["metrics"]:
            router_schema["properties"]["metric_plan"] = {
                "type": "object",
                "description": "지표 사전으로 채울 수 있을 때의 설계도 (use=false 이면 sql_query 를 직접 작성)",
                "properties": {
                    "use": {"type": "boolean"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                    "dimensions": {"type": "array", "items": {"type": "string"}},
                    "filters": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"dimension": {"type": "string"}, "values": {"type": "array", "items": {"type": "string"}}},
                        "required": ["dimension", "values"], "additionalProperties": False}},
                },
                "required": ["use", "metrics", "dimensions", "filters"],
                "additionalProperties": False,
            }
            router_schema["required"].append("metric_plan")

        # [큰 문서 확인 후 재요청] 보관해 둔 라우터 응답 원문을 재사용 (라우터 재호출/비용 없음)
        # 이후 JSON 파싱·SQL 컬럼 보정은 같은 입력으로 다시 실행되므로 결과가 동일합니다.
        resume_state = None
        if pending_id:
            purge_pending_router()
            resume_state = PENDING_ROUTER.get(pending_id)
            if not resume_state:
                return {
                    "status": "cancelled",
                    "reason": "pending_expired",
                    "message": "⏱️ 확인 대기 시간(15분)이 지나 요청이 만료되었습니다. 같은 요청을 다시 보내 주세요."
                }

        log_question = question  # 감사 로그에 남길 질문 (확인 후 이어지는 요청이면 원 로그 번호 표시)
        if choice_state:
            prev_id = choice_state.get("log_id")
            picked = ", ".join(f"{c['topic']}={c['answer']}" for c in user_choices or [])
            log_question = f"[{'#' + str(prev_id) + ' ' if prev_id else ''}이어서 · 기준 선택: {picked}] {original_question}"
        if resume_state:
            # 라우터 비용은 확인 대기 로그에 이미 기록됨 → 이어지는 요청은 추가 비용만 기록 (토큰 0)
            sql_response = llm_client.LLMResult(text=resume_state["router_text"], in_tokens=0, out_tokens=0)
            decision_str = "포함" if large_doc_decision == "include" else "제외"
            prev_id = resume_state.get("log_id")
            if not choice_state:
                log_question = f"[{'#' + str(prev_id) + ' ' if prev_id else ''}이어서 · 큰 문서 {decision_str}] {question}"
            print(f"[EXCEL-AUTOFILL] 🧠 라우터 AI: 이전 판단 결과 재사용 (큰 문서 {decision_str} 선택, 라우터 재호출 없음)")
        else:
            # 동기 SDK 호출이 이벤트 루프를 막지 않도록 별도 스레드에서 실행
            sql_response = await asyncio.to_thread(
                llm_client.generate, router_model_name, router_api_key, sql_router_prompt,
                json_schema=router_schema, effort=router_effort, timeout=180, thinking_off=router_thinking_off
            )

        router_in_tokens = sql_response.in_tokens + revise_in
        router_out_tokens = sql_response.out_tokens + revise_out

        # 에러 방어: 변수 사전 초기화 (파싱 실패 시 서버 뻗음 방지)
        search_mode = "HYBRID"
        sql_query = "NONE"
        original_sql_query = "NONE"  # DOC_ONLY 등 쿼리가 없을 때도 감사 로그 기록이 실패하지 않도록
        target_documents = []
        rag_documents = []
        extra_sql_queries = []
        metric_notes, metric_plan_text = [], ""  # [지표 사전] 조립 안내·설계도 (답변·로그용)
        metric_plan_used = (choice_state or {}).get("metric_plan")  # 조립에 쓴 설계도 (기준 바꿔 다시 채우기용, 재요청이면 이전 것 유지)
        time_router_end = time.time()

        # JSON 파싱
        try:
            response_text = sql_response.text.strip()
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "").replace("```", "").strip()
            elif response_text.startswith("```"):
                response_text = response_text.replace("```", "").strip()
                
            parsed_json = json.loads(response_text)
            search_mode = parsed_json.get("search_mode", "HYBRID")
            sql_query = parsed_json.get("sql_query", "NONE")
            target_documents = parsed_json.get("target_documents", []) or []
            rag_documents = parsed_json.get("rag_documents", []) or []
            extra_sql_queries = [q for q in (parsed_json.get("extra_sql_queries", []) or []) if q and q.strip().upper() != "NONE"]

            # [지표 사전] 설계도가 있으면 SQL 을 지표 정의대로 조립 (사전에 없는 지표 등 오류면 AI 가 쓴 SQL 사용)
            plan = parsed_json.get("metric_plan") or {}
            if grid and plan:
                print(f"[EXCEL-AUTOFILL] 🧮 지표 설계도: {json.dumps(plan, ensure_ascii=False)}")
            # use=false 여도 지표가 모두 사전에 있어 조립되면 정의대로 조립한 SQL 을 우선 (AI 가 정의를 바꿔 쓰는 오류 방지)
            if grid and (plan.get("use") or plan.get("metrics")) and search_mode != "DOC_ONLY":
                # 양식에 없는 구분(지역·정원내외 등)은 빼고 조립 (결과 행이 불어나 대응표가 흔들리는 것 방지)
                import value_resolver
                from main import get_value_dictionary
                plan, dropped_dims = metric_query.prune_dimensions(
                    plan, metric_catalog, [[l for l in s["labels"] if not excel_grid.is_total_label(l)] for s in grid["slots"]],
                    get_value_dictionary(conn) if conn else {}, value_resolver.HISTORY)
                if dropped_dims:
                    metric_notes.append(f"양식에 칸이 없는 구분 {dropped_dims} 은(는) 빼고 조회")
                    print(f"[EXCEL-AUTOFILL] 🧮 양식에 없는 구분 제외: {dropped_dims}")
                built, plan_notes, plan_errors = metric_query.build_sql(plan, metric_catalog)
                if built:
                    sql_query, extra_sql_queries = built[0], built[1:]
                    metric_plan_used = plan
                    metric_notes += plan_notes
                    metric_plan_text = (f"-- [지표 사전 설계도] 지표 {plan.get('metrics')} / 구분 {plan.get('dimensions')} / 조건 "
                                        + ", ".join(f"{f.get('dimension')}={f.get('values')}" for f in plan.get("filters") or []))
                    print(f"[EXCEL-AUTOFILL] 🧮 지표 사전으로 SQL 조립: {len(built)}개 쿼리 {plan_notes}")
                elif sql_query and sql_query.strip().upper() != "NONE":
                    print(f"[EXCEL-AUTOFILL] 🧮 지표 설계도 사용 불가 → AI 작성 SQL 사용: {plan_errors}")
                else:
                    metric_notes.append(f"지표 설계도를 쓸 수 없음: {'; '.join(plan_errors)}")

            if target_documents:
                print(f"[EXCEL-AUTOFILL] 🎯 타겟 문서 지정됨: {target_documents}")
            if rag_documents:
                print(f"[EXCEL-AUTOFILL] 📄 라우터 선택 문서: {rag_documents}")

            # [사용자 명시 지시 우선 적용] 라우터 판단보다 질문의 명시적 한정을 우선합니다.
            if explicit_docs and explicit_doc_only and not db_only_reason:
                search_mode = "DOC_ONLY"
                print(f"[EXCEL-AUTOFILL] 👤 사용자 지정 문서만 사용: {[d['meta'].get('filename') for d in explicit_docs]}")
            elif db_only_reason and not explicit_docs:
                search_mode = "DB_ONLY"
                print(f"[EXCEL-AUTOFILL] 👤 사용자 지정 '{db_only_reason}' 한정 → 정형 DB만 조회")

            if search_mode == "DOC_ONLY":
                sql_query = "NONE"
            
            time_router_end = time.time()
            print(f"[EXCEL-AUTOFILL] ⏱️ 1단계(라우터 AI 판단) 소요 시간: {time_router_end - start_time:.2f}초")
            print(f"[EXCEL-AUTOFILL] 🔀 라우터 판별 검색 모드: {search_mode}")
            
            # [2차 절대 방어선] 정규식을 이용해 대괄호 [ ] 내부의 모든 종류의 공백(띄어쓰기, 줄바꿈, 탭, 눈에 보이지 않는 유니코드 공백 등) 강제 삭제
            # 예: [수험 번호] 또는 [ 수험번호] -> [수험번호]
            if sql_query and sql_query != "NONE":
                original_sql_query = sql_query  # [수정] 오타 교정 전의 진짜 원본 쿼리 보존
                if metric_plan_text:
                    original_sql_query = f"{metric_plan_text}\n{sql_query}" + "".join(
                        f"\n\n-- [지표 사전 조립 Q{i}]\n{q}" for i, q in enumerate(extra_sql_queries, 2))
                
                # [1.5차 절대 방어선] 따옴표('') 내부의 줄바꿈(\n) 강제 제거 (문자열 중간 엔터 에러 방지)
                sql_query = re.sub(r"'[^']*'", lambda m: m.group(0).replace('\n', '').replace('\r', ''), sql_query)

                # \s+ 로 일반 공백 처리 후, 모든 형태의 공백을 리스트로 명시하여 완벽 제거
                sql_query = re.sub(r'\[([^\]]+)\]', lambda m: '[' + re.sub(r'[\s\u200B\u200C\u200D\uFEFF\u3000]+', '', m.group(1)) + ']', sql_query)
                sql_query = sql_query.replace("[ ", "[").replace(" ]", "]")
                
                # [3차 방어선] 스키마 기반 동적 오타 자동 교정 (Self-Healing)
                import difflib
                try:
                    # 1. DB에서 실제 유효한 컬럼명 리스트 확보
                    valid_columns = []
                    if conn:
                        # 실제 DB 열 이름 기준 (읽지 못하면 카탈로그로 대체)
                        real_cols = get_real_table_columns(conn)
                        if real_cols:
                            valid_columns = [c for cols in real_cols.values() for c, _ in cols]
                        else:
                            col_cursor = conn.cursor()
                            col_cursor.execute("SELECT column_name FROM Sys_ColumnCatalog")
                            valid_columns = [row[0] for row in col_cursor.fetchall()]
                    
                    if valid_columns:
                        # CTE 등에서 자주 쓰이는 가상 컬럼명/별칭 강제 추가 (오타 교정 대상에서 제외)
                        # 이 쿼리 안에서 직접 만든 이름(AS 별칭·WITH 임시 테이블)과 실제 테이블 이름은 오타 교정 대상에서 제외
                        # (예전에는 자주 쓰던 별칭을 코드에 고정 목록으로 적어 두었음)
                        valid_columns.extend(re.findall(r'(?i)\bAS\s*\[([^\]]+)\]', sql_query))
                        valid_columns.extend(re.findall(r'(?i)(?:\bWITH|,)\s*\[?([A-Za-z0-9_가-힣]+)\]?\s+AS\s*\(', sql_query))
                        if real_cols:
                            valid_columns.extend(real_cols.keys())
                        
                        # 2. AS 별칭 부분 보호 (AS [별칭] 부분을 임시 문자열로 치환하여 교정에서 제외)
                        # 공백이 없거나(AS[별칭]) 테이블명.컬럼명([A].[컬럼명]) 등 보호
                        alias_placeholders = {}
                        def alias_replacer(match):
                            placeholder = f"__ALIAS_{len(alias_placeholders)}__"
                            alias_placeholders[placeholder] = match.group(0)
                            return placeholder
                            
                        temp_query = re.sub(r'(?i)\bAS\s*\[([^\]]+)\]', alias_replacer, sql_query)
                        
                        # 3. 남은 쿼리 내의 모든 [컬럼명] 추출 및 유사도 대조
                        def column_healer(match):
                            col_name = match.group(1)
                            # 실제 컬럼 목록에 없으면 가장 유사한 컬럼으로 교정 (정확도 85% 이상으로 상향하여 과도한 교정 방지)
                            if col_name not in valid_columns:
                                matches = difflib.get_close_matches(col_name, valid_columns, n=1, cutoff=0.85)
                                if matches:
                                    print(f"[동적 교정 완료] AI 오타 감지 및 수정: {col_name} -> {matches[0]}")
                                    return f"[{matches[0]}]"
                            return match.group(0)
                            
                        temp_query = re.sub(r'\[([^\]]+)\]', column_healer, temp_query)
                        
                        # 4. 보호했던 AS 별칭 복원
                        for placeholder, original_alias in alias_placeholders.items():
                            temp_query = temp_query.replace(placeholder, original_alias)
                            
                        sql_query = temp_query
                        
                except Exception as col_err:
                    print(f"[EXCEL-AUTOFILL] 동적 컬럼 교정 실패 (무시됨): {col_err}")

        except Exception as e:
            print(f"[EXCEL-AUTOFILL] SQL JSON 파싱 오류: {e}")
            sql_query = "NONE"
            original_sql_query = "NONE"
            
        # 8127 구문 에러 원천 차단을 위해 ORDER BY 절 강제 제거
        raw_sql_query = re.sub(r'(?i)\s*ORDER\s+BY\s+.*', '', sql_query).strip()
        if not raw_sql_query.endswith(';'):
            raw_sql_query += ';'
            
        print_sql = format_sql_query(raw_sql_query)
        
        # SSMS 검증을 위한 쿼리 자동 저장 (가독성을 위해 포맷팅 적용)
        try:
            with open('latest_query.sql', 'w', encoding='utf-8') as f:
                f.write(print_sql)
        except Exception as f_err:
            print(f"[EXCEL-AUTOFILL] latest_query.sql 저장 실패: {f_err}")

        print(f"[EXCEL-AUTOFILL] [QUERY] AI 원본 쿼리문:")
        print("--- T-SQL START ---")
        print(format_sql_query(sql_query))
        print("--- T-SQL END ---")
        
        print(f"[EXCEL-AUTOFILL] [QUERY] 파이썬 보정 후 실제 실행 쿼리문:")
        print("--- T-SQL START ---")
        print(print_sql)
        print("--- T-SQL END ---")
        
        # 3. 쿼리 실행
        sql_context = "추출된 DB 데이터 없음"
        db_rows = []
        value_notes = []  # [이름 보정] 조건 값을 실제 DB 값으로 고친 내역 (답변·로그에 표시)
        if (raw_sql_query.upper().startswith("SELECT") or raw_sql_query.upper().startswith("WITH")) and conn:
            try:
                print("[EXCEL-AUTOFILL] 🔍 3단계: 통계 DB 데이터 획득 중...")
                raw_sql_query = resolve_values(conn, raw_sql_query, value_notes)
                query_runner = db_access.QueryRunner(conn, "staff")  # [DB 권한 분리] 읽기 계정 · 조회만
                try:
                    cursor = query_runner.execute(raw_sql_query)
                except db_access.QueryBlocked:
                    raise
                except Exception as first_err:
                    # [자가 교정 1회] 열 이름 오류·형변환 오류 등은 실제 열 목록과 오류 메시지를 주고 AI 가 한 번만 다시 쓰게 합니다.
                    print(f"[EXCEL-AUTOFILL] ⚠️ DB 에러 → AI 쿼리 재작성 1회 시도: {first_err}")
                    fixed_sql, fix_in, fix_out = await ai_fix_sql(
                        conn, question, existing_data_context, raw_sql_query, first_err, router_model_name, router_api_key)
                    router_in_tokens += fix_in
                    router_out_tokens += fix_out
                    if not fixed_sql:
                        raise first_err
                    fixed_sql = resolve_values(conn, fixed_sql, value_notes)
                    sql_query = fixed_sql
                    raw_sql_query = fixed_sql
                    original_sql_query = f"{original_sql_query}\n\n-- [DB 오류: {str(first_err)[:200]}]\n-- [AI 재작성 후 실행 쿼리]\n{raw_sql_query}"
                    print("[EXCEL-AUTOFILL] [QUERY] AI 재작성 쿼리문:")
                    print("--- T-SQL START ---")
                    print(format_sql_query(raw_sql_query))
                    print("--- T-SQL END ---")
                    cursor = query_runner.execute(raw_sql_query)
                cols = [column[0] for column in cursor.description]
                rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
                query_runner.close()

                for r in rows:
                    for k, v in r.items():
                        if hasattr(v, 'isoformat'):
                            r[k] = v.isoformat()
                        elif isinstance(v, Decimal):
                            r[k] = float(v)
                            
                # 파이썬 레벨에서 DB 결과 강제 정렬 (ORDER BY 8127 에러 회피 및 하드코딩 제거)
                # 쿼리의 SELECT 컬럼 순서(보통 대분류->소분류)를 기준으로 자동 그룹핑 정렬을 수행합니다.
                if rows:
                    rows.sort(key=lambda x: tuple(str(v) for v in x.values()))
                        
                db_rows = rows
                sql_context = json.dumps(rows, ensure_ascii=False)
            except Exception as e:
                # DB 에러 발생 시 2단계 AI로 넘어가면 가짜(환각) 데이터를 생성하므로 즉시 에러를 던져 중단합니다.
                error_msg = f"DB 쿼리 실행 중 오류가 발생했습니다: {str(e)}\n\n[AI 원본 쿼리]\n{original_sql_query}\n\n[실제 실행 쿼리]\n{sql_query}"
                print(f"[EXCEL-AUTOFILL] DB 에러 (즉시 중단): {e}")
                raise HTTPException(status_code=500, detail=error_msg)

        # [NEW] 3.5단계: 비정형 DB(ChromaDB)에서 문서 검색
        print("[EXCEL-AUTOFILL] 📚 3.5단계: 비정형 DB 문서 검색 중...")
        chroma_context = "검색된 비정형 문서가 없습니다."
        # 파일명에서 학년도 자동 추출, 없으면 질문에서 추출
        year_match = re.search(r'(202\d)', file.filename)
        if not year_match:
            year_match = re.search(r'(202\d)', question)
        target_year = year_match.group(1) if year_match else "ALL"

        chroma_context = ""
        used_doc_names = []
        try:
            if search_mode == "DB_ONLY":
                chroma_context = "사용자 지시로 인해 비정형 문서 검색이 생략되었습니다."
                print("[EXCEL-AUTOFILL] 🚫 사용자 지시(DB_ONLY)에 따라 비정형 DB 검색 생략.")
            else:
                from main import rule_db, reference_db, name_bigram_score

                # =======================================================
                # [문서 선택] 기존에는 연도만 맞으면 문서를 전부(최대 200개) 넣어 토큰이 폭증했으므로,
                # 1) 질문에 직접 적힌 문서(명시 지정)  2) 라우터가 고른 문서(target_documents + rag_documents)만 넣습니다.
                # 3) 둘 다 없으면 질문·엑셀 파일명과 문서 제목의 한글 2글자 겹침 점수(0.6 이상, 연도 일치) 상위 2건으로 보완합니다.
                # (영어 임베딩의 한글 의미 검색은 신뢰도가 낮아 사용하지 않음)
                # =======================================================
                all_docs = []
                for source, col in (("rule", rule_db), ("ref", reference_db)):
                    got = col.get(include=["documents", "metadatas"])
                    for doc_text, meta in zip(got["documents"], got["metadatas"]):
                        all_docs.append({"doc_text": doc_text, "meta": meta, "source": source})

                def doc_matches(doc, names):
                    f_n = norm_doc_name(doc["meta"].get("filename"))
                    t_n = norm_doc_name(doc["meta"].get("title"))
                    for n in names:
                        n_n = norm_doc_name(n)
                        if len(n_n) >= 2 and any(x and (n_n in x or x in n_n) for x in (f_n, t_n)):
                            return True
                    return False

                explicit_names = {d["meta"].get("filename") for d in explicit_docs}
                router_names = list(target_documents) + list(rag_documents)
                selected = []
                if explicit_docs:
                    selected.extend(explicit_docs)
                if not (explicit_docs and explicit_doc_only):
                    for d in all_docs:
                        if d["meta"].get("filename") not in explicit_names and router_names and doc_matches(d, router_names):
                            selected.append(d)
                if not selected:
                    probe = f"{question} {file.filename}"
                    scored = []
                    for d in all_docs:
                        d_year = str(d["meta"].get("year", "ALL"))
                        if target_year != "ALL" and d_year not in (target_year, "ALL"):
                            continue
                        score = name_bigram_score(probe, d["meta"].get("title") or d["meta"].get("filename"))
                        if score >= 0.6:
                            scored.append((score, d))
                    selected = [d for _, d in sorted(scored, key=lambda x: -x[0])[:2]]
                    print(f"[EXCEL-AUTOFILL] 📄 지정/라우터 선택 문서 없음 → 글자 겹침 보완 선발 {len(selected)}건")

                # 같은 파일 중복 제거
                uniq, seen_f = [], set()
                for d in selected:
                    f = d["meta"].get("filename", "이름없음")
                    if f not in seen_f:
                        seen_f.add(f)
                        uniq.append(d)
                selected = uniq
                print(f"[EXCEL-AUTOFILL] 📄 최종 후보 문서: {[d['meta'].get('filename') for d in selected]}")

                # =======================================================
                # [큰 문서 확인 게이트] 사용자가 지정하지 않은 큰 문서(LARGE_DOC_TOKENS 초과)는 포함 여부를 묻습니다.
                # =======================================================
                if large_doc_decision != "include" and selected:
                    large_docs = []
                    large_doc_limit = app_config.get("LARGE_DOC_TOKENS")  # 환경설정 '큰 문서 확인 기준'
                    for d in selected:
                        fname = d["meta"].get("filename", "이름없음")
                        if fname in explicit_names or (target_documents and doc_matches(d, target_documents)):
                            continue  # 사용자가 지정한 문서
                        if len(d["doc_text"]) * 3 < large_doc_limit:
                            continue
                        tok = await asyncio.to_thread(llm_client.count_tokens, model_name, chat_api_key, d["doc_text"])
                        print(f"[EXCEL-AUTOFILL] [큰 문서 후보] {fname}: {len(d['doc_text']):,}자 / {tok:,} 토큰")
                        if tok > large_doc_limit:
                            large_docs.append((d, tok))

                    if large_docs:
                        large_ids = {id(d) for d, _ in large_docs}
                        if resume_state and large_doc_decision == "exclude":
                            selected = [d for d in selected if id(d) not in large_ids]
                            for d, tok in large_docs:
                                print(f"[EXCEL-AUTOFILL] [큰 문서 제외] {d['meta'].get('filename')} ({tok:,} 토큰)")
                        else:
                            large_chars = sum(len(d["doc_text"]) for d, _ in large_docs) or 1
                            large_tokens = sum(tok for _, tok in large_docs)
                            ratio = large_tokens / large_chars
                            other_chars = sum(len(d["doc_text"]) for d in selected if id(d) not in large_ids)
                            other_chars += len(sql_context or "") + len(json.dumps(empty_cells_info, ensure_ascii=False)) + len(existing_data_context or "") + len(question or "")
                            base_tokens = int(other_chars * ratio) + 5000
                            include_tokens = base_tokens + large_tokens
                            is_claude_model = llm_client.is_claude(model_name)

                            def cost_str(tokens):
                                if not is_claude_model:
                                    return ""
                                krw = llm_client.estimate_cost_krw(model_name, llm_client.LLMResult(text="", in_tokens=tokens))
                                return f" (입력 비용 약 ₩{krw:,.1f})"

                            lines = ["📚 **엑셀 채우기에 AI가 아래 큰 문서를 참고하려 합니다.**"]
                            for d, tok in large_docs:
                                lines.append(f"- {d['meta'].get('filename', '이름없음')}: 약 {tok:,} 토큰")
                            lines.append("")
                            include_line = f"- 포함하면: 입력 약 {include_tokens:,} 토큰{cost_str(include_tokens)}"
                            if is_claude_model and include_tokens > llm_client.MAX_PROMPT_TOKENS:
                                include_line += f" ⚠️ 한도 {llm_client.MAX_PROMPT_TOKENS:,} 토큰을 넘어 취소될 수 있습니다 (Gemini 모델 권장)"
                            lines.append(include_line)
                            lines.append(f"- 제외하면: 입력 약 {base_tokens:,} 토큰{cost_str(base_tokens)}")
                            lines.append("")
                            lines.append("이 문서가 엑셀 채우기에 꼭 필요한지 선택해 주세요. (토큰 수는 추정치이며, 출력 비용은 별도입니다)")

                            new_pending_id = uuid.uuid4().hex
                            # [확인 대기 로그] 지금까지 쓴 라우터 비용을 먼저 기록 (확인 없이 끝나도 비용이 로그에 남도록)
                            interim_log_id = insert_interim_audit_log(
                                conn, user_role=user_role, question=f"[큰 문서 확인 대기] {question}",
                                scraped_context=f"### [첨부 엑셀] 파일명: {file.filename}\n검색 모드: {search_mode} / 빈 셀 {len(empty_cells_info)}개",
                                sql_query=original_sql_query, answer="\n".join(lines),
                                latency_ms=int((time.time() - start_time) * 1000),
                                model_name=model_name, router_model_name=router_model_name,
                                router_in=router_in_tokens, router_out=router_out_tokens,
                                rag_documents="\n".join(f"{i}) {d['meta'].get('filename', '이름없음')} (약 {tok:,} 토큰, 확인 대기)" for i, (d, tok) in enumerate(large_docs, 1)),
                                router_latency_ms=int((time_router_end - start_time) * 1000),
                                router_mode=llm_client.mode_label(router_model_name, router_effort, router_thinking_off),
                                chat_mode="확인 대기 (최종 AI 미호출)")
                            PENDING_ROUTER[new_pending_id] = {
                                "created_at": time.time(),
                                "router_text": sql_response.text,
                                "router_in_tokens": router_in_tokens,
                                "router_out_tokens": router_out_tokens,
                                "log_id": interim_log_id,
                            }
                            print(f"[EXCEL-AUTOFILL] ✋ 큰 문서 {len(large_docs)}건 발견 → 사용자 확인 대기 (pending_id={new_pending_id[:8]}...)")
                            return {
                                "status": "confirm_large_docs",
                                "pending_id": new_pending_id,
                                "large_docs": [{"filename": d["meta"].get("filename", "이름없음"), "tokens": tok} for d, tok in large_docs],
                                "base_tokens": base_tokens,
                                "include_tokens": include_tokens,
                                "message": "\n".join(lines)
                            }

                doc_texts = [f"[{d['meta'].get('filename', '이름없음')}]\n{d['doc_text']}" for d in selected]
                used_doc_names = [d["meta"].get("filename", "이름없음") for d in selected]

                if doc_texts:
                    # 100개 이상의 청크(전체 PDF 분량)를 그대로 결합하여 테이블 누락 방지!
                    chroma_context = "\n\n".join(doc_texts[:200])
                    print(f"[EXCEL-AUTOFILL] 📚 검색 성공: {len(doc_texts)}개의 문서 문단(전체) 참조")
                else:
                    print("[EXCEL-AUTOFILL] 📚 검색된 문서 문단이 없습니다.")
        except Exception as e:
            print(f"[EXCEL-AUTOFILL] ⚠️ ChromaDB 문서 검색 오류 (무시됨): {e}")

        time_db_end = time.time()
        print(f"[EXCEL-AUTOFILL] ⏱️ 2단계(DB 및 문서 검색) 소요 시간: {time_db_end - time_router_end:.2f}초")

        # [빈 양식 직접 기록] 머리글만 있는 양식이고 DB 결과 열이 머리글과 일치하면 매핑 AI 없이 그대로 적습니다.
        direct_fill = build_direct_fill(ws, empty_cells_info, db_rows)
        direct_fill_used = direct_fill is not None

        # [격자 직접 기록] 행 이름 × N단 머리글 양식: 대응표 AI + 파이썬 계산·검산 (실패하면 기존 AI 매핑)
        grid_res = None
        # (조회 결과가 0행이어도 격자 경로에서 쿼리 보정을 시도 — 기존 AI 매핑은 0 으로 채워 버림)
        if not direct_fill_used and grid and conn and raw_sql_query.upper().startswith(("SELECT", "WITH")):
            print(f"[EXCEL-AUTOFILL] 🧩 4단계: 격자 직접 기록 시도 (추가 쿼리 {len(extra_sql_queries)}개, 대응표 AI: {model_name})")
            grid_res = await run_grid_fill(conn, grid, question, pre_supplemental_text, raw_sql_query, db_rows, extra_sql_queries,
                                           existing_data_context, model_name, chat_api_key, router_model_name, router_api_key, effort,
                                           schema_text=dynamic_schema.split("\n[현재 AI가 접근 가능한 비정형")[0],
                                           user_choices=user_choices, hint_text=f"{original_question} {file.filename}",
                                           value_notes=value_notes, metric_plan=metric_plan_used, metric_catalog=metric_catalog,
                                           reuse_mapping=reuse_mapping)
            router_in_tokens += grid_res["fix_in"]
            router_out_tokens += grid_res["fix_out"]
            if grid_res["sql_log"]:
                original_sql_query = f"{original_sql_query}\n\n{grid_res['sql_log']}"
            if grid_res["ok"]:
                print(f"[EXCEL-AUTOFILL] ✍️ 격자 직접 기록 {len(grid_res['cells'])}칸 (경고 {len(grid_res['warnings'])}건)")
            else:
                print(f"[EXCEL-AUTOFILL] ↩️ 격자 직접 기록 불가 → 기존 AI 매핑: {grid_res['fail'][:5]}")
                extra = [s for s in grid_res.get("sources", [])[1:]]
                if extra:
                    sql_context += "\n" + "\n".join(f"[추가 쿼리 {s['name']} 결과]\n{json.dumps(s['rows'], ensure_ascii=False)}" for s in extra)
        grid_used = bool(grid_res and grid_res["ok"])

        def make_choice_state(log_id):
            """[채우기 기준 확인] 기준만 바꿔 다시 채울 수 있도록 라우터 판단(실제 실행한 SQL 포함)과 기준 목록을 보관"""
            state_id = uuid.uuid4().hex
            PENDING_ROUTER[state_id] = {
                "created_at": time.time(),
                "ttl": app_config.get("EXCEL_CHOICE_TTL_SEC"),  # 기준 바꿔 다시 채우기 보관 시간 (기본 2시간, 지나면 처음부터 다시 실행)
                "type": "excel_choice",
                "router_text": json.dumps({
                    "search_mode": search_mode,
                    "sql_query": grid_res["sources"][0]["sql"] if grid_res.get("sources") else raw_sql_query,
                    "target_documents": target_documents, "rag_documents": rag_documents,
                    "extra_sql_queries": [s["sql"] for s in grid_res["sources"][1:]],
                }, ensure_ascii=False),
                "router_in_tokens": 0, "router_out_tokens": 0,
                "question": original_question,
                "decisions": grid_res["decisions"],
                "metric_plan": metric_plan_used,
                "mapping": grid_res.get("mapping"),
                "large_doc_decision": large_doc_decision,
                "log_id": log_id,
            }
            return state_id

        # [채우기 기준 확인] 질문·저장된 기본값·사용자 선택 어디에도 없는 계산 기준이 있으면 채우기 전에 묻기
        if grid_used and not choice_state:
            unresolved = excel_grid.unresolved_decisions(grid_res["decisions"])
            if unresolved:
                ask_lines = ["🧮 **채우기 전에 계산 기준을 확인해 주세요.** (질문이나 저장된 기본값에 없는 기준입니다)"]
                for d in unresolved:
                    ask_lines.append(f"- {d['question']} (AI 제안: {d['applied']})")
                interim_id = insert_interim_audit_log(
                    conn, user_role=user_role, question=f"[채우기 기준 확인 대기] {original_question}",
                    scraped_context=(f"### [첨부 엑셀] 파일명: {file.filename}\n검색 모드: {search_mode} / 빈 셀 {len(empty_cells_info)}개 (기준 확인 대기, 아직 채우지 않음)\n\n"
                                     f"[물어본 기준]\n" + "\n".join(f"- {d['topic']}: {d['question']} 선택지 {d['options']} (AI 제안: {d['applied']})" for d in unresolved)
                                     + f"\n\n[대응표 (AI 제안 기준)]\n{grid_res['mapping_text']}"),
                    sql_query=original_sql_query, answer="\n".join(ask_lines),
                    latency_ms=int((time.time() - start_time) * 1000),
                    model_name=model_name, router_model_name=router_model_name,
                    router_in=router_in_tokens, router_out=router_out_tokens,
                    chat_in=grid_res["map_in"], chat_out=grid_res["map_out"],
                    rag_documents="\n".join(f"{i}) {n}" for i, n in enumerate(used_doc_names, 1)),
                    router_latency_ms=int((time_router_end - start_time) * 1000),
                    db_latency_ms=int((time_db_end - time_router_end) * 1000),
                    chat_latency_ms=int((time.time() - time_db_end) * 1000),
                    router_mode=llm_client.mode_label(router_model_name, router_effort, router_thinking_off),
                    chat_mode="기준 확인 대기 · 대응표 " + llm_client.mode_label(model_name, grid_res["effort"]))
                state_id = make_choice_state(interim_id)
                print(f"[EXCEL-AUTOFILL] ✋ 계산 기준 {len(unresolved)}건 확인 대기 (pending={state_id[:8]}..., 로그 #{interim_id})")
                return {
                    "status": "confirm_excel_options",
                    "pending_id": state_id,
                    "log_id": interim_id,
                    "decisions": unresolved,
                    "message": "\n".join(ask_lines),
                }

        if direct_fill_used:
            mapping_result, direct_count = direct_fill
            final_in_tokens = final_out_tokens = 0
            final_effort = "-"
            answer_text = f"정형 DB 조회 결과 {direct_count}행을 엑셀 머리글에 맞춰 그대로 기록했습니다. (AI 매핑 생략: 행 누락·값 변형 없음)"
            print(f"[EXCEL-AUTOFILL] ✍️ 4단계: DB 결과 직접 기록 {direct_count}행 (최종 매핑 AI 호출 생략)")
        elif grid_used:
            mapping_result = grid_res["cells"]
            final_in_tokens, final_out_tokens = grid_res["map_in"], grid_res["map_out"]
            final_effort = grid_res["effort"]
            warn = grid_res["warnings"]
            lines = [f"격자 양식 {len(mapping_result)}칸을 DB 값으로 직접 계산해 기록했습니다. (AI 는 이름 대응표만 작성, 합계·비율은 시스템 계산)"]
            ok_notes = [n for n in grid_res["notes"] if n.startswith("총합 일치")]
            if ok_notes:
                lines.append("검산: " + " / ".join(n.replace("총합 일치: ", "") for n in ok_notes))
            if warn:
                lines.append(f"⚠️ 확인 필요 {len(warn)}건:")
                lines += [f"- {w}" for w in warn[:10]]
                if len(warn) > 10:
                    lines.append(f"- … 외 {len(warn) - 10}건 (감사 로그 참고)")
            else:
                lines.append("중복 배정·총합 불일치 없음.")
            if grid_res["summed"]:
                lines.append("합산된 구분 (엑셀에 칸이 없어 모두 더함, 의도와 다르면 질문에 조건을 적어 다시 요청):")
                lines += [f"- {x}" for x in grid_res["summed"]]
            if grid_res["omitted"]:
                lines.append("참고 (양식 범위 안에서 엑셀에 없는 DB 값, 의도한 것이면 무시):")
                lines += [f"- {o}" for o in grid_res["omitted"][:5]]
            if grid_res["criteria_text"]:
                lines.append("")
                lines.append(grid_res["criteria_text"])
                lines.append("(기준을 바꾸려면 아래 [기준 바꿔서 다시 채우기] 버튼 또는 질문에 기준을 적어 다시 요청하세요)")
            answer_text = "\n".join(lines)
        else:
            # 4. 최종 매핑 AI 구동
            print(f"[EXCEL-AUTOFILL] 🧠 4단계: 최종 엑셀 매핑 및 답변 생성 중... (사용 모델: {model_name})")

            final_prompt = f"""
            너는 대동대학교 입시처의 [엑셀 데이터 매핑 AI]야.

            [사용자 질문]
            {question}

            [관리자 등록 최상위 사전지식]
            {pre_supplemental_text if pre_supplemental_text else "등록된 사전지식 없음"}
            - 위 사전지식은 엑셀에 데이터를 매핑할 때 반드시 준수해야 하는 행정 룰입니다.

            [🚨 사용자 특별 지시사항 (최우선 적용 규칙) 🚨]
            - 사용자의 [사용자 질문] 내에 엑셀 값 입력과 관련된 명시적인 조건이나 제약(예: "제한없음은 제한없음으로 써라", "하이픈(-)은 제외하라" 등)이 있다면, **아래의 모든 기본 출력 지침보다 사용자의 이 지시를 최우선으로, 그리고 완벽하게 따르십시오!**
            - 단, 사용자의 질문이 엑셀 값에 대한 명시적 조건이 아니라 단순한 대화형 질문(예: "왜 이렇게 많아?", "이거 줄바꿈이니?" 등)일 경우, 사용자의 질문 내용 때문에 엑셀 매핑을 포기하거나 숫자를 임의로 0으로 만들어서는 안 됩니다. 무조건 DB 데이터를 있는 그대로 매핑하십시오.

            [주의 사항 (환각 방지 및 병합된 셀 처리)]
            - 사용자가 데이터 추출을 요청한 대상 연도는 '{target_year}'학년도입니다. 
            - 💡 **[데이터 매핑 최우선 및 결측치 규칙]**: 빈 셀을 채울 때는 무조건 [1. 정형 DB 추출 통계 데이터]의 값을 최우선적으로 매핑하십시오. DB 데이터에 값(예: 123)이 명확히 존재하는데도 사용자 질문 내용에 휘둘리거나 엑셀의 헤더명과 완벽하게 일치하지 않는다는 이유로 임의로 0으로 무시하고 덮어쓰는 행위는 절대 금지됩니다! (유연하게 의미를 파악하여 매핑하세요.) 오직 **DB와 PDF 양쪽 모두에 데이터가 존재하지 않을 때만** 다른 연도 데이터를 지어내지 말고 0으로 처리하십시오.
            - 💡 **[PDF 표 병합(Merge) 데이터 추론 규칙]**: 비정형 PDF 문서의 표(Table) 특성상, 인접한 두 학과의 데이터가 동일할 경우 셀이 병합되어 텍스트 추출 시 **첫 번째 학과에만 값이 적히고 그 아래 학과는 값이 누락된 것(빈칸)처럼 보일 수 있습니다.** 만약 특정 학과 전형의 값이 비어있다면, **반드시 바로 위(또는 근처) 학과의 동일 전형 값을 확인하고, 병합된 셀이라고 판단되면 그 값을 똑같이 상속(복사)하여 채워 넣으십시오.**

            [데이터베이스 스키마 및 힌트]
            (각 테이블과 컬럼의 의미(ai_description)를 참고하여 아래 추출된 통계 데이터의 맥락을 이해하세요.)
            {dynamic_schema}

            [1. 정형 DB 추출 통계 데이터]
            {sql_context}
            [2. 비정형 PDF 추출 규정 문서 참조 내용]
            (🎯 핵심 지시: DB 통계와 함께 아래 PDF 문서 텍스트를 교차 검증하여 엑셀의 빈칸을 채우십시오.)
            {chroma_context}
        
            [첨부 엑셀 파일명]
            {file.filename}

            [현재 엑셀 파일에 존재하는 데이터(헤더 및 기존 값)]
            {existing_data_context if existing_data_context else "없음"}

            [엑셀 빈 셀 구조]
            (아래 빈 셀 좌표가 주어졌다면 해당 좌표에 맞게 채우고, 만약 비어있다면([]) 위 헤더 구조를 보고 AI가 스스로 적절한 행(예: 2행, 3행...)을 새롭게 무한대로 추가해가며 표를 완성해서 좌표를 생성하세요.)
            {json.dumps(empty_cells_info, ensure_ascii=False)}
        
            [출력 지침]
        
            출력은 반드시 안내 텍스트로 시작하되, 
            안내 텍스트는 **무조건 3줄 이내로 극도로 짧게 핵심만 요약**해. (절대 학과별로 길게 나열하지 마십시오! 최대 출력 한도에 걸립니다.)
        
            그 다음, 엑셀에 주입할 실제 데이터는 **반드시 마지막에 순수한 JSON 배열 형식으로만** 작성해.
            - **[중요: 의미 보존형 Key 네이밍 규칙 (Self-Correction)]** 출력 길이를 압축하면서도, 100줄 이상 장문 출력 시 AI 스스로 열(Column)이 밀리는 환각(Shift)을 원천 방지하기 위해 **각 행의 열 Key는 반드시 `[알파벳]_[컬럼명]` 형태로 결합**하여 작성하십시오. 절대 의미 없는 알파벳 단독(`"A"`)으로 쓰지 마십시오! 스스로 의미를 각인해야 합니다.
            - **[표기 일관성 범용 강제]** 데이터 표기 방식(예: 연도, 부서명 포맷 등)은 최초 1행에서 결정한 형식을 마지막 행까지 100% 동일하게 유지(Consistency)하십시오. 중간에 표기법을 임의로 변경하지 마십시오.
            - **[🔥 강력한 의미 유추 매핑 규칙 🔥]** DB 통계 결과의 전형명(예: `만학도`, `장애인대상자`)과 엑셀 헤더명(예: `만학도(7호)`, `장애인대상자(4호)`)이 글자 토씨 하나까지 완벽히 일치하지 않더라도, 괄호 안의 부가설명이나 기호 차이일 뿐 **핵심 의미가 같다면 반드시 동일한 항목으로 간주하여 데이터를 매핑하십시오.** 절대로 "이름이 다르다"며 0으로 누락시켜서는 안 됩니다! 데이터를 최대한 유연하고 똑똑하게 추론하여 실제 추출된 숫자 데이터를 적극적으로 채우십시오.
            - **[🚨 데이터 행(Row) 완전성 보장 (세로 생략 금지) 🚨]** 빈 엑셀 템플릿에 행을 창조해 낼 때, 문서에 존재하는 모든 학과와 전형 조합을 **단 하나도 누락시키지 말고 끝까지(100%) 추출하십시오.** 출력이 150줄을 넘어가더라도 중간에 힘들다고 임의로 생략하거나 멈추는 행위(Lazy Generation)는 절대 금지됩니다! 무조건 100% 전부 배열에 담으십시오.
            - **[🚨 데이터 열(Column) 완전성 보장 (가로 생략 금지) 🚨]** 각 행(row)을 출력할 때, [엑셀 빈 셀 구조]에 제시된 **마지막 열(예: `BI_`)까지 모든 컬럼(열) Key를 단 하나도 빠짐없이 100% 전부 적어 넣으십시오.** 뒤쪽에 위치한 '서해5도', '다자녀가정', '합계', '지원율' 등의 컬럼들도 값이 0이거나 비어있더라도 절대 임의로 생략(Truncation)하지 마십시오. 컬럼이 누락되면 시스템이 파괴됩니다.
            - **[🔥 치명적 규칙: "row" 키 절대 필수 🔥]** 답변 배열의 각 JSON 객체 안에는 무조건 `"row": [해당 행 번호]` 키를 **제일 첫 번째 항목**으로 반드시 포함하십시오. (예: `{{"row": 5, ...}}`) 만약 `"row"` 번호가 단 하나라도 누락되면 엑셀에 데이터를 매핑할 수 없어서 파멸적인 오류가 발생합니다! 빈 좌표를 참고하거나, 새 행을 창조할 때는 이전 행에서 `+1`씩 증가시켜서라도 **무조건 모든 객체에 "row" 키를 집어넣으십시오.**
            - 기본 규칙 (단, 위 '사용자 특별 지시사항'과 충돌 시 사용자 지시를 100% 우선함): 데이터 값이 숫자일 경우 가급적 정수형(`int`)으로 입력.
            - 💡 **[데이터 충돌 시 우선순위 규칙]**: 만약 [정형 DB 추출 통계 데이터]와 [비정형 PDF 추출 규정 문서]의 내용이 서로 상이하거나 충돌할 경우, 최신 통계 데이터인 **[정형 DB 추출 통계 데이터]의 값을 최우선으로 참고**하십시오.
            - **[필수: 문자열 보존 규칙] 만약 사용자가 "제한없음" 문자열이나 "하이픈(-)", 빈칸을 유지하라고 지시했다면, 강제로 숫자로 변환하지 말고 사용자의 요구대로 문자열을 그대로 매핑하거나 해당 셀을 과감히 생략하십시오.**
            - 만약 사용자가 "해당되지 않으면 0으로 채워줘"라고 지시했다면, 해당 영역의 빈칸이나 하이픈(-)에 0 값을 적극적으로 출력하십시오.
            - **[표 기호 해석 및 병합 셀 상속]**: 하이픈(-)·'제한없음' 해석과 병합 셀 상속 범위(같은 모집시기 내부만 등)는 위 [관리자 등록 최상위 사전지식]의 02_도메인룰·03_엑셀매핑 규칙을 그대로 따르십시오.
            ```json
            [
              {{"row": 2, "A_입시학년도": 2026, "C_지원학과명": "간호학부", "D_정원내외구분": "정원내", "E_전형명": "일반고"}},
              {{"row": 3, "A_입시학년도": 2026, "C_지원학과명": "응급구조과", "D_정원내외구분": "정원내", "E_전형명": "일반고"}}
            ]
            ```
            """
        
            # 수백 줄 JSON 출력이 필요하므로 Claude 는 max_tokens 를 넉넉히(64000) 지정
            final_effort = llm_client.resolve_effort(effort)
            final_response = await asyncio.to_thread(
                llm_client.generate, model_name, chat_api_key, final_prompt,
                effort=final_effort, timeout=600, max_tokens=64000
            )
            final_text = final_response.text

            final_in_tokens = final_response.in_tokens
            final_out_tokens = final_response.out_tokens
        
            # 5. 매핑 추출 및 엑셀 주입
            mapping_result = {}
            answer_text = final_text
        
            # 새로운 JSON 포맷 파싱 시도 (행 단위 2D 압축 포맷)
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', final_text, re.DOTALL)
            if not json_match:
                # 백틱이 없거나 닫히지 않았을 수 있음
                json_match = re.search(r'(\[\s*\{\s*"row".*)', final_text, re.DOTALL)

            if json_match:
                answer_text = final_text.replace(json_match.group(0), "").strip()
                try:
                    data_list = json.loads(json_match.group(1))
                    for item in data_list:
                        row_idx = item.get("row")
                        if row_idx is None:
                            continue
                        for col_key, val in item.items():
                            if col_key != "row" and isinstance(col_key, str):
                                # 의미 보존형 Key("A_입시학년도" 또는 "A")에서 앞의 알파벳만 추출
                                match = re.match(r'^([A-Z]+)', col_key.upper())
                                if match:
                                    coord = f"{match.group(1)}{row_idx}"
                                    mapping_result[coord] = val
                except Exception as e:
                    print(f"[EXCEL-AUTOFILL] 신규 JSON 2D 파싱 실패(정규식 폴백 시도): {e}")

            # JSON 파싱 실패했거나(Truncated), 파싱했지만 비어있는 경우 정규식으로 직접 추출 (Truncated 방어)
            if not mapping_result:
                print("[EXCEL-AUTOFILL] ⚠️ 강력한 정규식 추출 모드 가동 (Truncated JSON 방어)")
                row_blocks = re.findall(r'\{\s*"row"\s*:\s*(\d+)(.*?)\}', final_text, re.DOTALL)
                for row_idx_str, col_data in row_blocks:
                    kv_pattern = r'"([a-zA-Z]+)[^"]*"\s*:\s*(?:"([^"]+)"|([0-9\.-]+))'
                    for match in re.finditer(kv_pattern, col_data):
                        col_letter = match.group(1).upper()
                        str_val = match.group(2)
                        num_val = match.group(3)
                    
                        val = str_val if str_val is not None else num_val
                        if val is not None:
                            if isinstance(val, str) and re.match(r'^-?\d+(\.\d+)?$', val):
                                val = float(val) if '.' in val else int(val)
                            mapping_result[f"{col_letter}{row_idx_str}"] = val

            # 기존 방식 fallback
            if not mapping_result:
                map_match = re.search(r'\[EXCEL_MAP_START\](.*?)\[EXCEL_MAP_END\]', final_text, re.DOTALL)
                if map_match:
                    json_str = map_match.group(1).strip()
                    answer_text = final_text.replace(map_match.group(0), "").strip()
                    pattern = r'"([a-zA-Z]+[0-9]+)"\s*:\s*([0-9\.-]+)'
                    matches = re.findall(pattern, json_str)
                    for k, v in matches:
                        mapping_result[k.upper()] = float(v) if '.' in v else int(v)

        if metric_plan_text or metric_notes:
            answer_text = ((answer_text or "") + "\n\n지표 사전 사용: " + (metric_plan_text.replace("-- [지표 사전 설계도] ", "") or "-")
                           + "".join(f"\n- {n}" for n in metric_notes))
        if value_notes:
            answer_text = (answer_text or "") + "\n\n조건 값 보정 (실제 DB 값 기준):\n" + "\n".join(f"- {n}" for n in value_notes)

        filled_count = 0
        for coord, val in mapping_result.items():
            try:
                ws[coord].value = val
                filled_count += 1
            except Exception as e:
                print(f"[EXCEL-AUTOFILL] 셀 {coord} 쓰기 실패: {e}")
                
        def calc_cost(model, in_tok, out_tok):
            if llm_client.is_claude(model):
                return llm_client.estimate_cost_krw(model, llm_client.LLMResult(text="", in_tokens=in_tok, out_tokens=out_tok))
            elif "3.5" in model:
                return (in_tok / 1000000 * 1.25 + out_tok / 1000000 * 5.0) * 1400 * (1 + llm_client.VAT_RATE)
            else:
                return (in_tok / 1000000 * 0.075 + out_tok / 1000000 * 0.3) * 1400 * (1 + llm_client.VAT_RATE)
        
        router_cost = calc_cost(router_model_name, router_in_tokens, router_out_tokens)
        final_cost = calc_cost(model_name, final_in_tokens, final_out_tokens)
        total_cost = router_cost + final_cost
        total_tokens = router_in_tokens + router_out_tokens + final_in_tokens + final_out_tokens

        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        print(f"[EXCEL-AUTOFILL] ⏱️ 엑셀 채우기 총 소요 시간: {end_time - start_time:.2f}초")
        print(f"[EXCEL-AUTOFILL] 🎉 하이브리드 엑셀 채우기 성공! ({latency_ms}ms)")
        
        print("\n==================================================")
        print("🧾 [💸 엑셀 AI 요금 결제 내역 (영수증)]")
        print(f"[라우터 AI] 사용 모델: {router_model_name}")
        print(f"  - 입력: {router_in_tokens:,} / 출력: {router_out_tokens:,} (예상 비용: 약 {router_cost:.3f} 원)")
        print("--------------------------------------------------")
        print(f"[최종 매핑 AI] 사용 모델: {model_name}")
        print(f"  - 입력: {final_in_tokens:,} Tokens")
        print(f"  - 출력: {final_out_tokens:,} Tokens")
        print(f"  - 예상 비용: 약 {final_cost:.3f} 원")
        print("--------------------------------------------------")
        print(f"🔹 총 소모 토큰 합계: {total_tokens:,} Tokens")
        print(f"💰 총 예상 청구 비용: 약 {total_cost:.3f} 원 (KRW, 부가세 {llm_client.VAT_RATE:.0%} 포함)")
        print("==================================================\n")

        audit_log_id = None
        if conn:
            try:
                def safe_str(s):
                    return s.encode('cp949', errors='replace').decode('cp949') if s else ""

                # 로그 화면의 스크랩 칸에 첨부 엑셀의 파일명·머리글·빈 셀 수를 남깁니다.
                excel_log_context = (
                    f"### [첨부 엑셀] 파일명: {file.filename}\n"
                    f"검색 모드: {search_mode} / 빈 셀 {len(empty_cells_info)}개 → 채운 셀 {filled_count}개 "
                    f"({'DB 직접 기록' if direct_fill_used else '격자 직접 기록' if grid_used else 'AI 매핑'})\n"
                    f"[채운 후 엑셀 ({ws.title})]\n{sheet_to_log_table(ws)}"
                )
                if grid_res:
                    parts = []
                    if grid_res["fail"]:
                        parts.append("[격자 직접 기록 불가 사유]\n" + "\n".join(grid_res["fail"]))
                    if grid_res["criteria_text"]:
                        parts.append(grid_res["criteria_text"])
                    if grid_res["mapping_text"]:
                        parts.append("[대응표]\n" + grid_res["mapping_text"])
                    if grid_res["warnings"] or grid_res["notes"] or grid_res["omitted"]:
                        parts.append("[검산]\n" + "\n".join(["⚠️ " + w for w in grid_res["warnings"]] + grid_res["notes"]
                                                         + ["참고: " + o for o in grid_res["omitted"]]))
                    excel_log_context += "\n\n" + "\n\n".join(parts)

                log_cursor = conn.cursor()
                log_cursor.execute('''
                    INSERT INTO Sys_AIAuditLog (
                        created_at, user_role, question, answer, scraped_context, sql_query,
                        latency_ms, model_name, router_model_name,
                        router_in_tokens, router_out_tokens,
                        chat_in_tokens, chat_out_tokens, total_tokens,
                        estimated_cost, router_mode, chat_mode,
                        rag_documents, router_latency_ms, db_latency_ms, chat_latency_ms
                    )
                    OUTPUT INSERTED.id
                    VALUES (
                        GETDATE(), ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?
                    )
                ''', (
                    safe_str(user_role), safe_str(log_question), safe_str(answer_text[:2000]), safe_str(excel_log_context), safe_str(original_sql_query),
                    latency_ms, safe_str(model_name), safe_str(router_model_name),
                    router_in_tokens, router_out_tokens,
                    final_in_tokens, final_out_tokens, total_tokens,
                    total_cost,
                    safe_str(llm_client.mode_label(router_model_name, router_effort, router_thinking_off)),
                    safe_str("AI 매핑 생략 (DB 직접 기록)" if direct_fill_used else ("격자 직접 기록 · 대응표 " + llm_client.mode_label(model_name, final_effort)) if grid_used else llm_client.mode_label(model_name, final_effort)),
                    safe_str("\n".join(f"{i}) {n}" for i, n in enumerate(used_doc_names, 1)) or None),
                    int((time_router_end - start_time) * 1000), int((time_db_end - time_router_end) * 1000), int((end_time - time_db_end) * 1000)
                ))
                inserted = log_cursor.fetchone()
                audit_log_id = inserted[0] if inserted else None
                conn.commit()
            except Exception as e:
                print(f"[EXCEL-AUTOFILL] Audit Log 저장 실패: {e}")

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
        time_final_end = time.time()
        print(f"[EXCEL-AUTOFILL] ⏱️ 3단계(최종 엑셀 매핑 AI) 소요 시간: {time_final_end - time_db_end:.2f}초")
        print(f"[EXCEL-AUTOFILL] ⏱️ 엑셀 채우기 총 소요 시간: {time_final_end - start_time:.2f}초")
        print(f"[EXCEL-AUTOFILL] 🎉 하이브리드 엑셀 채우기 성공! ({latency_ms}ms)")
        print("[EXCEL-AUTOFILL] ==================================================\n")
        
        result = {
            "status": "success",
            "answer": answer_text,
            "log_id": audit_log_id if audit_log_id else -1,
            "latency_ms": latency_ms,
            "excel_base64": excel_base64,
            "excel_filename": f"AutoFilled_{file.filename}"
        }
        # [기준 바꿔서 다시 채우기] 격자 채우기에 계산 기준이 있으면 15분간 다시 채울 수 있게 보관
        if grid_used and grid_res.get("decisions"):
            result["criteria_pending_id"] = make_choice_state(audit_log_id)
            result["decisions"] = grid_res["decisions"]
        return result
        
    except asyncio.CancelledError:
        print(f"[EXCEL-AUTOFILL] 🛑 사용자에 의해 요청이 취소되었습니다.")
        raise
    except llm_client.TokenLimitExceeded as e:
        # [토큰 한도 초과 취소] API 호출 전에 취소되어 과금 없음
        return {
            "status": "cancelled",
            "reason": "token_limit",
            "tokens": e.tokens,
            "limit": e.limit,
            "message": llm_client.token_limit_message(
                e, extra_hint="모집요강처럼 큰 문서가 필요한 엑셀 채우기는 Gemini 모델로 전환해서 실행해 주세요."
            )
        }
    except Exception as e:
        print(f"[EXCEL-AUTOFILL] ❌ 에러 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals() and conn:
            try:
                conn.close()
            except:
                pass
