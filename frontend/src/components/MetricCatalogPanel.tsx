import { useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Pencil, Save, X } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';

// [지표 사전] 지표(계산 정의)·구분(테이블별 열) 조회/추가/수정/사용 중지. 저장할 때 서버가 계산식을 실제로 실행해 검증
type Metric = {
  metric_id?: number; metric_name: string; synonyms: string; table_name: string; expression: string;
  base_condition: string; value_kind: string; description: string; is_active: string; updated_at?: string;
};
type Dim = { dim_id?: number; dim_name: string; table_name: string; column_name: string; description: string; is_active: string; updated_at?: string };

const KINDS: Record<string, string> = { count: '건수', number: '숫자', mixed: '글자 섞임 (원본 값)' };
const EMPTY_METRIC: Metric = { metric_name: '', synonyms: '', table_name: '', expression: '', base_condition: '', value_kind: 'count', description: '', is_active: 'Y' };
const EMPTY_DIM: Dim = { dim_name: '', table_name: '', column_name: '', description: '', is_active: 'Y' };
const input = 'w-full border border-slate-300 rounded-md px-2 py-1.5 text-xs focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 outline-none';
const label = 'block text-[11px] font-bold text-slate-500 mb-0.5';

export default function MetricCatalogPanel() {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [dims, setDims] = useState<Dim[]>([]);
  const [tables, setTables] = useState<Record<string, string[]>>({});
  const [editMetric, setEditMetric] = useState<Metric | null>(null);
  const [editDim, setEditDim] = useState<Dim | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const res = await axios.get('/api/metric-catalog');
      setMetrics(res.data.metrics || []);
      setDims(res.data.dims || []);
      setTables(res.data.tables || {});
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: e?.response?.data?.detail || '지표 사전을 불러오지 못했습니다.' });
    }
  };
  useEffect(() => { load(); }, []);

  const save = async (kind: 'metrics' | 'dims', item: any, idKey: string) => {
    try {
      setBusy(true);
      const id = item[idKey];
      if (id) await axios.put(`/api/metric-catalog/${kind}/${id}`, item);
      else await axios.post(`/api/metric-catalog/${kind}`, item);
      kind === 'metrics' ? setEditMetric(null) : setEditDim(null);
      await load();
      CustomSwal.fire({ icon: 'success', title: '저장 완료', text: kind === 'metrics' ? '계산식을 실행해 확인한 뒤 저장했습니다.' : '저장했습니다.', timer: 1500, showConfirmButton: false });
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '저장 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  const toggle = (kind: 'metrics' | 'dims', item: any, idKey: string) =>
    save(kind, { ...item, is_active: item.is_active === 'Y' ? 'N' : 'Y' }, idKey);

  const tableSelect = (value: string, onChange: (v: string) => void) => (
    <select className={input} value={value} onChange={e => onChange(e.target.value)}>
      <option value="">테이블 선택</option>
      {Object.keys(tables).map(t => <option key={t} value={t}>{t}</option>)}
    </select>
  );
  const badge = (active: string) => (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${active === 'Y' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>{active === 'Y' ? '사용' : '중지'}</span>
  );
  const btn = 'px-2 py-1 text-[11px] font-bold rounded-md border transition-colors disabled:opacity-50';

  const metricForm = (m: Metric) => (
    <div className="bg-indigo-50/50 border border-indigo-200 rounded-lg p-3 grid gap-2 md:grid-cols-2">
      <div><span className={label}>지표명</span><input className={input} value={m.metric_name} onChange={e => setEditMetric({ ...m, metric_name: e.target.value })} placeholder="예: 지원인원" /></div>
      <div><span className={label}>비슷한 말 (쉼표 구분)</span><input className={input} value={m.synonyms} onChange={e => setEditMetric({ ...m, synonyms: e.target.value })} placeholder="예: 지원자수,지원자" /></div>
      <div><span className={label}>테이블</span>{tableSelect(m.table_name, v => setEditMetric({ ...m, table_name: v }))}</div>
      <div><span className={label}>종류</span>
        <select className={input} value={m.value_kind} onChange={e => setEditMetric({ ...m, value_kind: e.target.value })}>
          {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <div className="md:col-span-2"><span className={label}>계산식 (SELECT 식)</span><input className={`${input} font-mono`} value={m.expression} onChange={e => setEditMetric({ ...m, expression: e.target.value })} placeholder="예: SUM(CASE WHEN [최초합격구분명] = '합격' THEN 1 ELSE 0 END)" /></div>
      <div className="md:col-span-2"><span className={label}>기본 조건 (WHERE 식, 없으면 비움)</span><input className={`${input} font-mono`} value={m.base_condition} onChange={e => setEditMetric({ ...m, base_condition: e.target.value })} placeholder="예: [신입편입구분] = '신입'" /></div>
      <div className="md:col-span-2"><span className={label}>설명 (AI 가 지표를 고를 때 참고)</span><input className={input} value={m.description} onChange={e => setEditMetric({ ...m, description: e.target.value })} /></div>
      {m.table_name && tables[m.table_name] && (
        <div className="md:col-span-2 text-[11px] text-slate-500 break-words">열 목록: {tables[m.table_name].join(', ')}</div>
      )}
      <div className="md:col-span-2 flex justify-end gap-2">
        <button className={`${btn} border-slate-300 text-slate-600 bg-white`} onClick={() => setEditMetric(null)}><X size={12} className="inline" /> 취소</button>
        <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={busy} onClick={() => save('metrics', m, 'metric_id')}><Save size={12} className="inline" /> 실행 확인 후 저장</button>
      </div>
    </div>
  );

  const dimForm = (d: Dim) => (
    <div className="bg-indigo-50/50 border border-indigo-200 rounded-lg p-3 grid gap-2 md:grid-cols-4">
      <div><span className={label}>구분명</span><input className={input} value={d.dim_name} onChange={e => setEditDim({ ...d, dim_name: e.target.value })} placeholder="예: 학과" /></div>
      <div><span className={label}>테이블</span>{tableSelect(d.table_name, v => setEditDim({ ...d, table_name: v, column_name: '' }))}</div>
      <div><span className={label}>열</span>
        <select className={input} value={d.column_name} onChange={e => setEditDim({ ...d, column_name: e.target.value })}>
          <option value="">열 선택</option>
          {(tables[d.table_name] || []).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div><span className={label}>설명</span><input className={input} value={d.description} onChange={e => setEditDim({ ...d, description: e.target.value })} /></div>
      <div className="md:col-span-4 flex justify-end gap-2">
        <button className={`${btn} border-slate-300 text-slate-600 bg-white`} onClick={() => setEditDim(null)}><X size={12} className="inline" /> 취소</button>
        <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={busy} onClick={() => save('dims', d, 'dim_id')}><Save size={12} className="inline" /> 저장</button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4 min-w-0">
      <div className="text-xs text-slate-500 px-1">
        엑셀 격자 채우기에서 AI 는 아래 지표·구분 이름만 고르고, SQL 은 서버가 이 정의대로 조립합니다. 정의를 바꾸면 다음 요청부터 바로 적용됩니다.
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
        <div className="px-4 py-2.5 bg-slate-50 border-b border-gray-200 flex items-center gap-2">
          <span className="text-sm font-bold text-slate-700">지표 ({metrics.length})</span>
          <button className={`${btn} ml-auto border-indigo-300 text-indigo-700 bg-white hover:bg-indigo-50`} onClick={() => setEditMetric({ ...EMPTY_METRIC })}><Plus size={12} className="inline" /> 지표 추가</button>
        </div>
        <div className="divide-y divide-gray-100">
          {editMetric && !editMetric.metric_id && <div className="p-3">{metricForm(editMetric)}</div>}
          {metrics.map(m => (
            <div key={m.metric_id} className={`px-4 py-2.5 text-sm min-w-0 ${m.is_active === 'Y' ? '' : 'opacity-60'}`}>
              {editMetric && editMetric.metric_id === m.metric_id ? metricForm(editMetric) : (
                <div className="flex flex-col md:flex-row md:items-start gap-2 min-w-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-slate-800">{m.metric_name}</span>{badge(m.is_active)}
                      <span className="text-[11px] text-slate-400">{m.table_name} · {KINDS[m.value_kind] || m.value_kind}</span>
                    </div>
                    <div className="text-[11px] font-mono text-slate-600 break-all mt-0.5">{m.expression}{m.base_condition ? `  WHERE ${m.base_condition}` : ''}</div>
                    {(m.synonyms || m.description) && <div className="text-[11px] text-slate-500 mt-0.5">{m.synonyms && `비슷한 말: ${m.synonyms}`}{m.synonyms && m.description && ' · '}{m.description}</div>}
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} onClick={() => setEditMetric({ ...m })}><Pencil size={12} className="inline" /> 수정</button>
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} disabled={busy} onClick={() => toggle('metrics', m, 'metric_id')}>{m.is_active === 'Y' ? '사용 중지' : '다시 사용'}</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
        <div className="px-4 py-2.5 bg-slate-50 border-b border-gray-200 flex items-center gap-2">
          <span className="text-sm font-bold text-slate-700">구분 ({dims.length})</span>
          <span className="text-[11px] text-slate-400 hidden md:inline">같은 구분이 테이블마다 어느 열인지 (예: 학과 = 지원학과명 / 모집학과명)</span>
          <button className={`${btn} ml-auto border-indigo-300 text-indigo-700 bg-white hover:bg-indigo-50`} onClick={() => setEditDim({ ...EMPTY_DIM })}><Plus size={12} className="inline" /> 구분 추가</button>
        </div>
        <div className="divide-y divide-gray-100">
          {editDim && !editDim.dim_id && <div className="p-3">{dimForm(editDim)}</div>}
          {dims.map(d => (
            <div key={d.dim_id} className={`px-4 py-2 text-sm min-w-0 ${d.is_active === 'Y' ? '' : 'opacity-60'}`}>
              {editDim && editDim.dim_id === d.dim_id ? dimForm(editDim) : (
                <div className="flex flex-col md:flex-row md:items-center gap-2 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 min-w-0 flex-1">
                    <span className="font-bold text-slate-800 w-20 shrink-0">{d.dim_name}</span>{badge(d.is_active)}
                    <span className="text-xs text-slate-600 break-all">{d.table_name}.<b>{d.column_name}</b></span>
                    {d.description && <span className="text-[11px] text-slate-500">{d.description}</span>}
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} onClick={() => setEditDim({ ...d })}><Pencil size={12} className="inline" /> 수정</button>
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} disabled={busy} onClick={() => toggle('dims', d, 'dim_id')}>{d.is_active === 'Y' ? '사용 중지' : '다시 사용'}</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
