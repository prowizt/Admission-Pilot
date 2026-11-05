"""
[환경설정] 운영 중 자주 바꾸는 값 (대시보드 '환경 설정' 메뉴)

- 우선순위: 화면에서 정한 값(Sys_SystemSetting) → .env → 코드 기본값
- 질문마다 DB 를 읽지 않도록 잠시(CACHE_TTL_SEC) 보관. 화면에서 바꾸면 보관 값도 바로 바뀜 → 재시작 불필요
- API 키·DB 계정·비밀번호는 여기 두지 않음 (.env 전용, 화면에 노출 금지)
"""
import os
import time

CACHE_TTL_SEC = 60

EFFORTS = ["low", "medium", "high"]
STUDENT_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "gemini-2.5-flash"]

# key: (묶음, 이름, 종류, 기본값, 설명, 선택지 또는 (최소, 최대))
SPEC = {
    "STUDENT_MODEL": ("학생 챗봇", "답변 모델", "choice", "gemini-2.5-flash",
                      "학생 챗봇이 쓰는 모델. Gemini 는 STUDENT_API_KEY, Claude 는 ANTHROPIC_API_KEY(.env)를 씁니다.", STUDENT_MODELS),
    "STUDENT_EFFORT": ("학생 챗봇", "답변 추론 강도", "choice", "low",
                       "높을수록 표 읽기·환산이 정확하지만 느리고 비쌉니다 (Claude 에만 적용).", EFFORTS),
    "STUDENT_DOC_TOKENS": ("학생 챗봇", "참고 문서 분량 한도 (토큰)", "int", 70000,
                           "학생 답변에 넣는 문서 전체 분량의 상한.", (5000, 95000)),
    "STUDENT_NAMED_DOC_LIMIT": ("학생 챗봇", "이름으로 지정된 문서 최대 개수", "int", 8,
                                "질문·라우터가 문서 이름을 정확히 짚은 경우 넣을 수 있는 문서 수.", (1, 20)),
    "STAFF_EFFORT": ("교직원 챗봇", "답변 추론 강도", "choice", "medium",
                     "교직원 챗봇·엑셀 채우기의 최종 답변 추론 강도 (Claude 에만 적용). 높을수록 정밀하지만 느리고 비쌉니다.", EFFORTS),
    "QUERY_ROUTER_EFFORT": ("교직원 챗봇", "쿼리 요청 라우터 추론 강도", "choice", "medium",
                            "'쿼리 만들어줘' 요청에서 SQL 을 설계하는 라우터의 추론 강도.", EFFORTS),
    "ROUTER_THINKING": ("교직원 챗봇", "라우터 추론", "choice", "off",
                        "일반 질문 라우터(문서·SQL 판단)의 추론. off 가 빠르고 저렴합니다.", ["off", "on"]),
    "MAX_PROMPT_TOKENS": ("비용 보호", "호출 차단 한도 (토큰)", "int", 100000,
                          "Claude 호출 1건의 입력이 이 값을 넘으면 호출하지 않고 취소 (Haiku 는 10만 초과 시 5배 과금).", (10000, 1000000)),
    "LARGE_DOC_TOKENS": ("비용 보호", "큰 문서 확인 기준 (토큰)", "int", 20000,
                         "교직원 질문에서 이보다 큰 문서는 넣기 전에 포함 여부를 묻습니다.", (1000, 200000)),
    "FAQ_ALL_TOKENS": ("비용 보호", "입학처 Q&A 전부 넣는 기준 (토큰)", "int", 3000,
                       "사용 중인 Q&A 가 이 값 이하이면 전부 넣고, 넘으면 AI 가 주제를 골라 넣습니다.", (0, 50000)),
    "GRID_MAP_EFFORT": ("엑셀 채우기", "칸 매핑 추론 강도", "choice", "low",
                        "엑셀 양식의 칸과 지표를 연결하는 단계의 추론 강도.", EFFORTS),
    "EXCEL_GRID_ROUTER_THINKING": ("엑셀 채우기", "격자 라우터 추론 강도", "choice", "low",
                                   "엑셀 격자 채우기의 설계도 라우터 추론. off 는 추론 끔.", ["off"] + EFFORTS),
    "EXCEL_CHOICE_TTL_SEC": ("엑셀 채우기", "'기준 바꿔 다시 채우기' 보관 시간 (초)", "int", 7200,
                             "지나면 처음부터 다시 실행해야 합니다.", (600, 86400)),
    "VALUE_DICT_TTL_SEC": ("기타", "실제 값 사전 새로 고침 주기 (초)", "int", 3600,
                           "구분 열의 실제 값 목록을 다시 읽는 주기 (만료 후 첫 질문 때 뒤에서 갱신).", (300, 86400)),
    # [Claude 크레딧] 화면의 '콘솔 잔액으로 맞추기'에서 함께 저장 (일반 설정 목록에는 표시하지 않음)
    "CREDIT_BASE_USD": ("Claude 크레딧", "기준 잔액 (USD)", "float", 0,
                        "콘솔(Billing)에서 본 크레딧 잔액. 0 이면 잔액 계산 안 함.", (0, 1000000)),
    "CREDIT_BASE_AT": ("Claude 크레딧", "기준 잔액을 맞춘 시각", "datetime", "",
                       "이 시각 이후 로그 비용을 기준 잔액에서 뺍니다.", None),
    "KRW_PER_USD": ("비용 계산", "환율 (원/달러)", "float", 1450,
                    "Claude 달러 가격을 원화로 바꿀 때 씀 (로그의 질문별 원화 비용, 통계·잔액의 원화). 사용 통계 탭에서 [충전 기록]을 하면 카드값으로 자동 계산됩니다.", (500, 3000)),
    "VAT_RATE": ("비용 계산", "부가세율", "float", 0.10,
                 "로그의 원화 비용에 더하는 부가세 비율 (0.10 = 10%).", (0, 0.5)),
}

_cache = {}  # key -> (DB 값 또는 None, 읽은 시각)


def _owner_conn():
    import db_access
    return db_access._connect(os.getenv("DB_USER"), os.getenv("DB_PWD"))


def get_raw(key):
    """화면(Sys_SystemSetting)에 저장된 값 (없으면 None). 잠시 보관해 질문마다 DB 를 읽지 않음"""
    hit = _cache.get(key)
    if hit and time.time() - hit[1] < CACHE_TTL_SEC:
        return hit[0]
    value = None
    conn = None
    try:
        conn = _owner_conn()
        cur = conn.cursor()
        cur.execute("SELECT setting_value FROM Sys_SystemSetting WHERE setting_key = ?", (key,))
        row = cur.fetchone()
        value = row[0] if row and row[0] not in (None, "") else None
    except Exception as e:
        print(f"[환경설정] '{key}' 조회 오류 → .env/기본값 사용: {str(e)[:120]}")
        if hit:
            value = hit[0]  # DB 오류면 직전 값 유지
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    _cache[key] = (value, time.time())
    return value


def _convert(key, raw):
    """문자 값을 종류에 맞게 바꾸고 범위·선택지를 검사. 맞지 않으면 ValueError"""
    _, _, kind, _, _, rule = SPEC[key]
    s = str(raw).strip()
    if kind == "datetime":
        import datetime as _dt
        try:
            return _dt.datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError("시각은 YYYY-MM-DD HH:MM:SS 형식이어야 합니다.")
    if kind == "choice":
        s = s.lower() if s.lower() in rule else s
        if s not in rule:
            raise ValueError(f"선택지({', '.join(rule)}) 중 하나여야 합니다.")
        return s
    try:
        v = int(float(s)) if kind == "int" else float(s)
    except ValueError:
        raise ValueError("숫자여야 합니다.")
    lo, hi = rule
    if not (lo <= v <= hi):
        raise ValueError(f"{lo} ~ {hi} 사이여야 합니다.")
    return v


def source_and_value(key):
    """(출처, 값): 출처는 'screen' / 'env' / 'default'. 잘못된 값은 건너뛰고 다음 순위 사용"""
    default = SPEC[key][3]
    for source, raw in (("screen", get_raw(key)), ("env", os.getenv(key))):
        if raw not in (None, ""):
            try:
                return source, _convert(key, raw)
            except ValueError:
                print(f"[환경설정] {key} 의 {source} 값 '{raw}' 이(가) 올바르지 않아 무시")
    return "default", default


def get(key):
    return source_and_value(key)[1]


def set_value(key, raw):
    """화면에서 정한 값 저장 (검사 후). raw 가 None 이면 화면 값을 지워 .env/기본값으로 되돌림"""
    if key not in SPEC:
        raise KeyError(key)
    conn = _owner_conn()
    try:
        cur = conn.cursor()
        if raw is None:
            cur.execute("DELETE FROM Sys_SystemSetting WHERE setting_key = ?", (key,))
            value = None
        else:
            value = _convert(key, raw)
            cur.execute("UPDATE Sys_SystemSetting SET setting_value = ?, updated_at = GETDATE() WHERE setting_key = ?", (str(value), key))
            if cur.rowcount == 0:
                cur.execute("INSERT INTO Sys_SystemSetting (setting_key, setting_value, description) VALUES (?, ?, ?)",
                            (key, str(value), f"[{SPEC[key][0]}] {SPEC[key][1]}"))
        conn.commit()
    finally:
        conn.close()
    _cache[key] = (None if value is None else str(value), time.time())
    print(f"[환경설정] {key} → {'(.env/기본값으로 되돌림)' if value is None else value}")
    return value


def _load_all():
    """화면 목록용: 설정 전체를 한 번에 읽어 보관 (항목마다 DB 연결하지 않도록)"""
    conn = None
    try:
        conn = _owner_conn()
        cur = conn.cursor()
        cur.execute("SELECT setting_key, setting_value FROM Sys_SystemSetting")
        stored = {k: v for k, v in cur.fetchall()}
        now = time.time()
        for key in SPEC:
            v = stored.get(key)
            _cache[key] = (v if v not in (None, "") else None, now)
    except Exception as e:
        print(f"[환경설정] 전체 조회 오류: {str(e)[:120]}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def describe():
    """화면용 목록: 묶음·이름·설명·현재 값·출처·.env 값·기본값·선택지/범위"""
    _load_all()
    out = []
    for key, (group, label, kind, default, desc, rule) in SPEC.items():
        source, value = source_and_value(key)
        env = os.getenv(key)
        out.append({
            "key": key, "group": group, "label": label, "kind": kind, "description": desc,
            "value": value, "source": source, "env_value": env if env not in (None, "") else None, "default": default,
            "choices": rule if kind == "choice" else None,
            "min": rule[0] if kind in ("int", "float") else None, "max": rule[1] if kind in ("int", "float") else None,
        })
    return out
