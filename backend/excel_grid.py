"""
[격자(가로 펼침) 엑셀 직접 채우기]
행 이름 열(학과 등) × N단 머리글(모집구분 > 전형 > 지표 등) 양식을 대상으로
  1) 파이썬이 양식 구조(머리글 경로·행 이름·채울 칸·합계)를 읽고
  2) AI 는 '엑셀 이름 ↔ DB 실제 값' 대응표만 만들고 (MAPPING_SCHEMA)
  3) 파이썬이 DB 결과를 그대로 더해 칸을 채우고, 합계·비율을 계산하고, 검산합니다.
대응이 하나라도 안 되면 None/실패를 돌려주어 호출부가 기존 AI 매핑으로 넘어가게 합니다.
"""
import re
from collections import Counter, defaultdict
from decimal import Decimal

from openpyxl.utils import get_column_letter, coordinate_to_tuple

BLANK = object()  # 칸을 비워 둘 값
TOTAL_WORDS = {"합계", "총계", "소계", "총합계", "전체", "계", "합", "총합"}


def norm(s) -> str:
    return re.sub(r"\s+", "", "" if s is None else str(s))


def is_total_label(s) -> bool:
    n = norm(s)
    return bool(n) and (n in TOTAL_WORDS or n.endswith(("합계", "소계", "총계")))


def to_num(v):
    """숫자 또는 숫자 문자열이면 숫자, 아니면 None ('제한없음' 등)"""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return float(s)
    return None


def round_half_up(x, dec):
    """엑셀 ROUND 와 같은 사사오입 (파이썬 round 는 31.25 → 31.2 로 내림)"""
    from decimal import ROUND_HALF_UP
    q = Decimal(1).scaleb(-dec)
    v = Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP)
    return int(v) if dec == 0 else float(v)


def clean_number(x):
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


# =======================================================
# 1. 양식 구조 읽기
# =======================================================
def analyze_grid(ws, empty_cells_info):
    """
    빈 셀 분포로 채울 칸 덩어리(데이터 행 × 데이터 열)를 찾고, 그 위를 머리글 단, 그 왼쪽을 행 이름 열로 봅니다.
    격자 구조로 읽을 수 없으면 None.
    """
    empty = set()
    for e in empty_cells_info or []:
        try:
            empty.add(coordinate_to_tuple(e["coord"]))
        except Exception:
            pass
    if len(empty) < 4:
        return None

    rc = Counter(r for r, _ in empty)
    cc = Counter(c for _, c in empty)
    max_r, max_c = max(rc.values()), max(cc.values())
    # 빈 칸이 대부분인 행/열만 데이터 영역 (머리글 아래 남는 빈칸 1~2개 등은 제외)
    data_rows = sorted(r for r, n in rc.items() if n >= max_r * 0.5)
    data_cols = sorted(c for c, n in cc.items() if n >= max_c * 0.5)
    if not data_rows or not data_cols:
        return None
    r0, c0 = data_rows[0], data_cols[0]
    if r0 <= 1 or c0 <= 1:
        return None  # 머리글 또는 행 이름 열이 없음

    merged = {}
    for mr in ws.merged_cells.ranges:
        c1, r1, c2, r2 = mr.bounds
        v = ws.cell(row=r1, column=c1).value
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                merged[(r, c)] = (v, r1, c1)

    def raw(r, c):
        return merged.get((r, c), (ws.cell(row=r, column=c).value, r, c))

    def txt(v):
        return "" if v is None else str(v).strip()

    # --- 머리글 경로: 가로 병합은 상속, 세로 병합의 아래쪽은 빈 이름 ---
    header_rows = [r for r in range(1, r0) if any(txt(raw(r, c)[0]) for c in data_cols)]
    if not header_rows:
        return None
    col_paths = {}
    for c in data_cols:
        path = []
        for r in header_rows:
            v, mr_r, _ = raw(r, c)
            path.append(txt(v) if mr_r == r else "")
        col_paths[c] = path
    # 병합 없이 첫 칸에만 적힌 상위 머리글은 오른쪽으로 이어 받기 (아래 단이 합계면 이어 받지 않음 → 전체 합계)
    for lv in range(len(header_rows) - 1):
        prev = ""
        for c in data_cols:
            lab = col_paths[c][lv]
            lower_total = any(is_total_label(x) for x in col_paths[c][lv + 1:])
            if lab:
                prev = lab
            elif prev and not lower_total:
                col_paths[c][lv] = prev

    # --- 행 이름: 병합은 가로·세로 모두 상속 ---
    key_cols = [c for c in range(1, c0) if any(txt(raw(r, c)[0]) for r in data_rows)]
    if not key_cols:
        return None
    row_paths = {r: [txt(raw(r, c)[0]) for c in key_cols] for r in data_rows}
    for ki in range(len(key_cols) - 1):
        prev = ""
        for r in data_rows:
            lab = row_paths[r][ki]
            lower_total = any(is_total_label(x) for x in row_paths[r][ki + 1:])
            if lab:
                prev = lab
            elif prev and not lower_total:
                row_paths[r][ki] = prev

    data_row_set, data_col_set = set(data_rows), set(data_cols)
    cells = sorted((r, c) for r, c in empty if r in data_row_set and c in data_col_set and any(row_paths[r]))
    if not cells:
        return None

    slots = []
    for i, c in enumerate(key_cols):
        labels = sorted({row_paths[r][i] for r in data_rows if row_paths[r][i]})
        slots.append({"id": f"R:{get_column_letter(c)}", "axis": "row", "index": i,
                      "desc": f"행 이름 열 {get_column_letter(c)}", "labels": labels})
    for i, r in enumerate(header_rows):
        labels = sorted({col_paths[c][i] for c in data_cols if col_paths[c][i]})
        slots.append({"id": f"C:{r}", "axis": "col", "index": i,
                      "desc": f"{r}행 머리글 ({i + 1}단)", "labels": labels})

    return {
        "header_rows": header_rows, "key_cols": key_cols,
        "data_rows": data_rows, "data_cols": data_cols,
        "col_paths": col_paths, "row_paths": row_paths,
        "cells": cells, "slots": slots,
        "ignored_empty": len(empty) - len(cells),
    }


def grid_summary_text(grid) -> str:
    """라우터·대응표 AI 에 줄 양식 구조 요약 (빈 셀 좌표 전체 대신 이름 목록만)"""
    lines = [f"- 채울 칸 {len(grid['cells'])}개 (데이터 행 {len(grid['data_rows'])}줄 × 데이터 열 {len(grid['data_cols'])}칸)"]
    for s in grid["slots"]:
        flag = [l for l in s["labels"] if is_total_label(l)]
        extra = f" (합계로 보이는 이름: {flag})" if flag else ""
        lines.append(f"- 칸 [{s['id']}] {s['desc']}: {s['labels']}{extra}")
    sample_cols = grid["data_cols"][:6]
    lines.append("- 열 머리글 경로 예시: " + "; ".join(
        f"{get_column_letter(c)}열 = {' > '.join(x for x in grid['col_paths'][c] if x) or '(없음)'}" for c in sample_cols))
    return "\n".join(lines)


# =======================================================
# 2. 대응표 AI 입력/출력 형식
# =======================================================
MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "slots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "string", "description": "양식 구조의 칸 id (예: R:A, C:1)"},
                    "role": {"type": "string", "enum": ["dimension", "measure", "ignore"]},
                    "fields": {
                        "type": "array",
                        "description": "role=dimension 일 때 이 칸이 대응하는 출처별 DB 결과 열",
                        "items": {
                            "type": "object",
                            "properties": {"source": {"type": "string"}, "field": {"type": "string"}},
                            "required": ["source", "field"], "additionalProperties": False
                        }
                    },
                    "labels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "엑셀에 적힌 이름 그대로"},
                                "kind": {"type": "string", "enum": ["value", "total", "ignore"]},
                                "values": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "source": {"type": "string"},
                                            "db_values": {"type": "array", "items": {"type": "string"}}
                                        },
                                        "required": ["source", "db_values"], "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["label", "kind", "values"], "additionalProperties": False
                        }
                    }
                },
                "required": ["slot", "role", "fields", "labels"], "additionalProperties": False
            }
        },
        "measures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "측정값 머리글 이름 (측정값 칸이 없으면 '*')"},
                    "kind": {"type": "string", "enum": ["field", "ratio"]},
                    "source": {"type": "string"}, "field": {"type": "string"},
                    "num_source": {"type": "string"}, "num_field": {"type": "string"},
                    "den_source": {"type": "string"}, "den_field": {"type": "string"},
                    "scale": {"type": "number"}, "decimals": {"type": "integer"},
                    "text_policy": {"type": "string", "enum": ["keep", "blank", "replace"],
                                    "description": "kind=field 의 열에 숫자 아닌 값(예: 제한없음)이 있을 때: keep 글자 그대로, blank 비움, replace 다른 열 값으로 대체"},
                    "text_replace_source": {"type": "string"}, "text_replace_field": {"type": "string"}
                },
                "required": ["label", "kind", "source", "field", "num_source", "num_field",
                             "den_source", "den_field", "scale", "decimals",
                             "text_policy", "text_replace_source", "text_replace_field"],
                "additionalProperties": False
            }
        },
        "decisions": {
            "type": "array",
            "description": "해석이 갈릴 수 있는 계산 기준 (비율 계산식, 개수 지표 정의, 숫자 아닌 값 처리)",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "지표 이름 그대로 (예: 등록율) 또는 '숫자 아닌 값(열이름)' (예: 숫자 아닌 값(모집인원))"},
                    "question": {"type": "string", "description": "사용자에게 물을 질문 한 줄"},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "선택지 2~4개 (적용한 기준 포함)"},
                    "applied": {"type": "string", "description": "이번 대응표에 적용한 기준 (options 중 하나와 같은 문장)"},
                    "basis": {"type": "string", "enum": ["question", "default", "user", "ai"],
                              "description": "question 질문에 지시 있음, default 저장된 기본 기준, user 사용자 선택, ai 지시가 없어 AI 가 정함"},
                    "affects_query": {"type": "boolean", "description": "다른 선택지로 바꾸면 DB 조회(SQL)를 다시 해야 하는지 (개수 지표 정의 변경 등)"}
                },
                "required": ["topic", "question", "options", "applied", "basis", "affects_query"],
                "additionalProperties": False
            }
        },
        "unmapped": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["label", "reason"], "additionalProperties": False
            }
        }
    },
    "required": ["slots", "measures", "decisions", "unmapped"],
    "additionalProperties": False
}

DEFAULT_CRITERIA_TITLE = "[통계 기본 기준]"  # 엑셀 채우기·쿼리 요청이 함께 쓰는 기본 정의 (사전지식 1건)
OLD_CRITERIA_TITLES = ("[엑셀 채우기 기본 기준]",)  # 예전 제목 (찾기용)
DEFAULT_CRITERIA_NOTE = ("(엑셀 채우기·쿼리 요청에서 정의가 둘 이상인 지표를 셀 때 쓰는 기본 기준. "
                         "엑셀 채우기의 '다음에도 이 기준 사용'으로 저장됨. 질문에 다른 지시가 있으면 질문이 우선)")
BASIS_LABEL = {"question": "질문에서 지정", "default": "저장된 기본값", "user": "이번에 선택하심", "ai": "AI 판단 · 확인 필요"}
TEXT_TOPIC_PREFIX = "숫자 아닌 값"


def describe_sources(sources, max_values=150) -> str:
    """대응표 AI 에 줄 DB 결과 요약: 출처별 열 목록, 구분 열의 실제 값 목록, 숫자 열 목록"""
    out = []
    for s in sources:
        rows = s["rows"]
        cols = list(rows[0].keys()) if rows else []
        out.append(f"### 출처 {s['name']} ({len(rows)}행)\nSQL: {s['sql']}")
        for col in cols:
            vals = [r.get(col) for r in rows]
            non_null = [v for v in vals if v is not None]
            nums = [v for v in non_null if to_num(v) is not None]
            distinct = sorted({str(v).strip() for v in non_null})
            if nums and len(nums) >= len(non_null) * 0.5:
                texts = sorted({str(v).strip() for v in non_null if to_num(v) is None})
                out.append(f"- [{col}] 숫자 열 (값 예: {distinct[:8]})" + (f" (숫자 아닌 값: {texts})" if texts else ""))
            else:
                shown = distinct[:max_values]
                more = f" …외 {len(distinct) - max_values}개" if len(distinct) > max_values else ""
                out.append(f"- [{col}] 구분 열 값: {shown}{more}")
    return "\n".join(out)


def build_mapping_prompt(question, supplemental, grid, sources, schema_text="", user_choices=None) -> str:
    choices_text = "\n".join(f"- {c.get('topic')}: {c.get('answer')}" for c in (user_choices or [])) or "없음"
    return f"""너는 엑셀 양식의 이름(약칭 포함)을 DB 조회 결과의 실제 값에 대응시키는 [대응표 작성 AI]야.
숫자는 시스템이 DB 에서 직접 계산해 넣으므로 너는 숫자를 만들지 말고 '이름 ↔ DB 값' 대응만 정확히 작성해.

[사용자 질문]
{question}

[관리자 등록 사전지식 (용어 대응 규칙은 반드시 따를 것)]
{supplemental or "없음"}

[사용자가 이번에 선택한 계산 기준 (최우선 적용)]
{choices_text}

[엑셀 양식 구조]
{grid_summary_text(grid)}

[DB 조회 결과 (출처별)]
{describe_sources(sources)}

[DB 스키마 ('└ [열] 실제 값' 에 학년도별 실제 값이, 열 설명에 값 목록이 적혀 있음 — 조회 결과에 없는 값을 대응할 때 참고, 실제 값 우선)]
{schema_text or "없음"}

[작성 규칙]
1. 양식 구조의 모든 칸(slot)에 대해 role 을 정해:
   - dimension: 이 칸의 이름이 DB 구분 열(학과, 전형, 모집구분 등)의 값을 가리킴 → fields 에 출처별 대응 열을 적음 (해당 열이 있는 모든 출처를 적을 것)
   - measure: 이 칸의 이름이 지표(지원인원, 등록인원, 등록율 등)를 가리킴 → measures 에 각 지표를 정의
   - ignore: 설명용 칸(예: 주야처럼 DB 로 구분하지 않는 열, 표 제목 줄)
2. dimension 칸의 labels 에는 그 칸에 나온 이름을 하나도 빠짐없이 적고:
   - kind=value: values 에 출처별로 대응하는 DB 실제 값을 [DB 조회 결과]에 있는 글자 그대로 적음. 하나의 이름이 여러 DB 값의 합이면 모두 나열 (예: 정시 → 정시1차, 정시2차 …).
     조회 결과에는 없지만 [DB 스키마]의 실제 값·열 설명 값 목록에 같은 뜻의 값이 있으면 그 값을 적음 (그해 해당자가 없는 것이므로 시스템이 0 으로 계산). 해당 값이 어디에도 없지만 뜻은 분명하면 db_values 를 빈 배열로 (0 으로 계산).
   - kind=total: 합계·계·소계·전체 등 (values 는 빈 배열, 시스템이 같은 칸의 다른 이름들을 더함)
   - kind=ignore: 숫자와 무관한 이름
   - 약칭(예: 간호, 인문고)은 사전지식과 DB 값 목록을 보고 같은 뜻의 실제 값으로 대응. 같은 DB 값을 두 이름에 중복 배정하지 말 것.
3. measures: 측정값 칸의 각 이름마다 하나씩.
   - kind=field: source·field 에 그 숫자 열 (num_/den_ 는 빈 문자열, scale 1, decimals 0)
   - kind=ratio: 비율(%)이면 num_source·num_field ÷ den_source·den_field × scale(보통 100), decimals 는 소수 자리(보통 1). 출처가 달라도 됨 (예: 등록인원 ÷ 모집인원)
   - 측정값 칸이 없고 지표가 하나뿐이면 label 을 '*' 로 하나만 정의
   - text_policy: kind=field 의 열에 숫자 아닌 값(예: 모집인원의 '제한없음')이 있으면 처리 방식 — keep(글자 그대로 표시), blank(비움), replace(같은 칸의 다른 열 값으로 대체, 예: 제한없음 → 그 칸의 지원인원; text_replace_source·text_replace_field 에 대체할 출처·열). 숫자 아닌 값이 없으면 keep, 대체 열은 빈 문자열.
     비율의 분모·분자 열에 숫자 아닌 값이 있으면 그 열을 kind=field 로 쓰는 지표의 text_policy 를 따르고, 그런 지표가 없으면 비율 칸에 글자를 그대로 표시함.
4. 뜻을 전혀 알 수 없는 이름만 추측하지 말고 unmapped 에 이유와 함께 적어 (시스템이 다른 방식으로 처리함). 조회 결과에 값이 없다는 이유만으로 unmapped 에 넣지 말 것.
5. unmapped 가 있더라도 slots 에는 양식의 모든 칸을 빠짐없이 적을 것.
7. decisions: 아래 세 종류만 작성 (양식에 해당 지표·값이 있을 때만). 그 외는 절대 넣지 말 것.
   - 모든 비율 지표 (topic = 지표 이름 그대로): 분자·분모 계산식. options·applied 는 양식의 측정값 이름으로 적을 것 (예: '등록인원 ÷ 합격인원 × 100', '등록인원 ÷ 지원인원 × 100'). 분자·분모가 양식의 다른 측정값 칸과 같은 이름이면 그 칸과 같은 열을 쓸 것 (정의는 그 칸의 개수 지표 기준을 따름)
   - 입시 업무상 뜻이 둘 이상인 개수 지표 (topic = 지표 이름 그대로; 예: 합격인원 = 최초합격인지 최종합격인지, 등록인원 = 전체 등록인지 최초합격자 중 등록인지): 조회 SQL 에 쓰인 정의를 applied 로
   - 숫자 아닌 값이 있는 열 (topic = '숫자 아닌 값(열이름)'): text_policy 처리 방식
   decisions 가 아닌 것 (넣지 말 것): 학과·전형 등 이름 대응(예: 대학 → 대학졸업자), 학년도·모집구분 조건, 집계 방식(건수 vs 중복 제거 등 기술적 세부), 지원인원처럼 뜻이 하나뿐인 지표.
   basis 판정: 사용자가 이번에 선택한 기준에 있으면 user / 사용자 질문에 지시가 있으면 question / 사전지식의 {DEFAULT_CRITERIA_TITLE} 항목에 있으면 default / 셋 다 없으면 ai (가장 일반적인 기준으로 applied 를 정하되 사용자에게 물어볼 수 있도록 options 에 다른 선택지 포함).
   affects_query: 개수 지표 정의처럼 다른 선택지로 바꾸려면 SQL 을 다시 짜야 하면 true, 비율 계산식·숫자 아닌 값 처리처럼 대응표만 바꾸면 되면 false.
   applied 는 options 중 하나와 글자까지 같게 쓰고, 대응표(measures)는 applied 대로 작성.
6. source 는 반드시 [DB 조회 결과]의 출처 이름({", ".join(s["name"] for s in sources)}) 중 하나로 적고 테이블 이름을 쓰지 말 것. field 도 그 출처 결과에 실제로 있는 열 이름만 쓸 것.
"""


# =======================================================
# 3. 값 넣기 + 합계 + 검산
# =======================================================
def fill_grid(grid, sources, mapping, hint_text=""):
    """
    반환: dict(ok, cells={좌표: 값}, warnings=[...], notes=[...], fail=[...], mapping_text)
    ok=False 면 호출부는 기존 AI 매핑으로 넘어갑니다.
    """
    fail, warnings, notes = [], [], []
    src_by_name = {s["name"]: s for s in sources}
    slot_defs = {s["id"]: s for s in grid["slots"]}

    # AI 가 출처 이름(Q1) 대신 테이블 이름(UI_IPSI_M_V 등)을 쓴 경우: 그 테이블을 조회한 출처가 하나뿐이면 그 출처로 바꿈
    table_to_src = defaultdict(set)
    for s in sources:
        for t in re.findall(r'(?i)\b(?:FROM|JOIN)\s+\[?(\w+)\]?', s.get("sql") or ""):
            table_to_src[t.upper()].add(s["name"])

    def fix_src(name):
        if name in src_by_name:
            return name
        cands = table_to_src.get(str(name).upper(), set())
        if len(cands) == 1:
            return next(iter(cands))
        return name  # 그대로 두면 아래 검사에서 실패 처리

    for sm in mapping.get("slots", []):
        for f in sm.get("fields", []):
            f["source"] = fix_src(f.get("source"))
        for lab in sm.get("labels", []):
            for v in lab.get("values", []):
                v["source"] = fix_src(v.get("source"))
    for m in mapping.get("measures", []):
        for k in ("source", "num_source", "den_source"):
            if m.get(k):
                m[k] = fix_src(m[k])

    # [열 이름 보정] AI 가 결과 열 이름(별칭) 대신 원래 열 이름을 쓰거나(전형명 ↔ [전형명] AS [전형]) 띄어쓰기가 다르면 실제 결과 열로 바꿈
    for sm in mapping.get("slots", []):
        for f in sm.get("fields", []):
            f["field"] = fix_field(src_by_name, f.get("source"), f.get("field"))
    for m in mapping.get("measures", []):
        for sk, fk in (("source", "field"), ("num_source", "num_field"), ("den_source", "den_field"),
                       ("text_replace_source", "text_replace_field")):
            if m.get(fk):
                m[fk] = fix_field(src_by_name, m.get(sk), m[fk])
    notes += unify_ratio_fields(mapping)

    smap = {}
    for sm in mapping.get("slots", []):
        if sm.get("slot") in slot_defs:
            smap[sm["slot"]] = sm

    # 값이 하나뿐인 칸(예: 주야 = 주간만)은 나누는 효과가 없으므로, 대응 못 한 이름이 그 칸의 유일한 값이면 '설명용(ignore)'으로 처리
    unmapped = list(mapping.get("unmapped") or [])
    single_label_slots = {sid: s["labels"][0] for sid, s in slot_defs.items()
                          if len([l for l in s["labels"] if not is_total_label(l)]) == 1}
    for u in list(unmapped):
        hit = [sid for sid, lab in single_label_slots.items() if norm(lab) == norm(u.get("label"))]
        if hit:
            for sid in hit:
                smap[sid] = {"slot": sid, "role": "ignore", "fields": [], "labels": []}
            unmapped.remove(u)
            notes.append(f"값이 하나뿐인 칸 {hit} ('{u.get('label')}') 은 구분 없이 계산 (설명용)")
    if unmapped:
        fail += [f"대응 못 함: '{u.get('label')}' ({u.get('reason')})" for u in unmapped]
    measures = {norm(m.get("label")): m for m in mapping.get("measures", [])}
    for sid in slot_defs:
        if sid not in smap:
            # AI 가 측정값 칸을 빠뜨렸지만 그 칸의 이름이 모두 정의된 지표이면 측정값 칸으로 간주
            labels = slot_defs[sid]["labels"]
            if labels and all(norm(l) in measures for l in labels):
                smap[sid] = {"slot": sid, "role": "measure", "fields": [], "labels": []}
            else:
                fail.append(f"칸 [{sid}] 의 역할이 대응표에 없음")
    for m in measures.values():
        need = [(m.get("source"), m.get("field"))] if m.get("kind") == "field" else \
               [(m.get("num_source"), m.get("num_field")), (m.get("den_source"), m.get("den_field"))]
        for src, fld in need:
            if src not in src_by_name or not src_by_name[src]["rows"] or fld not in src_by_name[src]["rows"][0]:
                # 대응표가 필요로 하는 열을 쿼리가 돌려주지 않음 → 쿼리 문제 (쿼리 보정 대상)
                fail.append(f"[쿼리] 지표 '{m.get('label')}' 에 필요한 열 {src}.{fld} 이 조회 결과에 없음 (쿼리에 이 지표 열이 필요함)")
            elif _hides_text_values(src_by_name[src].get("sql"), fld):
                # 숫자 아닌 값(제한없음 등)이 쿼리에서 0 으로 바뀌면 사용자에게 처리 방식을 물을 수 없음 → 원본 값으로 다시 조회
                fail.append(f"[쿼리] 지표 '{m.get('label')}' 의 열 {src}.{fld} 을 ISNUMERIC 등으로 숫자만 남겨 '제한없음' 같은 숫자 아닌 값이 사라짐 "
                            f"(원본 열 그대로, GROUP BY 없이 행 단위로 조회해야 함)")

    # 칸별 이름 대응
    label_maps = {}
    for sid, sm in smap.items():
        if sm.get("role") != "dimension":
            continue
        fields = {f["source"]: f["field"] for f in sm.get("fields", [])}
        for src, fld in fields.items():
            if src not in src_by_name or (src_by_name[src]["rows"] and fld not in src_by_name[src]["rows"][0]):
                fail.append(f"[쿼리] 칸 [{sid}] ({', '.join(slot_defs[sid]['labels'][:6])} …)을 나눌 열 {src}.{fld} 이 조회 결과에 없음 "
                            f"(쿼리의 SELECT·GROUP BY 에 이 구분 열이 필요함)")
        lm = {}
        for lab in sm.get("labels", []):
            bad_src = [v.get("source") for v in lab.get("values", []) if v.get("source") not in src_by_name]
            if bad_src:
                fail.append(f"칸 [{sid}] '{lab.get('label')}' 의 출처 {bad_src} 이 DB 결과에 없음")
            lm[norm(lab.get("label"))] = {
                "kind": lab.get("kind"),
                "values": {v["source"]: {norm(x) for x in v.get("db_values", [])} for v in lab.get("values", [])},
            }
        missing = [l for l in slot_defs[sid]["labels"] if norm(l) not in lm]
        if missing:
            fail.append(f"칸 [{sid}] 이름 대응 누락: {missing}")
        # 같은 DB 값이 두 이름에 배정되었는지
        for src in fields:
            seen = defaultdict(list)
            for lname, d in lm.items():
                if d["kind"] == "value":
                    for v in d["values"].get(src, set()):
                        seen[v].append(lname)
            for v, names in seen.items():
                if len(names) > 1:
                    fail.append(f"중복 배정: {src} 의 '{v}' 가 칸 [{sid}] 의 {names} 에 함께 들어감 (한 이름에만 배정할 것)")
        label_maps[sid] = {"fields": fields, "labels": lm}

    # [쿼리-양식 불일치] 지표에 쓰이는 출처에서 어떤 칸 이름의 절반 이상이 대응 값을 못 찾으면,
    # 대응표 문제가 아니라 쿼리가 그 칸을 나눌 열 없이 다른 열로 묶인 것 (예: 전형 대신 고교구분으로 GROUP BY)
    measure_srcs = set()
    for m in measures.values():
        for k in ("source", "num_source", "den_source"):
            if m.get(k):
                measure_srcs.add(m[k])
    for sid, d in label_maps.items():
        value_labels = [(name, x) for name, x in d["labels"].items() if x["kind"] == "value"]
        if len(value_labels) < 3:
            continue
        for src in measure_srcs:
            if src not in d["fields"]:
                continue
            empties = [name for name, x in value_labels if not x["values"].get(src)]
            if len(empties) * 2 >= len(value_labels):
                fail.append(f"[쿼리] 출처 {src} 결과에 칸 [{sid}] ({', '.join(slot_defs[sid]['labels'][:6])} …)을 나눌 구분 열이 없음 — "
                            f"지금은 [{d['fields'][src]}] 열에 대응되어 {len(empties)}/{len(value_labels)}개 이름이 비어 있음 "
                            f"(대응 안 된 이름: {empties[:6]})")

    if fail:
        return {"ok": False, "fail": fail, "warnings": warnings, "notes": notes, "cells": {}}

    # 출처별로 대응에 쓰이는 구분 열 → ROLLUP 등 빈 값 행 제외
    used_fields = defaultdict(set)
    for sid, d in label_maps.items():
        for src, fld in d["fields"].items():
            used_fields[src].add(fld)
    rows_by_src = {}
    for s in sources:
        rows_by_src[s["name"]] = [r for r in s["rows"] if all(r.get(f) is not None for f in used_fields[s["name"]])]

    # [자동 조건] 양식에 칸이 없는 구분 열(모집구분·학년도 등)의 값이 질문·파일명에 나오면 그 값만 남김
    # (예: 파일명 '2026학년도수시1차-채우기양식' → 모집구분 = 수시1차. 라우터가 WHERE 조건을 빠뜨려도 여러 모집구분이 합산되지 않도록)
    auto_conditions = []
    hint = norm(hint_text)
    used_measure_cols = defaultdict(set)
    for m in measures.values():
        for k_src, k_fld in (("source", "field"), ("num_source", "num_field"), ("den_source", "den_field")):
            if m.get(k_src) and m.get(k_fld):
                used_measure_cols[m[k_src]].add(m[k_fld])
    if hint:
        for s in sources:
            name = s["name"]
            rows = rows_by_src.get(name, [])
            if not rows:
                continue
            for col in rows[0].keys():
                if col in used_fields[name] or col in used_measure_cols[name]:
                    continue
                distinct = sorted({str(r.get(col)).strip() for r in rows if r.get(col) is not None})
                if not (1 < len(distinct) <= 50) or all(to_num(x) is not None for x in distinct):
                    continue
                hits = [v for v in distinct if len(norm(v)) >= 2 and norm(v) in hint]
                # 더 긴 값에 포함되는 짧은 값은 제외 (예: 질문에 '정시1차추가'가 있으면 '정시1차'는 빼고 '정시1차추가'만)
                hits = [v for v in hits if not any(v != w and norm(v) in norm(w) for w in hits)]
                if hits and len(hits) < len(distinct):
                    keep = {norm(v) for v in hits}
                    rows_by_src[name] = [r for r in rows_by_src[name] if norm(r.get(col)) in keep]
                    auto_conditions.append(f"{col} = {', '.join(hits)}")
                    notes.append(f"자동 조건: {name}.{col} = {hits} (질문·파일명에서) → 나머지 {len(distinct) - len(hits)}개 값 제외")

    def slot_values(sid, label, src):
        """칸 sid 의 이름 label 이 출처 src 에서 가리키는 DB 값 집합 (None = 조건 없음)"""
        d = label_maps[sid]
        if not label:
            return None
        lm = d["labels"][norm(label)]
        if lm["kind"] == "ignore":
            return None
        if lm["kind"] == "total":
            vals = set()
            for other in d["labels"].values():
                if other["kind"] == "value":
                    vals |= other["values"].get(src, set())
            return vals
        return lm["values"].get(src, set())

    def agg(src, field, filters, text_rows=None):
        total, texts, matched = 0.0, Counter(), 0
        for row in rows_by_src[src]:
            if all(norm(row.get(f)) in vals for f, vals in filters.items()):
                matched += 1
                n = to_num(row.get(field))
                if n is None:
                    if row.get(field) not in (None, ""):
                        texts[str(row.get(field)).strip()] += 1
                        if text_rows is not None:
                            text_rows.append(row)
                else:
                    total += n
        return total, texts, matched

    # 숫자 아닌 값(제한없음 등) 처리 방식: kind=field 지표에 정의된 text_policy 를 (출처, 열) 단위로 적용
    text_policies = {}
    for m in measures.values():
        if m.get("kind") == "field":
            text_policies.setdefault((m.get("source"), m.get("field")), m)

    def filters_for(src, labels_by_slot):
        f = {}
        for sid, label in labels_by_slot:
            d = label_maps.get(sid)
            if not d:
                continue
            vals = slot_values(sid, label, src)
            if vals is None:
                continue
            fld = d["fields"].get(src)
            if fld is None:
                # 이 출처에 해당 구분 열이 없음: 양식의 이 칸에 실제 구분값이 하나뿐(예: 주야 = 주간만)이면 나눌 필요가 없으므로 조건 없이 계산
                n_values = sum(1 for lm in d["labels"].values() if lm["kind"] == "value")
                if n_values <= 1:
                    continue
                return None  # 구분값이 여러 개인데 이 출처로는 나눌 수 없음 → 계산 불가
            f[fld] = vals
        return f

    def field_value(src, fld, labels_by_slot, coord):
        """반환: (칸에 넣을 값, 계산에 쓸 숫자, 검산용 DB 숫자 합). 칸을 비워야 하면 값 BLANK"""
        flt = filters_for(src, labels_by_slot)
        if flt is None:
            fail.append(f"{coord}: [쿼리] 출처 {src} 결과에 양식의 구분 칸을 나눌 열이 없음 (쿼리의 SELECT·GROUP BY 에 양식 각 단의 구분 열이 필요함)")
            return None, 0, 0
        text_rows = []
        total, texts, matched = agg(src, fld, flt, text_rows)
        if not texts:
            return clean_number(total), total, total
        pol = text_policies.get((src, fld), {})
        policy = pol.get("text_policy") or "keep"
        if policy == "replace" and pol.get("text_replace_source") and pol.get("text_replace_field"):
            rsrc, rfld = pol["text_replace_source"], pol["text_replace_field"]
            base = filters_for(rsrc, labels_by_slot)
            if base is None or rsrc not in rows_by_src:
                fail.append(f"{coord}: 숫자 아닌 값 대체 출처 {rsrc} 로 계산 불가")
                return None, 0, 0
            added = 0.0
            for row in text_rows:
                rf = dict(base)
                # 글자 값이 있던 행의 구분값(학과·전형 등)과 같은 대체 출처 행만 더함
                for d in label_maps.values():
                    f_src, f_rep = d["fields"].get(src), d["fields"].get(rsrc)
                    if f_src and f_rep:
                        rf[f_rep] = {norm(row.get(f_src))}
                added += agg(rsrc, rfld, rf)[0]
            notes.append(f"{coord}: 숫자 아닌 값 {dict(texts)} 을 {rsrc}.{rfld} 값 {clean_number(added)} 로 대체")
            return clean_number(total + added), total + added, total
        if policy == "blank":
            if total == 0 and len(text_rows) == matched:
                return BLANK, 0, 0
            notes.append(f"{coord}: 숫자 아닌 값 {dict(texts)} 은 빼고 합산")
            return clean_number(total), total, total
        # keep
        if total == 0:
            return ("/".join(sorted(texts)), 0, 0)
        notes.append(f"{coord}: 숫자 아닌 값 {dict(texts)} 은 빼고 합산")
        return clean_number(total), total, total

    single_measure = list(measures.values())[0] if len(measures) == 1 else None
    result = {}
    measure_sums = defaultdict(float)  # (src, field) → 합계 아닌 칸들의 합 (검산용)
    over_100 = defaultdict(list)  # 지표 → [(칸 이름, 값)] 100% 를 넘은 백분율 칸 (기준 불일치 경고용)
    for (r, c) in grid["cells"]:
        coord = f"{get_column_letter(c)}{r}"
        labels_by_slot = []
        measure = None
        is_total_cell = False
        paths = [(f"R:{get_column_letter(kc)}", grid["row_paths"][r][i]) for i, kc in enumerate(grid["key_cols"])] + \
                [(f"C:{hr}", grid["col_paths"][c][i]) for i, hr in enumerate(grid["header_rows"])]
        for sid, label in paths:
            role = smap[sid].get("role")
            if role == "ignore":
                continue
            if role == "measure":
                if label:
                    measure = measures.get(norm(label))
                    if measure is None:
                        fail.append(f"{coord}: 지표 '{label}' 정의 없음")
                continue
            if label and label_maps[sid]["labels"][norm(label)]["kind"] == "total":
                is_total_cell = True
            labels_by_slot.append((sid, label))
        if measure is None:
            measure = single_measure or measures.get("*")
            if measure is None:
                fail.append(f"{coord}: 어떤 지표인지 정할 수 없음")
                continue

        if measure.get("kind") == "ratio":
            num, num_raw, _ = field_value(measure["num_source"], measure["num_field"], labels_by_slot, coord)
            den, den_raw, _ = field_value(measure["den_source"], measure["den_field"], labels_by_slot, coord)
            if num is None or den is None:
                continue
            if den is BLANK or num is BLANK:
                continue  # 비움 처리
            if isinstance(num, str) and not isinstance(den, str):
                result[coord] = num  # 분자가 글자
            elif isinstance(den, str):
                result[coord] = den  # 분모가 '제한없음' 등 글자
            elif not den_raw:
                result[coord] = 0
            else:
                dec = int(measure.get("decimals") or 0)
                result[coord] = round_half_up(num_raw / den_raw * float(measure.get("scale") or 100), dec)
                if float(measure.get("scale") or 100) == 100 and result[coord] > 100:
                    # 백분율이 100% 를 넘으면 분자·분모의 기준이 서로 다를 가능성 (예: 등록(충원 포함) ÷ 최초합격)
                    over_100[measure.get("label")].append(("·".join(l for _, l in labels_by_slot if l) or coord, result[coord]))
        else:
            val, _, check_total = field_value(measure["source"], measure["field"], labels_by_slot, coord)
            if val is None or val is BLANK:
                continue
            result[coord] = val
            if not is_total_cell:
                measure_sums[(measure["source"], measure["field"])] += check_total

    for label, cells in over_100.items():
        m = measures.get(norm(label)) or {}
        warnings.append(f"비율 100% 초과: '{label}' {len(cells)}칸 (예: " + ", ".join(f"{n} {clean_number(v)}" for n, v in cells[:3])
                        + f") — 분자({m.get('num_field')})와 분모({m.get('den_field')})의 기준이 서로 맞는지 확인 (예: 충원 포함 등록 ÷ 최초합격)")

    if fail:
        # 칸마다 같은 사유가 반복되므로 사유별로 묶어 칸 수와 예시 좌표만 남김
        grouped = defaultdict(list)
        for f in fail:
            coord, _, reason = f.partition(": ")
            if not reason or coord not in grouped[reason]:
                grouped[reason or coord].append(coord if reason else "")
        fail = [f"{reason} — {len(coords)}칸 (예: {', '.join(c for c in coords[:5] if c)})" if any(coords) else reason
                for reason, coords in grouped.items()]
        return {"ok": False, "fail": fail, "warnings": warnings, "notes": notes, "cells": {}}

    # ---- 검산 1: 엑셀에 들어가지 않은 DB 값 ----
    measure_fields = defaultdict(set)
    for m in measures.values():
        if m.get("kind") == "field":
            measure_fields[m["source"]].add(m["field"])
        else:
            measure_fields[m["num_source"]].add(m["num_field"])
            measure_fields[m["den_source"]].add(m["den_field"])
    def mapped_values(d, src):
        vals = set()
        for lm in d["labels"].values():
            if lm["kind"] == "value":
                vals |= lm["values"].get(src, set())
        return vals

    omitted = []  # 참고: 양식의 다른 칸 범위 안에서 엑셀에 없는 DB 구분값
    for sid, d in label_maps.items():
        for src, fld in d["fields"].items():
            mapped = mapped_values(d, src)
            # 다른 칸(학과·모집구분 등)이 대응된 범위 안의 행만 확인 (양식 범위 밖 값은 제외)
            scope = {}
            for sid2, d2 in label_maps.items():
                f2 = d2["fields"].get(src)
                if sid2 != sid and f2 and f2 != fld:
                    scope[f2] = mapped_values(d2, src)
            left = defaultdict(lambda: defaultdict(float))
            scope_total = defaultdict(float)
            for row in rows_by_src.get(src, []):
                if not all(norm(row.get(f)) in vals for f, vals in scope.items()):
                    continue
                for mf in measure_fields.get(src, ()):
                    scope_total[mf] += to_num(row.get(mf)) or 0
                if norm(row.get(fld)) not in mapped:
                    for mf in sorted(measure_fields.get(src, ())):
                        left[row.get(fld)][mf] += to_num(row.get(mf)) or 0
            items = []
            for v, sums in left.items():
                if any(sums.values()):
                    items.append(f"'{v}'(" + ", ".join(f"{mf} {clean_number(s)}" for mf, s in sums.items()) + ")")
            if items:
                omitted.append(f"엑셀에 없는 DB 값 {src}.{fld}: " + ", ".join(items))
                # 빠진 값이 지표 합계의 5% 를 넘으면 참고가 아니라 확인 필요 경고
                for mf, tot in scope_total.items():
                    miss = sum(sums.get(mf, 0) for sums in left.values())
                    if tot and miss / tot > 0.05:
                        warnings.append(f"엑셀에 안 들어간 DB 값이 큼: {src}.{fld} 의 {mf} {clean_number(miss)} / 전체 {clean_number(tot)} "
                                        f"({miss / tot * 100:.1f}%) — 양식·쿼리 대응 확인 필요")
                        break

    # ---- 검산 2: 엑셀 칸 합계 = DB 합계 (대응된 값 범위 안에서) ----
    for (src, fld), excel_sum in measure_sums.items():
        flt = {}
        for sid, d in label_maps.items():
            f = d["fields"].get(src)
            if f:
                vals = set()
                for lm in d["labels"].values():
                    if lm["kind"] == "value":
                        vals |= lm["values"].get(src, set())
                flt[f] = vals
        db_total, _, _ = agg(src, fld, flt)
        if abs(db_total - excel_sum) > 0.001:
            warnings.append(f"총합 불일치: {src}.{fld} 엑셀 칸 합 {clean_number(excel_sum)} ≠ DB {clean_number(db_total)} (중복·겹침 확인 필요)")
        else:
            notes.append(f"총합 일치: {src}.{fld} = {clean_number(db_total)}")

    # ---- 엑셀에 구분이 없어 합산된 DB 열 (답변에도 표시해 의도와 다른 합산을 바로 알아볼 수 있게) ----
    summed = []
    for s in sources:
        rows = rows_by_src.get(s["name"], [])
        if not rows or not measure_fields.get(s["name"]):
            continue  # 지표에 쓰이지 않은 출처는 생략
        for col in rows[0].keys():
            if col in used_fields[s["name"]] or col in measure_fields.get(s["name"], ()):
                continue
            distinct = {str(r.get(col)) for r in rows if r.get(col) is not None}
            if 1 < len(distinct) <= 30 and not all(to_num(x) is not None for x in distinct):
                notes.append(f"엑셀에 구분이 없어 합산됨: {s['name']}.{col} {sorted(distinct)}")
                summed.append(f"{col} {len(distinct)}종 ({', '.join(sorted(distinct)[:8])}{' …' if len(distinct) > 8 else ''})")

    mapping["decisions"] = sanitize_decisions(mapping, rows_by_src, {s["name"]: s.get("sql") or "" for s in sources})
    plain_ratio_decisions(mapping)
    return {"ok": True, "cells": result, "warnings": warnings, "notes": notes, "omitted": omitted, "fail": [],
            "mapping_text": mapping_to_text(mapping), "decisions": mapping["decisions"],
            "summed": summed, "auto_conditions": auto_conditions,
            "criteria_text": criteria_text(mapping, auto_conditions)}


def _nospace(x) -> str:
    return re.sub(r"\s+", "", str(x or ""))


def _base_name(x) -> str:
    """'합격인원(최초)' → '합격인원' (정의 구분 괄호를 뗀 지표 이름, 공백 무시)"""
    return _nospace(re.sub(r"\s*[(（].*$", "", str(x or "")))


def fix_field(src_by_name, src, fld):
    """대응표의 열 이름을 실제 조회 결과 열 이름으로 (그대로 / 띄어쓰기만 다름 / SQL 의 '[원래 열] AS [별칭]' 의 원래 열)"""
    s = src_by_name.get(src)
    if not s or not s.get("rows") or not fld:
        return fld
    cols = list(s["rows"][0].keys())
    if fld in cols:
        return fld
    same = [c for c in cols if _nospace(c) == _nospace(fld)]
    if len(same) == 1:
        return same[0]
    aliases = {_nospace(o): a for o, a in re.findall(r"\[([^\]]+)\]\s+AS\s+\[([^\]]+)\]", s.get("sql") or "", re.I)}
    alias = aliases.get(_nospace(fld))
    hit = [c for c in cols if alias and _nospace(c) == _nospace(alias)]
    return hit[0] if len(hit) == 1 else fld


def unify_ratio_fields(mapping) -> list:
    """
    [비율 기준 일치] 비율의 분자·분모가 양식에 있는 같은 이름의 개수 칸(예: 합격인원)과 정의만 다르면(합격인원(최초) vs 합격인원(최종))
    그 칸이 쓰는 열로 맞춤 → 합격인원 칸은 최종인데 등록율은 최초로 나누는 엇갈림 방지. 반환: 안내 문구
    """
    notes = []
    fields = [m for m in mapping.get("measures", []) if m.get("kind") == "field"]
    for m in mapping.get("measures", []):
        if m.get("kind") != "ratio":
            continue
        for sk, fk, part in (("num_source", "num_field", "분자"), ("den_source", "den_field", "분모")):
            b = _base_name(m.get(fk))
            same = [f for f in fields if norm(f.get("label")) == norm(b) or _base_name(f.get("field")) == b]
            if len(same) == 1 and (same[0].get("source"), same[0].get("field")) != (m.get(sk), m.get(fk)):
                notes.append(f"'{m.get('label')}' 의 {part} {m.get(fk)} → 양식 '{same[0].get('label')}' 칸과 같은 {same[0].get('field')} 로 맞춤")
                m[sk], m[fk] = same[0].get("source"), same[0].get("field")
    return notes


def plain_ratio_decisions(mapping):
    """비율 기준 문구의 '합격인원(최초)' 같은 정의 표시를 양식의 칸 이름(합격인원)으로 — 정의는 개수 지표 기준에서 따로 고름"""
    labels = {norm(m.get("label")): m.get("label") for m in mapping.get("measures", []) if m.get("kind") == "field"}
    ratios = {norm(m.get("label")) for m in mapping.get("measures", []) if m.get("kind") == "ratio"}

    def plain(text):
        return re.sub(r"([0-9A-Za-z가-힣]+)\s*[(（][^)）]*[)）]",
                      lambda mt: labels.get(norm(mt.group(1)), mt.group(0)), str(text or ""))

    for d in mapping.get("decisions", []):
        if norm(d.get("topic")) in ratios:
            d["options"] = list(dict.fromkeys(plain(o) for o in d.get("options") or []))
            d["applied"] = plain(d.get("applied"))
            if d["applied"] not in d["options"]:
                d["options"].insert(0, d["applied"])


def rename_fields(mapping, renames):
    """[기준 바꿔 다시 채우기] 지표 정의만 바뀐 경우 이전 대응표의 열 이름만 바꿈 (예: 등록인원(전체) → 등록인원(최초합격자 중))"""
    import copy
    m2 = copy.deepcopy(mapping)
    ren = {_nospace(o): n for o, n in renames.items()}
    for sm in m2.get("slots", []):
        for f in sm.get("fields", []):
            f["field"] = ren.get(_nospace(f.get("field")), f.get("field"))
    for m in m2.get("measures", []):
        for k in ("field", "num_field", "den_field", "text_replace_field"):
            if m.get(k):
                m[k] = ren.get(_nospace(m[k]), m[k])
    return m2


def apply_choices(mapping, choices):
    """고른 기준을 대응표의 기준 목록에 반영 (applied·basis=user)"""
    by_topic = {norm(c.get("topic")): c.get("answer") for c in choices or []}
    for d in mapping.get("decisions", []):
        ans = by_topic.get(norm(d.get("topic")))
        if ans:
            d["applied"], d["basis"] = ans, "user"
            if ans not in (d.get("options") or []):
                d["options"] = list(d.get("options") or []) + [ans]


def _hides_text_values(sql, field) -> bool:
    """SQL 에서 이 지표 열이 ISNUMERIC 등으로 숫자만 남겨져 '제한없음' 같은 글자 값이 사라졌는지"""
    m = re.search(r"((?:SUM|MAX|MIN)\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))\s+AS\s+\[?" + re.escape(field) + r"\]?", sql or "", re.I)
    return bool(m and re.search(r"\bISNUMERIC\b|\bTRY_CAST\b|\bTRY_CONVERT\b", m.group(1), re.I))


def _is_conditional_count(sql, field) -> bool:
    """SQL 에서 이 열이 조건부 집계(SUM/COUNT(CASE WHEN ...))로 만들어졌는지. 조건 없는 COUNT(*) 등은 뜻이 하나뿐인 지표"""
    m = re.search(r"((?:SUM|COUNT)\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))\s+AS\s+\[?" + re.escape(field) + r"\]?", sql or "", re.I)
    return bool(m and re.search(r"\bCASE\b", m.group(1), re.I))


def sanitize_decisions(mapping, rows_by_src, sql_by_src=None):
    """
    계산 기준(decisions)을 세 종류로만 제한합니다: 비율 계산식 / 지표 정의 (topic = 양식의 지표 이름) / 숫자 아닌 값 처리.
    - 이름 대응·학년도 등 지표가 아닌 항목은 버림
    - 숫자 아닌 값 항목은 지표에 실제로 쓰이는 열에 글자 값이 있을 때만 남기고, AI 가 빠뜨렸으면 시스템이 추가
    """
    measures = mapping.get("measures", [])
    labels = {norm(m.get("label")) for m in measures}
    # 지표(kind=field)로 쓰이는 열 중 글자 값(제한없음 등)이 있는 열
    text_cols = {}
    for m in measures:
        if m.get("kind") != "field":
            continue
        vals = {str(r.get(m.get("field"))).strip() for r in rows_by_src.get(m.get("source"), [])
                if r.get(m.get("field")) not in (None, "") and to_num(r.get(m.get("field"))) is None}
        if vals:
            text_cols[norm(m.get("label"))] = (m, sorted(vals))

    kept, text_topics = [], {}
    for d in mapping.get("decisions", []):
        topic = d.get("topic") or ""
        if norm(topic).startswith(norm(TEXT_TOPIC_PREFIX)):
            inner = norm(re.sub(r"^.*?[(（:]", "", topic).rstrip(")）"))
            hit = next((k for k in text_cols if k == inner or norm(text_cols[k][0].get("field")) == inner), None)
            if hit:
                # 선택지는 시스템이 표준 문구(글자 그대로 / 비움 / '지표' 값으로 채움)로 다시 만들고, 기준 출처만 유지
                text_topics[hit] = d.get("basis") or "ai"
        elif norm(topic) in labels:
            m = next(x for x in measures if norm(x.get("label")) == norm(topic))
            if m.get("kind") == "ratio":
                kept.append(d)
            elif _is_conditional_count((sql_by_src or {}).get(m.get("source"), ""), m.get("field")):
                kept.append(d)  # 합격인원·등록인원처럼 조건으로 세는 지표만 (정의가 갈릴 수 있음)

    for key, (m, vals) in text_cols.items():
        others = [x.get("label") for x in measures if x.get("kind") == "field" and norm(x.get("label")) != key]
        options = ["글자 그대로 표시", "비움"] + [f"'{o}' 값으로 채움" for o in others]
        pol = m.get("text_policy") or "keep"
        if pol == "blank":
            applied = "비움"
        elif pol == "replace":
            rep = next((x.get("label") for x in measures if x.get("kind") == "field"
                        and x.get("source") == m.get("text_replace_source") and x.get("field") == m.get("text_replace_field")), None)
            applied = f"'{rep}' 값으로 채움" if rep else f"{m.get('text_replace_field')} 값으로 채움"
            if applied not in options:
                options.append(applied)
        else:
            applied = "글자 그대로 표시"
        kept.append({"topic": f"{TEXT_TOPIC_PREFIX}({m.get('label')})",
                     "question": f"'{m.get('label')}'에 {vals[:3]} 같은 글자 값이 있습니다. 이 칸과 이 값이 들어가는 비율·합계를 어떻게 채울까요?",
                     "options": options, "applied": applied, "basis": text_topics.get(key, "ai"), "affects_query": False})
    return kept


def criteria_text(mapping, auto_conditions=None) -> str:
    """답변·로그용 [적용한 계산 기준] 블록 (각 기준이 어디서 정해졌는지 함께 표시)"""
    lines = [f"- 조건: {c}  (질문·파일명에서 자동 적용)" for c in auto_conditions or []]
    covered = set()
    for d in mapping.get("decisions", []):
        lines.append(f"- {d.get('topic')} = {d.get('applied')}  ({BASIS_LABEL.get(d.get('basis'), d.get('basis'))})")
        covered.add(norm(d.get("topic")))
    for m in mapping.get("measures", []):
        if m.get("kind") == "ratio" and norm(m.get("label")) not in covered:
            lines.append(f"- {m.get('label')} = {m.get('num_field')} ÷ {m.get('den_field')} × {clean_number(float(m.get('scale') or 100))}, "
                         f"소수 {m.get('decimals')}자리  ({BASIS_LABEL['ai']})")
    return ("[적용한 계산 기준]\n" + "\n".join(lines)) if lines else ""


def unresolved_decisions(decisions):
    """질문·기본값·사용자 선택 어디에도 없어 AI 가 정한 기준 (사용자에게 물어볼 항목)"""
    return [d for d in decisions or [] if d.get("basis") == "ai"]


def mapping_to_text(mapping) -> str:
    """로그용 대응표 요약"""
    lines = []
    for sm in mapping.get("slots", []):
        fields = ", ".join(f"{f['source']}.{f['field']}" for f in sm.get("fields", []))
        lines.append(f"[{sm.get('slot')}] {sm.get('role')}" + (f" → {fields}" if fields else ""))
        if sm.get("role") == "dimension":
            for lab in sm.get("labels", []):
                if lab.get("kind") == "value":
                    vals = "; ".join(f"{v['source']}:{v.get('db_values')}" for v in lab.get("values", []))
                    lines.append(f"   '{lab.get('label')}' → {vals}")
                else:
                    lines.append(f"   '{lab.get('label')}' → ({lab.get('kind')})")
    for m in mapping.get("measures", []):
        if m.get("kind") == "ratio":
            lines.append(f"[지표] '{m.get('label')}' = {m.get('num_source')}.{m.get('num_field')} ÷ "
                         f"{m.get('den_source')}.{m.get('den_field')} × {m.get('scale')} (소수 {m.get('decimals')}자리)")
        else:
            pol = m.get("text_policy") or "keep"
            pol_txt = {"keep": "", "blank": " (숫자 아닌 값은 비움)",
                       "replace": f" (숫자 아닌 값은 {m.get('text_replace_source')}.{m.get('text_replace_field')} 로 대체)"}.get(pol, "")
            lines.append(f"[지표] '{m.get('label')}' = {m.get('source')}.{m.get('field')}{pol_txt}")
    return "\n".join(lines)
