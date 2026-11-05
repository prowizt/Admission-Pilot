# Admission-Pilot 시스템 아키텍처 및 배포 가이드 (최종 요약본)

이 문서는 Admission-Pilot 프로젝트의 전체 시스템 구성, 설치 환경, 배포 프로세스 및 핵심 비즈니스 로직을 요약한 것입니다. 향후 새로운 개발자나 AI 에이전트가 프로젝트를 파악하고 유지보수할 때 핵심 참고 자료로 사용됩니다.

> **마지막 점검: 2026-11-05** (Claude Code 와 코드 대조). 작업 규칙은 `CLAUDE.md`, 날짜별 변경 내역은 `docs/작업기록_YYYY-MM-DD.md` 참고.

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
  - 엑셀 자동채우기 (`excel_autofill.py`): 업로드된 엑셀 서식을 분석하여 DB 및 RAG에서 데이터를 긁어와 자동으로 셀을 채워주는 기능. 가로로 펼친 격자 양식은 AI 가 '엑셀 이름 ↔ DB 값' 대응표만 만들고, 숫자·합계는 파이썬이 DB 값으로 넣고 검산함.
- **AI 모델**: Gemini 와 Claude(Haiku 5.5 등)를 함께 지원 (`llm_client.py`). 교직원은 크롬 확장에서 모델을 고르고, 학생 챗봇 모델은 대시보드 환경 설정에서 고름 (2026-11 현재 `claude-haiku-5-5`).
- **주요 파일**:
  | 파일 | 역할 |
  |---|---|
  | `main.py` | 서버 진입점, `/chat` 라우팅(라우터 → DB/문서 수집 → 최종 답변), 대시보드 API |
  | `excel_autofill.py` | 엑셀 자동 채우기 (`/chat-excel-autofill`) |
  | `llm_client.py` | Gemini·Claude 호출, 토큰 계산, 10만 토큰 초과 호출 차단, 비용 계산 |
  | `db_access.py` | 역할별 DB 계정으로 조회 실행, 조회문만 허용하는 사전 검사 |
  | `app_config.py` | 운영 설정값 (대시보드 환경 설정 > `.env` > 기본값 순) |
  | `metric_query.py` | 지표 사전 기반 SQL 조립 (쿼리 요청·엑셀 격자) |
  | `value_resolver.py` | 이름 보정 (SQL 조건 값을 그 학년도 실제 값으로 맞춤) |
  | `doc_db_overlap.py` | 공문 검토 시 문서의 숫자 줄과 DB 구분 값 겹침 검사 → 라우터에 대조 쿼리 힌트 |
  | `process_log.py` | 요청별 콘솔 출력을 모아 감사 로그 `process_log` 칸에 저장 |
  | `claude_billing.py` | Claude 크레딧 예상 잔액 (콘솔 잔액 − 로그 비용) |
  | `tools/` | 로그 점검 도구 (`readlog.py`, `review_list.py`, `review_mark.py`) |

### 2.2. Student Chatbot (학생용 챗봇)
- **위치**: `/student-web`
- **기술 스택**: React + Vite + TailwindCSS
- **구동 환경 (로컬 개발)**: `http://localhost:5176/` (Vite Proxy를 통해 로컬 백엔드로 자동 연결됨)
- **구동 환경 (운영 배포)**: Nginx의 **443번 포트 (HTTPS)**를 통해 `student-web/dist` 폴더의 정적 파일 서빙 (80번 접속 시 443으로 강제 리다이렉트).
- **특징**:
  - API 호출 시 상대 경로(`/api/chat`, `/api/health`)를 사용하며, 로컬에서는 Vite가, 운영에서는 Nginx가 이를 백엔드(8000)로 똑똑하게 프록시 전달함.
  - 모델은 대시보드 **환경 설정 > 학생 챗봇 > 답변 모델**에서 고름 (2026-11 현재 `claude-haiku-5-5`, Claude 는 서버 `.env` 의 `ANTHROPIC_API_KEY`, Gemini 는 `STUDENT_API_KEY` 사용).
  - 보안을 위해 `user_role = "student"`로 백엔드에 요청하며, 비공개 문서 및 테이블에 접근하지 못하도록 통제됨. DB 조회는 **학생 전용 DB 계정**(공개 테이블의 공개 열만 SELECT)으로만 실행.
  - 입학처 Q&A(`Sys_StudentFAQ`)를 함께 참고해 답함. 문서는 라우터가 이름으로 짚은 것만 넣음(관련성 필터).

### 2.3. Staff Dashboard (교직원 관리자 대시보드)
- **위치**: `/frontend`
- **기술 스택**: React + Vite + TailwindCSS
- **구동 환경 (로컬 개발)**: `http://localhost:5175/` (Vite Proxy를 통해 로컬 백엔드로 자동 연결됨)
- **구동 환경 (운영 배포)**: Nginx의 **8443번 포트 (HTTPS)**를 통해 `frontend/dist` 폴더의 정적 파일 서빙.
- **기능** (메뉴: 지식 카탈로그 / 시스템 로그 / 환경 설정, 머리글의 [📖 도움말]에 탭별 설명서):
  - **지식 카탈로그**: 비정형 문서(토큰 수 표시)·정형 데이터·사전지식·입학처 Q&A·실제 값 현황·지표 사전, 상단 **기준 입시학년도** 선택
  - **시스템 로그**: 실시간 대화 로그(검색·필터, 라우터/챗봇 모델·추론 ON/OFF, 처리 과정 보기, 🤖 점검·👤 확인 표시), Claude 사용 통계(일별·월별, 크레딧 예상 잔액·충전 기록)
  - **환경 설정**: 자주 바꾸는 운영 값(모델·추론 강도·비용 보호 한도 등). API 키·비밀번호는 화면에 두지 않고 `.env` 에만.

### 2.4. Staff Chrome Extension (교직원용 크롬 확장프로그램)
- **위치**: `/extension`
- **특징**:
  - 브라우저 우측 사이드 패널로 동작.
  - 그룹웨어 기안문 등 브라우저 화면의 텍스트를 드래그/스크랩하여 즉시 AI에게 분석 요청.
  - 모델은 확장 설정의 **내 AI 모델 관리**에서 등록 (Gemini·Claude Haiku 등, 라우터 모델 따로 지정 가능). 추론 강도는 확장이 아니라 대시보드 환경 설정을 따름.
  - 큰 문서(2만 토큰 초과) 포함 여부·엑셀 계산 기준을 묻는 확인 말풍선을 표시.
  - **하이브리드 환경 자동 인식**: 코드 내 하드코딩 대신 설정창(톱니바퀴)의 **개발자 모드 체크박스**를 통해 로컬 환경(`http://127.0.0.1:8000`)과 운영 환경(`https://ipw.daedong.ac.kr:8443/api`)을 자유자재로 전환하여 안전하게 통신함.

---

## 3. 데이터베이스 및 지식 카탈로그 (Database & RAG)

### 3.1. MS-SQL (정형 데이터 및 카탈로그)
- **접속 정보**: `SERVER=10.10.1.11,1433; DATABASE=DDU_ADMISSION` (운영 DB 를 개발 PC 와 서버가 함께 씀 — 쓰기는 바로 실서비스에 반영)
- **핵심 역할**: 입시 통계, 학과별 지원율 등 정형 데이터 제공.
- **DB 계정** (비밀번호는 `.env` 에만):
  | 계정 | `.env` 항목 | 용도 · 권한 |
  |---|---|---|
  | `admission_ai` | `DB_USER`, `DB_PWD` | 대시보드·카탈로그·로그 기록 (DB 오너) |
  | `admission_ai_ro` | `DB_RO_USER`, `DB_RO_PWD` | 교직원 챗봇 조회 (읽기 전용). 학사 DB 를 참조하는 뷰(입시마스타)는 권한이 없어, 사전 검사를 통과한 조회만 기존 계정으로 다시 실행 |
  | `admission_ai_student` | `DB_STUDENT_USER`, `DB_STUDENT_PWD` | 학생 챗봇 조회 (학생 공개 테이블의 공개 열만 SELECT). 학생은 어떤 경우에도 다른 계정으로 넘어가지 않음 |
  - 학사 DB(DC_DAEDONG_C/U) 권한은 주지 않음. 계정 생성 쿼리는 `SERVER_SETUP_GUIDE.md` 부록 참고.
- **시스템 테이블** (모든 테이블·컬럼에 MS_Description 주석 → `extract_schema.py` 로 `db_schema_full.txt` 생성):
  | 테이블 | 역할 |
  |---|---|
  | `Sys_TableCatalog`, `Sys_ColumnCatalog` | AI 가 보는 테이블·열 설명(힌트), 공개 여부, 값 사전 포함 여부. AI 스키마의 열 이름은 실제 DB 에서 읽고 카탈로그는 설명만 붙임 |
  | `Sys_DocumentCatalog` | 비정형 문서 이름·설명(힌트)·연도·공개 여부·토큰 수 |
  | `Sys_SupplementalKnowledge` | 사전지식 (업무 규칙·예외, 적용 대상: 교직원/공통/학생) — 업무 규칙은 프롬프트가 아니라 여기에 둠 |
  | `Sys_StudentFAQ` | 입학처 Q&A (공통 또는 특정 학년도) |
  | `Sys_SystemSetting` | 운영 설정값 (기준 입시학년도, 환경 설정 화면 값, 크레딧 기준 잔액·충전 기록) |
  | `Sys_ValueDictionary` | 구분 열의 학년도별 실제 값 (1시간마다 갱신, AI 스키마·이름 보정에 사용) |
  | `Sys_MetricCatalog`, `Sys_DimensionCatalog` | 지표 사전(지원인원·합격인원 등 계산식)·구분 사전(학과·전형이 테이블마다 어느 열인지) |
  | `Sys_AIAuditLog` | 대화 감사 로그 (토큰·비용·호출 설정, `process_log` 처리 과정, `reviewed_*` 점검 표시) |

### 3.2. ChromaDB (비정형 문서 벡터 DB)
- **위치**: `/backend/db/chroma.sqlite3`
- **핵심 역할**: 입시 요강, 학칙, 회계 규정 등의 PDF 텍스트를 임베딩하여 시맨틱 검색(RAG) 제공.
- **컬렉션 구조** (`main.py` 의 `rule_db`, `reference_db`):
  - `rule_db`: 모집요강(분할본), 학칙, 규정·지침 등 (팩트 체크·답변 근거).
  - `reference_db`: 과거 입시 결과, 참고 공문·양식 등 (참고 데이터).
- **주의**: 임베딩 모델이 영어 전용이라 한글 의미 검색은 부정확함 → 라우터가 **공식 문서명**으로 고르고, 서버는 파일명·제목이 맞는 문서만 넣음(관련성 필터).

---

## 4. 핵심 AI 로직 (AI Routing Logic)

사용자가 질문을 던지면 `main.py` 내부에서 다음과 같은 **하이브리드 라우팅**이 발생합니다:

1. **라우터 (Router) 판단**:
   - 학생일 경우: 만약 공개된 DB 테이블이 없다면(학생 권한), AI 라우팅을 생략하고 즉시 RAG 문서 검색으로 직행(`Fast-Track`).
   - 교직원일 경우: 질문 의도와 카탈로그를 대조하여, SQL(정형 데이터) 쿼리를 만들 것인지, 문서(RAG)를 뒤질 것인지, 혹은 둘 다 할 것인지 JSON 형태로 판단 결과(`sql_query`, `need_rag`, `target_documents` 등)를 생성.
   - 라우터는 JSON 형식이 강제됨(`ROUTER_SCHEMA`). 일반 질문은 추론 끔·effort low, **공문 검토(스크랩·첨부)** 는 추론 켬·medium, **"쿼리/SQL" 요청**은 추론 켬(`QUERY_ROUTER_EFFORT`).
   - 공문 검토 때 문서의 숫자 줄에 DB 구분 값(학과 등)이 여러 개 나오면 대조 쿼리를 권하는 힌트와 지표 정의를 덧붙임. 라우터가 등록되지 않은 문서명을 '지정 문서'로 넣으면 무시.
2. **실행 (Execution)**:
   - SQL 쿼리가 있으면 사전 검사(조회문만, 형식상 쿼리 차단) 후 역할별 DB 계정으로 조회. 조건 값은 이름 보정으로 실제 값에 맞춤. 쿼리 요청은 지표 설계도로 시스템이 SQL 을 조립하고, 실행 오류 시 1회 자동 수정.
   - 문서 검색(`need_rag`)이 필요하면 ChromaDB 에서 후보를 뽑고 **관련성 필터**(이름 매칭)와 공문 제목 보완을 거쳐 선발 (교직원 최대 `STAFF_DOC_LIMIT` 건). 학생 요청인 경우 비공개(`is_public != 'Y'`) 문서는 제외.
   - **비용 보호**: 2만 토큰 넘는 문서는 포함 여부를 먼저 물음(교직원), Claude 호출 입력이 10만 토큰을 넘으면 보내지 않고 취소.
3. **최종 응답 (Generation)**:
   - 조회된 DB 데이터, 문서, 사전지식, 입학처 Q&A, 오늘 날짜·기준 입시학년도를 종합해 최종 AI 가 답변 (학생은 스트리밍).
   - 감사 로그에 토큰·비용(부가세 포함)·호출 설정과 **처리 과정(콘솔 기록)** 을 남김.

---

## 5. 배포 프로세스 (CI/CD Pipeline)

개발 PC에서 `git push`를 실행하면, 229번 서버의 **GitHub Actions Runner**가 다음 절차를 자동으로 수행합니다 (`.github/workflows/deploy.yml` 참고).

### 5.1. 환경 변수 (`.env`) 관리 및 보안
- **위치**: `C:\actions-runner\.env` (229번 서버 내부 안전 영역)
- **이유**: API 키·DB 비밀번호 같은 민감 정보는 깃허브(공개/공용 환경)에 올리지 않고, 서버의 안전한 폴더에 격리 보관.
- **적용**: 배포 로봇이 구동될 때 이 파일을 프로젝트 내부의 `backend\.env`로 복사하여 덮어씀.
- **들어가야 할 항목**은 `SERVER_SETUP_GUIDE.md` 3장 참고 (`ANTHROPIC_API_KEY`, `DB_*` 계정 3개 등). 개발 PC 의 `backend\.env` 를 바꾸면 서버 쪽 파일도 같이 맞춰야 함.
- 모델·추론 강도·한도 같은 운영 값은 `.env` 가 아니라 대시보드 **환경 설정**(DB 저장)에서 바꾸며, 재시작 없이 반영됨.

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
  - 대시보드 환경 설정의 학생 답변 모델을 확인하고, 그 모델의 키(`ANTHROPIC_API_KEY` 또는 `STUDENT_API_KEY`)가 `C:\actions-runner\.env` 에 올바르게 들어 있는지 확인 후 재배포합니다.
  - Claude 크레딧이 떨어졌는지 대시보드 시스템 로그 > Claude 사용 통계의 예상 잔액과 콘솔 잔액을 확인합니다.
- **답변이 이상할 때 (원인 찾기)**:
  - 대시보드 대화 로그에서 해당 로그를 열고 **[처리 과정 (서버 기록)]** 을 펼치면 라우터가 고른 문서·SQL·오류가 그대로 남아 있습니다.
  - 개발 PC 에서는 `python backend/tools/readlog.py <로그ID>` 로 같은 내용을 볼 수 있습니다.
