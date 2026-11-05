"""
[이름 보정기] AI 가 쓴 SQL 의 조건 값(전형명·학과명 등)을 값 사전(실제 DB 값)과 대조해 고칩니다.
- 정확히 같으면 그대로
- 띄어쓰기만 다르거나 / 실제 값에 포함되거나 / 철자가 비슷한 후보가 1개면 자동 교체 + 안내 문구
- 후보가 여러 개면 사용자에게 물을 항목으로 돌려줌
- 후보가 없으면 "그 학년도에 없는 값" 안내 (다른 학년도에만 있으면 그 사실도 표시)
SQL 에는 항상 DB 에 실제로 있는 값만 들어가도록 하는 것이 목적입니다.
"""
import difflib
import re


def _norm(s: str) -> str:
    return re.sub(r"[\s·ㆍ_\-()（）\[\]]", "", str(s)).lower()


def _column_values(value_dict: dict) -> dict:
    """{열: {학년도: set(값)}} — 같은 이름의 열이 여러 테이블에 있으면 합침"""
    cols = {}
    for t_cols in (value_dict or {}).values():
        for col, by_year in t_cols.items():
            dst = cols.setdefault(col, {})
            for y, vals in by_year.items():
                dst.setdefault(str(y), set()).update(vals)
    return cols


def _sql_years(sql: str) -> list:
    """SQL 의 학년도 조건 (예: 입시학년도 = 2027, 학년도 IN (2026, 2027))"""
    years = []
    for m in re.finditer(r"학년도\]?\s*(?:=\s*N?'?(\d{4})'?|IN\s*\(([^)]*)\))", sql, re.I):
        if m.group(1):
            years.append(m.group(1))
        else:
            years += re.findall(r"\d{4}", m.group(2))
    return sorted(set(years))


def find_candidates(given: str, valid: set) -> list:
    """given 과 같은 뜻으로 보이는 실제 값 후보 (가까운 순)"""
    if given in valid:
        return [given]
    g = _norm(given)
    if not g:
        return []
    same = [v for v in valid if _norm(v) == g]
    if same:
        return sorted(same)
    contains = [v for v in valid if len(g) >= 2 and (g in _norm(v) or (len(_norm(v)) >= 2 and _norm(v) in g))]
    if contains:
        return sorted(contains, key=lambda v: (abs(len(_norm(v)) - len(g)), v))
    norm_map = {}
    for v in valid:
        norm_map.setdefault(_norm(v), []).append(v)
    close = difflib.get_close_matches(g, list(norm_map.keys()), n=3, cutoff=0.6)
    return [v for k in close for v in sorted(norm_map[k])]


# [열] / 별칭.[열] / 열 / REPLACE([열], ' ', '') 다음의 = 'x', <> 'x', IN ('x', 'y')
HISTORY = {}                 # {테이블: {열: 지난 학년도까지 모든 값}} — 값 사전을 갱신할 때 main 이 채움
ALL_CHOICE = "__ALL__"      # 사용자가 '후보 모두 포함'을 고른 경우의 선택 값
_MULTI_SEP = "\x00"          # 값 하나 자리에 여러 값을 넣을 때 쓰는 임시 구분자

_LITERAL_RE = re.compile(r"N?'((?:[^']|'')*)'")


def resolve_sql_values(sql: str, value_dict: dict, choices: dict = None):
    """
    반환: (고친 SQL, 안내 문구 목록, 물어볼 항목 목록)
    물어볼 항목: [{"column", "given", "candidates", "years"}]
    choices: {given: 선택한 값} — 사용자가 고른 값 (다시 요청할 때)
    """
    choices = choices or {}
    cols = _column_values(value_dict)
    if not sql or not cols:
        return sql, [], []
    years = _sql_years(sql)
    notes, ask, seen = [], [], set()
    col_alt = "|".join(sorted((re.escape(c) for c in cols), key=len, reverse=True))
    pattern = re.compile(
        r"(?P<col>(?:REPLACE\s*\(\s*)?(?:\w+\.)?(?:\[(?:" + col_alt + r")\]|(?<![\w가-힣])(?:" + col_alt + r")(?![\w가-힣]))"
        r"(?:\s*,\s*N?'\s'\s*,\s*N?''\s*\))?)"
        r"(?P<op>\s*(?:=|<>|!=|NOT\s+IN|IN|NOT\s+LIKE|LIKE)\s*)"
        r"(?P<rhs>\(\s*N?'(?:[^']|'')*'(?:\s*,\s*N?'(?:[^']|'')*')*\s*\)|N?'(?:[^']|'')*')",
        re.I)

    def fix_literal(col, lit, is_like=False):
        given = lit.replace("''", "'")
        by_year = cols[col]
        valid = set().union(*(by_year.get(y, set()) for y in years)) if years and any(y in by_year for y in years) \
            else set().union(*by_year.values())
        if given in valid or not given.strip():
            return lit  # 빈 값('') 비교는 '값 없음' 처리용이라 보정 대상 아님
        # 조회 학년도가 값 사전(최근 학년도)보다 넓거나 학년도 조건이 없으면, 지난 학년도에만 있는 실제 값(옛 이름)은 그대로 둠
        if given not in choices and (not years or any(y not in by_year for y in years)) \
                and any(given in t_cols.get(col, ()) for t_cols in HISTORY.values()):
            if (col, given) not in seen:
                notes.append(f"'{given}' 은(는) 지난 학년도의 실제 값 ({col}, 최근 학년도에는 없음) → 그대로 조회")
            seen.add((col, given))
            return lit
        if is_like and given not in choices:
            # LIKE: 패턴에 맞는 실제 값이 있으면 그대로 두고, 여러 값이 함께 걸리면 답변에서 밝히도록 안내
            rx = "^" + "".join(".*" if ch == "%" else "." if ch == "_" else re.escape(ch) for ch in given) + "$"
            matched = sorted(v for v in valid if re.match(rx, v, re.I))
            if matched:
                if len(matched) > 1 and (col, given) not in seen:
                    notes.append(f"{col} LIKE '{given}' 에 실제 값 {len(matched)}개가 함께 포함됨: {', '.join(matched[:10])}")
                seen.add((col, given))
                return lit
            given = given.strip("%")
        if given in choices:
            chosen = choices[given]
            if chosen == ALL_CHOICE:
                # '모두 포함' 선택: 후보 전체를 IN 목록으로 (repl 에서 = / LIKE → IN 으로 바꿈)
                every = find_candidates(given, valid)
                notes.append(f"'{given}' → {', '.join(every)} 모두 포함 (사용자 선택, {col})")
                return _MULTI_SEP.join(v.replace("'", "''") for v in every)
            if chosen and chosen != given:
                notes.append(f"'{given}' → '{chosen}' (사용자 선택, {col})")
            return (chosen or given).replace("'", "''")
        cands = find_candidates(given, valid)
        key = (col, given)
        if len(cands) == 1:
            if key not in seen:
                notes.append(f"'{given}' → '{cands[0]}' 로 해석 ({col}, 실제 DB 값 기준)")
            seen.add(key)
            return cands[0].replace("'", "''")
        if len(cands) > 1:
            if key not in seen:
                ask.append({"column": col, "given": given, "candidates": cands[:6], "years": years})
            seen.add(key)
            return lit
        if key not in seen:
            other = sorted(y for y, vals in by_year.items() if given in vals or any(_norm(v) == _norm(given) for v in vals))
            year_str = f"{', '.join(years)}학년도" if years else "DB"
            msg = f"'{given}' 은(는) {year_str}의 {col} 실제 값에 없음"
            if other:
                msg += f" ({', '.join(other)}학년도에만 있음)"
            notes.append(msg)
        seen.add(key)
        return lit

    def repl(m):
        col_text = m.group("col")
        col = next(c for c in sorted(cols, key=len, reverse=True) if c in col_text)
        is_like = "LIKE" in m.group("op").upper()
        rhs = _LITERAL_RE.sub(lambda lm: lm.group(0)[:lm.start(1) - lm.start(0)] + fix_literal(col, lm.group(1), is_like) + "'",
                              m.group("rhs"))
        op = m.group("op")
        if _MULTI_SEP in rhs and not rhs.lstrip().startswith("("):
            negate = bool(re.search(r"<>|!=|NOT", op, re.I))
            op, rhs = (" NOT IN " if negate else " IN "), "(" + rhs + ")"
        return col_text + op + rhs.replace(_MULTI_SEP, "', N'")

    new_sql = pattern.sub(repl, sql)
    return new_sql, notes, ask

