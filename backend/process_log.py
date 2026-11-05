"""
[처리 과정 기록] 요청 1건을 처리하는 동안 서버 콘솔에 출력된 줄을 따로 모아 감사 로그(Sys_AIAuditLog.process_log)에 저장합니다.
- 화면 출력은 그대로 두고 복사만 함 (sys.stdout 을 감싸는 방식)
- 요청별로 분리: contextvars 사용 → 다른 요청·뒤에서 도는 작업(값 사전 갱신 등)의 출력은 섞이지 않음
- 스트리밍 응답은 생성기가 조각마다 다른 문맥에서 실행되므로 bind_generator 로 같은 기록에 묶음
"""
import contextvars
import re
import sys

MAX_CHARS = 20000
_BUF = contextvars.ContextVar("process_log_buf", default=None)
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# 혹시 콘솔에 찍힌 비밀 값 가리기 (API 키 형태, 비밀번호 표기)
_SECRETS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "sk-ant-***"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "AIza***"),
    (re.compile(r"(?i)(pwd|password|api[_-]?key)\s*[=:]\s*[^\s;,'\"]+"), r"\1=***"),
]


class _TeeStdout:
    def __init__(self, base):
        self._base = base

    def write(self, s):
        buf = _BUF.get()
        if buf is not None and buf["size"] < MAX_CHARS * 3:
            buf["parts"].append(s)
            buf["size"] += len(s)
        return self._base.write(s)

    def flush(self):
        return self._base.flush()

    def __getattr__(self, name):
        return getattr(self._base, name)


def install():
    if not isinstance(sys.stdout, _TeeStdout):
        sys.stdout = _TeeStdout(sys.stdout)


def start():
    """요청 처리 시작 시 호출. 반환한 기록 묶음은 스트리밍 생성기에 넘길 때 씀"""
    buf = {"parts": [], "size": 0}
    _BUF.set(buf)
    return buf


def current():
    return _BUF.get()


def bind_generator(gen, buf):
    """스트리밍 생성기의 출력도 같은 기록에 모음"""
    while True:
        token = _BUF.set(buf)
        try:
            item = next(gen)
        except StopIteration:
            return
        finally:
            _BUF.reset(token)
        yield item


def text(buf=None) -> str:
    buf = buf if buf is not None else _BUF.get()
    if not buf:
        return ""
    s = _ANSI.sub("", "".join(buf["parts"]))
    for pat, rep in _SECRETS:
        s = pat.sub(rep, s)
    s = s.strip()
    if len(s) > MAX_CHARS:
        head, tail = int(MAX_CHARS * 0.7), int(MAX_CHARS * 0.3)
        s = s[:head] + f"\n\n... (중간 {len(s) - head - tail:,}자 생략) ...\n\n" + s[-tail:]
    return s


def save(log_id, buf=None, conn_factory=None, to_safe=None):
    """감사 로그 행에 처리 과정 기록 저장 (실패해도 요청 처리에는 영향 없음)"""
    if not log_id or conn_factory is None:
        return
    body = text(buf)
    if not body:
        return
    if to_safe:
        body = to_safe(body)
    conn = None
    try:
        conn = conn_factory()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("UPDATE Sys_AIAuditLog SET process_log = ? WHERE id = ?", (body, log_id))
        conn.commit()
    except Exception as e:
        sys.__stdout__.write(f"[처리 과정 기록] 저장 실패 (#{log_id}): {e}\n")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
