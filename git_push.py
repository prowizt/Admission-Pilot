import subprocess
import sys
import os

def run_command(command):
    try:
        # 한글 깨짐 방지를 위해 인코딩 처리
        subprocess.run(command, check=True, text=True, shell=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 오류 발생: {e}")
        return False

def main():
    # 실행되는 CWD가 꼬이지 않도록 스크립트 파일이 존재하는 물리 폴더로 무조건 작업 디렉터리를 변경합니다.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("="*50)
    print("🚀 [Admission-Pilot] GitHub 자동 백업 스크립트 (독립 실행 모드)")
    print("="*50)

    # 1. 변경 사항 확인
    print("\n🔍 현재 상태 확인:")
    run_command("git status -s")

    # 2. 커밋 메시지 입력
    commit_message = input("\n📝 백업(커밋) 메시지를 입력하세요 (한글 가능): ").strip()
    
    if not commit_message:
        print("❌ 커밋 메시지가 입력되지 않았습니다. 중단합니다.")
        input("\n엔터키를 누르면 창이 닫힙니다...")
        return

    # 3. Git 작업 수행
    print("\n📦 작업을 시작합니다...")
    
    # git add .
    if not run_command("git add ."):
        input("\n엔터키를 누르면 창이 닫힙니다...")
        return

    # git commit -m "..."
    if not run_command(f'git commit -m "{commit_message}"'):
        input("\n엔터키를 누르면 창이 닫힙니다...")
        return

    # git push
    print("\n📤 원격 저장소로 업로드 중...")
    
    # [Upstream 에러 방지] 현재 브랜치명을 조회하여 origin으로 안전하게 업스트림 설정을 포함해 푸시합니다.
    try:
        # 현재 브랜치명 획득 (예: main)
        branch_res = subprocess.run(
            "git rev-parse --abbrev-ref HEAD", 
            capture_output=True, 
            text=True, 
            shell=True, 
            check=True
        )
        current_branch = branch_res.stdout.strip()
    except Exception:
        current_branch = "main" # 예외 발생 시 기본 브랜치명 적용

    if not run_command(f"git push -u origin {current_branch}"):
        print("\n⚠️ Push 실패! remote 설정을 확인하거나, 'git pull'을 먼저 해야 할 수도 있습니다.")
        input("\n엔터키를 누르면 창이 닫힙니다...")
        return

    print("\n✅ Admission-Pilot 코드가 성공적으로 백업되었습니다!")
    input("\n💡 엔터키를 누르면 백업 창이 닫힙니다...")

if __name__ == "__main__":
    main()