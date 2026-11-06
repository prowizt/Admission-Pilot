# Admission-Pilot — Claude 작업 안내

대동대학교 입학처 AI 챗봇(교직원 공문 검토·DB 조회·엑셀 채우기 / 수험생 상담) 프로젝트.
FastAPI 백엔드(`backend/main.py`) + MS-SQL(DDU_ADMISSION, **운영 DB 공유**) + ChromaDB 문서 검색 + React 대시보드(`frontend`) + 학생 웹(`student-web`) + 크롬 확장(`extension`).

## 반드시 지킬 것

- **한국어로** 답하고 설명한다. 사용자는 비개발자 관점의 쉬운 말을 선호.
- **계획 먼저.** 바꾸기 전에 무엇을·왜·어떤 파일을 바꾸는지 보여 주고 진행한다.
- **DB 구조 변경(DDL)은 SQL 을 먼저 보여 주고 승인받은 뒤 실행.** 운영 DB 이므로 쓰기는 바로 실서비스에 반영됨.
  - 테이블·컬럼을 만들거나 바꾸면 **MS_Description 주석**을 같이 달고 `extract_schema.py`(`PYTHONIOENCODING=utf-8`)로 확인 → `db_schema_full.txt`.
- **업무 테이블(EXCEL_*, 입시마스타 등)에 INSERT/UPDATE 를 직접 실행하지 않는다.** 쿼리 초안만 주고 사용자가 SSMS 에서 실행. (Sys_* 시스템 테이블의 설정·로그 표시는 예외)
- **학사 DB(DC_DAEDONG_C / DC_DAEDONG_U) 접근 권한을 주거나 쓰지 않는다.**
- **`git push` 하지 않는다.** 커밋도 사용자가 요청할 때만.
  - 커밋은 **`main` 브랜치에 바로** 한다 (작업 브랜치를 따로 만들지 않음 — 사용자 지시 2026-11-05).
  - 서버가 저절로 바꾸는 파일(`__pycache__`, `backend/latest_query.sql`, `backend/temp/`)은 커밋에 넣지 않는다 (.gitignore 처리됨).
  - **문서 벡터 DB(`backend/db/`)는 커밋한다.** 배포가 서버 폴더를 git 상태로 덮어쓰므로, 운영 서버의 문서 DB = 마지막으로 커밋한 `backend/db`. 문서를 올리거나 지웠으면 `backend/db` 를 커밋·push 해야 운영에 반영된다. 운영 대시보드에서 직접 올린 문서는 다음 배포 때 사라지므로 **문서 등록은 개발 PC 에서**.
- **파일 전체 덮어쓰기 금지** — 부분 수정(Edit)으로. 줄바꿈(LF/CRLF)은 원래 파일 것을 유지.
- **프롬프트에 업무 이름(특정 학과·전형·문서명)을 하드코딩하지 않는다.** 카탈로그·값 사전·문서 목록에서 읽어 쓰는 범용 규칙으로.
- **학생 챗봇은 내부 정보(교직원 데이터·토큰·문서 내부 정보)를 내보내지 않는다.**
- **API 키·DB 비밀번호는 `backend/.env` 에만.** 출력·커밋하지 않고, 사용자가 채팅에 키를 붙여 넣지 않게 안내.
- **사전지식(Sys_SupplementalKnowledge)은 사용자가 직접 정리한다.** Claude 가 임의로 추가하지 않는다.
- **API 비용이 드는 시험은 먼저 원화 예상액을 보고하고, 사용자가 "시작해" 한 뒤에 실행한다** (사용자 지시 2026-11-06). 챗봇 질문·엑셀 채우기·문서 등록 임베딩 등 Claude/Gemini API 를 부르는 모든 시험이 대상. 예: "질문 2건, 건당 약 15원 → 약 30원". 서버 재시작·health 확인·DB 조회처럼 API 를 안 부르는 일은 바로 해도 된다. 실행 후에는 실제 비용(로그 금액)도 함께 보고.
- **챗봇 시험 질문은 앞에 `[테스트]`** 를 붙이고, 시험 로그는 **지우지 않는다** (Claude 크레딧 통계·예상 잔액이 로그 비용 기준).

## 코딩 표준 (예전 AI_GUIDELINES.md 에서 지금도 맞는 것만 옮김)

- **아키텍처·배포**는 `SYSTEM_ARCHITECTURE.md`(포트·프록시·도메인·구성·DB 계정), `SERVER_SETUP_GUIDE.md`(서버 구축·배포·서버 `.env` 항목)를 먼저 본다.
  - 구조(새 파일·테이블·DB 계정·메뉴), 배포 방식, `.env` 항목이 바뀌면 **이 두 문서도 같이 고치고** 맨 위 '마지막 점검' 날짜를 갱신한다. `.env` 항목을 추가하면 서버 `C:\actions-runner\.env` 에도 넣어야 한다고 사용자에게 알린다.
- **"실행해", "진행해", "시작해"** 같은 명시적 승인 뒤에 코드를 고친다. 사소한 수정·디버깅도 같음.
- 새 파일은 **맨 위에 파일 역할 주석**을 단다. 파일 이름은 snake_case.
- 요청하지 않은 기존 함수·라우터 연결을 지우거나 `...` 로 생략하지 않는다.
- DB 스키마나 API 응답 구조를 바꾸면 **크롬 확장(`extension/sidepanel.js`)·대시보드 파싱에 영향**이 있는지 함께 알린다. 확장은 일반 웹이 아님(chrome.storage, content/background script).
- 새 React 화면은 기존처럼 Tailwind CSS + lucide-react, 기존 화면과 같은 모양으로.
- 오류 보고를 받으면 원인(파싱·문서 검색·API 키·DB)부터 나눠 분석하고, 필요한 곳만 고친다.
- 외부 AI 로 보내기 전 **개인정보 마스킹**(`mask_pii`, 이름·주민번호·연락처 → `[MASKED]`)을 유지한다.
- MS-SQL·한글·PDF 처리에는 try-except, cp949/utf-8 인코딩을 고려한다. f-string 으로 T-SQL 을 조립할 때 문자열은 `.replace("'", "''")`.
- 쿼리에 대괄호 테이블·열 이름은 실제 DB 이름과 똑같이 (AI 스키마는 실제 DB 열 이름 + 카탈로그 설명). WHERE 값은 값 사전의 실제 값 그대로 (예: `[최종입시결과] = '최종등록자'`).
- 엑셀 빈칸을 맞추려고 `UNION ALL` 로 없는 행(0값 더미)을 만들지 않는다. 긴 JSON 은 중간 생략 없이 끝까지.
- 업무 기준(신입/편입, 정원내/외, 하이픈·제한없음 해석, 표 병합 상속 등)은 **사전지식이 기준**이다. 현재: 편입 언급이 없으면 **신입만** 조회.
- 학생 권한에서 공개 테이블이 하나도 없으면 라우터를 건너뛰고(`skip_router`) 문서 검색으로 간다. 건너뛸 때 뒤에서 쓰는 변수는 미리 초기화.
- 프롬프트에 동적으로 넣는 문구는 중복("2027학년도 2027학년도")되지 않게 정리한다.

## 챗봇 답변 형식 (교직원)

- LaTeX 기호(`\rightarrow`, `\times` 등) 금지 → `→`, `×` 같은 일반 기호.
- 통계 대조는 학과별 한 줄마다 `[일치]` / `[불일치 - 서류: O명, DB: O명]` / `[불일치 - 서류 미기재(DB 기준: O명)]`.
- 규정을 인용한 지적 끝에는 `(근거 문서: 문서명)`.
- 수치 검증 요청이면 대조 결과를 맨 위에, 규정 검토 중심이면 검토 의견을 맨 위에. 표 수집 한계 안내는 맨 아래 짧게.

## 환경 메모

- 서버: `python run_servers.py` (백엔드 127.0.0.1:8000 + 대시보드 vite + 학생 웹 vite). 백엔드는 파일 저장 시 **자동 재시작(WatchFiles)** 된다.
  - **서버는 Claude 가 Windows(WMI)에 맡겨 띄운다** — VS Code 안에서 `Start-Process` 로 띄우면 VS Code 를 끌 때 서버도 같이 꺼짐(2026-11-06, 종료 코드 3221225786 = Ctrl+C). PowerShell:
    `$py=(Get-Command python).Source; $si=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]7}; Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="`"$py`" run_servers.py"; CurrentDirectory='D:\Projects\Admission-Pilot'; ProcessStartupInformation=$si}` (python 은 전체 경로 필수 — 이름만 쓰면 반환값 9). 부모가 `WmiPrvSE` 면 정상.
  - 창 내용은 `logs/run_servers.log` 에 똑같이 남는다 (직전 실행은 `run_servers.prev.log`) → 시작 오류·콘솔 출력은 이 파일로 확인.
  - **사용자는 VS Code 아래 터미널의 "서버 화면 보기"로 본다**: `watch_servers.py` 가 로그 파일을 색상 그대로 실시간 표시(읽기만 함, 재시작도 자동으로 따라감). `.vscode/tasks.json` 이 폴더를 열 때 자동 실행 — 꺼졌으면 Terminal → Run Task… → "서버 화면 보기".
  - **백엔드 파일(`backend/*.py`)을 고친 뒤에는 반드시 15초쯤 뒤 `/health`·5175·5176 을 확인하고, 꺼졌으면 바로 위 명령으로 다시 띄운다** (사용자 지시 2026-11-06). Windows 에서 WatchFiles 자동 재시작의 Ctrl+C 신호가 같은 콘솔의 run_servers·vite 까지 꺼 버림 (`logs/run_servers.log` 에 `WatchFiles detected changes` → `종료 신호(Ctrl+C)`). 코드로 막지 않고 이렇게 처리하기로 함.
  - 재시작 요청 시: Admission-Pilot 프로세스만 골라 끈다 (`Get-CimInstance Win32_Process` 명령줄에 `Admission-Pilot`·`run_servers.py`·포트 8000 소유 프로세스). **다른 프로젝트(StudentInfo, LizLab-Agent 등) 서버도 같은 PC 에서 돌고 있으니 python/node 를 통째로 끄지 않는다.** 그다음 위 명령으로 다시 띄우고 `/health` 200 확인.
- 콘솔이 cp949 → 스크립트는 `PYTHONIOENCODING=utf-8` 로 실행. DB 에 넣는 문자열도 cp949 로 표현 못 하는 글자(₩·이모지)는 `cp949_safe` 로.
- DB 스크립트: `backend/tools/_db.py` 의 `connect()` 를 쓰거나, `load_dotenv(backend/.env)` 후 `app_config._owner_conn()`.
- 설정값은 `backend/app_config.py` SPEC(기본값) + 대시보드 환경 설정(Sys_SystemSetting). 코드에 상수를 박지 말고 설정으로.
- 타입 검사: `cd frontend && npx tsc -b` (배포 빌드와 같은 검사 — **오류가 하나라도 있으면 배포가 멈추므로 0개여야 함**). student-web 도 같음. 프런트를 고쳤으면 커밋 전에 `npm run build` 까지 확인.

## 작업기록 (매일)

- 하루 작업은 `docs/작업기록_YYYY-MM-DD.md` 에 남긴다 (요청 → 원인/판단 → 바꾼 것(파일) → 결정 사항 → DB 변경 → 점검한 로그 ID → 남은 일). 형식은 `docs/작업기록_2026-11-05.md` 참고.
- 세션 시작 hook(`.claude/hooks/worklog_reminder.py`)이 **작업기록이 없는 지난 작업일**을 알려 주면, 사용자 요청과 함께 그날 기록을 먼저 작성한다. 근거는 대화 기록(`~/.claude/projects/D--Projects-Admission-Pilot/*.jsonl`)에서 그날 timestamp 부분만 읽어 정리.
- 프로젝트 위치: **`D:\Projects\Admission-Pilot`** (2026-11-06 `D:\Admission-Pilot` 에서 옮김). 옮기기 전 대화 기록은 새 위치 폴더에 복사해 두었고, 원본 `~/.claude/projects/D--Admission-Pilot/` 도 남아 있다. 작업기록에 적힌 옛 jsonl 경로는 같은 파일 이름으로 새 폴더에서 찾으면 된다.
- 사용자가 "예전에 ○○ 얘기한 것 찾아줘" 하면 작업기록 → 대화 기록(jsonl) 순으로 검색한다. 대화 기록 보관 기간은 3650일로 설정됨.

## 로그 분석·점검

- 사용자는 대시보드 '실시간 대화 로그'에서 **ID(`#537`)만 복사해** 분석을 부탁한다.
- 감사 로그 `Sys_AIAuditLog` 의 `process_log` 칸에 그 요청의 **서버 콘솔 기록**(라우터 판단·검색 키워드·[Rule]/[Ref] 선발·지정 문서·SQL 실행·토큰·비용)이 있으니 꼭 함께 읽는다.
- 도구 (`backend/tools/`, 저장소 루트에서 실행):
  - `python backend/tools/readlog.py 537` — 로그 1건 전체 (처리 과정 포함)
  - `python backend/tools/review_list.py [--from N --to M | --since YYYY-MM-DD] [--review] [--detail]` — **미점검** 로그 목록
  - `python backend/tools/review_mark.py --file notes.txt --from N --to M` — Claude 점검 표시 기록 + 범위 남은 미점검 수

### 공문 검토 점검 절차 (사용자가 "점검해줘" 하면 — 빠뜨리지 말 것)

1. `review_list.py --detail` 로 **미점검** 대상부터 뽑는다 (범위를 안 주면 최근 미점검 교직원 로그).
2. 로그마다 확인: 관계없는 문서가 들어갔는지(답변에 인용 안 된 문서) · 필요한 규정(위임전결·예산회계 등) 누락 · DB 대조 쿼리가 문서의 숫자와 같은 지표(지표 사전 정의)로 셌는지 · 틀린 지적 · 비용·시간.
3. 결과를 로그별 한 줄(`아이디<TAB>정상 · …` 또는 `문제 · …`, 금액은 `16.5원` 처럼)로 파일에 적고 `review_mark.py --file … --from … --to …` 로 기록.
4. 출력의 **"남은 미점검 … 0건 ✅"** 을 확인 (0이 아니면 빠진 로그부터 마저 점검).
5. 사용자에게 보고할 때 **맨 끝에 표시한 로그 ID 목록**을 적는다.

- 대시보드 표시: 🤖 점검(정상 녹색·문제 주황) / 👤 확인(관리자가 모달 위쪽 [확인] 버튼으로 한 번에 표시·해제). **Claude 가 점검한 로그는 관리자 확인이 있어도 항상 🤖 점검으로 덮어쓴다.**
- 학생 로그도 점검을 부탁받으면 `review_list.py --all-roles` 로 포함.
- 비교 기준 사례 (공문 검토 라우터 추론 on·medium 적용 후): #542 간담회 계획 — 문서 3건, DB 대조 9개 학과 일치, 16.5원 / #543 회의비 지출기안 — 문서 5건, 18.1원.
