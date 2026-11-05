import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { RefreshCw, Search, ChevronDown, ChevronRight } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';

// [실제 값 현황] 값 사전(AI 에게 주는 구분 열의 학년도별 실제 값) 현황 + 열별 포함/제외 지정
type ValueItem = { value: string; count: number };
type ColumnStatus = {
  table: string; table_kr: string; column: string; mode: string; included: boolean; reason: string;
  row_count: number; years: { year: string; values: ValueItem[] }[]; new_values: string[]; removed_values: string[];
};

const MODES = [
  { value: 'Y', label: '포함', on: 'bg-white text-emerald-600 shadow-sm' },
  { value: 'AUTO', label: '자동', on: 'bg-white text-indigo-700 shadow-sm' },
  { value: 'N', label: '제외', on: 'bg-white text-red-600 shadow-sm' },
];

export default function ValueDictionaryPanel() {
  const [columns, setColumns] = useState<ColumnStatus[]>([]);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'included' | 'excluded' | 'changed'>('included');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  // [기존 데이터 맞추기] 엑셀 업로드 테이블마다 아직 맞추지 않은 표기 건수 (눌러 보지 않아도 표시)
  const [labelSummary, setLabelSummary] = useState<Record<string, { fix: number; fix_rows: number; unknown: number }>>({});
  const loadLabelSummary = async () => {
    try {
      const res = await axios.get('/api/value-dictionary/label-check-summary');
      setLabelSummary(res.data.tables || {});
    } catch { /* 건수 표시는 보조 기능이라 실패해도 화면은 그대로 */ }
  };

  const apply = (data: any) => {
    setColumns(data.columns || []);
    setRefreshedAt(data.refreshed_at || null);
  };

  const load = async (refresh = false) => {
    try {
      setBusy(true);
      const res = refresh ? await axios.post('/api/value-dictionary/refresh') : await axios.get('/api/value-dictionary');
      apply(res.data);
      if (refresh) loadLabelSummary();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: e?.response?.data?.detail || '값 사전을 불러오지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { load(); loadLabelSummary(); }, []);

  const setMode = async (c: ColumnStatus, mode: string) => {
    if (c.mode === mode) return;
    try {
      setBusy(true);
      const res = await axios.put('/api/value-dictionary/mode', { table_name: c.table, column_name: c.column, mode });
      apply(res.data);
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: e?.response?.data?.detail || '지정하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  // [기존 데이터 맞추기] 엑셀 업로드 테이블의 표기를 원본 시스템(입시마스타 등) 표기와 대조 → 미리보기 후 UPDATE
  const checkLabels = async (table: string) => {
    try {
      setBusy(true);
      const res = await axios.get(`/api/value-dictionary/label-check/${table}`);
      const items: any[] = res.data.items || [];
      const fixes = items.filter(i => i.kind === 'fix');
      const unknown = items.filter(i => i.kind === 'unknown');
      const esc = (s: string) => String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch] as string));
      const html = `<div style="text-align:left;font-size:13px;line-height:1.6">`
        + (fixes.length ? `<b>바꿀 표기 (${fixes.length}건)</b><br/>` + fixes.map(f => `· [${esc(f.column)}] '${esc(f.from)}' → '${esc(f.to)}' (${f.rows}행, 기준 ${esc(f.ref)})`).join('<br/>') : '<b>바꿀 표기 없음</b>')
        + (unknown.length ? `<br/><br/><b>기준 열에 없는 값 ${unknown.length}건 (그대로 둠, 신규 값이면 정상)</b><br/>` + unknown.map(u => `· [${esc(u.column)}] '${esc(u.from)}' (${u.rows}행, 기준 ${esc(u.ref)})`).join('<br/>') : '')
        + `</div>`;
      const ans = await CustomSwal.fire({
        title: `${table} 표기 점검`, html, width: 640,
        showCancelButton: fixes.length > 0, confirmButtonText: fixes.length ? `${fixes.length}건 맞추기` : '확인', cancelButtonText: '취소',
      });
      if (ans.isConfirmed && fixes.length) {
        const r2 = await axios.post(`/api/value-dictionary/label-fix/${table}`, { fixes: fixes.map(f => ({ column: f.column, from: f.from, to: f.to })) });
        const done: any[] = r2.data.done || [];
        CustomSwal.fire({ icon: 'success', title: '맞춤 완료', text: `${done.length}건, 총 ${done.reduce((s, d) => s + d.rows, 0)}행을 고쳤습니다.` });
        await load();
      }
      await loadLabelSummary();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: e?.response?.data?.detail || '표기 점검에 실패했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  const shown = useMemo(() => columns.filter(c => {
    if (filter === 'included' && !c.included) return false;
    if (filter === 'excluded' && c.included) return false;
    if (filter === 'changed' && !(c.new_values.length || c.removed_values.length)) return false;
    const q = query.trim().toLowerCase();
    return !q || `${c.table} ${c.table_kr} ${c.column}`.toLowerCase().includes(q)
      || c.years.some(y => y.values.some(v => v.value.toLowerCase().includes(q)));
  }), [columns, filter, query]);

  const byTable = useMemo(() => {
    const m: Record<string, ColumnStatus[]> = {};
    shown.forEach(c => { (m[c.table] = m[c.table] || []).push(c); });
    return m;
  }, [shown]);

  const counts = {
    all: columns.length,
    included: columns.filter(c => c.included).length,
    excluded: columns.filter(c => !c.included).length,
    changed: columns.filter(c => c.new_values.length || c.removed_values.length).length,
  };
  const filterBtn = (key: typeof filter, label: string) => (
    <button key={key} onClick={() => setFilter(key)}
      className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${filter === key ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
      {label} ({counts[key]})
    </button>
  );

  return (
    <div className="space-y-4 min-w-0">
      <div className="bg-white p-3 md:p-4 rounded-xl shadow-sm border border-gray-200 flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3 min-w-0">
        <div className="flex bg-slate-100 p-1 rounded-lg shrink-0 overflow-x-auto custom-scrollbar max-w-full">
          {filterBtn('included', 'AI 에게 주는 열')}
          {filterBtn('excluded', '제외된 열')}
          {filterBtn('changed', '학년도 변화 있음')}
          {filterBtn('all', '전체')}
        </div>
        <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto items-center min-w-0">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input type="text" placeholder="테이블, 열, 값 검색..." value={query} onChange={e => setQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 outline-none" />
          </div>
          <div className="text-xs text-slate-500 whitespace-nowrap">마지막 갱신: {refreshedAt || '-'} (1시간마다 자동)</div>
          <button onClick={() => load(true)} disabled={busy}
            className="w-full sm:w-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-md flex items-center justify-center gap-1.5 whitespace-nowrap">
            <RefreshCw size={14} className={busy ? 'animate-spin' : ''} /> 지금 새로고침
          </button>
        </div>
      </div>

      {Object.entries(labelSummary).some(([, v]) => v.fix > 0) && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-sm text-amber-900 flex flex-wrap items-center gap-2">
          <b>아직 맞추지 않은 표기가 있습니다:</b>
          {Object.entries(labelSummary).filter(([, v]) => v.fix > 0).map(([t, v]) => (
            <button key={t} onClick={() => checkLabels(t)} disabled={busy}
              className="px-2 py-0.5 text-xs font-bold rounded-md bg-white border border-amber-300 hover:bg-amber-100 disabled:opacity-50">
              {t} {v.fix}건
            </button>
          ))}
        </div>
      )}

      <div className="text-xs text-slate-500 px-1">
        AI 는 SQL 을 만들 때 아래 '실제 값'을 보고 조건 값을 고르고, 서버는 SQL 의 조건 값을 이 목록과 대조해 고칩니다.
        숫자·번호·개인정보 열은 포함하지 마세요. [자동]은 열 설명이 있거나 작은 테이블의 문자 열을 넣습니다.
      </div>

      {Object.keys(byTable).length === 0 && (
        <div className="bg-white p-8 rounded-xl border border-gray-200 text-center text-sm text-slate-400">{busy ? '불러오는 중...' : '해당하는 열이 없습니다.'}</div>
      )}

      {Object.entries(byTable).map(([table, cols]) => (
        <div key={table} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
          <div className="px-4 py-2.5 bg-slate-50 border-b border-gray-200 text-sm font-bold text-slate-700 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{cols[0].table_kr}</span>
            <span className="text-slate-400 font-normal">{table} · {cols[0].row_count.toLocaleString()}행</span>
            {table.toUpperCase().startsWith('EXCEL_') && (() => {
              const sm = labelSummary[table];
              const pending = sm ? sm.fix : 0;
              return (
                <span className="ml-auto flex items-center gap-1.5">
                  {sm && (pending > 0
                    ? <span className="px-2 py-0.5 text-[11px] font-bold rounded-md bg-amber-100 text-amber-800 border border-amber-200">맞출 표기 {pending}건 · {sm.fix_rows}행</span>
                    : <span className="px-2 py-0.5 text-[11px] font-bold rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200"
                        title={sm.unknown ? `참고: 기준 열에 없는 값 ${sm.unknown}건 (바꾸지 않음)` : ''}>✓ 표기 일치</span>)}
                  <button onClick={() => checkLabels(table)} disabled={busy}
                    className={`px-2.5 py-1 text-[11px] font-bold rounded-md border bg-white disabled:opacity-50 ${pending > 0
                      ? 'border-amber-400 text-amber-800 hover:bg-amber-50' : 'border-slate-200 text-slate-500 hover:bg-slate-50'}`}>
                    {pending > 0 ? '미리보기 · 맞추기' : '표기 점검'}
                  </button>
                </span>
              );
            })()}
          </div>
          <div className="divide-y divide-gray-100">
            {cols.map(c => {
              const key = `${c.table}.${c.column}`;
              const isOpen = !!open[key];
              const latest = c.years[0];
              return (
                <div key={key} className="px-4 py-2.5 text-sm min-w-0">
                  <div className="flex flex-col md:flex-row md:items-center gap-2 min-w-0">
                    <button onClick={() => setOpen({ ...open, [key]: !isOpen })} disabled={!c.years.length}
                      className="flex items-center gap-1 font-bold text-slate-800 text-left min-w-0 disabled:cursor-default">
                      {c.years.length ? (isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="w-3.5" />}
                      <span className="truncate">{c.column}</span>
                    </button>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold w-fit ${c.included ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                      {c.included ? '포함' : '제외'} · {c.reason}
                    </span>
                    {latest && !isOpen && (
                      <span className="text-xs text-slate-500 truncate min-w-0 flex-1">
                        {latest.year}: {latest.values.slice(0, 8).map(v => v.value).join(', ')}{latest.values.length > 8 ? ` 외 ${latest.values.length - 8}개` : ''}
                      </span>
                    )}
                    <div className="flex bg-slate-100 p-0.5 rounded-lg shrink-0 md:ml-auto w-fit">
                      {MODES.map(m => (
                        <button key={m.value} onClick={() => setMode(c, m.value)} disabled={busy}
                          className={`px-2.5 py-1 text-[11px] font-bold rounded-md transition-all ${c.mode === m.value ? m.on : 'text-slate-500 hover:text-slate-700'}`}>
                          {m.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  {(c.new_values.length > 0 || c.removed_values.length > 0) && (
                    <div className="mt-1.5 pl-5 text-xs space-y-0.5">
                      {c.new_values.length > 0 && <div className="text-blue-600">🆕 {c.years[0]?.year}에 새로 생김: {c.new_values.join(', ')}</div>}
                      {c.removed_values.length > 0 && <div className="text-amber-600">➖ {c.years[1]?.year}에는 있었으나 {c.years[0]?.year}에 (아직) 없음: {c.removed_values.join(', ')}</div>}
                    </div>
                  )}
                  {isOpen && (
                    <div className="mt-2 pl-5 grid gap-2 md:grid-cols-2">
                      {c.years.map(y => (
                        <div key={y.year} className="bg-slate-50 rounded-lg p-2 min-w-0">
                          <div className="text-xs font-bold text-slate-600 mb-1">{y.year} ({y.values.length}개)</div>
                          <div className="flex flex-wrap gap-1">
                            {y.values.map(v => (
                              <span key={v.value} className={`text-[11px] px-1.5 py-0.5 rounded border ${c.new_values.includes(v.value) && y.year === c.years[0].year ? 'border-blue-300 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-700'}`}>
                                {v.value} <span className="text-slate-400">{v.count.toLocaleString()}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
