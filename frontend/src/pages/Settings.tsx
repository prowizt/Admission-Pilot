import { useEffect, useState } from 'react';
import axios from 'axios';
import { Settings as SettingsIcon, RotateCcw, Save, Lock } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';
import AdmissionYearSelector from '@/components/AdmissionYearSelector';

// [환경설정] 운영 중 자주 바꾸는 값. 화면 값 → .env → 기본값 순으로 적용되며, 저장하면 다음 질문부터 바로 반영 (재시작 불필요)
type Item = {
  key: string; group: string; label: string; kind: 'int' | 'float' | 'choice' | 'date'; description: string;
  value: string | number; source: 'screen' | 'env' | 'default'; env_value: string | null; default: string | number;
  choices: string[] | null; min: number | null; max: number | null;
};

const SOURCE: Record<string, [string, string]> = {
  screen: ['화면 설정', 'bg-indigo-50 text-indigo-700'],
  env: ['.env', 'bg-amber-50 text-amber-700'],
  default: ['기본값', 'bg-slate-100 text-slate-500'],
};
// [천 단위 구분] 숫자는 1,000 단위 쉼표로 보여 주고, 저장할 때 쉼표를 뺌
const fmt = (v: any) => {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(String(v).replace(/,/g, ''));
  return Number.isFinite(n) ? n.toLocaleString('ko-KR', { maximumFractionDigits: 6 }) : String(v);
};
const unfmt = (v: string) => v.replace(/,/g, '').trim();
const btn = 'px-2 py-1 text-[11px] font-bold rounded-md border transition-colors disabled:opacity-40 whitespace-nowrap';

export default function Settings() {
  const [items, setItems] = useState<Item[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');

  const load = async () => {
    try {
      const res = await axios.get('/api/settings/config');
      setItems(res.data.items || []);
      setDrafts({});
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: e?.response?.data?.detail || '설정을 불러오지 못했습니다. 백엔드를 재시작했는지 확인해 주세요.' });
    }
  };
  useEffect(() => { load(); }, []);

  const save = async (it: Item, value: string) => {
    try {
      setBusy(it.key);
      await axios.put(`/api/settings/config/${it.key}`, { value });
      await load();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '저장 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy('');
    }
  };
  const reset = async (it: Item) => {
    try {
      setBusy(it.key);
      await axios.delete(`/api/settings/config/${it.key}`);
      await load();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '되돌리기 안 됨', text: e?.response?.data?.detail || '되돌리지 못했습니다.' });
    } finally {
      setBusy('');
    }
  };

  // 크레딧 기준값은 시스템 로그 → Claude 사용 통계 탭에서 다룸 (일반 설정 목록에서 제외)
  // 환율·부가세율(비용 계산)도 같은 탭의 크레딧 카드에서 다룸
  const groups = Array.from(new Set(items.map(i => i.group))).filter(g => g !== 'Claude 크레딧' && g !== '비용 계산');
  const input = 'border border-slate-300 rounded-md px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500';

  // [초 단위 설정] 초로 입력하되 옆에 '2시간 30분'처럼 시·분으로 풀어서 보여줌 (키 이름이 _SEC 로 끝나는 항목)
  const isSec = (it: Item) => it.key.endsWith('_SEC');
  const humanSec = (v: string | number) => {
    const n = Math.round(Number(String(v).replace(/,/g, '')));
    if (!Number.isFinite(n) || n <= 0) return '';
    const h = Math.floor(n / 3600), m = Math.floor((n % 3600) / 60), sec = n % 60;
    return [h && `${h}시간`, m && `${m}분`, sec && `${sec}초`].filter(Boolean).join(' ');
  };

  const control = (it: Item) => {
    if (it.kind === 'date') {
      return (
        <input type="date" className={`${input} w-40`} value={String(it.value || '')} disabled={busy === it.key}
               onChange={e => e.target.value && save(it, e.target.value)} />
      );
    }
    if (it.kind === 'choice') {
      return (
        <select className={`${input} min-w-[140px]`} value={String(it.value)} disabled={busy === it.key}
                onChange={e => save(it, e.target.value)}>
          {(it.choices || []).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      );
    }
    const draft = drafts[it.key];
    const changed = draft !== undefined && unfmt(draft) !== String(it.value);
    return (
      <div className="flex items-center gap-1.5">
        <input type="text" inputMode="decimal" className={`${input} w-32 text-right font-mono`} value={draft ?? fmt(it.value)}
               onChange={e => {
                 const raw = e.target.value.replace(/[^0-9.,]/g, '');
                 const plain = unfmt(raw);
                 // 입력 중에도 쉼표를 붙임 (소수점 입력 중이면 그대로)
                 setDrafts({ ...drafts, [it.key]: plain.includes('.') || plain === '' ? raw : fmt(plain) });
               }}
               onKeyDown={e => { if (e.key === 'Enter' && changed) save(it, unfmt(draft!)); }} />
        <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={!changed || busy === it.key}
                onClick={() => save(it, unfmt(draft!))}><Save size={12} className="inline" /> 저장</button>
        {isSec(it) && humanSec(draft ?? it.value) && (
          <span className="text-xs font-bold text-indigo-700 whitespace-nowrap">= {humanSec(draft ?? it.value)}</span>
        )}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col min-w-0 pb-24 md:pb-6 overflow-y-auto bg-slate-50/50 p-1 md:p-6">
      <div className="bg-gradient-to-br from-indigo-900 via-indigo-800 to-purple-900 rounded-xl shadow-md py-3 px-3 md:py-4 md:px-6 text-white">
        <div className="flex items-center gap-3">
          <div className="bg-white/10 p-2 rounded-lg border border-white/10"><SettingsIcon className="text-amber-400" size={20} /></div>
          <h1 className="text-lg md:text-xl font-extrabold tracking-tight">환경 설정</h1>
        </div>
        <div className="text-xs text-indigo-200 mt-2">
          저장하면 다음 질문부터 바로 반영됩니다 (백엔드 재시작 불필요). 적용 순서: <b className="text-white">화면 설정 → .env → 기본값</b>
        </div>
      </div>

      <div className="py-4 space-y-4 min-w-0">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 px-4 py-3 flex flex-wrap items-center gap-3">
          <span className="text-sm font-bold text-slate-700">기준 학년도</span>
          <div className="bg-indigo-900 rounded-lg p-1"><AdmissionYearSelector /></div>
          <span className="text-[11px] text-slate-500">지식 카탈로그 화면 상단의 선택 상자와 같은 값입니다.</span>
        </div>

        <div className="text-[11px] text-slate-500 px-1">Claude 크레딧 잔액·사용 통계와 비용 계산 기준(환율·부가세율)은 <b>시스템 로그 → Claude 사용 통계</b> 탭의 크레딧 카드에서 보고 맞춥니다.</div>

        {groups.map(g => (
          <div key={g} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
            <div className="px-4 py-2.5 bg-slate-50 border-b border-gray-200 text-sm font-bold text-slate-700">{g}</div>
            <div className="divide-y divide-gray-100">
              {items.filter(i => i.group === g).map(it => (
                <div key={it.key} className="px-4 py-3 flex flex-col md:flex-row md:items-center gap-2 min-w-0">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-slate-800">{it.label}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${SOURCE[it.source][1]}`}>{SOURCE[it.source][0]}</span>
                      <code className="text-[10px] text-slate-400">{it.key}</code>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5 break-words">
                      {it.description}
                      <span className="text-slate-400"> · 기본값 {it.kind === 'int' || it.kind === 'float' ? fmt(it.default) : (String(it.default) || '없음')}{isSec(it) ? `(${humanSec(it.default)})` : ''}{it.env_value ? ` · .env ${it.kind === 'int' || it.kind === 'float' ? fmt(it.env_value) : it.env_value}` : ''}{it.min !== null ? ` · 범위 ${fmt(it.min)} ~ ${fmt(it.max)}${isSec(it) ? ` (${humanSec(it.min)} ~ ${humanSec(it.max!)})` : ''}` : ''}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {control(it)}
                    <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} disabled={it.source !== 'screen' || busy === it.key}
                            title="화면에서 정한 값을 지우고 .env(없으면 기본값)로 되돌립니다" onClick={() => reset(it)}>
                      <RotateCcw size={12} className="inline" /> 되돌리기
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <div className="flex gap-2 text-[11px] text-slate-500 px-1">
          <Lock size={14} className="shrink-0 mt-0.5" />
          <span>API 키(ANTHROPIC_API_KEY, STUDENT_API_KEY)와 DB 서버·계정·비밀번호는 보안상 화면에 두지 않습니다. 바꿀 때는 backend/.env 를 고친 뒤 백엔드를 재시작하세요.</span>
        </div>
      </div>
    </div>
  );
}
