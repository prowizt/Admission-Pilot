# 229번 서버 초기 구축 및 배포 가이드 (Server Setup Guide)

본 문서는 텅 빈 Windows Server 2022 (IP: `210.93.0.229`, 도메인: `ipw.daedong.ac.kr`)에서 Admission-Pilot 서비스를 완벽하게 구동하기 위해 거쳐간 **모든 설치 및 세팅 과정**을 시행착오 없이 순서대로 따라 할 수 있도록 정리한 완성본 매뉴얼입니다.

> **마지막 점검: 2026-11-05** (Claude Code 와 코드 대조). 시스템 구조는 `SYSTEM_ARCHITECTURE.md`, 작업 규칙은 `CLAUDE.md` 참고.

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

## 2. Nginx 웹 서버 세팅 (HTTPS / SSL 인증서 포함)

학생용 챗봇(포트 443)과 교직원 대시보드(포트 8443)를 안전한 HTTPS 통신으로 서비스하기 위해 Nginx 및 와일드카드 인증서를 세팅합니다.

1. **설치 경로**: Nginx for Windows 압축 파일을 다운로드 후 `C:\tools\nginx-1.31.2` 에 압축 해제.
2. **SSL 인증서 수동 복사 (중요!)**:
   - `C:\tools\nginx-1.31.2\conf\ssl` 폴더를 생성합니다.
   - 보안상 깃허브에 올릴 수 없는 대동대학교 와일드카드 인증서 파일 2개(`fullchain.crt`, `private.key`)를 USB나 원격 접속을 통해 이 폴더에 직접 복사해 둡니다.
3. **설정 변경**: `C:\tools\nginx-1.31.2\conf\nginx.conf` 파일이 깃허브의 배포 스크립트를 통해 자동으로 덮어써지며 다음 규칙으로 동작합니다:
   - **80번 포트**: 443(HTTPS)으로 강제 리다이렉트
   - **443번 포트 (HTTPS)**: 학생용 챗봇 서빙 및 백엔드 프록시
   - **8443번 포트 (HTTPS)**: 교직원용 대시보드 서빙 및 백엔드 프록시
4. **실행**: 터미널을 열고 `C:\tools\nginx-1.31.2` 경로에서 `start nginx` 를 입력하여 백그라운드 실행.

---

## 3. 환경 변수 (보안 파일) 세팅

깃허브(GitHub) 공간은 퍼블릭일 수 있으며 코드가 외부로 노출될 위험이 있으므로, 중요 API Key는 서버 내 안전한 곳에 격리합니다.

- **경로**: `C:\actions-runner\.env` 파일 생성
- **내용** (값은 실제 키·비밀번호로 채움 — 이 문서나 채팅에는 절대 적지 말 것):
  ```env
  # AI 키
  ANTHROPIC_API_KEY=        # Claude (학생 챗봇 Haiku, 확장에 키를 넣지 않은 교직원 Claude 호출)
  STUDENT_API_KEY=          # Gemini (학생 챗봇 모델을 Gemini 로 쓸 때)

  # DB 접속 (서버·DB 이름은 기본값이 있어 보통 생략 가능)
  DB_SERVER=10.10.1.11,1433
  DB_NAME=DDU_ADMISSION
  DB_USER=admission_ai              # 대시보드·카탈로그·로그 기록 (DB 오너)
  DB_PWD=
  DB_RO_USER=admission_ai_ro        # 교직원 챗봇 조회 (읽기 전용)
  DB_RO_PWD=
  DB_STUDENT_USER=admission_ai_student   # 학생 챗봇 조회 (공개 테이블·열만)
  DB_STUDENT_PWD=
  ```
- **항목별로 없을 때**:
  | 항목 | 없으면 |
  |---|---|
  | `ANTHROPIC_API_KEY` | 학생 챗봇(Claude 모델)과 키 없는 교직원 Claude 호출이 응답하지 못함 |
  | `DB_RO_*` | 교직원 조회가 오너 계정으로 실행됨 (보안 약화) |
  | `DB_STUDENT_*` | 학생 DB 조회를 실행하지 않고 문서로만 답함 |
  | `DB_PWD` | 백엔드가 DB 에 연결하지 못함 (비밀번호를 바꾸면 이 파일도 같이 바꿀 것) |
- **예전 항목**: `GEMINI_API_KEY`, `STUDENT_MODEL` 은 지금 코드에서 쓰지 않음. 학생 모델·추론 강도·비용 한도 같은 운영 값은 대시보드 **환경 설정**에서 바꿈 (`.env` 에 같은 이름으로 적어도 화면 값이 우선).
- **작동 원리**: 배포 로봇이 실행될 때 이 파일을 프로젝트 백엔드 폴더 내부로 덮어쓰기하여 서버에 주입합니다. 개발 PC 의 `backend\.env` 에 항목을 추가했다면 이 파일에도 같이 추가해야 합니다.

---

## 4. GitHub Actions (자동 배포 로봇) 세팅

서버에 코드를 수동으로 옮길 필요 없이, 개발 PC에서 `git push`만 하면 자동으로 서버에 반영되도록 깃허브 자체 러너(Runner)를 설치합니다.

1. **설치 경로**: `C:\actions-runner` 폴더 생성
2. **연결**: GitHub 레포지토리 `Settings` > `Actions` > `Runners` 메뉴에서 제공하는 Windows 다운로드 및 설정 스크립트를 PowerShell에 복사/붙여넣기하여 실행.
3. **서비스 등록**: 서버 재부팅 시에도 로봇이 항상 돌아가게 하기 위해 러너를 서비스로 등록합니다.
   - ⚠️ 예전 문서에는 `.\svc.sh install` / `.\svc.sh start` 로 적혀 있었으나, `svc.sh` 는 리눅스·맥용 명령입니다. **229 서버에서 실제로 어떻게 등록했는지는 확인되지 않음** (2026-11-05 점검).
   - Windows 러너는 보통 설정 단계(`.\config.cmd`)에서 "서비스로 실행할지" 질문에 `Y` 로 답해 등록합니다 (`.\config.cmd --runasservice` 도 같은 뜻).
   - 확인 방법: 서버에서 `Get-Service actions.runner.*` 를 실행해 `Running` 이면 서비스로 등록된 상태입니다. 확인되면 이 항목을 실제 방법으로 고쳐 주세요.

---

## 5. 자동화 배포 스크립트 작성 (`deploy.yml`)

프로젝트 코드 최상단 `.github/workflows/deploy.yml` 을 만들어 다음 파이프라인을 구축했습니다.
1. **기존 서버 끄기**: PM2와 잠겨있는 Python 프로세스를 강제 종료하여 삭제 권한 확보(`EBUSY` 에러 방지).
2. **소스코드 다운로드**: 깃허브의 최신 버전을 내려받음.
3. **Python 환경 구축**: `venv` 생성 후 `requirements.txt` 설치.
4. **.env 주입**: 앞서 만든 `C:\actions-runner\.env` 파일을 백엔드로 복사.
5. **프론트엔드 빌드**: 학생용(`student-web`) 및 교직원용(`frontend`) 앱 빌드.
6. **Nginx 설정 업데이트**: 저장소의 `nginx/nginx.conf`를 `C:\tools\nginx-1.31.2\conf\nginx.conf`로 덮어쓰고 `nginx -s reload` 실행.
7. **서버 시작**: PM2를 사용해 `main.py`를 무중단 데몬으로 실행.

---

## 6. 방화벽 및 마무리

1. **방화벽 개방**: Windows Defender 방화벽 > 고급 설정 > 인바운드 규칙에서 **포트 443** (학생용 HTTPS) 및 **8443** (교직원용 HTTPS) 을 외부에서 접근할 수 있도록 허용.
   - (PowerShell 관리자 권한 명령어: `New-NetFirewallRule -DisplayName "Nginx HTTPS (443, 8443)" -Direction Inbound -LocalPort 443,8443 -Protocol TCP -Action Allow`)
2. **배포 테스트**: 개발 PC에서 코드를 수정하고 `git add .`, `git commit`, `git push`를 실행한 후, 서버에서 제대로 배포가 완료되는지 확인.
3. **결과 확인**:
   - 학생용: `https://ipw.daedong.ac.kr` 접속 성공 및 자물쇠 마크 확인
   - 교직원용: `https://ipw.daedong.ac.kr:8443` 접속 성공 및 자물쇠 마크 확인

---

## 7. 교직원용 크롬 확장프로그램 배포 및 설치 방법

자동 배포 스크립트 없이도 확장프로그램은 하이브리드로 작동합니다. 개발자 PC의 `extension` 폴더를 그대로 압축해서 배포하면 됩니다.

1. 개발 PC의 `extension` 폴더를 압축(`.zip`)하여 교직원들에게 배포합니다.
2. 교직원들은 압축을 풀고 크롬 브라우저를 열어 주소창에 `chrome://extensions/` 를 입력합니다.
3. 우측 상단의 **개발자 모드(Developer mode)** 스위치를 켭니다.
4. 좌측 상단의 **압축해제된 확장 프로그램을 로드합니다(Load unpacked)** 버튼을 클릭합니다.
5. 배포받은 `extension` 폴더를 선택하여 업로드하면 설치가 완료됩니다.
6. 크롬 주소창 옆의 퍼즐(🧩) 아이콘을 눌러 "대동대 AI 도우미"를 고정(Pin)하고 누르면, 브라우저 우측에 챗봇 사이드 패널이 즉시 나타납니다.

### 💡 [중요] 개발자 모드 체크박스 (하이브리드 환경 감지)
- 확장프로그램 하단의 ⚙️(설정)을 누르면 **`[ ] 개발자 모드 (로컬 127.0.0.1 백엔드 사용)`** 체크박스가 있습니다.
- **일반 교직원 (체크 해제됨)**: 기본적으로 229번 운영 서버(`https://ipw.daedong.ac.kr:8443`)를 바라보고 통신합니다.
- **개발자 (체크 켬)**: 개발 PC의 로컬 백엔드(`127.0.0.1:8000`)를 강제로 바라보게 하여 테스트망과 운영망을 분리합니다.

### 💡 확장프로그램 업데이트 방법 (기능 추가 시)
만약 나중에 코드가 수정되어 확장프로그램 기능이 업데이트된 경우, 기존에 설치했던 교직원들은 다음 방법으로 새로고침만 하면 됩니다.
1. 새로 배포된 `extension` 폴더 안의 파일들을 기존 폴더에 **덮어쓰기** 합니다.
2. 크롬 브라우저 `chrome://extensions/` 에 접속합니다.
3. 설치되어 있는 "Admission-Pilot 확장프로그램" 항목에 있는 **새로고침(원형 화살표 ↻)** 버튼을 클릭합니다. (삭제하고 다시 깔 필요가 없습니다.)

---

## 8. Nginx 엔진 (소프트웨어) 수동 업그레이드 방법

보안 취약점 패치 등 Nginx 프로그램 자체의 버전업이 필요할 경우, 229번 서버에 원격 접속하여 다음 순서대로 수동 업그레이드를 진행합니다. (자동화 불가 영역)

1. **다운로드**:
   - 서버 인터넷 브라우저에서 공식 홈페이지(https://nginx.org/en/download.html)에 접속합니다.
   - 화면 중간의 `Stable version` (안정화 버전) 목록에서 **`nginx/Windows-x.x.x`** 링크를 클릭하여 zip 파일을 다운로드합니다.
2. **기존 Nginx 완전 종료**:
   ```cmd
   cd C:\tools\nginx-1.31.2
   nginx -s stop
   ```
3. **새 버전 압축 풀기**: 받은 zip 을 `C:\tools\` 아래에 풉니다 (예: `C:\tools\nginx-1.32.0`).
4. **설정·인증서 옮기기**: 기존 폴더의 아래 두 가지를 새 폴더의 같은 위치로 복사합니다.
   - `conf\nginx.conf`
   - `conf\ssl\` 폴더 전체 (`fullchain.crt`, `private.key`)
5. **경로 처리 (둘 중 하나)**: 배포 스크립트(`.github/workflows/deploy.yml`)와 이 문서가 `C:\tools\nginx-1.31.2` 경로를 씁니다.
   - **간단한 방법**: 기존 폴더 이름을 `nginx-1.31.2_old` 로 바꾸고, 새 폴더 이름을 `nginx-1.31.2` 로 바꿉니다. (스크립트 수정 불필요)
   - 또는 새 폴더 이름을 그대로 쓰려면 `deploy.yml` 의 `$nginxDir` 경로를 고치고 커밋·배포합니다.
6. **새 Nginx 시작**:
   ```cmd
   cd C:\tools\nginx-1.31.2
   nginx -t
   start nginx
   ```
   (`nginx -t` 는 설정 문법 검사 — `successful` 이 나와야 함)
7. **성공 확인**:
   - 브라우저를 열고 `https://ipw.daedong.ac.kr` 에 정상적으로 접속되는지 확인한 뒤, 문제없이 챗봇이 열리면 구버전 폴더는 삭제하셔도 됩니다.

위 과정을 통해 Nginx 코어 엔진 업그레이드가 완료되며, 기존의 모든 라우팅 설정은 그대로 유지됩니다.

---

## 부록 A. DB 계정 만들기 (읽기 전용·학생용)

2026-11-04 에 만든 계정입니다. 새 서버나 새 DB 로 옮길 때 다시 만들 때 씁니다.

- **SSMS 에서 sa 같은 서버 관리자 계정으로 실행**합니다. (`admission_ai` 는 DB 안에서만 오너라 로그인을 만들 수 없음)
- 비밀번호 칸은 실제 강한 비밀번호로 바꿉니다. 서버 비밀번호 정책 때문에 **14자 이상, 대문자·소문자·숫자·특수문자 중 3가지 이상, 계정 이름(admission 등) 미포함**이어야 합니다 (오류 15118 이 나면 이 조건 확인).
- 만든 뒤 비밀번호는 개발 PC `backend\.env` 와 서버 `C:\actions-runner\.env` 에만 넣습니다.

```sql
-- ① 서버 로그인 생성 (sa 등 서버 관리자로 실행)
USE master;
GO
CREATE LOGIN admission_ai_ro      WITH PASSWORD = N'여기에_강한비밀번호1', CHECK_POLICY = ON, DEFAULT_DATABASE = DDU_ADMISSION;
CREATE LOGIN admission_ai_student WITH PASSWORD = N'여기에_강한비밀번호2', CHECK_POLICY = ON, DEFAULT_DATABASE = DDU_ADMISSION;
GO

-- ② DB 사용자 연결과 권한
USE DDU_ADMISSION;
GO
-- 교직원 조회용: 전체 읽기만, 쓰기·실행은 명시적으로 금지
CREATE USER admission_ai_ro FOR LOGIN admission_ai_ro;
ALTER ROLE db_datareader ADD MEMBER admission_ai_ro;
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER ON SCHEMA::dbo TO admission_ai_ro;

-- 학생 조회용: 공개 테이블의 공개 열만 (만들 당시는 고교구분 6개 열)
CREATE USER admission_ai_student FOR LOGIN admission_ai_student;
GRANT SELECT ON dbo.EXCEL_HIGHSCHOOLTYPE
    (학교명, 학교종류명, 시도명, 고등학교구분명, 고등학교일반전문구분명, 특수목적고등학교계열명)
    TO admission_ai_student;
DENY INSERT, UPDATE, DELETE, EXECUTE, ALTER ON SCHEMA::dbo TO admission_ai_student;
GO

-- ③ 확인: 권한 오류가 나야 정상
EXECUTE AS USER = 'admission_ai_student';
SELECT TOP 1 * FROM dbo.UI_IPSI_M_V;          -- 비공개 테이블이므로 거부되어야 함
REVERT;
```

- **학생 공개 테이블·열은** 대시보드에서 공개로 바꾸면 프로그램이 학생 계정의 SELECT 권한을 자동으로 맞춥니다. 위 ②의 GRANT 는 처음 만들 때의 상태입니다.
- **학사 DB(DC_DAEDONG_C / DC_DAEDONG_U) 권한은 주지 않습니다.** 입시마스타 뷰(`UI_IPSI_M_V`)는 학사 DB 함수를 써서 읽기 계정으로는 열리지 않으므로, 프로그램이 사전 검사를 통과한 교직원 조회만 오너 계정으로 다시 실행합니다.

### 기존 계정 비밀번호 바꾸기

```sql
-- sa 로 실행
ALTER LOGIN admission_ai WITH PASSWORD = N'새_강한비밀번호';
```
바꾼 뒤 개발 PC `backend\.env` 와 서버 `C:\actions-runner\.env` 의 `DB_PWD` 를 함께 바꾸고, 백엔드를 재시작(서버는 재배포)합니다.
