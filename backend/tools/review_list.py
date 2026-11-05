"""
[점검 대상 목록] 미점검(reviewed_at IS NULL) 로그를 요약해 보여 줌. 점검은 항상 이 스크립트에서 시작.
사용:
  python backend/tools/review_list.py                     최근 미점검 교직원 로그 30건 (테스트 포함)
  python backend/tools/review_list.py --from 533 --to 543 ID 범위
  python backend/tools/review_list.py --since 2026-11-05  날짜 이후
  python backend/tools/review_list.py --review            공문 검토(스크랩·첨부 있음)만
  python backend/tools/review_list.py --all-roles         학생 로그도 포함
  python backend/tools/review_list.py --include-done      점검한 로그도 포함 (표시와 함께)
  python backend/tools/review_list.py --detail            각 로그의 처리 과정 핵심 줄(문서 선발·SQL·지정 문서 등)까지
  python backend/tools/review_list.py --limit 50
"""
import argparse
import re

from _db import connect, utf8_stdout

KEY_LINES = re.compile(r"검색 키워드|\[Rule\]|\[Ref\]|지정 문서|문서·DB 값 겹침|공문 검토|MS-SQL:|공문 제목 보완|큰 문서|이름 보정|오류|LLM\]")


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="id_from", type=int)
    ap.add_argument("--to", dest="id_to", type=int)
    ap.add_argument("--since")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--all-roles", action="store_true")
    ap.add_argument("--include-done", action="store_true")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    a = ap.parse_args()

    where, params = [], []
    if not a.include_done:
        where.append("reviewed_at IS NULL")
    if not a.all_roles:
        where.append("user_role = 'staff'")
    if a.id_from:
        where.append("id >= ?"); params.append(a.id_from)
    if a.id_to:
        where.append("id <= ?"); params.append(a.id_to)
    if a.since:
        where.append("created_at >= ?"); params.append(a.since)
    if a.review:
        where.append("LEN(ISNULL(scraped_context, '')) > 0")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur = connect().cursor()
    cur.execute(f"SELECT COUNT(*) FROM Sys_AIAuditLog {where_sql}", params)
    total = cur.fetchone()[0]
    cur.execute(f"""
        SELECT TOP {int(a.limit)} id, CONVERT(VARCHAR(16), created_at, 120), user_role,
               LEFT(REPLACE(REPLACE(question, CHAR(13), ' '), CHAR(10), ' '), 60),
               CASE WHEN LEN(ISNULL(scraped_context, '')) > 0 THEN 1 ELSE 0 END,
               ISNULL(sql_query, ''), ISNULL(rag_documents, ''), estimated_cost, latency_ms,
               router_mode, reviewed_by, review_note, ISNULL(process_log, '')
        FROM Sys_AIAuditLog {where_sql} ORDER BY id DESC""", params)
    rows = cur.fetchall()
    print(f"대상 {total}건 (표시 {len(rows)}건){' · 점검 포함' if a.include_done else ' · 미점검만'}\n")
    for (lid, at, role, q, has_doc, sql, rag, cost, lat, rmode, rby, rnote, plog) in rows:
        n_docs = len([l for l in rag.splitlines() if re.match(r"\d+\)", l)])
        mark = f" [{'🤖' if rby == 'claude' else '👤'} {rnote or ''}]" if rby else ""
        print(f"#{lid} {at} {role}{' 📎' if has_doc else ''} ₩{float(cost or 0):.1f} {(lat or 0) / 1000:.0f}s "
              f"문서{n_docs} SQL{'○' if sql and sql != 'NONE' else '×'} 라우터[{rmode or '-'}]{mark}")
        print(f"     Q. {q}")
        if a.detail and plog:
            for line in plog.splitlines():
                if KEY_LINES.search(line):
                    print(f"     │ {line.strip()[:160]}")
        elif a.detail:
            print("     │ (처리 과정 기록 없음)")
    if total > len(rows):
        print(f"\n… {total - len(rows)}건 더 있음 (--limit 늘리거나 범위 지정)")


if __name__ == "__main__":
    main()
