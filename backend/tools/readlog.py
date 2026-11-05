"""
[로그 1건 전체 보기] 감사 로그(Sys_AIAuditLog) 1건의 모든 칸을 출력 (처리 과정 process_log 포함)
사용: python backend/tools/readlog.py 537            → 화면 출력
      python backend/tools/readlog.py 537 out.txt    → 파일로 저장
"""
import sys

from _db import connect, utf8_stdout


def main():
    utf8_stdout()
    if len(sys.argv) < 2:
        print(__doc__)
        return
    lid = int(sys.argv[1].lstrip("#"))
    cur = connect().cursor()
    cur.execute("SELECT * FROM Sys_AIAuditLog WHERE id = ?", lid)
    row = cur.fetchone()
    if not row:
        print(f"#{lid} 로그 없음")
        return
    cols = [c[0] for c in cur.description]
    text = "".join(f"===== {c} =====\n{v}\n" for c, v in zip(cols, row))
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(text)
        print(f"#{lid} → {sys.argv[2]}")
    else:
        print(text)


if __name__ == "__main__":
    main()
