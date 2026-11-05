"""
[검토 문서 ↔ DB 구분 값 겹침 검사]
교직원이 공문·기안을 검토 요청할 때, 문서의 '숫자가 적힌 줄'에 DB 구분 열(학과·전형 등)의 실제 값이
여러 개 나오면 그 숫자는 DB 로 셀 수 있는 값(구분별 인원 등)일 가능성이 높으므로 라우터에게 대조 쿼리를 권하는 힌트를 만듭니다.
- 특정 이름을 코드에 적지 않고, 값 사전(get_value_dictionary)의 실제 값만 씁니다.
- 숫자 없이 본문에 이름만 나오는 문서는 힌트를 만들지 않습니다.
"""
import re

MIN_VALUES = 3          # 같은 열의 서로 다른 값이 이만큼 이상 숫자 줄에 나와야 힌트를 냄
MAX_SHOW = 12           # 힌트에 보여 줄 값 개수
_NUM = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})*(?![\d.])|(?<![\d.])\d+(?![\d.])")


def _number_lines(text: str):
    """숫자가 들어 있는 조각들. 표의 한 줄(| a | b |)이나 문장 한 줄 단위로 나눔"""
    for line in text.splitlines():
        line = line.strip()
        if line and _NUM.search(line):
            yield line


def find_overlaps(scraped: str, value_dict: dict) -> list:
    """반환: [(테이블, 열, [겹친 값 ...]), ...]  겹친 값 개수 많은 순"""
    if not scraped or not value_dict:
        return []
    lines = list(_number_lines(scraped))
    if not lines:
        return []
    found = []
    for t_name, cols in value_dict.items():
        for c_name, by_year in cols.items():
            if "학년도" in c_name:
                continue
            values = {v for vals in by_year.values() for v in vals
                      if isinstance(v, str) and len(v.strip()) >= 2 and not v.strip().isdigit()}
            hit = []
            for v in sorted(values, key=len, reverse=True):
                for line in lines:
                    # 값 자리를 지운 뒤에도 숫자가 남아야 '이름 + 숫자' 줄로 봄 (이름 안의 숫자 제외)
                    if v in line and _NUM.search(line.replace(v, " ")):
                        hit.append(v)
                        break
            # 긴 값에 포함된 짧은 값(예: '합격' ⊂ '불합격')은 따로 세지 않음
            hit = [v for v in hit if not any(v != o and v in o for o in hit)]
            if len(hit) >= MIN_VALUES:
                found.append((t_name, c_name, hit))
    found.sort(key=lambda x: -len(x[2]))
    return found


def router_hint(scraped: str, value_dict: dict, metrics: list = None) -> str:
    """metrics: metric_query.load_catalog(conn)["metrics"]. 겹친 테이블의 지표 정의(예: 합격자 = 최초 합격)를 함께 보여 줌"""
    overlaps = find_overlaps(scraped, value_dict)
    if not overlaps:
        return ""
    # 같은 값 묶음이 여러 테이블에서 겹치면 한 줄로 (예: 학과명이 입시마스타·모집인원·입학정원 모두에 있음)
    groups = {}
    for t_name, c_name, hit in overlaps:
        groups.setdefault(tuple(sorted(hit)), (hit, []))[1].append(f"{t_name}.[{c_name}]")
    lines = []
    for hit, cols in groups.values():
        shown = ", ".join(hit[:MAX_SHOW]) + (f" 외 {len(hit) - MAX_SHOW}개" if len(hit) > MAX_SHOW else "")
        lines.append(f"          · {' / '.join(cols)}: {shown} ({len(hit)}개)")
    tables = {t for t, _, _ in overlaps}
    # 문서에 이름·비슷한 말이 나온 지표만 보여 줌 (관계없는 지표 이름이 라우터의 문서 선택을 끌어가지 않도록).
    # 하나도 안 맞으면 겹친 테이블의 지표를 모두 보여 줌
    cand = [m for m in (metrics or []) if m.get("table") in tables]
    def _words(m):
        names = [m.get("name", "")] + (m.get("synonyms") or "").split(",")
        return [re.sub(r"\(.*?\)", "", w).strip() for w in names if len(re.sub(r"\(.*?\)", "", w).strip()) >= 3]  # 2글자 말(모집·등록)은 다른 낱말 안에서 우연히 맞기 쉬움 (예: 신입생모집)
    matched = [m for m in cand if any(w in scraped for w in _words(m))]
    m_lines = []
    for m in (matched or cand):
        if True:
            syn = f" (비슷한 말: {m['synonyms']})" if m.get("synonyms") else ""
            desc = f" — {m['description']}" if m.get("description") else ""
            cond = f" WHERE {m['condition']}" if m.get("condition") else ""
            m_lines.append(f"          · '{m['name']}'{syn}{desc}: {m['expression']} FROM [{m['table']}]{cond}")
    metric_text = ""
    if m_lines:
        metric_text = ("        - 문서의 숫자 이름(예: 합격자, 지원자, 등록자)에 맞는 아래 지표 정의(관리자 등록)를 그대로 쓰십시오. "
                       "구분 없이 '합격자'처럼만 적혀 있으면 설명에 '이라고만 하면 이 지표'라고 된 지표를 쓰십시오.\n"
                       + "\n".join(m_lines) + "\n")
    return ("\n        [검토 문서와 DB 구분 값 겹침 (시스템 자동 검사)]\n"
            "        - 검토 문서의 숫자가 적힌 줄에 아래 DB 구분 열의 실제 값이 여러 개 나옵니다.\n"
            + "\n".join(lines) + "\n" + metric_text +
            "        - 문서가 이 구분별 숫자(인원·건수 등)를 적고 그 숫자를 위 테이블에서 셀 수 있다면, 규칙 8의 '다만' 항목에 따라 "
            "문서와 같은 묶음 기준·조건(학년도·모집구분 등 문서에 적힌 조건)으로 집계하는 대조 쿼리를 sql_query 에 만드십시오. "
            "문서의 숫자가 DB 로 셀 수 없는 값(배정 금액 등)뿐이면 NONE 으로 두십시오.\n")
