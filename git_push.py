import subprocess
import sys
import os

# Windows 환경에서 한글 및 이모지 입출력 cp949 에러 방지
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except Exception:
        pass

def run_command(command):
    try:
        # 한글 깨짐 방지를 위해 인코딩 처리
        subprocess.run(command, check=True, text=True, shell=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 오류 발생: {e}")
        return False

def main():
    print("="*50)
    print("🚀 [Admission-Pilot] GitHub 자동 백업 스크립트")
    print("="*50)

    # 1. 변경 사항 확인
    print("\n🔍 현재 상태 확인:")
    run_command("git status -s")

    # 2. 커밋 메시지 입력
    commit_message = input("\n📝 백업(커밋) 메시지를 입력하세요 (한글 가능): ").strip()
    
    if not commit_message:
        print("❌ 커밋 메시지가 입력되지 않았습니다. 중단합니다.")
        return False

    # 3. Git 작업 수행
    print("\n📦 작업을 시작합니다...")
    
    # git add .
    if not run_command("git add ."):
        return False

    # git commit -m "..."
    if not run_command(f'git commit -m "{commit_message}"'):
        return False

    # git push
    print("\n📤 원격 저장소로 업로드 중...")
    if not run_command("git push"):
        print("\n⚠️ Push 실패! remote 설정을 확인하거나, 'git pull'을 먼저 해야 할 수도 있습니다.")
        return False

    print("\n✅ Admission-Pilot 코드가 성공적으로 백업되었습니다!")
    return True

if __name__ == "__main__":
    # 명시적으로 --popup 옵션을 부여한 경우에만 외부 CMD 콘솔 팝업 실행
    if "--popup" in sys.argv:
        if sys.platform == "win32" and "--child" not in sys.argv:
            script_path = os.path.abspath(__file__)
            # 새 콘솔 창에서 본 스크립트 실행
            cmd = f'cmd.exe /c "python \"{script_path}\" --child --popup"'
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            sys.exit(0) # 기존 안티그래비티 터미널의 부모 프로세스는 즉시 종료
            
    main()
    
    # 외부 팝업창 모드(--child)로 기동된 경우 완료 로그를 확인하기 위해 대기
    if "--child" in sys.argv:
        input("\n💡 엔터키를 누르면 백업 창이 닫힙니다...")