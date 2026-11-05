import { useEffect, useState } from 'react';
import axios from 'axios';
import { CalendarDays } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';

/**
 * [기준 입시학년도] 대시보드 상단 선택 상자 (Sys_SystemSetting 'admission_year')
 * - Q&A·문서 등록의 학년도 기본값, 챗봇의 '올해/작년'·학년도 없는 질문 해석 기준
 * - 바꾸면 'admission-year-changed' 이벤트를 보내 열린 화면(Q&A 탭 등)이 다시 불러옴
 */
export default function AdmissionYearSelector() {
  const [year, setYear] = useState('');
  const [dateYear, setDateYear] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get('/api/settings/admission-year').then(res => {
      setYear(res.data.year || '');
      setDateYear(res.data.date_year || '');
    }).catch(() => {});
  }, []);

  const change = async (y: string) => {
    const ok = await CustomSwal.fire({
      icon: 'question', title: `기준 입시학년도를 ${y}학년도로 바꿀까요?`,
      text: `챗봇의 '올해/작년' 해석, 학년도 없는 질문의 Q&A, 새 문서·Q&A 등록 기본값이 ${y}학년도 기준이 됩니다.`,
      showCancelButton: true, confirmButtonText: '바꾸기', cancelButtonText: '취소',
    });
    if (!ok.isConfirmed) return;
    try {
      setBusy(true);
      const res = await axios.put('/api/settings/admission-year', { year: y });
      setYear(res.data.year);
      window.dispatchEvent(new CustomEvent('admission-year-changed', { detail: res.data.year }));
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '저장 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  if (!year) return null;
  const base = parseInt(year, 10);
  // 기준 앞뒤로 넉넉히 (지난 2년 ~ 앞으로 5년): 해가 지나도 선택지가 따라 늘어남
  const span = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i);
  const options = Array.from(new Set([...span(base - 2, base + 5), parseInt(dateYear || year, 10)])).sort();
  const differs = dateYear && dateYear !== year;

  return (
    <div className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/10 border border-white/20 text-xs text-white"
         title="입학처가 정하는 현재 업무 기준 학년도. 챗봇의 '올해/작년' 해석과 등록 기본값에 쓰입니다.">
      <CalendarDays size={14} className="text-amber-300" />
      <span className="hidden sm:inline font-bold">기준 입시학년도</span>
      <select value={year} disabled={busy} onChange={e => change(e.target.value)}
              className="bg-indigo-900 text-white font-bold border border-white/30 rounded px-1 py-0.5 outline-none">
        {options.map(y => <option key={y} value={String(y)}>{y}학년도</option>)}
      </select>
      {differs && <span className="hidden md:inline text-amber-300 text-[11px]">(날짜 기준 {dateYear}학년도)</span>}
    </div>
  );
}
