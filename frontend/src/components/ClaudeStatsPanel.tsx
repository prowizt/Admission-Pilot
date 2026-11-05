import { useEffect, useState } from 'react';
import axios from 'axios';
import { RefreshCw, X } from 'lucide-react';
import ClaudeCreditCard from '@/components/ClaudeCreditCard';

// [Claude 사용 통계] 일별(최근 31일) / 월별(최근 12개월) 건수·원화·달러, 학생/교직원 필터
// 건수와 금액은 단위가 달라 차트를 따로 그림 (두 눈금을 한 차트에 겹치지 않음)
type Row = { period: string; count: number; krw: number; usd: number; student_count: number; staff_count: number; student_krw: number; staff_krw: number; test_count: number; test_krw: number };

const BAR = '#2a78d6';   // 단일 계열 색 (파랑)
const BAR_HOVER = '#1c5cab';
const fmt = (n: number, d = 0) => n.toLocaleString('ko-KR', { maximumFractionDigits: d });
const usd = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function ColumnChart({ title, rows, value, tip, onPick }: {
  title: string; rows: Row[]; value: (r: Row) => number; tip: (r: Row) => string[];
  onPick?: (r: Row) => void;  // 월별 막대를 누르면 그달 일별로
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(0, ...rows.map(value)));
  const ticks = [max, max / 2, 0];
  const H = 160;
  const every = rows.length > 20 ? 5 : rows.length > 12 ? 2 : 1; // x축 글자 겹침 방지
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-3 min-w-0">
      <div className="text-sm font-bold text-slate-700 mb-2">{title}</div>
      <div className="flex min-w-0">
        <div className="relative shrink-0 w-12 text-right pr-1.5" style={{ height: H }}>
          {ticks.map((t, i) => (
            <div key={i} className="absolute right-1.5 text-[10px] text-slate-400 -translate-y-1/2" style={{ top: (i / 2) * H }}>{fmt(t, t < 10 ? 1 : 0)}</div>
          ))}
        </div>
        <div className="relative flex-1 min-w-0" style={{ height: H }} onMouseLeave={() => setHover(null)}>
          {ticks.map((_, i) => <div key={i} className={`absolute left-0 right-0 border-t ${i === 2 ? 'border-slate-300' : 'border-slate-100'}`} style={{ top: (i / 2) * H }} />)}
          <div className="absolute inset-0 flex items-end gap-[2px]">
            {rows.map((r, i) => {
              const v = value(r);
              const h = v > 0 ? Math.max(2, (v / max) * H) : 0;
              return (
                <div key={r.period} className={`relative flex-1 h-full flex items-end justify-center ${onPick ? 'cursor-pointer' : 'cursor-default'}`}
                     onMouseEnter={() => setHover(i)} tabIndex={0} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
                     onClick={() => onPick?.(r)} onKeyDown={e => { if (onPick && e.key === 'Enter') onPick(r); }}
                     aria-label={`${r.period}: ${tip(r).join(', ')}`}>
                  <div style={{ height: h, maxWidth: 24, background: hover === i ? BAR_HOVER : BAR, borderRadius: '4px 4px 0 0' }} className="w-full" />
                  {hover === i && (
                    <div className={`absolute bottom-full mb-1 z-10 whitespace-nowrap rounded-md bg-slate-900 text-white text-[11px] px-2 py-1 shadow-lg pointer-events-none ${i > rows.length * 0.7 ? 'right-0' : i < rows.length * 0.3 ? 'left-0' : 'left-1/2 -translate-x-1/2'}`}
                         style={{ marginBottom: 4 }}>
                      <div className="font-bold">{r.period}</div>
                      {tip(r).map((t, k) => <div key={k}>{t}</div>)}
                      {onPick && <div className="text-slate-300 mt-0.5">누르면 그달 일별 보기</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="flex ml-12 gap-[2px] mt-1">
        {rows.map((r, i) => (
          <div key={r.period} className="flex-1 text-center text-[10px] text-slate-400 overflow-visible whitespace-nowrap">
            {i % every === 0 || i === rows.length - 1 ? (r.period.length > 7 ? r.period.slice(5) : r.period.slice(2)) : ''}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ClaudeStatsPanel() {
  const [unit, setUnit] = useState<'day' | 'month'>('day');
  const [role, setRole] = useState<'all' | 'student' | 'staff'>('all');
  const [excludeTest, setExcludeTest] = useState(false); // '[테스트]' 표시된 시험 질문 빼고 보기
  const [month, setMonth] = useState('');  // 일별: '' = 최근 31일, 'YYYY-MM' = 그달
  const [year, setYear] = useState('');    // 월별: '' = 최근 12개월, 'YYYY' = 그해 1~12월
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setBusy(true);
      const res = await axios.get('/api/stats/claude', { params: { unit, role, exclude_test: excludeTest, month: unit === 'day' ? month : '', year: unit === 'month' ? year : '' } });
      setData(res.data); setErr('');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || '통계를 불러오지 못했습니다. 백엔드를 재시작했는지 확인해 주세요.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { load(); }, [unit, role, excludeTest, month, year]);

  // 월별에서 달을 누르면 그달 일별로
  const pickMonth = (r: Row) => { setMonth(r.period); setUnit('day'); };
  const firstMonth: string = data?.first_month || '';
  const thisMonth: string = data?.this_month || '';
  const years: string[] = [];
  if (firstMonth && thisMonth) for (let y = Number(thisMonth.slice(0, 4)); y >= Number(firstMonth.slice(0, 4)); y--) years.push(String(y));
  const fieldCls = 'border border-slate-300 rounded-md px-2 py-1 text-xs bg-white text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500';

  const seg = (on: boolean) => `px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${on ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`;
  const rows: Row[] = data?.rows || [];
  const unitLabel = unit === 'day' ? (month ? `${month.replace('-', '년 ')}월` : '최근 31일') : (year ? `${year}년` : '최근 12개월');
  const roleLabel = { all: '전체', student: '학생', staff: '교직원' }[role];
  const tipLines = (r: Row) => [
    `${fmt(r.count)}건 · ${fmt(r.krw)}원 · ${usd(r.usd)}`,
    ...(role === 'all' ? [`학생 ${fmt(r.student_count)}건 ${fmt(r.student_krw)}원 / 교직원 ${fmt(r.staff_count)}건 ${fmt(r.staff_krw)}원`] : []),
    ...(r.test_count ? [`그중 테스트 ${fmt(r.test_count)}건 ${fmt(r.test_krw)}원`] : []),
  ];
  const active = rows.filter(r => r.count > 0);

  return (
    <div className="space-y-4 min-w-0">
      <ClaudeCreditCard onSynced={load} />

      {/* 필터 한 줄 */}
      <div className="bg-white p-3 rounded-xl shadow-sm border border-gray-200 flex flex-wrap items-center gap-3">
        {/* [최근] 다른 달·연도를 보다가 한 번에 최근(31일/12개월)으로 돌아옴 */}
        <button className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-colors whitespace-nowrap ${(unit === 'day' ? !month : !year) ? 'border-indigo-300 bg-indigo-50 text-indigo-700' : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'}`}
                onClick={() => { setMonth(''); setYear(''); }}
                title={unit === 'day' ? '최근 31일' : '최근 12개월'}>
          최근
        </button>
        <div className="flex bg-slate-100 p-1 rounded-lg">
          <button className={seg(unit === 'day')} onClick={() => setUnit('day')}>일별</button>
          <button className={seg(unit === 'month')} onClick={() => setUnit('month')}>월별</button>
        </div>
        {/* 기간: 일별은 달 선택, 월별은 연도 선택 */}
        {unit === 'day' ? (
          <div className="flex items-center gap-1">
            <input type="month" value={month} onChange={e => setMonth(e.target.value)} title="달 선택 (비우면 최근 31일)"
                   min={firstMonth || undefined} max={thisMonth || undefined} className={fieldCls} />
            {month
              ? <button onClick={() => setMonth('')} title="최근 31일로" className="text-slate-400 hover:text-slate-600"><X size={14} /></button>
              : <span className="text-[11px] text-slate-400 whitespace-nowrap">최근 31일</span>}
          </div>
        ) : (
          <select value={year} onChange={e => setYear(e.target.value)} className={fieldCls}>
            <option value="">최근 12개월</option>
            {years.map(y => <option key={y} value={y}>{y}년</option>)}
          </select>
        )}
        <div className="flex bg-slate-100 p-1 rounded-lg">
          <button className={seg(role === 'all')} onClick={() => setRole('all')}>전체</button>
          <button className={seg(role === 'student')} onClick={() => setRole('student')}>학생</button>
          <button className={seg(role === 'staff')} onClick={() => setRole('staff')}>교직원</button>
        </div>
        <label className="flex items-center gap-1.5 text-xs font-bold text-slate-600 cursor-pointer select-none">
          <input type="checkbox" checked={excludeTest} onChange={e => setExcludeTest(e.target.checked)} className="accent-indigo-600" />
          테스트 제외
        </label>
        <button className="ml-auto px-2 py-1 text-[11px] font-bold rounded-md border border-slate-300 text-slate-600 bg-white hover:bg-slate-50" onClick={load} disabled={busy}>
          <RefreshCw size={12} className={`inline ${busy ? 'animate-spin' : ''}`} /> 새로 고침
        </button>
      </div>

      {err && <div className="text-sm text-red-600">{err}</div>}

      {data && (
        <>
          {/* 합계 */}
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-3">
            {[
              ['질문 수', `${fmt(data.total.count)}건`, `${unitLabel} · ${roleLabel}${excludeTest ? ' · 테스트 제외' : data.total.test_count ? ` · 그중 테스트 ${fmt(data.total.test_count)}건 ${fmt(data.total.test_krw)}원` : ''}`],
              ['원화 (부가세 포함)', `${fmt(data.total.krw)}원`, active.length ? `하루·한 달 평균 ${fmt(data.total.krw / active.length)}원 (사용한 ${unit === 'day' ? '날' : '달'} 기준)` : '사용 없음'],
              ['달러 (콘솔 차감 기준)', usd(data.total.usd), `건당 평균 ${data.total.count ? usd(data.total.usd / data.total.count) : '-'}`],
            ].map(([k, v, sub]) => (
              <div key={k} className="bg-white rounded-xl border border-gray-200 px-4 py-3">
                <div className="text-[11px] font-bold text-slate-500">{k}</div>
                <div className="text-xl font-extrabold text-slate-800 font-mono">{v}</div>
                <div className="text-[11px] text-slate-500">{sub}</div>
              </div>
            ))}
          </div>

          <div className="grid gap-3 lg:grid-cols-2 min-w-0">
            <ColumnChart title={`${unit === 'day' ? '일별' : '월별'} 질문 수 (건) · ${unitLabel}`} rows={rows} value={r => r.count} tip={tipLines} onPick={unit === 'month' ? pickMonth : undefined} />
            <ColumnChart title={`${unit === 'day' ? '일별' : '월별'} 비용 (원, 부가세 포함) · ${unitLabel}`} rows={rows} value={r => r.krw} tip={tipLines} onPick={unit === 'month' ? pickMonth : undefined} />
          </div>

          {/* 표 (정확한 숫자) */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden min-w-0">
            <div className="overflow-x-auto max-h-[360px]">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-slate-600">
                    <th className="text-left px-3 py-2 font-bold">{unit === 'day' ? '날짜' : '월'}</th>
                    <th className="text-right px-3 py-2 font-bold">건수</th>
                    <th className="text-right px-3 py-2 font-bold">원화</th>
                    <th className="text-right px-3 py-2 font-bold">달러</th>
                    {!excludeTest && <th className="text-right px-3 py-2 font-bold">테스트 (건 / 원)</th>}
                    {role === 'all' && <th className="text-right px-3 py-2 font-bold">학생 (건 / 원)</th>}
                    {role === 'all' && <th className="text-right px-3 py-2 font-bold">교직원 (건 / 원)</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {[...active].reverse().map(r => (
                    <tr key={r.period} className={`text-slate-700 ${unit === 'month' ? 'cursor-pointer hover:bg-indigo-50/60' : ''}`}
                        onClick={unit === 'month' ? () => pickMonth(r) : undefined} title={unit === 'month' ? '누르면 그달 일별 보기' : undefined}>
                      <td className={`px-3 py-1.5 font-mono ${unit === 'month' ? 'text-indigo-700 font-bold underline decoration-dotted underline-offset-2' : ''}`}>{r.period}</td>
                      <td className="px-3 py-1.5 text-right font-mono">{fmt(r.count)}</td>
                      <td className="px-3 py-1.5 text-right font-mono">{fmt(r.krw)}</td>
                      <td className="px-3 py-1.5 text-right font-mono">{usd(r.usd)}</td>
                      {!excludeTest && <td className="px-3 py-1.5 text-right font-mono text-slate-400">{r.test_count ? `${fmt(r.test_count)} / ${fmt(r.test_krw)}` : '-'}</td>}
                      {role === 'all' && <td className="px-3 py-1.5 text-right font-mono">{fmt(r.student_count)} / {fmt(r.student_krw)}</td>}
                      {role === 'all' && <td className="px-3 py-1.5 text-right font-mono">{fmt(r.staff_count)} / {fmt(r.staff_krw)}</td>}
                    </tr>
                  ))}
                  {active.length === 0 && <tr><td colSpan={7} className="px-3 py-6 text-center text-slate-400">이 기간에 Claude 사용 기록이 없습니다.</td></tr>}
                </tbody>
                {/* [합계] 표 맨 아래 고정 — 스크롤해도 보임 */}
                {active.length > 0 && (
                  <tfoot className="sticky bottom-0 bg-indigo-50 border-t-2 border-indigo-200">
                    <tr className="text-indigo-900 font-bold">
                      <td className="px-3 py-2">합계 <span className="font-normal text-[11px] text-indigo-700">({unitLabel} · {fmt(active.length)}{unit === 'day' ? '일' : '개월'})</span></td>
                      <td className="px-3 py-2 text-right font-mono">{fmt(data.total.count)}</td>
                      <td className="px-3 py-2 text-right font-mono">{fmt(data.total.krw)}</td>
                      <td className="px-3 py-2 text-right font-mono">{usd(data.total.usd)}</td>
                      {!excludeTest && <td className="px-3 py-2 text-right font-mono">{data.total.test_count ? `${fmt(data.total.test_count)} / ${fmt(data.total.test_krw)}` : '-'}</td>}
                      {role === 'all' && <td className="px-3 py-2 text-right font-mono">{fmt(active.reduce((a, r) => a + r.student_count, 0))} / {fmt(active.reduce((a, r) => a + r.student_krw, 0))}</td>}
                      {role === 'all' && <td className="px-3 py-2 text-right font-mono">{fmt(active.reduce((a, r) => a + r.staff_count, 0))} / {fmt(active.reduce((a, r) => a + r.staff_krw, 0))}</td>}
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>

          <div className="text-[11px] text-slate-400 px-1">
            감사 로그에 기록된 Claude 호출 기준(라우터·답변 합계)의 대략값입니다. 질문에 [테스트]가 붙은 기록은 시험 호출입니다(실제 비용이라 지우지 않고 표시만 함). 원화는 기록할 때의 환율, 달러는 현재 환율 {fmt(data.krw_per_usd)}원·부가세 {Math.round(data.vat_rate * 100)}%로 되돌린 값입니다.
          </div>
        </>
      )}
    </div>
  );
}
