"""
[서버 화면 보기] run_servers.py 가 남기는 logs/run_servers.log 를 따라 읽어 터미널에 실시간으로 보여 줌.
- VS Code 터미널용 (.vscode/tasks.json 이 폴더를 열 때 자동 실행). 서버는 Claude 가 별도 창으로 띄우고 끄고 켬.
- 이 프로그램은 서버를 켜거나 끄지 않고 **읽기만** 함. Ctrl+C 로 닫아도 서버는 계속 돎.
- 파일을 매번 잠깐 열었다 닫으며 읽음 → run_servers.py 가 재시작 때 로그 파일 이름을 바꾸는 것을 막지 않음.
- 서버가 다시 시작돼 로그 파일이 새로 생기면(크기가 줄거나 첫 줄이 달라짐) 새 기록을 처음부터 보여 줌.
"""
import os
import sys
import time

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "run_servers.log")
SHOW_LAST_LINES = 300  # 처음 켤 때 보여 줄 최근 줄 수
POLL_SEC = 0.5
COLORS = {"[BACKEND]": "\033[91m", "[FRONTEND]": "\033[92m", "[STUDENT]": "\033[96m"}
RESET = "\033[0m"


def colorize(line):
    for tag, color in COLORS.items():
        if line.startswith(tag):
            return color + tag + RESET + line[len(tag):]
    return line


def read_from(pos):
    with open(LOG, "rb") as f:
        head = f.read(200)
        f.seek(pos)
        data = f.read()
        return head, data, f.tell()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if sys.platform == "win32":
        os.system("")  # Windows 콘솔 색상(ANSI) 켜기

    print("=" * 60)
    print(" [서버 화면] logs/run_servers.log 를 실시간으로 보여 줍니다")
    print(" * 서버 켜기·끄기·재시작은 Claude 에게 말해 주세요. 이 창을 닫아도 서버는 계속 돕니다.")
    print("=" * 60)

    pos, head, buf, first, waiting = 0, None, b"", True, False
    while True:
        try:
            size = os.path.getsize(LOG)
            if head is not None and size < pos:
                raise ValueError("rotated")
            new_head, data, new_pos = read_from(pos)
            if head is not None and new_head[:len(head)] != head[:len(new_head)]:
                raise ValueError("rotated")
        except FileNotFoundError:
            if not waiting:
                print("[서버 화면] 아직 서버 기록이 없습니다. 서버가 시작되면 여기에 나옵니다...")
                waiting = True
            time.sleep(POLL_SEC)
            continue
        except ValueError:
            print("\n" + "=" * 20 + " 서버가 다시 시작됨 " + "=" * 20)
            pos, head, buf = 0, None, b""
            continue
        except OSError:
            time.sleep(POLL_SEC)  # 서버가 파일을 바꾸는 순간 — 다음에 다시 읽음
            continue

        waiting = False
        if head is None or len(head) < 200:
            head = new_head
        if data:
            pos = new_pos
            lines = (buf + data).split(b"\n")
            buf = lines.pop()
            if first:
                lines = lines[-SHOW_LAST_LINES:]
            for raw in lines:
                print(colorize(raw.decode("utf-8", errors="replace").rstrip("\r")))
            sys.stdout.flush()
        first = False
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[서버 화면] 보기를 닫았습니다. (서버는 계속 돌고 있습니다)")
