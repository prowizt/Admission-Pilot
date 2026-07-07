# Admission-Pilot 시스템 아키텍처 및 배포 가이드 (최종 요약본)

이 문서는 Admission-Pilot 프로젝트의 전체 시스템 구성, 설치 환경, 배포 프로세스 및 핵심 비즈니스 로직을 요약한 것입니다. 향후 새로운 개발자나 AI 에이전트가 프로젝트를 파악하고 유지보수할 때 핵심 참고 자료로 사용됩니다.

---

## 1. 서버 환경 (Server Environment)
- **운영 도메인 및 IP**: `ipw.daedong.ac.kr` (IP: `210.93.0.229`)
- **운영 체제 (OS)**: Windows Server 2022
- **필수 설치 프로그램**:
  - **Python**: 백엔드 서버 구동용 (3.11 이상 권장)
  - **Node.js & npm**: 프론트엔드 빌드 및 프로세스 관리자(PM2) 구동용
  - **PM2**: 백엔드(FastAPI) 프로세스를 백그라운드에서 24시간 안정적으로 구동하는 데몬 매니저 (글로벌 설치: `npm install -g pm2`)
  - **Nginx**: 웹 서버 및 리버스 프록시 (포트 80 트래픽을 443(HTTPS)으로 리다이렉트, 443 및 8443 포트로 프론트엔드 정적 파일 서빙 및 SSL 암호화 처리)
  - **Git & GitHub Actions Runner**: 소스코드 관리 및 CI/CD 자동 배포 서비스 (`C:\actions-runner` 에 설치됨)

---

## 2. 전체 시스템 구성도 (System Components)

### 2.1. Backend (FastAPI)
- **위치**: `/backend`
- **구동 포트**: `127.0.0.1:8000` (내부망 전용)
- **주요 역할**: 
  - Chat API (`/api/chat`): AI 챗봇의 두뇌 역할. RAG 및 Text-to-SQL 라우팅 수행.
  - 지식 업로드 API (`/api/upload-knowledge`): 관리자가 업로드한 PDF 문서를 분할(Chunk)하여 ChromaDB에 벡터 저장 및 MS-SQL 카탈로그에 메타데이터 기록.
  - 엑셀 자동채우기 (`excel_autofill.py`): 업로드된 엑셀 서식을 분석하여 DB 및 RAG에서 데이터를 긁어와 자동으로 셀을 채워주는 기능.
- **주요 파일**: `main.py` (서버 진입점 및 라우팅 로직)

### 2.2. Student Chatbot (학생용 챗봇)
- **위치**: `/student-web`
- **기술 스택**: React + Vite + TailwindCSS
- **구동 환경 (로컬 개발)**: `http://localhost:5176/` (Vite Proxy를 통해 로컬 백엔드로 자동 연결됨)
- **구동 환경 (운영 배포)**: Nginx의 **443번 포트 (HTTPS)**를 통해 `student-web/dist` 폴더의 정적 파일 서빙 (80번 접속 시 443으로 강제 리다이렉트).
- **특징**:
  - API 호출 시 상대 경로(`/api/chat`, `/api/health`)를 사용하며, 로컬에서는 Vite가, 운영에서는 Nginx가 이를 백엔드(8000)로 똑똑하게 프록시 전달함.
  - **gemini-2.5-flash** 모델 사용 (비용 절감 목적).
  - 보안을 위해 `user_role = "student"`로 백엔드에 요청하며, 비공개 문서 및 테이블에 접근하지 못하도록 통제됨.

### 2.3. Staff Dashboard (교직원 관리자 대시보드)
- **위치**: `/frontend`
- **기술 스택**: React + Vite + TailwindCSS
- **구동 환경 (로컬 개발)**: `http://localhost:5175/` (Vite Proxy를 통해 로컬 백엔드로 자동 연결됨)
- **구동 환경 (운영 배포)**: Nginx의 **8443번 포트 (HTTPS)**를 통해 `frontend/dist` 폴더의 정적 파일 서빙.
- **기능**: 지식베이스(문서) 업로드, 서버 헬스체크, 통계/로그 확인 등 관리자 기능 수행.

### 2.4. Staff Chrome Extension (교직원용 크롬 확장프로그램)
- **위치**: `/extension`
- **특징**:
  - 브라우저 우측 사이드 패널로 동작.
  - 그룹웨어 기안문 등 브라우저 화면의 텍스트를 드래그/스크랩하여 즉시 AI에게 분석 요청.
  - **gemini-3.5-flash** 모델 사용 (고성능 추론).
  - **하이브리드 환경 자동 인식**: 코드 내 하드코딩 대신 설정창(톱니바퀴)의 **개발자 모드 체크박스**를 통해 로컬 환경(`http://127.0.0.1:8000`)과 운영 환경(`https://ipw.daedong.ac.kr:8443/api`)을 자유자재로 전환하여 안전하게 통신함.

---

## 3. 데이터베이스 및 지식 카탈로그 (Database & RAG)

### 3.1. MS-SQL (정형 데이터 및 카탈로그)
- **접속 정보**: `SERVER=10.10.1.11,1433; DATABASE=DDU_ADMISSION`
- **핵심 역할**: 입시 통계, 학과별 지원율 등 정형 데이터 제공.
- **시스템 테이블**:
  - `Sys_TableCatalog`, `Sys_ColumnCatalog`: AI가 현재 DB 구조를 파악하고 동적으로 SQL을 생성할 수 있도록 테이블 및 컬럼 설명을 보관.
  - `Sys_DocumentCatalog`: 업로드된 비정형 문서(PDF)의 이름, 설명, 연도, 공개 여부(학생용/교직원용) 메타데이터 보관.

### 3.2. ChromaDB (비정형 문서 벡터 DB)
- **위치**: `/backend/db/chroma.sqlite3`
- **핵심 역할**: 입시 요강, 학칙, 회계 규정 등의 PDF 텍스트를 임베딩하여 시맨틱 검색(RAG) 제공.
- **컬렉션 구조**:
  - `admission_rules`: 학칙 및 규정 (엄격한 규칙).
  - `admission_references`: 과거 입시 결과 및 요강 등 (참고 데이터).

---

## 4. 핵심 AI 로직 (AI Routing Logic)

사용자가 질문을 던지면 `main.py` 내부에서 다음과 같은 **하이브리드 라우팅**이 발생합니다:

1. **라우터 (Router) 판단**:
   - 학생일 경우: 만약 공개된 DB 테이블이 없다면(학생 권한), AI 라우팅을 생략하고 즉시 RAG 문서 검색으로 직행(`Fast-Track`).
   - 교직원일 경우: 질문 의도와 카탈로그를 대조하여, SQL(정형 데이터) 쿼리를 만들 것인지, 문서(RAG)를 뒤질 것인지, 혹은 둘 다 할 것인지 JSON 형태로 판단 결과(`sql_query`, `need_rag`, `target_documents` 등)를 생성.
2. **실행 (Execution)**:
   - SQL 쿼리가 있으면 `10.10.1.11` MS-SQL에서 데이터 조회.
   - 문서 검색(`need_rag`)이 필요하면 ChromaDB에서 유사 문단 추출. 학생 요청인 경우, 메타데이터에 비공개(`is_public != 'Y'`) 처리된 문서는 필터링됨.
3. **최종 응답 (Generation)**:
   - 조회된 DB 데이터와 문서 문단을 종합하여 최종 AI가 스트리밍(Streaming) 방식으로 답변을 반환.

---

## 5. 배포 프로세스 (CI/CD Pipeline)

개발 PC에서 `git push`를 실행하면, 229번 서버의 **GitHub Actions Runner**가 다음 절차를 자동으로 수행합니다 (`.github/workflows/deploy.yml` 참고).

### 5.1. 환경 변수 (`.env`) 관리 및 보안
- **위치**: `C:\actions-runner\.env` (229번 서버 내부 안전 영역)
- **이유**: `GEMINI_API_KEY` 같은 민감 정보는 깃허브(공개/공용 환경)에 올리지 않고, 서버의 안전한 폴더에 격리 보관.
- **적용**: 배포 로봇이 구동될 때 이 파일을 프로젝트 내부의 `backend\.env`로 복사하여 덮어씀.

### 5.2. 자동 배포 절차 (Workflow Steps)
1. **🛑 기존 백엔드 정지**: 
   - `pm2 delete admission-backend` 및 `taskkill /f /im python.exe` 실행. (잠김 현상 방지를 위해 권한 충돌이 없도록 예외 처리된 PowerShell `try-catch` 구문 적용)
2. **📥 소스코드 다운로드**: 깃허브에서 최신 코드를 내려받음.
3. **📦 파이썬 환경 설정**: 가상환경(`venv`) 생성 및 `requirements.txt` 설치.
4. **🔐 `.env` 주입**: 앞서 만든 `C:\actions-runner\.env` 파일을 백엔드로 복사.
5. **⚛️ 프론트엔드 빌드**: 학생용(`student-web`) 및 교직원용(`frontend`) 앱 빌드.
6. **🌐 Nginx 설정 자동 업데이트**: 저장소의 `nginx/nginx.conf`를 서버 `C:\tools\nginx-1.31.2\conf\nginx.conf`로 복사하고 Nginx 재시작(`nginx -s reload`). (※ SSL 인증서 폴더인 `ssl/`은 깃허브에 올라가지 않으므로, 최초 1회는 서버에 수동으로 복사되어 있어야 함)
7. **🚀 백엔드 PM2 시작**: `pm2 start main.py` 로 서비스 재가동.

---

## 6. 문제 발생 시 점검 매뉴얼 (Troubleshooting)

- **서버가 죽었는지 확인 (229 서버 접속 후)**:
  - `pm2 list` (상태가 'online' 인지 확인)
  - `pm2 logs admission-backend` (에러 로그 실시간 모니터링)
- **백엔드 직접 재시작**:
  - `pm2 restart admission-backend`
- **배포 실패 (잠김 오류/EBUSY 발생 시)**:
  - 배포 로봇의 권한 한계로 기존 파이썬이 꺼지지 않아 코드를 덮어쓰지 못하는 현상입니다.
  - 서버(229)에서 터미널을 열고 수동으로 `pm2 delete admission-backend` 와 `taskkill /f /im python.exe` 명령을 실행하여 프로세스를 죽인 후 깃허브 배포를 재실행합니다.
- **학생용 API 에러 / 토큰 부족 오류 발생 시**:
  - `C:\actions-runner\.env` 파일 안에 `STUDENT_API_KEY`와 `STUDENT_MODEL` 등 환경 변수가 올바르게 기입되어 있는지 확인 후 재배포합니다.
