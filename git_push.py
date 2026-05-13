import subprocess

def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='cp949')
    if result.returncode != 0:
        print(f"❌ 오류 발생:\n{result.stderr}")
        return False
    print(result.stdout)
    return True

print("=== 🚀 Admission-Pilot GitHub 자동 백업 ===")
commit_msg = input("📝 백업(커밋) 메시지를 한글로 입력하세요: ")

if run_command("git add ."):
    if run_command(f'git commit -m "{commit_msg}"'):
        if run_command("git push"):
            print("✅ GitHub 백업이 성공적으로 완료되었습니다!")
