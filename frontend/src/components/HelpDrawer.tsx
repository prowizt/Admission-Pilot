import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X, BookOpen, Lightbulb } from 'lucide-react';

/**
 * [화면 설명서] 지식 카탈로그 관리의 탭마다 '도움말' 버튼으로 여는 설명서
 * 내용은 아래 HELP 에서 탭 이름(activeTab)별로 관리합니다.
 */

const H = ({ children }: { children: ReactNode }) => (
  <h3 className="text-sm font-extrabold text-indigo-900 mt-5 mb-2 first:mt-0">{children}</h3>
);
const P = ({ children }: { children: ReactNode }) => <p className="text-[13px] text-slate-700 leading-relaxed mb-2">{children}</p>;
const Li = ({ children }: { children: ReactNode }) => <li className="text-[13px] text-slate-700 leading-relaxed">{children}</li>;
const Ul = ({ children }: { children: ReactNode }) => <ul className="list-disc pl-5 space-y-1 mb-2">{children}</ul>;
const Code = ({ children }: { children: ReactNode }) => (
  <code className="px-1 py-0.5 rounded bg-slate-100 text-[12px] text-indigo-700 font-mono">{children}</code>
);
const Tip = ({ children }: { children: ReactNode }) => (
  <div className="flex gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 my-3">
    <Lightbulb size={16} className="text-amber-500 shrink-0 mt-0.5" />
    <div className="text-[13px] text-amber-900 leading-relaxed">{children}</div>
  </div>
);
const Table = ({ head, rows }: { head: string[]; rows: ReactNode[][] }) => (
  <div className="overflow-x-auto my-2">
    <table className="w-full text-[12px] border border-slate-200 rounded">
      <thead className="bg-slate-100">
        <tr>{head.map((h) => <th key={h} className="text-left px-2 py-1.5 font-bold text-slate-700 border-b border-slate-200">{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-slate-100 last:border-0 align-top">
            {r.map((c, j) => <td key={j} className="px-2 py-1.5 text-slate-700">{c}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

/** 쿼리·통계 질문 요령 (여러 탭에서 공통으로 보여 줌) */
const QueryGuide = () => (
  <>
    <H>질문 방식에 따라 달라지는 길</H>
    <Table
      head={['질문 예', '처리 방식']}
      rows={[
        ['시도별 지원인원 알려줘', 'AI 가 열 힌트를 보고 SQL 을 직접 작성'],
        ['학과별 지원인원 쿼리 만들어줘 (쿼리·SQL 포함)', '지표 사전으로 설계도 → 시스템이 표 모양 SQL 조립 → 실행 결과와 함께 SQL 제공'],
        ['엑셀 양식 첨부 + 채워줘', '지표 사전으로 설계도 → 시스템이 칸마다 값 기록, 합계·비율도 시스템 계산'],
      ]}
    />
    <Ul>
      <Li>전형·학과 이름을 조금 틀려도 실제 DB 값으로 고쳐 조회합니다. (예: '기초생활' → 기초생활수급자) 후보가 여러 개면 어느 값인지 물어봅니다.</Li>
      <Li>"쿼리 만들어줘"에서 '행은 학과, 열은 전형별'처럼 표 모양을 말하면 그대로 만들어 줍니다. '모든 전형'이면 그 조건에 실제로 데이터가 있는 전형을 모두 열로 넣습니다.</Li>
      <Li>지표 사전에 없는 숫자가 필요하거나 목록을 요청하면 AI 가 SQL 을 직접 씁니다. (결과는 나오지만 정의가 사전만큼 고정되지는 않음)</Li>
    </Ul>
  </>
);

const HELP: Record<string, { title: string; body: ReactNode }> = {
  documents: {
    title: '비정형 문서',
    body: (
      <>
        <H>이 화면은</H>
        <P>모집요강·규정 같은 PDF 문서를 등록·관리하는 곳입니다. AI 는 질문에 맞는 문서를 골라 내용을 참고해 답합니다.</P>
        <Tip>문서 제목을 정확히 적어 두면 "2027학년도 모집요강만 보고 답해줘"처럼 문서를 지정한 질문이 정확해집니다. 아주 큰 문서는 쓰기 전에 포함할지 물어봅니다(비용 확인).</Tip>
        <QueryGuide />
      </>
    ),
  },
  tables: {
    title: '정형 데이터(DB) · 열 힌트',
    body: (
      <>
        <H>이 화면은</H>
        <P>AI 가 조회할 수 있는 DB 테이블과 열마다의 설명(AI 설명 = 열 힌트)을 관리합니다. 저장한 설명은 DB 주석(MS_Description)에도 함께 기록됩니다.</P>

        <H>열 힌트 넣는 법</H>
        <Ul>
          <Li>테이블의 열 목록을 열고, 열마다 'AI 설명' 칸을 고쳐 저장합니다.</Li>
          <Li>좋은 힌트는 <b>값 목록보다 뜻과 쓰는 법</b>입니다. 예: <Code>최종입시결과</Code> "최종등록자가 신입생임", <Code>최초합격구분명</Code> "최종등록 여부는 최종입시결과에서 알 수 있음"</Li>
        </Ul>

        <H>코드명 목록을 적어 둔 힌트는?</H>
        <Ul>
          <Li>이제 열의 실제 값은 '실제 값 현황'이 자동으로 AI 에게 주고, 힌트에 적은 목록보다 우선합니다. 그래서 힌트의 목록은 해마다 낡을 수 있습니다. (띄어쓰기 섞임, 더 이상 없는 전형 등)</Li>
          <Li><b>지우지는 마시고</b> 차츰 뜻 설명으로 바꾸시면 좋습니다.</Li>
        </Ul>
        <Tip>입시마스타처럼 2만 행이 넘는 테이블은 힌트가 빈 열을 '실제 값' 목록에서 자동으로 뺍니다. 힌트를 비울 거면 '실제 값 현황' 탭에서 그 열을 [포함]으로 지정하세요.</Tip>

        <H>사례: 이름이 바뀐 값 (시도명)</H>
        <P>최근 2개 학년도의 실제 값은 자동으로 AI 에게 주어지므로, 힌트에는 <b>목록 대신 "언제 무엇이 무엇으로 바뀌었는지"</b>를 문장으로 적습니다. 여러 해를 비교하는 질문에서 AI 가 옛 이름과 새 이름을 함께 조회하게 됩니다.</P>
        <Table
          head={['지역', '~2024', '2025', '2026', '2027']}
          rows={[
            ['강원', '강원도', '강원도', '강원특별자치도', '강원특별자치도'],
            ['전북', '전라북도', '전북특별자치도', '전북특별자치도', '전북특별자치도'],
            ['제주', '제주특별자치도교육청', '제주특별자치도교육청', '제주특별자치도', '제주특별자치도'],
            ['광주·전남', '광주광역시 / 전라남도', '광주광역시 / 전라남도', '광주광역시 / 전라남도', '전남광주통합특별시'],
          ]}
        />
        <P>입시마스타 <Code>출신고교시도</Code> 힌트 예:</P>
        <div className="text-[12px] bg-slate-50 border border-slate-200 rounded p-2 mb-2 text-slate-700 leading-relaxed">
          출신 고교가 있는 시도. 학년도에 따라 이름이 바뀜: 강원도 → 강원특별자치도(2026학년도부터), 전라북도 → 전북특별자치도(2025학년도부터),
          제주특별자치도교육청 → 제주특별자치도(2026학년도부터), 광주광역시·전라남도 → 전남광주통합특별시(2027학년도부터 통합, 광주와 전남 구분 불가).
          여러 학년도를 비교할 때는 옛 이름과 새 이름을 IN 으로 함께 조회하고, 광주·전남은 2026학년도까지 두 값을 합쳐야 2027학년도와 비교됨.
        </div>
        <Ul>
          <Li><b>값을 괄호로 묶어 나열하지 마세요.</b> 예: "전남광주통합특별시(광주광역시·전라남도)" — AI 는 힌트에 나열된 값을 실제 DB 값으로 보고 글자 그대로 조건에 넣을 수 있습니다.</Li>
          <Li>테이블마다 표기가 다를 수 있습니다. 고교구분 테이블은 <Code>전남광주통합특별시(광주)</Code>/<Code>(전남)</Code>으로 나뉘어 있어, 그 테이블의 <Code>시도명</Code> 힌트에 따로 적어 두었습니다.</Li>
          <Li>이름 보정은 지난 학년도 값도 기억합니다. "2024~2027 강원" 처럼 옛 학년도가 포함되면 <Code>'강원도'</Code>를 그대로 두고, "2027 강원도" 처럼 최근 학년도만이면 <Code>'강원특별자치도'</Code>로 고칩니다.</Li>
        </Ul>
        <Tip>앞으로 시도·학과·전형 이름이 또 바뀌면, 이 힌트에 "옛 이름 → 새 이름(몇 학년도부터)" 한 줄만 추가하면 됩니다.</Tip>

        <H>열 힌트와 지표 사전의 차이</H>
        <Table
          head={['', '열 힌트', '지표 사전']}
          rows={[
            ['설명 대상', '열 하나의 뜻', '숫자 하나의 계산법'],
            ['쓰는 주체', 'AI 가 읽고 참고', '시스템이 정의를 그대로 SQL 에 사용'],
            ['쓰이는 곳', '모든 질문', '엑셀 격자 채우기, "쿼리 만들어줘"'],
            ['비유', '재료 설명', '레시피'],
          ]}
        />
        <QueryGuide />
      </>
    ),
  },
  knowledge: {
    title: '사전지식',
    body: (
      <>
        <H>이 화면은</H>
        <P>AI 가 질문을 해석하고 SQL 을 설계할 때 가장 먼저 지키는 업무 규칙입니다. (예: "편입 포함 말이 없으면 신입만 조회")</P>
        <Ul>
          <Li>숫자의 계산법(지원인원·등록인원 정의 등)은 사전지식보다 <b>지표 사전</b>에 두는 것이 정확합니다. 지표 사전은 시스템이 정의를 그대로 쓰기 때문입니다.</Li>
          <Li>엑셀 채우기에서 "다음에도 이 기준 사용"으로 저장한 계산 기준은 <Code>[통계 기본 기준]</Code> 한 건으로 저장됩니다. (예: 합격인원 = 합격인원(최초))</Li>
        </Ul>
        <H>[통계 기본 기준] 이 쓰이는 곳</H>
        <Ul>
          <Li><b>엑셀 채우기</b>: 정의가 둘 이상인 지표(합격인원·등록인원 등)를 묻지 않고 이 기준으로 채웁니다.</Li>
          <Li><b>"쿼리 만들어줘"</b>: 질문에 정의가 없으면 이 기준을 씁니다. 순서는 <b>질문에서 지정 → 저장된 기본값 → 지표 사전 기본 정의</b>입니다. 답변의 '가정한 내용'에 근거와 다른 정의가 함께 나오므로 필요하면 "최종합격 기준으로" 처럼 다시 요청하세요.</Li>
          <Li>비율(등록율 등)의 분자·분모는 같은 표의 합격인원·등록인원과 같은 정의를 씁니다. 그래도 비율이 100% 를 넘으면 엑셀·쿼리 모두 "⚠️ 비율 100% 초과" 경고가 나옵니다. 보통 '충원 포함 등록 ÷ 최초합격'처럼 기준이 엇갈린 경우입니다.</Li>
        </Ul>
        <H>사례: 권역 정의 (부울경)</H>
        <P>여러 값을 묶은 업무 용어는 <b>정확한 값 목록 + 나눠 달라고 할 때의 묶는 법</b>을 함께 적습니다.</P>
        <Ul>
          <Li>조건: <Code>{"[출신고교시도] IN (N'부산광역시', N'울산광역시', N'경상남도')"}</Code> — 정확히 비교하고 <b>LIKE·OR 로 풀지 말 것</b>. (괄호 없이 OR 로 이으면 학년도 조건이 일부에만 걸려 숫자가 부풀 수 있음)</Li>
          <Li>'부울경과 그 외'로 나눌 때: <Code>{"CASE WHEN … IN (…) THEN N'부울경' WHEN … IS NULL OR … = '' THEN N'미상' ELSE N'그 외' END"}</Code></Li>
          <Li>세 시도는 이름이 바뀐 적이 없어 학년도와 관계없이 같은 목록을 씁니다. 이름이 바뀐 시도는 '정형 데이터(DB)' 도움말의 시도명 사례처럼 열 힌트에 적습니다.</Li>
        </Ul>
        <Tip>같은 규칙을 사전지식과 다른 곳(코드·힌트)에 겹쳐 적지 마세요. 한쪽만 고치면 낡은 쪽을 AI 가 따를 수 있습니다.</Tip>
      </>
    ),
  },
  values: {
    title: '실제 값 현황',
    body: (
      <>
        <H>이 화면은</H>
        <P>구분 열(전형명·학과명·모집구분 등)에 DB 에 실제로 들어 있는 값을 학년도별로 보여 줍니다. 이 값들은 두 곳에 쓰입니다.</P>
        <Ul>
          <Li><b>AI 가 보는 스키마</b>에 함께 붙습니다. 예: <Code>└ [전형명] 실제 값 (2027: 일반고, 특성화고, 기초생활수급자 …)</Code></Li>
          <Li><b>이름 보정</b>: 질문의 '기초생활', '간호'를 실제 값 '기초생활수급자', '간호학부'로 고쳐 조회합니다.</Li>
        </Ul>
        <P>값 목록은 1시간마다(또는 [지금 새로고침]) 다시 읽으므로, 2028학년도 데이터가 올라오면 새 전형도 자동으로 반영됩니다. 🆕 는 새로 생긴 값, ➖ 는 사라진 값입니다.</P>

        <H>포함 / 자동 / 제외 버튼</H>
        <Tip><b>쿼리 조건과는 관계없습니다.</b> 어떤 버튼을 골라도 조회 결과에서 데이터가 빠지지 않습니다. 정하는 것은 "이 열의 값 목록을 AI 에게 보여 주고 이름 보정에 쓸지" 하나뿐입니다.</Tip>
        <Table
          head={['버튼', '뜻', '전형명 열의 예']}
          rows={[
            [<b>자동</b>, '기본값. 시스템 규칙으로 판단 (숫자·번호 위주, 값이 너무 많음, 큰 테이블인데 힌트 없음 → 뺌)', '값 13개 정도의 구분 열이라 자동 포함'],
            [<b>포함</b>, '규칙과 상관없이 항상 넣음. 큰 테이블에서 힌트가 없어 빠진 구분 열을 살릴 때', '(이미 포함이라 필요 없음)'],
            [<b>제외</b>, '값 목록을 보여 주지 않음. AI 는 열 이름과 힌트만 봄', "'기초생활'을 고쳐 주지 못해 0건이 나올 수 있음"],
          ]}
        />
        <P>제외는 값 목록이 오히려 방해되는 열(의미 없는 코드값, 해마다 수백 개씩 바뀌는 값)에만 쓰세요. 각 열 옆에 포함·제외된 이유가 적혀 있습니다.</P>

        <H>표기 점검 · 기존 데이터 맞추기 (업로드한 EXCEL_ 테이블)</H>
        <Ul>
          <Li>업로드한 표의 값을 같은 뜻의 기준 열(값이 가장 많이 겹치는 열, 입시마스타 우선)과 비교합니다.</Li>
          <Li><b>바꿀 항목</b>: 띄어쓰기만 다른 값 등 (예: '재외국민 및 외국인' → '재외국민및외국인'). [맞추기]를 누르면 이 항목만 고칩니다.</Li>
          <Li><b>기준 열에 없는 값</b>: 안내만 하고 <b>절대 바꾸지 않습니다.</b></Li>
          <Li>엑셀을 새로 업로드할 때도 같은 점검이 자동으로 돌아 띄어쓰기 차이를 맞춥니다. 2028학년도 데이터를 올릴 때 직접 고치실 필요가 없습니다.</Li>
        </Ul>
        <Tip>고교구분 테이블처럼 기준이 될 열이 사실상 없는 표는 결과를 참고만 하세요. 예: 시도명은 입시마스타(지원자가 있는 지역만)보다 고교 테이블(전국 모든 고교)에 값이 더 많아 '없는 값'으로 나오고, 고등학교구분명은 '일반고·특성화고' 글자가 겹쳐 전형명이 기준으로 잡히지만 의미는 없습니다.</Tip>
      </>
    ),
  },
  faq: {
    title: '입학처 Q&A',
    body: (
      <>
        <H>이 화면은</H>
        <P>학생들이 자주 묻는 질문에 대한 <b>입학처 공식 답변</b>을 등록하는 곳입니다. 학생 챗봇과 교직원 챗봇이 답할 때 함께 참고하며, 문서 내용보다 이 답변을 우선 기준으로 안내합니다. 저장하면 다음 질문부터 바로 반영됩니다. (예전처럼 텍스트 파일을 다시 올릴 필요가 없습니다.)</P>

        <H>적용 학년도</H>
        <Table
          head={['적용 학년도', '언제 쓰이나', '예']}
          rows={[
            ['공통', '매년, 어떤 학년도 질문에도', '기숙사 있어요? → 있습니다'],
            ['2027학년도', '2027학년도 입시 질문에만', '만학도 기준 출생일 (해마다 바뀜)'],
          ]}
        />
        <Ul>
          <Li>질문에 학년도가 없으면 화면 상단 <b>기준 입시학년도</b>의 Q&A 와 공통 Q&A 를 씁니다. 기준 학년도는 날짜로 자동으로 바뀌지 않으므로, 지난 학년도 통계 업무가 끝나는 시점(예: 4월 말)에 직접 바꿔 주세요.</Li>
          <Li>"2026학년도", "작년"처럼 학년도를 말하면 그 학년도의 Q&A 와 공통 Q&A 를 씁니다.</Li>
          <Li>같은 주제가 공통과 특정 학년도에 모두 있으면 그 학년도 답변만 씁니다. 해마다 바뀌는 부분만 학년도 Q&A 로 따로 등록하면 됩니다.</Li>
        </Ul>
        <Tip>기준 입시학년도를 바꾸면 지난 학년도 Q&A 는 자동으로 쓰이지 않습니다. 새 학년도에도 맞는 내용이면 적용 학년도만 바꾸거나 공통으로 바꾸세요.</Tip>

        <H>등록 방법</H>
        <Ul>
          <Li><b>여기서 직접</b>: [Q&A 추가] → 주제·답변·적용 학년도 입력</Li>
          <Li><b>감사 로그에서</b>: 로그 상세의 <b>[답변 등록]</b> → 질문과 AI 답변이 채워진 창이 열리면 공식 답변으로 고쳐 등록 (어느 로그에서 등록했는지 함께 남음)</Li>
          <Li>잠시 빼려면 [사용 중지], 완전히 지우려면 휴지통</Li>
        </Ul>

        <H>분량</H>
        <P>사용 중인 Q&A 가 약 3,000 토큰 이하이면 해당 학년도 Q&A 를 모두 넣고, 넘으면 AI 가 주제 목록을 보고 질문에 맞는 주제만 골라 넣습니다. 그래서 주제(제목)를 내용이 드러나게 적어 두는 것이 좋습니다. (기준은 서버 설정 <Code>FAQ_ALL_TOKENS</Code>)</P>
      </>
    ),
  },
  metrics: {
    title: '지표 사전',
    body: (
      <>
        <H>이 화면은</H>
        <P>자주 쓰는 숫자의 <b>정확한 계산법</b>을 등록하는 곳입니다. 엑셀 격자 채우기와 "쿼리 만들어줘" 요청에서 AI 는 설계도(어떤 지표를 무엇별로, 어떤 조건으로)만 고르고, SQL 은 시스템이 여기 정의대로 조립합니다. 같은 질문에는 항상 같은 숫자가 나옵니다.</P>

        <H>① 지표</H>
        <Ul>
          <Li><b>계산식</b>: 예 <Code>COUNT(*)</Code>, <Code>{"SUM(CASE WHEN [최종입시결과] = '최종등록자' THEN 1 ELSE 0 END)"}</Code></Li>
          <Li><b>기본 조건</b>: 이 지표에 항상 붙는 조건. 예 <Code>{"[신입편입구분] = '신입'"}</Code></Li>
          <Li><b>종류</b>: 건수 / 숫자 / 글자 섞임(모집인원의 '제한없음'처럼 글자가 섞인 열. 쿼리에서는 숫자만 합산하고 주석으로 표시)</Li>
          <Li><b>비슷한 말</b>: 질문에 쓰는 다른 표현 (예: 지원자수, 지원자)</Li>
          <Li>저장하기 전에 서버가 계산식을 실제로 한 번 실행해 봅니다. 열 이름이 틀리거나 위험한 문구(DROP 등)가 있으면 저장되지 않습니다.</Li>
        </Ul>
        <Tip><b>뜻이 둘 이상인 지표는 괄호로 나눠 이름을 지으세요.</b> 예: <Code>등록인원(전체)</Code> / <Code>등록인원(최초합격자 중)</Code>. 괄호 앞 이름이 같으면 한 묶음이 되어, 엑셀 채우기의 [기준 바꿔서 다시 채우기] 선택지로 나옵니다. 기준을 바꾸면 AI 호출 없이 정의만 바꿔 다시 조립합니다.</Tip>

        <H>② 구분 (무엇별로 나누고, 무엇으로 거를지)</H>
        <P>같은 뜻이 테이블마다 다른 열 이름으로 들어 있어서, 구분명마다 "이 테이블에서는 이 열"이라고 정해 둔 목록입니다.</P>
        <Table
          head={['구분명', '입시마스타', '모집인원 표', '입학정원 표']}
          rows={[
            ['학과', '지원학과명', '모집학과명', '학과'],
            ['모집구분', '모집구분명', '모집구분', '—'],
            ['전형', '전형명', '전형명', '—'],
          ]}
        />
        <P>예: "2026 수시1차 학과별 모집인원·지원인원 쿼리" → AI 는 <i>지표 = 모집인원·지원인원, 행 = 학과, 조건 = 모집구분: 수시1차</i> 만 정합니다. 시스템이 모집인원 표는 <Code>모집학과명</Code>·<Code>[모집구분]</Code>, 입시마스타는 <Code>지원학과명</Code>·<Code>[모집구분명]</Code> 으로 묶고 거른 뒤, 학과끼리 이어 붙입니다. 테이블에 그 구분이 없으면 "합쳐서 계산"이라고 안내합니다.</P>
        <Ul>
          <Li><b>열 힌트와의 차이</b>: 힌트는 AI 가 읽고 참고만 하므로 열을 잘못 고를 수 있습니다. 구분은 AI 가 구분 이름만 고르고 실제 열 이름은 시스템이 넣으므로 헷갈릴 여지가 없습니다.</Li>
          <Li><b>언제 추가하나</b>: 나누는 기준이 새로 필요할 때. 예: 구분명 <Code>지역</Code> / 테이블 <Code>UI_IPSI_M_V</Code> / 열 <Code>출신고교시도</Code></Li>
        </Ul>
        <Tip>구분에는 '비슷한 말' 칸이 없으니 <b>설명 칸에 비슷한 말을 적으세요.</b> 예: 지역 → 설명 "시도, 시도별, 출신지역, 출신고교 소재지". AI 가 '시도별', '출신지역별' 같은 표현을 이 구분으로 연결합니다. 혹시 AI 가 사전에 없는 구분명을 쓰면 설계도를 버리고 AI 가 직접 쓴 SQL 로 진행하므로 엉뚱한 결과가 나오지는 않습니다.</Tip>
        <QueryGuide />
      </>
    ),
  },
};

export default function HelpDrawer({ tab, open, onClose }: { tab: string; open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  const help = HELP[tab] || HELP.documents;
  return createPortal(
    <div className="fixed inset-0 z-[9999] flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="relative w-full max-w-xl h-full bg-white shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-gradient-to-r from-indigo-900 to-purple-900 text-white">
          <div className="flex items-center gap-2 font-extrabold">
            <BookOpen size={18} className="text-amber-400" /> 설명서 · {help.title}
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/10" aria-label="닫기"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{help.body}</div>
      </aside>
    </div>,
    document.body
  );
}
