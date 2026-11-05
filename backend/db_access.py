"""
[DB 조회 권한 분리] 챗봇·엑셀 채우기에서 AI 가 만든 SQL 을 실행할 때 쓰는 연결과 사전 검사.

- 학생 쿼리: DB_STUDENT_USER 계정 (학생 공개 테이블의 공개 열만 SELECT 권한) + 공개 테이블만 허용
- 교직원 쿼리: DB_RO_USER 계정 (읽기 전용). 다른 DB 를 참조하는 뷰처럼 읽기 계정에 권한이 없는
  경우(오류 916)에만, 사전 검사를 통과한 쿼리를 기존 계정으로 다시 실행
- 공통: 한 문장의 SELECT/WITH 만 허용 (여러 문장, INSERT·UPDATE·DELETE·EXEC 등 금지)
- 학생 계정의 SELECT 권한은 sync_student_grants() 가 카탈로그(공개 열)에 맞춰 자동으로 GRANT/REVOKE
"""
import os
import re

import pyodbc


class QueryBlocked(Exception):
    """사전 검사에서 실행을 막은 쿼리 (실행하지 않음)"""


_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|EXECUTE|CREATE|TRUNCATE|MERGE|GRANT|REVOKE|DENY|BACKUP|RESTORE|"
    r"SHUTDOWN|DBCC|OPENROWSET|OPENQUERY|OPENDATASOURCE|INTO|WAITFOR|RECONFIGURE|xp_\w+|sp_\w+)\b", re.I)


def _strip_literals(sql):
    """문자열 값·주석을 지움 (값 안의 단어가 금지어로 잡히지 않도록). 대괄호 식별자는 남김"""
    s = re.sub(r"N?'(?:[^']|'')*'", "''", sql)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    return re.sub(r"--[^\n]*", " ", s)


def referenced_tables(sql):
    """FROM / JOIN 뒤의 테이블 이름 (WITH 로 만든 임시 이름은 제외)"""
    s = _strip_literals(sql)
    ctes = {m.lower() for m in re.findall(r"(?:\bWITH|,)\s*\[?([^\s\[\],()]+)\]?\s+AS\s*\(", s, re.I)}
    names = []
    for raw in re.findall(r"\b(?:FROM|JOIN)\s+(\[[^\]]+\](?:\.\[[^\]]+\])*|[\w.]+)", s, re.I):
        parts = [a or b for a, b in re.findall(r"\[([^\]]+)\]|([^.\[\]]+)", raw)]
        name = parts[-1] if parts else raw  # [dbo].[표] · dbo.표 · [표] → 표
        if name.lower() not in ctes and name not in names:
            names.append(name)
    return names


def check_sql(sql, allowed_tables=None):
    """실행하면 안 되는 쿼리면 이유(문구), 괜찮으면 빈 문자열. allowed_tables 를 주면 그 테이블만 허용 (학생)"""
    s = _strip_literals(sql or "").strip().rstrip(";").strip()
    s_noident = re.sub(r"\[[^\]]*\]", "[]", s)  # 열 이름 안의 글자(예: [UPDATE일자])는 검사하지 않음
    # 여러 결과를 한 번에 받는 'SELECT …; SELECT …' 는 허용하되, 모든 문장이 조회여야 함
    for stmt in (x.strip() for x in s_noident.split(";")):
        if stmt and not re.match(r"(SELECT|WITH)\b", stmt, re.I):
            return "조회(SELECT/WITH)가 아닌 문장이 들어 있어 실행하지 않습니다."
    if not s_noident:
        return "빈 쿼리입니다."
    m = _FORBIDDEN.search(s_noident)
    if m:
        return f"조회 외 명령({m.group(1).upper()})이 들어 있어 실행하지 않습니다."
    if allowed_tables is not None:
        allowed = {t.lower() for t in allowed_tables}
        bad = [t for t in referenced_tables(sql) if t.lower() not in allowed]
        if bad:
            return f"공개되지 않았거나 없는 테이블: {', '.join(bad)}"
    return ""


def student_public_columns(owner_conn):
    """학생 공개 테이블 → 공개 열 목록 (활성 테이블 · is_public='Y' 열, 실제로 있는 열만)"""
    cur = owner_conn.cursor()
    cur.execute("""
        SELECT c.table_name, c.column_name FROM Sys_ColumnCatalog c
        JOIN Sys_TableCatalog t ON t.table_name = c.table_name
        WHERE t.is_active = 'Y' AND c.is_public = 'Y'
          AND COL_LENGTH(c.table_name, c.column_name) IS NOT NULL
        ORDER BY c.table_name, c.id""")
    out = {}
    for t, c in cur.fetchall():
        out.setdefault(t, []).append(c)
    return out


def expand_star_for_student(sql, public_cols):
    """학생 계정은 공개 열에만 권한이 있으므로 'SELECT [TOP n] * FROM [표]' 의 * 를 공개 열 목록으로 바꿈"""
    m = re.match(r"\s*SELECT\s+(TOP\s+\(?\d+\)?\s+)?\*\s+FROM\s+(\[[^\]]+\]|\w+)", sql, re.I)
    if not m:
        return sql
    cols = public_cols.get(m.group(2).strip("[]"))
    if not cols:
        return sql
    star = m.start() + m.group(0).index("*", len("SELECT"))
    return sql[:star] + ", ".join(f"[{c}]" for c in cols) + sql[star + 1:]


def _connect(user, pwd):
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if not drivers:
        return None
    driver = next((p for p in ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server",
                               "SQL Server Native Client 11.0", "SQL Server"] if p in drivers), drivers[0])
    conn = pyodbc.connect(
        f"DRIVER={{{driver}}};SERVER={os.getenv('DB_SERVER', '10.10.1.11,1433')};"
        f"DATABASE={os.getenv('DB_NAME', 'DDU_ADMISSION')};UID={user};PWD={pwd};TrustServerCertificate=yes;",
        autocommit=True)
    conn.setdecoding(pyodbc.SQL_CHAR, encoding='cp949')
    conn.setdecoding(pyodbc.SQL_WCHAR, encoding='cp949')
    conn.setencoding(encoding='cp949')
    return conn


def role_connection(role):
    """역할별 조회 계정 연결. 계정 설정이 없거나 연결에 실패하면 None"""
    prefix = "DB_STUDENT" if role == "student" else "DB_RO"
    user, pwd = os.getenv(prefix + "_USER"), os.getenv(prefix + "_PWD")
    if not (user and pwd):
        return None
    try:
        return _connect(user, pwd)
    except Exception as e:
        print(f"[DB 권한] {prefix} 계정 연결 실패: {str(e)[:150]}")
        return None


class QueryRunner:
    """AI 쿼리 실행기. execute() 는 결과를 읽을 cursor 를 돌려주며, 연결은 close() 때까지 유지"""

    def __init__(self, owner_conn, role):
        self.owner_conn = owner_conn
        self.role = role
        self.conn = None
        self.used = ""  # 실제로 실행한 계정 (로그용)

    def execute(self, sql):
        if self.role == "student":
            # 엑셀 업로드·뷰 동기화 등 어느 화면에서 공개 열이 바뀌었든 실행 직전에 권한을 맞춤 (차이가 있을 때만 GRANT/REVOKE)
            sync_student_grants(self.owner_conn)
            public_cols = student_public_columns(self.owner_conn)
            reason = check_sql(sql, allowed_tables=list(public_cols))
            if reason:
                raise QueryBlocked(reason)
            self.conn = self.conn or role_connection("student")
            if not self.conn:
                # 학생 계정이 없으면 실행하지 않음 (기존 계정은 모든 권한이 있어 학생 쿼리에 쓰지 않음)
                raise QueryBlocked("학생 조회 계정(DB_STUDENT_USER)이 설정되지 않아 실행하지 않습니다.")
            sql = expand_star_for_student(sql, public_cols)
            cur = self.conn.cursor()
            cur.execute(sql)
            self.used = "학생 계정"
            return cur
        reason = check_sql(sql)
        if reason:
            raise QueryBlocked(reason)
        self.conn = self.conn or role_connection("staff")
        if self.conn:
            try:
                cur = self.conn.cursor()
                cur.execute(sql)
                self.used = "읽기 계정"
                return cur
            except pyodbc.Error as e:
                if "(916)" not in str(e):  # 916: 다른 DB 를 참조하는 뷰에 읽기 계정 권한 없음
                    raise
                print("[DB 권한] 읽기 계정이 다른 DB 참조 뷰에 접근할 수 없어(916) 기존 계정으로 실행 (사전 검사 통과한 조회만)")
        cur = self.owner_conn.cursor()
        cur.execute(sql)
        self.used = "기존 계정"
        return cur

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None


def sync_student_grants(owner_conn):
    """학생 계정의 SELECT 권한을 카탈로그의 공개 열과 똑같이 맞춤 (공개 전환 → GRANT, 비공개 → REVOKE)"""
    user = os.getenv("DB_STUDENT_USER")
    if not user or not owner_conn:
        return
    try:
        cur = owner_conn.cursor()
        cur.execute("SELECT USER_ID(?)", (user,))
        if cur.fetchone()[0] is None:
            print(f"[DB 권한] DB 사용자 '{user}' 가 없어 권한 동기화를 건너뜀")
            return
        desired = {t: set(cols) for t, cols in student_public_columns(owner_conn).items()}
        cur.execute("""
            SELECT OBJECT_NAME(major_id), COL_NAME(major_id, minor_id), minor_id
            FROM sys.database_permissions
            WHERE grantee_principal_id = USER_ID(?) AND class = 1 AND permission_name = 'SELECT' AND state = 'G'""", (user,))
        current = {}
        for t, c, minor in cur.fetchall():
            current.setdefault(t, set()).add(c if minor else "*")
        q = lambda n: "[" + n.replace("]", "]]") + "]"
        changed = []
        for t in set(current) | set(desired):
            if current.get(t) == desired.get(t):
                continue
            try:  # 테이블 하나가 실패해도 나머지는 계속 맞춤
                if t in current:
                    cur.execute(f"REVOKE SELECT ON dbo.{q(t)} FROM {q(user)}")
                if desired.get(t):
                    cols = ", ".join(q(c) for c in sorted(desired[t]))
                    cur.execute(f"GRANT SELECT ON dbo.{q(t)} ({cols}) TO {q(user)}")
                changed.append(f"{t}: {len(desired.get(t, ()))}개 열")
            except Exception as e:
                print(f"[DB 권한] {t} 권한 조정 오류: {str(e)[-150:]}")
        owner_conn.commit()
        if changed:
            print(f"[DB 권한] 학생 계정 SELECT 권한 동기화: {changed}")
    except Exception as e:
        print(f"[DB 권한] 학생 계정 권한 동기화 오류: {e}")
