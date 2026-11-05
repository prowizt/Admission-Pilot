"""
[Claude 점검 표시 기록] 점검을 마친 로그에 reviewed_at / reviewed_by='claude' / review_note 를 기록하고,
같은 범위에 남은 미점검 로그 수를 출력 (0이 아니면 빠뜨린 것)
사용:
  python backend/tools/review_mark.py 542 "정상 · 문서 3건 적절, DB 대조 일치"
  python backend/tools/review_mark.py --file notes.txt          (한 줄에 '아이디<TAB>결과' 여러 건)
  python backend/tools/review_mark.py --file notes.txt --from 533 --to 543   (범위 남은 미점검 확인)
결과 한 줄은 '정상 · …' 또는 '문제 · …' 로 시작 (대시보드 배지 색: 정상 녹색, 문제 주황)
※ 관리자가 확인한 로그(reviewed_by='admin')도 항상 Claude 점검으로 덮어씀 (사용자 지시 2026-11-05)
"""
import argparse

from _db import connect, utf8_stdout


def cp949_safe(text: str) -> str:
    """DB 드라이버가 cp949 로 보내므로 표현 못 하는 글자(₩·이모지 등)를 바꾸거나 뺌"""
    text = text.replace("₩", "원 ").replace("→", "->").replace("↔", "<->")
    return text.encode("cp949", errors="ignore").decode("cp949")


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("log_id", nargs="?")
    ap.add_argument("note", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--from", dest="id_from", type=int)
    ap.add_argument("--to", dest="id_to", type=int)
    a = ap.parse_args()

    items = []
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#!"):
                    continue
                lid, _, note = line.partition("\t")
                items.append((int(lid.strip().lstrip("#")), note.strip()))
    if a.log_id:
        items.append((int(a.log_id.lstrip("#")), (a.note or "").strip()))
    if not items:
        print(__doc__)
        return

    conn = connect()
    cur = conn.cursor()
    done, skipped = [], []
    for lid, note in items:
        if not note.startswith(("정상", "문제")):
            print(f"⚠️ #{lid}: 결과는 '정상 · …' 또는 '문제 · …' 로 시작해야 함 → 건너뜀")
            skipped.append(lid)
            continue
        cur.execute("UPDATE Sys_AIAuditLog SET reviewed_at = GETDATE(), reviewed_by = 'claude', review_note = ? WHERE id = ?",
                    (cp949_safe(note)[:500], lid))
        (done if cur.rowcount else skipped).append(lid)
        if not cur.rowcount:
            print(f"⚠️ #{lid}: 없는 로그 → 건너뜀")
    conn.commit()
    print(f"기록 {len(done)}건: {', '.join('#' + str(i) for i in done) or '-'}")
    if skipped:
        print(f"건너뜀 {len(skipped)}건: {', '.join('#' + str(i) for i in skipped)}")

    lo = a.id_from or min(i for i, _ in items)
    hi = a.id_to or max(i for i, _ in items)
    cur.execute("SELECT id FROM Sys_AIAuditLog WHERE reviewed_at IS NULL AND user_role = 'staff' AND id BETWEEN ? AND ? ORDER BY id",
                (lo, hi))
    left = [r[0] for r in cur.fetchall()]
    print(f"범위 #{lo}~#{hi} 남은 미점검 교직원 로그: {len(left)}건" + (f" → {', '.join('#' + str(i) for i in left)}" if left else " ✅"))


if __name__ == "__main__":
    main()
