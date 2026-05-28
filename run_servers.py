import os
import sys
import subprocess
import threading
import time

# Windows 환경에서 ANSI 이스케이프 코드 활성화 (색상 정상 출력 처리)
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # stdout(-11)과 stderr(-12) 스트림 둘 다 가상 터미널 프로세싱(0x0004)을 켭니다.
        for handle_id in [-11, -12]:
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception as e:
        print(f"[경고] Windows 가상 터미널 프로세싱 활성화 실패: {e}")

def watch_keyboard_input(root_dir):
    print("\n💡 [백업 안내] 서버가 실행 중인 터미널에서 'b' 또는 'ㅠ'를 입력하고 [엔터]를 누르면, 개발 서버 종료 없이 외부 새 창에서 깃 백업(git_push.py)을 실행합니다!\n")
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            command = line.strip().lower()
            if command in ('b', 'ㅠ'):
                print("\n[시스템] 깃 백업 요청 감지! 외부 새 창으로 백업 스크립트를 기동합니다...")
                script_path = os.path.join(root_dir, "git_push.py")
                if sys.platform == "win32":
                    cmd = f'cmd.exe /c "python \"{script_path}\""'
                    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen(["python", script_path])
        except Exception as e:
            print(f"[오류] 입력 감지 에러: {e}")
            break

def read_output(pipe, prefix):
    try:
        for line in iter(pipe.readline, b''):
            # 엄격한 utf-8 디코딩 시도 (에러 없이 replace 방지하여 cp949 분기 활성화)
            try:
                decoded_line = line.decode('utf-8').rstrip()
            except UnicodeDecodeError:
                decoded_line = line.decode('cp949', errors='replace').rstrip()
            except Exception:
                decoded_line = line.decode('utf-8', errors='replace').rstrip()
                
            print(f"{prefix} {decoded_line}")
            sys.stdout.flush()
    except Exception as e:
        print(f"{prefix} [오류] 로그 수신 에러: {e}")
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def start_servers():
    print("==================================================")
    print("🚀 [Admission-Pilot] 통합 서버 기동 스크립트 (통합 로그 모드)")
    print("   * 종료하려면 현재 터미널에서 Ctrl + C를 누르세요.")
    print("==================================================")
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")
    
    # 파이썬 실시간 출력 보장 환경변수 주입
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # 1. 백엔드 FastAPI 서버 실행
    print("[시스템] 백엔드 FastAPI 서버 준비 중...")
    backend_proc = subprocess.Popen(
        ["python", "main.py"],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env
    )
    
    # 2. 프론트엔드 Vite 서버 실행 (Windows 배치파일 기동을 위해 shell=True 사용)
    print("[시스템] 프론트엔드 Vite React 서버 준비 중...")
    frontend_proc = subprocess.Popen(
        "npm run dev",
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True
    )
    
    # 3. 실시간 리딩 스레드 구동 (ANSI 컬러 접두사 부여 - 밝은 빨강 / 밝은 초록)
    t_backend = threading.Thread(
        target=read_output, 
        args=(backend_proc.stdout, "\033[91m[BACKEND]\033[0m"), 
        daemon=True
    )
    t_frontend = threading.Thread(
        target=read_output, 
        args=(frontend_proc.stdout, "\033[92m[FRONTEND]\033[0m"), 
        daemon=True
    )
    t_input = threading.Thread(
        target=watch_keyboard_input,
        args=(root_dir,),
        daemon=True
    )
    
    t_backend.start()
    t_frontend.start()
    t_input.start()
    
    try:
        # 두 서브프로세스가 동작하는지 주기적으로 핑 점검
        while True:
            time.sleep(1)
            
            if backend_proc.poll() is not None:
                print(f"[경고] 백엔드 프로세스가 비정상 종료되었습니다 (코드: {backend_proc.poll()})")
                break
            if frontend_proc.poll() is not None:
                print(f"[경고] 프론트엔드 프로세스가 비정상 종료되었습니다 (코드: {frontend_proc.poll()})")
                break
    except KeyboardInterrupt:
        print("\n[시스템] 종료 신호(Ctrl+C)가 감지되어 모든 서버를 안전하게 중단합니다...")
    finally:
        # 프로세스 자원 청소 및 포트 점유 해제
        print("[시스템] 자식 프로세스들을 종료시키는 중...")
        
        # 1차 부드러운 종료 시도
        try:
            backend_proc.terminate()
        except Exception:
            pass
        try:
            frontend_proc.terminate()
        except Exception:
            pass
            
        # 2초 대기 후 아직 살아있다면 강제 중단(Kill)
        try:
            backend_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                backend_proc.kill()
            except Exception:
                pass
        except Exception:
            pass
            
        try:
            frontend_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                frontend_proc.kill()
            except Exception:
                pass
        except Exception:
            pass
            
        print("==================================================")
        print("✅ 모든 개발 서버가 성공적으로 중단되었습니다.")
        print("==================================================")

if __name__ == "__main__":
    start_servers()
