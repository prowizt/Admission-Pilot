import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Plus, Pencil, Save, X, Trash2, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';

// [입학처 Q&A] Sys_StudentFAQ: 학생·교직원 챗봇이 참고하는 입학처 공식 답변
// apply_year 'ALL' = 공통(매년 같은 답변), '2027' 등 = 그 입시학년도 질문에만 참고
export type Faq = {
  faq_id?: number; topic: string; answer: string; apply_year: string; sample_question?: string | null;
  is_active: string; source_log_id?: number | null; created_at?: string; updated_at?: string | null;
};

const input = 'w-full border border-slate-300 rounded-md px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 outline-none';
const label = 'block text-[11px] font-bold text-slate-500 mb-0.5';
const btn = 'px-2 py-1 text-[11px] font-bold rounded-md border transition-colors disabled:opacity-50';

export const yearLabel = (y: string) => (y === 'ALL' ? '공통' : `${y}학년도`);
export const yearOptions = (current: string, extra: string[] = []) => {
  const c = parseInt(current || String(new Date().getFullYear() + 1), 10);
  // 기준 학년도 앞뒤로 넉넉히 (지난 2년 ~ 앞으로 5년) + 이미 등록된 학년도
  const range = Array.from({ length: 8 }, (_, i) => String(c - 2 + i));
  return Array.from(new Set([...range, ...extra.filter(y => y && y !== 'ALL')])).sort();
};

export async function saveFaq(item: Faq) {
  if (item.faq_id) await axios.put(`/api/catalog/faq/${item.faq_id}`, item);
  else await axios.post('/api/catalog/faq', item);
}

/** Q&A 입력 양식 (대시보드 Q&A 탭 · 감사 로그 [답변 등록] 공용) */
export function FaqForm({ value, onChange, currentYear, years = [] }: {
  value: Faq; onChange: (f: Faq) => void; currentYear: string; years?: string[];
}) {
  return (
    <div className="grid gap-2 md:grid-cols-4">
      <div className="md:col-span-3"><span className={label}>주제 (짧은 제목 · Q&A 가 많아지면 AI 가 이 제목을 보고 골라 씀)</span>
        <input className={input} value={value.topic} onChange={e => onChange({ ...value, topic: e.target.value })} placeholder="예: 기숙사 유무, 고교명 변경" autoFocus={!value.topic} />
      </div>
      <div><span className={label}>적용 학년도</span>
        <select className={input} value={value.apply_year} onChange={e => onChange({ ...value, apply_year: e.target.value })}>
          <option value="ALL">공통 (매년 같은 답변)</option>
          {yearOptions(currentYear, years).map(y => <option key={y} value={y}>{y}학년도만{y === currentYear ? ' (기준 학년도)' : ''}</option>)}
        </select>
      </div>
      <div className="md:col-span-4"><span className={label}>답변</span>
        <textarea className={`${input} min-h-[120px]`} value={value.answer} onChange={e => onChange({ ...value, answer: e.target.value })} placeholder="학생에게 안내할 입학처 공식 답변" />
      </div>
      <div className="md:col-span-4"><span className={label}>실제 질문 예 (선택)</span>
        <input className={input} value={value.sample_question || ''} onChange={e => onChange({ ...value, sample_question: e.target.value })} placeholder="예: 기숙사 있어요?" />
      </div>
    </div>
  );
}

/** 감사 로그에서 [답변 등록] 할 때 쓰는 창 */
export function FaqRegisterModal({ initial, onClose }: { initial: Faq; onClose: (saved: boolean) => void }) {
  const [item, setItem] = useState<Faq>(initial);
  const [currentYear, setCurrentYear] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    axios.get('/api/catalog/faq').then(res => {
      const cy = res.data.current_year || '';
      setCurrentYear(cy);
      setItem(it => (it.apply_year ? it : { ...it, apply_year: cy || 'ALL' }));
    }).catch(() => {});
  }, []);
  const submit = async () => {
    try {
      setBusy(true);
      await saveFaq(item);
      CustomSwal.fire({ icon: 'success', title: '등록 완료', text: '다음 질문부터 챗봇이 이 답변을 참고합니다.', timer: 1500, showConfirmButton: false });
      onClose(true);
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '등록 안 됨', text: e?.response?.data?.detail || '등록하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };
  return createPortal(
    <div className="fixed inset-0 z-[1000] bg-black/40 flex items-center justify-center p-4" onClick={() => onClose(false)}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-4 space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex items-center">
          <span className="font-bold text-slate-800">입학처 Q&A 등록</span>
          <span className="ml-2 text-[11px] text-slate-400">{initial.source_log_id ? `감사 로그 #${initial.source_log_id}` : ''}</span>
          <button className="ml-auto text-slate-400 hover:text-slate-700" onClick={() => onClose(false)}><X size={18} /></button>
        </div>
        <div className="text-[11px] text-slate-500">AI 답변이 채워져 있습니다. 입학처 공식 답변으로 고친 뒤 등록하세요. 해마다 달라지는 내용이면 적용 학년도를 그 학년도로 고르세요.</div>
        <FaqForm value={item} onChange={setItem} currentYear={currentYear} />
        <div className="flex justify-end gap-2">
          <button className={`${btn} border-slate-300 text-slate-600 bg-white`} onClick={() => onClose(false)}>취소</button>
          <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={busy} onClick={submit}><Save size={12} className="inline" /> 등록</button>
        </div>
      </div>
    </div>,
    document.body
  );
}

const EMPTY: Faq = { topic: '', answer: '', apply_year: 'ALL', sample_question: '', is_active: 'Y' };

export default function FaqPanel() {
  const [items, setItems] = useState<Faq[]>([]);
  const [meta, setMeta] = useState({ active_tokens: 0, all_tokens_limit: 3000, current_year: '' });
  const [edit, setEdit] = useState<Faq | null>(null);
  const [yearFilter, setYearFilter] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const res = await axios.get('/api/catalog/faq');
      setItems(res.data.data || []);
      setMeta({ active_tokens: res.data.active_tokens || 0, all_tokens_limit: res.data.all_tokens_limit || 3000, current_year: res.data.current_year || '' });
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: e?.response?.data?.detail || 'Q&A 를 불러오지 못했습니다.' });
    }
  };
  useEffect(() => {
    load();
    // 상단에서 기준 입시학년도를 바꾸면 기본값·안내를 다시 불러옴
    const onYear = () => load();
    window.addEventListener('admission-year-changed', onYear);
    return () => window.removeEventListener('admission-year-changed', onYear);
  }, []);

  const save = async (item: Faq) => {
    try {
      setBusy(true);
      await saveFaq(item);
      setEdit(null);
      await load();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '저장 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };
  const remove = async (item: Faq) => {
    const ok = await CustomSwal.fire({ icon: 'warning', title: 'Q&A 삭제', text: `'${item.topic}' 을(를) 삭제할까요? (잠시 빼려면 '사용 중지')`, showCancelButton: true, confirmButtonText: '삭제', cancelButtonText: '취소' });
    if (!ok.isConfirmed) return;
    try {
      await axios.delete(`/api/catalog/faq/${item.faq_id}`);
      await load();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '삭제 안 됨', text: e?.response?.data?.detail || '삭제하지 못했습니다.' });
    }
  };

  const years = Array.from(new Set(items.map(i => i.apply_year).filter(y => y !== 'ALL'))).sort();
  const q = query.trim();
  const shown = items.filter(i => (!yearFilter || i.apply_year === yearFilter) && (!q || i.topic.includes(q) || i.answer.includes(q) || (i.sample_question || '').includes(q)));
  // [페이지 나누기] 10건씩. 필터·검색을 바꾸면 1쪽으로
  const PAGE_SIZE = 10;
  const totalPages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const curPage = Math.min(page, totalPages);
  const paged = shown.slice((curPage - 1) * PAGE_SIZE, curPage * PAGE_SIZE);
  useEffect(() => { setPage(1); }, [yearFilter, query]);
  const pager = totalPages > 1 && (
    <div className="flex flex-col sm:flex-row justify-between items-center gap-2 px-4 py-2.5 border-t border-gray-100 bg-slate-50/50">
      <div className="text-[11px] text-gray-500 font-bold">총 {shown.length}건 중 {(curPage - 1) * PAGE_SIZE + 1} - {Math.min(curPage * PAGE_SIZE, shown.length)}건 표시</div>
      <div className="flex items-center gap-1.5">
        <button onClick={() => setPage(Math.max(1, curPage - 1))} disabled={curPage === 1} className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 text-gray-500 disabled:opacity-30 hover:bg-gray-50"><ChevronLeft size={16} /></button>
        {Array.from({ length: totalPages }, (_, i) => i + 1).map(n => {
          if (totalPages > 7 && n !== 1 && n !== totalPages && Math.abs(curPage - n) > 1) {
            return (n === 2 || n === totalPages - 1) ? <span key={n} className="text-gray-400">...</span> : null;
          }
          return <button key={n} onClick={() => setPage(n)} className={`w-7 h-7 rounded-md text-xs font-bold ${curPage === n ? 'bg-indigo-600 text-white shadow-md' : 'text-gray-600 hover:bg-indigo-50'}`}>{n}</button>;
        })}
        <button onClick={() => setPage(Math.min(totalPages, curPage + 1))} disabled={curPage === totalPages} className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 text-gray-500 disabled:opacity-30 hover:bg-gray-50"><ChevronRight size={16} /></button>
      </div>
    </div>
  );
  const over = meta.active_tokens > meta.all_tokens_limit;

  const form = (f: Faq) => (
    <div className="bg-indigo-50/50 border border-indigo-200 rounded-lg p-3 space-y-2">
      <FaqForm value={f} onChange={setEdit} currentYear={meta.current_year} years={years} />
      <div className="flex justify-end gap-2">
        <button className={`${btn} border-slate-300 text-slate-600 bg-white`} onClick={() => setEdit(null)}><X size={12} className="inline" /> 취소</button>
        <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={busy} onClick={() => save(f)}><Save size={12} className="inline" /> 저장</button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4 min-w-0">
      <div className="text-xs text-slate-500 px-1 space-y-0.5">
        <div>학생·교직원 챗봇이 답변할 때 참고하는 입학처 공식 답변입니다. 저장하면 다음 질문부터 바로 반영됩니다.</div>
        <div><b>공통</b>은 매년 같은 답변이고, <b>OOOO학년도</b>는 그 학년도 입시 질문에만 쓰입니다. 질문에 학년도가 없으면 상단의 기준 입시학년도({meta.current_year ? `${meta.current_year}학년도` : '-'}) 기준입니다. 같은 주제가 공통과 학년도에 모두 있으면 학년도 답변이 쓰입니다.</div>
        <div>사용 중인 Q&A 분량: 약 <b className={over ? 'text-amber-700' : ''}>{meta.active_tokens.toLocaleString()}</b> 토큰 / {meta.all_tokens_limit.toLocaleString()} 토큰 이하이면 전부 넣고, 넘으면 AI 가 질문에 맞는 주제만 골라 넣습니다.{over && ' (지금은 주제를 골라 넣는 중)'}</div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
        <div className="px-4 py-2.5 bg-slate-50 border-b border-gray-200 flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold text-slate-700">Q&A ({shown.length}{shown.length !== items.length ? ` / ${items.length}` : ''})</span>
          <select className="border border-slate-300 rounded-md px-2 py-1 text-xs bg-white" value={yearFilter} onChange={e => setYearFilter(e.target.value)}>
            <option value="">전체 학년도</option>
            <option value="ALL">공통</option>
            {years.map(y => <option key={y} value={y}>{y}학년도</option>)}
          </select>
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="border border-slate-300 rounded-md pl-6 pr-2 py-1 text-xs w-40" value={query} onChange={e => setQuery(e.target.value)} placeholder="주제·답변 검색" />
          </div>
          <button className={`${btn} ml-auto border-indigo-300 text-indigo-700 bg-white hover:bg-indigo-50`} onClick={() => setEdit({ ...EMPTY })}><Plus size={12} className="inline" /> Q&A 추가</button>
        </div>
        <div className="divide-y divide-gray-100">
          {edit && !edit.faq_id && <div className="p-3">{form(edit)}</div>}
          {shown.length === 0 && !edit && <div className="px-4 py-6 text-center text-sm text-slate-400">등록된 Q&A 가 없습니다.</div>}
          {paged.map(f => (
            <div key={f.faq_id} className={`px-4 py-3 text-sm min-w-0 ${f.is_active === 'Y' ? '' : 'opacity-60'}`}>
              {edit && edit.faq_id === f.faq_id ? form(edit) : (
                <div className="flex flex-col md:flex-row md:items-start gap-2 min-w-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-slate-800">{f.topic}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${f.apply_year === 'ALL' ? 'bg-slate-100 text-slate-600' : 'bg-indigo-50 text-indigo-700'}`}>{yearLabel(f.apply_year)}</span>
                      {f.is_active !== 'Y' && <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold bg-slate-100 text-slate-400">중지</span>}
                      <span className="text-[11px] text-slate-400">#{f.faq_id} · {f.updated_at || f.created_at}{f.source_log_id ? ` · 로그 #${f.source_log_id}에서 등록` : ''}</span>
                    </div>
                    <div className="text-[13px] text-slate-700 whitespace-pre-wrap break-words mt-1">{f.answer}</div>
                    {f.sample_question && <div className="text-[11px] text-slate-500 mt-1 break-words">질문 예: {f.sample_question}</div>}
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} onClick={() => setEdit({ ...f })}><Pencil size={12} className="inline" /> 수정</button>
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} disabled={busy} onClick={() => save({ ...f, is_active: f.is_active === 'Y' ? 'N' : 'Y' })}>{f.is_active === 'Y' ? '사용 중지' : '다시 사용'}</button>
                    <button className={`${btn} border-red-200 text-red-600 bg-white hover:bg-red-50`} onClick={() => remove(f)}><Trash2 size={12} className="inline" /></button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        {pager}
      </div>
    </div>
  );
}
