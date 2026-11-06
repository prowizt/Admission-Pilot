"""
[작업기록 알림] Claude Code 세션 시작(SessionStart) 때 실행.
이 프로젝트의 대화 기록(~/.claude/projects/<폴더 경로 이름>/*.jsonl)에서 작업한 날짜를 모으고,
오늘 이전 날짜 중 docs/작업기록_YYYY-MM-DD.md 가 없는 날을 찾아 Claude 에게 "먼저 작업기록을 써라"고 알려 줌.
(최근 14일만 확인. 출력은 hook JSON — 화면 안내(systemMessage) + Claude 에게 주는 지시(additionalContext))
"""
import datetime as dt
import glob
import json
import os
import re

# 프로젝트 폴더는 이 파일 위치(.claude/hooks)에서 계산 → 폴더를 옮겨도 고칠 필요 없음
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
# Claude 는 폴더 경로의 : \ / 를 - 로 바꾼 이름으로 대화 기록을 보관 (예: D:\Projects\Admission-Pilot → D--Projects-Admission-Pilot)
TRANSCRIPTS = os.path.join(PROJECTS_ROOT, re.sub(r"[:\\/]", "-", PROJECT))
# 예전 위치의 기록도 함께 봄 (끝 폴더 이름이 같은 것: D--Admission-Pilot 등)
TRANSCRIPT_DIRS = [TRANSCRIPTS] + [d for d in sorted(glob.glob(os.path.join(PROJECTS_ROOT, "*-" + os.path.basename(PROJECT)))) if os.path.normcase(d) != os.path.normcase(TRANSCRIPTS)]
DOCS = os.path.join(PROJECT, "docs")
LOOKBACK_DAYS = 14
TS = re.compile(rb'"timestamp":"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')


def work_dates():
    """대화 기록 파일별로 메시지가 있었던 날짜(로컬 시간) → 파일 목록"""
    since = dt.date.today() - dt.timedelta(days=LOOKBACK_DAYS)
    offset = dt.datetime.now().astimezone().utcoffset()
    dates = {}
    paths = {}
    for folder in TRANSCRIPT_DIRS:
        for path in glob.glob(os.path.join(folder, "*.jsonl")):
            paths.setdefault(os.path.basename(path), path)  # 복사본은 한 번만 (새 위치 우선)
    for path in paths.values():
        if dt.date.fromtimestamp(os.path.getmtime(path)) < since:
            continue
        seen = set()
        with open(path, "rb") as f:
            for line in f:
                m = TS.search(line)
                if not m:
                    continue
                local = dt.datetime.fromisoformat(m.group(1).decode()) + offset
                d = local.date()
                if d >= since and d not in seen:
                    seen.add(d)
                    dates.setdefault(d, []).append(path)
    return dates


def main():
    today = dt.date.today()
    missing = []
    for d, paths in sorted(work_dates().items()):
        if d >= today:
            continue
        if not os.path.exists(os.path.join(DOCS, f"작업기록_{d.isoformat()}.md")):
            missing.append((d, paths))
    if not missing:
        return
    days = ", ".join(d.isoformat() for d, _ in missing)
    lines = [
        f"[작업기록 알림] 작업기록이 없는 지난 작업일: {days}.",
        "사용자 요청을 처리하기 전에(또는 처리와 함께) 이 날짜들의 작업기록을 먼저 작성하십시오.",
        f"- 위치: {os.path.join(DOCS, '작업기록_YYYY-MM-DD.md')} (형식은 docs 폴더의 기존 작업기록을 따름)",
        "- 근거: 아래 대화 기록 파일에서 그날 날짜(timestamp)의 사용자 요청과 결과만 추려 정리 (파일이 크므로 grep 으로 그날 부분만 읽기)",
        "- 내용: 요청 → 원인/판단 → 바꾼 것(파일) → 결정 사항 → 남은 일 / DB 변경(DDL) / 점검한 로그 ID",
        "- 작성 후 사용자에게 '지난 작업기록을 남겼다'고 한 줄로 알리기",
    ]
    for d, paths in missing:
        lines.append(f"  · {d.isoformat()}: " + ", ".join(paths))
    out = {
        "systemMessage": f"작업기록이 없는 지난 작업일이 있습니다: {days} — Claude 가 먼저 정리합니다.",
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)},
    }
    print(json.dumps(out, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 알림이 실패해도 세션 시작은 막지 않음
        print(json.dumps({"systemMessage": f"[작업기록 알림] 확인 실패: {e}"}, ensure_ascii=True))
