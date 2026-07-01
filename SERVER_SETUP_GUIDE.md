# 229번 서버 초기 구축 및 배포 가이드 (Server Setup Guide)

본 문서는 텅 빈 Windows Server 2022 (IP: `210.93.0.229`, 도메인: `ipw.daedong.ac.kr`)에서 Admission-Pilot 서비스를 완벽하게 구동하기 위해 거쳐간 **모든 설치 및 세팅 과정**을 시행착오 없이 순서대로 따라 할 수 있도록 정리한 완성본 매뉴얼입니다.

---

## 1. 필수 프로그램 설치

### 1.1. Python 및 의존성
- **설치**: Python 3.11 이상 설치 (설치 시 반드시 `Add Python to PATH` 체크)
- **DB 드라이버**: 파이썬(`pyodbc`)에서 MS-SQL과 통신하기 위해 **Microsoft ODBC Driver 17 (또는 18) for SQL Server** 다운로드 및 설치.

### 1.2. Node.js 및 PM2
- **설치**: Node.js (LTS 버전) 설치
- **PM2 전역 설치**: 파이썬 백엔드를 24시간 백그라운드에서 구동하기 위해 터미널을 관리자 권한으로 열고 아래 명령어 실행.
  ```powershell
  npm install -g pm2
  ```

### 1.3. Git
- **설치**: Git for Windows 설치. 기본 설정으로 진행하되, 줄바꿈 설정(CRLF)은 기본값을 유지.

---

## 2. Nginx 웹 서버 세팅

학생용 챗봇(포트 80)과 교직원 대시보드(포트 8080)를 동시에 서비스하고, API 요청을 백엔드로 넘겨주기 위해 Nginx를 세팅합니다.

1. **다운로드**: Nginx for Windows 압축 파일을 다운로드 후 `C:\nginx` 에 압축 해제.
2. **설정 변경**: `C:\nginx\conf\nginx.conf` 파일을 열고 아래와 같이 수정합니다.
   ```nginx
   http {
       # ...기본 설정 생략...
       
       # [1] 학생용 챗봇 서버 (80번 포트)
       server {
           listen       80;
           server_name  ipw.daedong.ac.kr localhost;
           location / {
               root   "C:/actions-runner/_work/Admission-Pilot/Admission-Pilot/student-web/dist";
               index  index.html index.htm;
               try_files $uri $uri/ /index.html;
           }
           location /api/ {
               proxy_pass http://127.0.0.1:8000/;
           }
       }

       # [2] 교직원용 대시보드 (8080번 포트)
       server {
           listen       8080;
           server_name  ipw.daedong.ac.kr localhost;
           location / {
               root   "C:/actions-runner/_work/Admission-Pilot/Admission-Pilot/frontend/dist";
               index  index.html index.htm;
               try_files $uri $uri/ /index.html;
           }
           location /api/ {
               proxy_pass http://127.0.0.1:8000/;
           }
       }
   }
   ```
3. **실행**: `C:\nginx` 폴더에서 명령 프롬프트를 열고 `start nginx` 를 입력하여 백그라운드 실행.

---

## 3. 환경 변수 (보안 파일) 세팅

깃허브(GitHub) 공간은 퍼블릭일 수 있으며 코드가 외부로 노출될 위험이 있으므로, 중요 API Key는 서버 내 안전한 곳에 격리합니다.

- **경로**: `C:\actions-runner\.env` 파일 생성
- **내용**:
  ```env
  GEMINI_API_KEY="AI API 키 입력"
  STUDENT_API_KEY="학생용 챗봇 인증 키"
  STUDENT_MODEL="gemini-2.5-flash"
  # DB 접속 정보 및 기타 보안 정보
  ```
- **작동 원리**: 배포 로봇이 실행될 때 이 파일을 프로젝트 백엔드 폴더 내부로 덮어쓰기하여 서버에 주입합니다.

---

## 4. GitHub Actions (자동 배포 로봇) 세팅

서버에 코드를 수동으로 옮길 필요 없이, 개발 PC에서 `git push`만 하면 자동으로 서버에 반영되도록 깃허브 자체 러너(Runner)를 설치합니다.

1. **설치 경로**: `C:\actions-runner` 폴더 생성
2. **연결**: GitHub 레포지토리 `Settings` > `Actions` > `Runners` 메뉴에서 제공하는 Windows 다운로드 및 설정 스크립트를 PowerShell에 복사/붙여넣기하여 실행.
3. **서비스 등록**: 서버 재부팅 시에도 로봇이 항상 돌아가게 하기 위해 러너를 서비스로 등록합니다.
   - `C:\actions-runner` 폴더에서 `.\svc.sh install` 및 `.\svc.sh start` 실행.

---

## 5. 자동화 배포 스크립트 작성 (`deploy.yml`)

프로젝트 코드 최상단 `.github/workflows/deploy.yml` 을 만들어 다음 파이프라인을 구축했습니다.
1. **기존 서버 끄기**: PM2와 잠겨있는 Python 프로세스를 강제 종료하여 삭제 권한 확보(`EBUSY` 에러 방지).
2. **소스코드 다운로드**: 깃허브의 최신 버전을 내려받음.
3. **동적 패치**: 크롬 확장프로그램의 API 주소를 로컬호스트에서 `ipw.daedong.ac.kr` 도메인으로 치환.
4. **Python 환경 구축**: `venv` 생성 후 `requirements.txt` 설치.
5. **.env 주입**: 앞서 만든 `C:\actions-runner\.env` 파일을 백엔드로 복사.
6. **프론트엔드 빌드**: 학생용(`student-web`) 및 교직원용(`frontend`) React 앱을 `npm run build`로 컴파일하여 Nginx가 읽을 수 있게 함.
7. **서버 시작**: PM2를 사용해 `main.py`를 무중단 데몬으로 실행.

---

## 6. 방화벽 및 마무리

1. **방화벽 개방**: Windows Defender 방화벽 > 고급 설정 > 인바운드 규칙에서 **포트 80** 및 **8080** 을 외부에서 접근할 수 있도록 허용.
2. **배포 테스트**: 개발 PC에서 코드를 수정하고 `git add .`, `git commit`, `git push`를 실행한 후, 서버에서 제대로 배포가 완료되는지 확인.
3. **결과 확인**:
   - 학생용: `http://ipw.daedong.ac.kr` 접속 성공 확인
   - 교직원용: `http://ipw.daedong.ac.kr:8080` 접속 성공 확인

위 과정이 모두 정상적으로 끝났다면, 이후의 모든 유지보수는 서버(229)에 원격 접속할 필요 없이 개발 PC에서 코드 수정 후 푸시(Push)하는 것만으로 100% 자동 적용됩니다.
