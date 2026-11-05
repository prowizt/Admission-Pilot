"""
[지표 사전 → SQL 조립] AI 는 '설계도'(지표·구분·조건)만 고르고, SQL 은 Sys_MetricCatalog / Sys_DimensionCatalog 정의대로 파이썬이 조립합니다.
- 지표마다 정의된 테이블·계산식·기본 조건을 그대로 사용 (같은 테이블·같은 기본 조건의 지표는 쿼리 하나로 묶음)
- 구분은 테이블마다 정의된 열을 구분명 별칭으로 SELECT·GROUP BY (예: 지원학과명 AS [학과], 모집학과명 AS [학과])
- 글자 섞인 지표(value_kind = mixed, 예: 모집인원 '제한없음')는 집계하지 않고 행 단위로 원본 값 조회
- 사전에 없는 지표가 있으면 조립하지 않음 → 호출부가 AI 자유 SQL 로 대체
조건 값의 표기 보정은 조립한 SQL 을 value_resolver 가 다시 확인합니다.
"""
import re


def load_catalog(conn) -> dict:
    """사용 중인 지표·구분 정의. 테이블이 없거나 오류면 빈 사전"""
    cat = {"metrics": [], "dims": []}
    try:
        cur = conn.cursor()
        cur.execute("SELECT metric_name, ISNULL(synonyms, ''), table_name, expression, ISNULL(base_condition, ''), value_kind, ISNULL(description, '') "
                    "FROM Sys_MetricCatalog WHERE is_active = 'Y' ORDER BY metric_id")
        cat["metrics"] = [dict(zip(("name", "synonyms", "table", "expression", "condition", "kind", "description"), r)) for r in cur.fetchall()]
        cur.execute("SELECT dim_name, table_name, column_name, ISNULL(description, '') FROM Sys_DimensionCatalog WHERE is_active = 'Y' ORDER BY dim_id")
        cat["dims"] = [dict(zip(("name", "table", "column", "description"), r)) for r in cur.fetchall()]
    except Exception as e:
        print(f"[지표 사전] 불러오기 실패 (AI 자유 SQL 로 진행): {e}")
    return cat


def catalog_prompt_text(cat: dict) -> str:
    """라우터 AI 에게 보여 줄 지표·구분 목록"""
    if not cat.get("metrics"):
        return ""
    lines = ["[지표 사전 (관리자 등록 정의)]"]
    for m in cat["metrics"]:
        syn = f" / 비슷한 말: {m['synonyms']}" if m["synonyms"] else ""
        desc = f" — {m['description']}" if m["description"] else ""
        lines.append(f"- 지표 '{m['name']}' ({m['table']}){syn}{desc}")
    dims = {}
    for d in cat["dims"]:
        dims.setdefault(d["name"], []).append(f"{d['table']}.{d['column']}" + (f" ({d['description']})" if d["description"] else ""))
    lines.append("[구분 사전]")
    lines += [f"- 구분 '{n}': {', '.join(v)}" for n, v in dims.items()]
    return "\n".join(lines)


def _quote(v) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def build_sql(plan: dict, cat: dict):
    """
    plan: {"metrics": [지표명], "dimensions": [구분명], "filters": [{"dimension": 구분명, "values": [값]}]}
    반환: (SQL 목록, 안내 문구 목록, 오류 문구 목록). 오류가 있으면 SQL 목록은 빈 목록 (호출부가 자유 SQL 로 대체)
    """
    by_name = {m["name"]: m for m in cat.get("metrics", [])}
    dim_col = {(d["name"], d["table"]): d["column"] for d in cat.get("dims", [])}
    metrics = [x for x in dict.fromkeys(plan.get("metrics") or []) if x]
    dims = [x for x in dict.fromkeys(plan.get("dimensions") or []) if x]
    filters = [f for f in (plan.get("filters") or []) if f.get("dimension") and f.get("values")]
    errors = [f"지표 사전에 없는 지표: '{m}'" for m in metrics if m not in by_name]
    known_dims = {d["name"] for d in cat.get("dims", [])}
    # 사전에 없는 구분(예: 양식의 '주야' 열)은 빼고 진행 (합쳐서 계산될 뿐 숫자는 틀리지 않음). 조건은 빼면 범위가 넓어지므로 오류
    unknown_dims = [d for d in dims if d not in known_dims]
    dims = [d for d in dims if d in known_dims]
    errors += [f"구분 사전에 없는 조건: '{f['dimension']}'" for f in filters if f["dimension"] not in known_dims]
    if not metrics:
        errors.append("지표가 비어 있음")
    if errors:
        return [], [], errors

    groups = {}
    for name in metrics:
        m = by_name[name]
        groups.setdefault((m["table"], m["condition"].strip(), m["kind"] == "mixed"), []).append(m)

    queries = []
    notes = [f"구분 사전에 없는 '{', '.join(unknown_dims)}' 은(는) 빼고 조회 (필요하면 지표 사전의 구분에 추가)"] if unknown_dims else []
    for (table, condition, is_mixed), ms in groups.items():
        sel_dims = [(d, dim_col[(d, table)]) for d in dims if (d, table) in dim_col]
        missing = [d for d in dims if (d, table) not in dim_col]
        if missing:
            notes.append(f"{table}에는 '{', '.join(missing)}' 구분이 없어 {', '.join(m['name'] for m in ms)}을(를) 합쳐서 계산")
        where = _filter_where(table, condition, filters, dim_col, notes)
        select = [f"[{c}] AS [{d}]" for d, c in sel_dims] + [f"{m['expression']} AS [{m['name']}]" for m in ms]
        sql = f"SELECT {', '.join(select)} FROM [{table}]"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if not is_mixed and sel_dims:
            sql += " GROUP BY " + ", ".join(f"[{c}]" for _, c in sel_dims)
        queries.append(sql)
    return queries, notes, []


def _base(name) -> str:
    """지표 묶음 이름: '등록인원(최초합격자 중)' → '등록인원' (공백 무시)"""
    return re.sub(r"\s+", "", re.sub(r"\s*[(（].*$", "", str(name or "")))


def family(cat: dict, name) -> list:
    """같은 묶음(괄호 앞 이름이 같은)의 지표명 목록. 예: 등록인원 → [등록인원(전체), 등록인원(최초합격자 중)]"""
    b = _base(name)
    return [m["name"] for m in cat.get("metrics", []) if b and _base(m["name"]) == b]


def align_decisions(decisions, plan: dict, cat: dict) -> bool:
    """
    [계산 기준 ↔ 지표 사전] 설계도로 조립한 경우, 정의가 둘 이상인 지표의 기준 선택지를 지표 사전의 지표명으로 맞춤.
    (기준을 바꾸면 설계도의 지표만 바꿔 SQL 을 다시 조립할 수 있도록) 바뀐 것이 있으면 True
    """
    used = list((plan or {}).get("metrics") or [])
    changed = False
    for d in decisions or []:
        members = family(cat, d.get("topic"))
        hit = next((m for m in used if m in members), None)
        if len(members) < 2 or not hit:
            continue
        if d.get("options") != members or d.get("applied") != hit or not d.get("affects_query"):
            d.update({"options": members, "applied": hit, "affects_query": True})
            changed = True
    return changed


def swap_metrics(plan: dict, choices, cat: dict):
    """
    고른 기준(지표 사전의 지표명)으로 설계도의 같은 묶음 지표를 바꾼 새 설계도.
    고른 값이 지표 사전에 없는 등 바꿀 수 없는 기준이 하나라도 있으면 None (호출부가 AI 수정으로 대체)
    """
    names = {re.sub(r"\s+", "", m["name"]): m["name"] for m in cat.get("metrics", [])}
    metrics = list((plan or {}).get("metrics") or [])
    for c in choices or []:
        new = names.get(re.sub(r"\s+", "", str(c.get("answer") or "")))
        members = family(cat, c.get("topic"))
        idx = next((i for i, m in enumerate(metrics) if m in members), None)
        if not new or new not in members or idx is None:
            return None
        metrics[idx] = new
    return dict(plan, metrics=list(dict.fromkeys(metrics)))


def _filter_where(table, condition, filters, dim_col, notes):
    """기본 조건 + 질문 조건(학년도 4자리로 맞춤). 그 테이블에 없는 구분의 조건은 안내만"""
    where = [f"({condition})"] if condition else []
    for f in filters:
        col = dim_col.get((f["dimension"], table))
        if not col:
            notes.append(f"{table}에는 '{f['dimension']}' 구분이 없어 조건 {f['values']} 미적용")
            continue
        vals = [str(v).strip() for v in f["values"] if str(v).strip()]
        if "학년도" in f["dimension"]:
            vals = [(re.search(r"\d{4}", v) or re.search(r".+", v)).group(0) for v in vals]
        if len(vals) == 1 and re.search(rf"\[{re.escape(col)}\]\s*=\s*N?'{re.escape(vals[0])}'", condition or ""):
            continue  # 기본 조건과 같은 조건(예: 신입)은 한 번만
        if len(vals) == 1:
            where.append(f"[{col}] = {_quote(vals[0])}")
        elif vals:
            where.append(f"[{col}] IN ({', '.join(_quote(v) for v in vals)})")
    return where


def _nospace(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _ident(s) -> str:
    return str(s).replace("]", "")


def _scale(ratio) -> int:
    try:
        return int(float(ratio.get("scale") or 100))
    except (TypeError, ValueError):
        return 100


def build_query_sql(plan: dict, cat: dict, value_dict=None, conn=None):
    """
    [쿼리 요청 → 표 모양 SQL 하나] 설계도로 SSMS 에서 바로 실행할 수 있는 완성 쿼리를 조립합니다.
    plan: metrics, rows(행 구분), column_dimension(열로 펼칠 구분, 없으면 ""), column_values(펼칠 값, 비우면 실제 값 전부),
          ratios([{name, numerator, denominator, scale}] — scale 100 이면 %, 1 이면 배수(경쟁률)), filters
    - 지표는 테이블·기본 조건별 CTE 로 집계, 테이블이 여럿이면 행 구분 값(띄어쓰기 무시)으로 LEFT JOIN
    - 열 펼치기는 SUM(CASE WHEN ...) — 값 비교는 띄어쓰기를 무시해 테이블마다 표기가 달라도 같은 열로 모음
    - 글자 섞인 지표(모집인원 '제한없음' 등)는 숫자만 합산 (주석으로 표시)
    반환: (SQL, 안내 문구 목록, 오류 목록). 오류가 있으면 SQL 은 "" (호출부가 AI 작성 SQL 사용)
    """
    by_name = {m["name"]: m for m in cat.get("metrics", [])}
    dim_col = {(d["name"], d["table"]): d["column"] for d in cat.get("dims", [])}
    known_dims = {d["name"] for d in cat.get("dims", [])}
    ratios = [r for r in (plan.get("ratios") or []) if r.get("name") and r.get("numerator") and r.get("denominator")]
    metrics = [x for x in dict.fromkeys(list(plan.get("metrics") or []) + [r[k] for r in ratios for k in ("numerator", "denominator")]) if x]
    rows = [x for x in dict.fromkeys(plan.get("rows") or []) if x]
    pivot = (plan.get("column_dimension") or "").strip()
    filters = [f for f in (plan.get("filters") or []) if f.get("dimension") and f.get("values")]
    errors = [f"지표 사전에 없는 지표: '{m}'" for m in metrics if m not in by_name]
    unknown_rows = [d for d in rows if d not in known_dims]
    rows = [d for d in rows if d in known_dims]
    errors += [f"구분 사전에 없는 구분: '{d}'" for d in ([pivot] if pivot else []) + [f["dimension"] for f in filters] if d not in known_dims]
    if pivot and pivot in rows:
        errors.append(f"'{pivot}'이(가) 행과 열에 모두 있음")
    if not metrics:
        errors.append("지표가 비어 있음")
    if errors:
        return "", [], errors

    notes = [f"구분 사전에 없는 '{', '.join(unknown_rows)}' 은(는) 행에서 빼고 조회 (필요하면 지표 사전의 구분에 추가)"] if unknown_rows else []
    groups = {}
    for name in metrics:
        m = by_name[name]
        groups.setdefault((m["table"], m["condition"].strip()), []).append(m)

    # 열로 펼칠 값: 지정값을 실제 값으로 맞추고, 비어 있으면 조건 학년도의 실제 값 전부 (띄어쓰기만 다른 값은 하나로)
    years = [re.search(r"\d{4}", str(v)).group(0) for f in filters if "학년도" in f["dimension"]
             for v in f["values"] if re.search(r"\d{4}", str(v))]
    pivot_vals = []
    if pivot:
        actual = []
        for (table, _cond) in groups:
            col = dim_col.get((pivot, table))
            by_year = ((value_dict or {}).get(table) or {}).get(col) or {}
            for y, vals in sorted(by_year.items()):
                if not years or y in years or y == "전체":
                    actual += sorted(vals)
        actual = list(dict.fromkeys(actual))
        if conn:
            # 조건(학년도·모집구분 등)에 실제로 데이터가 있는 값만 열로 (없는 전형의 빈 열 방지)
            present = []
            for (table, cond) in groups:
                col = dim_col.get((pivot, table))
                if not col:
                    continue
                where = _filter_where(table, cond, filters, dim_col, [])
                try:
                    cur = conn.cursor()
                    cur.execute(f"SELECT DISTINCT [{col}] FROM [{table}]" + (" WHERE " + " AND ".join(where) if where else ""))
                    present += [str(r[0]) for r in cur.fetchall() if r[0] not in (None, "")]
                except Exception as e:
                    print(f"[지표 사전] 열 값 조회 실패 (값 사전 사용): {e}")
                    present = []
                    break
            if present:
                keep = {_nospace(v) for v in present}
                actual = [v for v in actual if _nospace(v) in keep] + [v for v in sorted(set(present)) if _nospace(v) not in {_nospace(a) for a in actual}]
        given = [str(v).strip() for v in plan.get("column_values") or [] if str(v).strip()]
        if given:
            from value_resolver import find_candidates
            for g in given:
                cands = find_candidates(g, set(actual)) if actual else []
                if cands and cands[0] != g:
                    notes.append(f"열 값 '{g}' → 실제 값 '{cands[0]}'")
                pivot_vals.append(cands[0] if cands else g)
        else:
            pivot_vals = actual
        seen, uniq = set(), []
        for v in pivot_vals:
            if _nospace(v) not in seen:
                seen.add(_nospace(v))
                uniq.append(v)
        pivot_vals = uniq
        if not pivot_vals:
            return "", [], [f"'{pivot}' 의 실제 값을 찾지 못해 열로 펼칠 수 없음"]

    ctes, parts = [], []  # parts: 그룹별 {alias, dims, cols: {(지표, 열 값 또는 None=합계): CTE 열 이름}}
    for gi, ((table, condition), ms) in enumerate(groups.items(), 1):
        g_dims = [(d, dim_col[(d, table)]) for d in rows if (d, table) in dim_col]
        missing = [d for d in rows if (d, table) not in dim_col]
        if missing:
            notes.append(f"{table}에는 '{', '.join(missing)}' 구분이 없어 {', '.join(m['name'] for m in ms)}을(를) 합쳐서 계산")
        p_col = dim_col.get((pivot, table)) if pivot else None
        if pivot and not p_col:
            notes.append(f"{table}에는 '{pivot}' 구분이 없어 {', '.join(m['name'] for m in ms)}은(는) 합계만 표시")
        where = _filter_where(table, condition, filters, dim_col, notes)
        sel = [f"[{c}] AS [{_ident(d)}]" for d, c in g_dims]
        grp = [f"[{c}]" for _, c in g_dims]
        if p_col:
            sel.append(f"[{p_col}] AS [__열]")
            grp.append(f"[{p_col}]")
        comments = []
        for j, m in enumerate(ms):
            expr = m["expression"]
            if m["kind"] == "mixed":
                expr = f"SUM(TRY_CAST({expr} AS INT))"
                comments.append(f"    -- {m['name']}: 숫자 아닌 값('제한없음' 등)은 합산에서 제외됨")
            sel.append(f"{expr} AS [m{j}]")
        sql = "".join(c + "\n" for c in comments) + f"    SELECT {', '.join(sel)} FROM [{table}]"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if grp:
            sql += " GROUP BY " + ", ".join(grp)
        alias = f"g{gi}"
        cols = {}
        if p_col:
            # 열 펼치기: 그룹 CTE 위에서 값마다 SUM(CASE WHEN)
            pv_sel = [f"[{_ident(d)}]" for d, _ in g_dims]
            for j, m in enumerate(ms):
                for k, v in enumerate(pivot_vals):
                    pv_sel.append(f"SUM(CASE WHEN REPLACE([__열], ' ', '') = {_quote(_nospace(v))} THEN [m{j}] END) AS [m{j}_{k}]")
                    cols[(m["name"], v)] = f"m{j}_{k}"
                pv_sel.append(f"SUM([m{j}]) AS [m{j}_t]")
                cols[(m["name"], None)] = f"m{j}_t"
            ctes.append(f"{alias}_raw AS (\n{sql}\n)")
            pv = f"    SELECT {', '.join(pv_sel)} FROM {alias}_raw"
            if g_dims:
                pv += " GROUP BY " + ", ".join(f"[{_ident(d)}]" for d, _ in g_dims)
            ctes.append(f"{alias} AS (\n{pv}\n)")
        else:
            ctes.append(f"{alias} AS (\n{sql}\n)")
            for j, m in enumerate(ms):
                cols[(m["name"], None)] = f"m{j}"
        parts.append({"alias": alias, "dims": [d for d, _ in g_dims], "cols": cols,
                      "kinds": {m["name"]: m["kind"] for m in ms}})

    # 행 구분: 모든 행 구분이 있는 그룹들의 값을 합쳐 기준 행으로 (띄어쓰기만 다른 값은 한 행)
    out_dims = rows if any(len(p["dims"]) == len(rows) for p in parts) else parts[0]["dims"]
    for d in rows:
        if d not in out_dims:
            notes.append(f"'{d}' 구분은 표에서 빠짐 (지표 테이블에 없음)")
    if len(parts) == 1 or not out_dims:
        base_from = " CROSS JOIN ".join(p["alias"] for p in parts)
        dim_ref = {d: f"{parts[0]['alias']}.[{_ident(d)}]" for d in out_dims}
        joins = ""
    else:
        full = [p for p in parts if all(d in p["dims"] for d in out_dims)]
        union = "\n        UNION ALL\n".join(
            f"        SELECT {', '.join(f'[{_ident(d)}]' for d in out_dims)} FROM {p['alias']}" for p in full)
        keys_sel = ", ".join(f"MIN([{_ident(d)}]) AS [{_ident(d)}]" for d in out_dims)
        keys_grp = ", ".join(f"REPLACE([{_ident(d)}], ' ', '')" for d in out_dims)
        ctes.append(f"k AS (\n    SELECT {keys_sel} FROM (\n{union}\n    ) u GROUP BY {keys_grp}\n)")
        base_from = "k"
        dim_ref = {d: f"k.[{_ident(d)}]" for d in out_dims}
        joins = ""
        for p in parts:
            on = [f"REPLACE(k.[{_ident(d)}], ' ', '') = REPLACE({p['alias']}.[{_ident(d)}], ' ', '')" for d in out_dims if d in p["dims"]]
            joins += f"\nLEFT JOIN {p['alias']} ON " + (" AND ".join(on) if on else "1 = 1")

    def ref(metric, v):
        for p in parts:
            c = p["cols"].get((metric, v))
            if c:
                r = f"{p['alias']}.[{c}]"
                return f"ISNULL({r}, 0)" if p["kinds"][metric] == "count" else r
        return None

    def label(v, name):
        return _ident(f"{v}_{name}" if v is not None else (f"합계_{name}" if pivot else name))

    select = [f"{r} AS [{_ident(d)}]" for d, r in dim_ref.items()]
    for v in (pivot_vals if pivot else []) + [None]:
        for m in metrics:
            r = ref(m, v)
            if r:
                select.append(f"{r} AS [{label(v, m)}]")
        for ra in ratios:
            num, den = ref(ra["numerator"], v), ref(ra["denominator"], v)
            if num and den:
                scale = _scale(ra)
                select.append(f"ROUND(CAST({num} AS FLOAT){' * ' + str(scale) if scale != 1 else ''} / NULLIF({den}, 0), {1 if scale != 1 else 2}) AS [{label(v, ra['name'])}]")
    for ra in ratios:
        scale = _scale(ra)
        notes.append(f"{ra['name']} = {ra['numerator']} ÷ {ra['denominator']}" + (f" × {scale} (소수 1자리" if scale != 1 else " (배수, 소수 2자리") + ", 분모 0 이면 NULL)")
    sql = "WITH " + ",\n".join(ctes) + f"\nSELECT {', '.join(select)}\nFROM {base_from}{joins}"
    if dim_ref:
        sql += "\nORDER BY " + ", ".join(dim_ref.values())
    return sql, notes, []


def prune_dimensions(plan: dict, cat: dict, slot_labels: list, value_dict=None, history=None):
    """
    [격자 양식 구분 정리] 라우터가 양식에 없는 구분(지역·정원내외 등)까지 넣으면 결과 행이 불어나 대응표가 흔들림.
    양식의 칸(행 이름 열·머리글 단)마다 이름이 가장 많이 맞는 구분 하나만 남김. 반환: (정리한 설계도, 뺀 구분 목록)
    slot_labels: [[칸의 이름들], ...]
    """
    def nz(x):
        return re.sub(r"\s+", "", str(x or "")).lower()

    dims = [d for d in dict.fromkeys(plan.get("dimensions") or []) if d]
    values = {}
    for d in cat.get("dims", []):
        if d["name"] not in dims:
            continue
        for src in (value_dict or {}, history or {}):
            col_vals = (src.get(d["table"]) or {}).get(d["column"])
            if isinstance(col_vals, dict) and col_vals and all(isinstance(v, (list, set, tuple)) for v in col_vals.values()):
                col_vals = set().union(*map(set, col_vals.values()))  # 값 사전: {학년도: [값]}
            values.setdefault(d["name"], set()).update(nz(v) for v in (col_vals or ()))

    def hits(dim, labels):
        vals = values.get(dim, set())
        return sum(1 for lab in labels if lab and any(lab == v or (len(lab) >= 2 and (lab in v or v in lab)) for v in vals))

    keep = set()
    for labels in slot_labels:
        labs = [nz(l) for l in labels]
        scores = {d: hits(d, labs) for d in dims}
        best = max(scores.values(), default=0)
        if best > 0:
            keep.update(d for d, sc in scores.items() if sc == best)
    if not keep:
        return plan, []  # 판단할 수 없으면 그대로
    dropped = [d for d in dims if d not in keep and d in values]
    if not dropped:
        return plan, []
    return dict(plan, dimensions=[d for d in dims if d not in dropped]), dropped


def read_default_criteria(conn, titles) -> dict:
    """사전지식의 [통계 기본 기준] 항목 → {주제(공백 없음): 기준}. 없으면 빈 사전"""
    try:
        cur = conn.cursor()
        for t in titles:
            cur.execute("SELECT TOP 1 content FROM Sys_SupplementalKnowledge WHERE is_active = 'Y' AND LEFT(content, ?) = ? ORDER BY id DESC",
                        (len(t), t))
            row = cur.fetchone()
            if row:
                out = {}
                for line in (row[0] or "").splitlines():
                    m = re.match(r"^- (.+?) = (.+)$", line.strip())
                    if m:
                        out[re.sub(r"\s+", "", m.group(1))] = m.group(2).strip()
                return out
    except Exception as e:
        print(f"[지표 사전] 기본 기준 읽기 실패: {e}")
    return {}


def _member_terms(cat: dict, members: list) -> dict:
    """정의마다 질문에서 그 정의를 콕 집는 표현 (다른 정의에도 들어가는 일반 표현은 제외). 예: 합격인원(최종) → 최종합격, 최종합격자, 충원포함합격"""
    nz = _nospace
    by_name = {m["name"]: m for m in cat.get("metrics", [])}
    raw = {}
    for name in members:
        base = _base(name)
        qual = re.search(r"[(（]([^)）]*)[)）]", name)
        prefix = re.sub(r"인원$", "", base)
        terms = {nz(name)} | {nz(x) for x in (by_name.get(name, {}).get("synonyms") or "").split(",") if x.strip()}
        if qual:
            terms.add(nz(qual.group(1)) + prefix)  # 최초 + 합격 → 최초합격
        raw[name] = {t for t in terms if t and t != base}
    out = {}
    for name, terms in raw.items():
        others = [t for o, ts in raw.items() if o != name for t in ts] + [o_n for o_n in members if o_n != name]
        out[name] = {t for t in terms if not any(t in nz(o) for o in others)}
    return out


def apply_default_definitions(plan: dict, cat: dict, question: str, defaults: dict):
    """
    [쿼리 요청 · 정의가 둘 이상인 지표] 질문에 정의가 있으면 그것, 없으면 [통계 기본 기준], 그것도 없으면 AI 가 고른 정의(지표 사전 설명 기준).
    설계도의 지표·비율에 같은 묶음의 정의가 섞이지 않게 하나로 맞춤. 반환: (새 설계도, 안내 문구 — '합격인원 = 합격인원(최초) (저장된 기본값 · 다른 정의: …)')
    """
    q = _nospace(question)
    plan = dict(plan, metrics=list(plan.get("metrics") or []), ratios=[dict(r) for r in plan.get("ratios") or []])
    used = list(dict.fromkeys(plan["metrics"] + [r.get(k) for r in plan["ratios"] for k in ("numerator", "denominator")]))
    notes, done = [], set()
    for name in used:
        members = family(cat, name)
        base = _base(name)
        if len(members) < 2 or base in done:
            continue
        done.add(base)
        terms = _member_terms(cat, members)
        explicit = [m for m in members if any(t in q for t in terms[m])]
        if len(explicit) > 1:
            notes.append(f"{base}: 질문에 정의 {len(explicit)}가지가 모두 나와 그대로 사용 ({', '.join(explicit)})")
            continue
        default = next((m for m in members if _nospace(m) == _nospace(defaults.get(base, ""))), None)
        current = next(m for m in used if m in members)
        target, basis = (explicit[0], "질문에서 지정") if explicit else (default, "저장된 기본값") if default else (current, "지표 사전 기본 정의")
        plan["metrics"] = list(dict.fromkeys(target if m in members else m for m in plan["metrics"]))
        for r in plan["ratios"]:
            for k in ("numerator", "denominator"):
                if r.get(k) in members:
                    r[k] = target
        others = [m for m in members if m != target]
        notes.append(f"{base} = {target} ({basis} · 다른 정의: {', '.join(others)})")
    return plan, notes
