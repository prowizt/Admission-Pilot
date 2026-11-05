import { useEffect, useState } from 'react';
import axios from 'axios';
import { Wallet, RefreshCw, Save, ChevronDown, ChevronUp } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';

// [Claude 크레딧] 예상 잔액 = 콘솔에서 본 잔액 − 그 뒤 감사 로그의 Claude 예상 비용 (시스템 로그 → Claude 사용 통계 탭)
const fmt = (v: number) => Math.round(v).toLocaleString('ko-KR');
const usd = (v: number) => `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const btn = 'px-2 py-1 text-[11px] font-bold rounded-md border transition-colors disabled:opacity-40 whitespace-nowrap';

export default function ClaudeCreditCard({ onSynced }: { onSynced?: () => void }) {
  const [bill, setBill] = useState<any>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);  // 충전 기록·콘솔 맞추기 펼침
  const [input, setInput] = useState('');
  const [payUsd, setPayUsd] = useState('');  // [충전 기록] 결제 금액 (USD, 부가세 포함)
  const [payKrw, setPayKrw] = useState('');  // 카드에 청구된 원화

  const load = async () => {
    try {
      setBusy(true);
      const res = await axios.get('/api/billing/claude');
      setBill(res.data); setErr('');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || '크레딧을 계산하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => { load(); }, []);

  const sync = async () => {
    const v = Number(input.replace(/,/g, '').trim());
    if (!input.trim() || !Number.isFinite(v) || v < 0) {
      CustomSwal.fire({ icon: 'warning', title: '잔액을 입력해 주세요', text: '콘솔 Billing 화면에 보이는 잔액(USD)을 숫자로 입력하세요. 예: 4.04' });
      return;
    }
    try {
      setBusy(true);
      const res = await axios.post('/api/billing/claude/sync', { balance_usd: v });
      setBill(res.data); setErr(''); setInput('');
      onSynced?.();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '맞추기 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  // [비용 계산 기준] 환율·부가세율 (환경 설정에서 옮겨 옴). 부가세는 화면에서 % 로 입력, 저장은 비율(0.1)
  const [rateIn, setRateIn] = useState<string | null>(null);
  const [vatIn, setVatIn] = useState<string | null>(null);
  const rateShown = rateIn ?? (bill ? fmt(bill.krw_per_usd) : '');
  const vatShown = vatIn ?? (bill ? String(Math.round(bill.vat_rate * 1000) / 10) : '');
  const saveRates = async () => {
    const r = Number((rateIn ?? '').replace(/,/g, ''));
    const v = Number(vatIn ?? '');
    const jobs: [string, string][] = [];
    if (rateIn !== null) {
      if (!(r >= 500 && r <= 3000)) { CustomSwal.fire({ icon: 'warning', title: '환율을 확인해 주세요', text: '500 ~ 3,000 원/달러 사이로 넣으세요.' }); return; }
      jobs.push(['KRW_PER_USD', String(r)]);
    }
    if (vatIn !== null) {
      if (!(v >= 0 && v <= 50)) { CustomSwal.fire({ icon: 'warning', title: '부가세율을 확인해 주세요', text: '0 ~ 50 % 사이로 넣으세요.' }); return; }
      jobs.push(['VAT_RATE', String(Math.round(v * 10) / 1000)]);
    }
    if (!jobs.length) return;
    try {
      setBusy(true);
      for (const [k, val] of jobs) await axios.put(`/api/settings/config/${k}`, { value: val });
      setRateIn(null); setVatIn(null);
      await load();
      onSynced?.();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '저장 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  const num = (v: string) => Number(v.replace(/,/g, '').trim());
  const previewRate = num(payUsd) > 0 && num(payKrw) > 0 ? num(payKrw) / num(payUsd) : 0;
  const charge = async () => {
    if (!(num(payUsd) > 0) || !(num(payKrw) > 0)) {
      CustomSwal.fire({ icon: 'warning', title: '결제 금액을 입력해 주세요', text: '콘솔 결제 금액(USD, 부가세 포함. 예: 5.5)과 카드에 청구된 원화(예: 7,445)를 넣으세요.' });
      return;
    }
    const ok = await CustomSwal.fire({
      icon: 'question', title: '충전을 기록할까요?',
      html: `결제 <b>$${num(payUsd)}</b> = <b>${fmt(num(payKrw))}원</b><br/>환율 <b>${fmt(previewRate)}원/달러</b>로 저장하고,<br/>예상 잔액에 크레딧 <b>${usd(num(payUsd) / (1 + (bill?.vat_rate ?? 0.1)))}</b>를 더합니다.`,
      showCancelButton: true, confirmButtonText: '기록', cancelButtonText: '취소',
    });
    if (!ok.isConfirmed) return;
    try {
      setBusy(true);
      const res = await axios.post('/api/billing/claude/charge', { paid_usd: num(payUsd), paid_krw: num(payKrw) });
      setBill(res.data); setErr(''); setPayUsd(''); setPayKrw('');
      onSynced?.();
    } catch (e: any) {
      CustomSwal.fire({ icon: 'error', title: '기록 안 됨', text: e?.response?.data?.detail || '저장하지 못했습니다.' });
    } finally {
      setBusy(false);
    }
  };

  // 원화 환산: 크레딧은 부가세를 내고 산 것이므로 USD × 환율 × (1 + 부가세율) — 로그의 원화(부가세 포함)와 같은 기준
  const toKrw = (u: number) => (bill ? u * bill.krw_per_usd * (1 + bill.vat_rate) : 0);
  const hasBalance = bill?.remaining_usd !== null && bill?.remaining_usd !== undefined;
  const low = hasBalance && bill.remaining_usd < 1;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
      {/* 예상 잔액만 한 줄로 보여주고, 충전 기록·콘솔 맞추기는 [관리]로 펼침 (자주 쓰지 않음) */}
      <div className={`px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 ${open ? 'bg-slate-50 border-b border-gray-200' : ''}`}>
        <Wallet size={16} className="text-indigo-600" />
        <span className="text-sm font-bold text-slate-700">Claude 크레딧</span>
        {bill && hasBalance && (
          <span className="flex items-baseline gap-2">
            <span className="text-[11px] text-slate-500 font-bold">예상 잔액</span>
            <span className={`font-mono font-extrabold text-lg ${low ? 'text-red-600' : 'text-indigo-800'}`}>{usd(bill.remaining_usd)}</span>
            <span className={`font-mono font-bold text-sm ${low ? 'text-red-600' : 'text-indigo-700'}`}>약 {fmt(toKrw(bill.remaining_usd))}원</span>
            {low && <span className="text-[11px] font-bold text-red-600">⚠️ $1 미만 — 충전을 준비하세요</span>}
          </span>
        )}
        {bill && !hasBalance && <span className="text-xs text-slate-500">콘솔 잔액을 넣으면 계산을 시작합니다</span>}
        {err && <span className="text-red-600 text-xs">{err}</span>}
        <div className="ml-auto flex items-center gap-1.5">
          <button className={`${btn} border-slate-300 text-slate-600 bg-white hover:bg-slate-50`} disabled={busy} onClick={load} title={bill?.checked_at ? `${bill.checked_at} 계산` : ''}>
            <RefreshCw size={12} className={`inline ${busy ? 'animate-spin' : ''}`} /> 새로 계산
          </button>
          <button className={`${btn} ${open ? 'border-indigo-300 bg-indigo-50 text-indigo-700' : 'border-slate-300 text-slate-600 bg-white hover:bg-slate-50'}`} onClick={() => setOpen(v => !v)}>
            충전·잔액 맞추기 {open ? <ChevronUp size={12} className="inline" /> : <ChevronDown size={12} className="inline" />}
          </button>
        </div>
      </div>
      {open && <div className="px-4 py-3 space-y-3">
        {bill && hasBalance && (
          <div className="text-xs text-slate-600 space-y-0.5">
            <div>기준: <b>{bill.base_at.slice(0, 16)}</b> 콘솔 잔액 <b>{usd(bill.base_usd)}</b> (약 {fmt(toKrw(bill.base_usd))}원)</div>
            <div>그 뒤 사용: <b>{usd(bill.since_base_usd)}</b> (로그 {fmt(bill.since_base_krw)}원) · 원화는 부가세 포함 환산 · {bill.checked_at} 계산</div>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50/60 border border-emerald-200 px-3 py-2">
          <span className="text-xs font-bold text-slate-700">충전 기록</span>
          <span className="text-xs text-slate-500">결제 $</span>
          <input type="text" inputMode="decimal" placeholder="예: 5.5" value={payUsd}
                 className="border border-slate-300 rounded-md px-2 py-1 text-sm w-20 text-right font-mono outline-none focus:ring-2 focus:ring-emerald-100 focus:border-emerald-500"
                 onChange={e => setPayUsd(e.target.value.replace(/[^0-9.,]/g, ''))} />
          <span className="text-xs text-slate-500">카드 청구</span>
          <input type="text" inputMode="numeric" placeholder="예: 7,445" value={payKrw}
                 className="border border-slate-300 rounded-md px-2 py-1 text-sm w-24 text-right font-mono outline-none focus:ring-2 focus:ring-emerald-100 focus:border-emerald-500"
                 onChange={e => { const d = e.target.value.replace(/[^0-9]/g, ''); setPayKrw(d ? Number(d).toLocaleString('ko-KR') : ''); }}
                 onKeyDown={e => { if (e.key === 'Enter') charge(); }} />
          <span className="text-xs text-slate-500">원</span>
          <button className={`${btn} border-emerald-600 bg-emerald-600 text-white`} disabled={busy} onClick={charge}>
            <Save size={12} className="inline" /> 기록
          </button>
          <span className="text-[11px] text-slate-500">
            {previewRate ? `→ 환율 ${fmt(previewRate)}원/달러 자동 저장 · 잔액에 크레딧 더함` : '충전할 때 결제 달러(부가세 포함)와 카드 원화를 넣으면 환율이 자동 계산됩니다.'}
          </span>
          {bill?.last_charge && (
            <span className="basis-full text-[11px] text-slate-500">
              마지막 충전: {String(bill.last_charge.at).slice(0, 16)} · 결제 {usd(bill.last_charge.paid_usd)} = {fmt(bill.last_charge.paid_krw)}원 · 환율 {fmt(bill.last_charge.rate)}원 · 크레딧 +{usd(bill.last_charge.credit_usd)}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2">
          <span className="text-xs font-bold text-slate-700">콘솔 잔액으로 맞추기</span>
          <span className="text-xs text-slate-500">$</span>
          <input type="text" inputMode="decimal" placeholder="예: 4.04" value={input}
                 className="border border-slate-300 rounded-md px-2 py-1 text-sm w-28 text-right font-mono outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500"
                 onChange={e => setInput(e.target.value.replace(/[^0-9.,]/g, ''))}
                 onKeyDown={e => { if (e.key === 'Enter') sync(); }} />
          <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={busy} onClick={sync}>
            <Save size={12} className="inline" /> 맞추기
          </button>
          <span className="text-[11px] text-slate-500">콘솔과 차이가 날 때 콘솔 Billing 화면의 남은 금액을 넣으면 지금 시각부터 다시 계산합니다.</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2">
          <span className="text-xs font-bold text-slate-700">비용 계산 기준</span>
          <span className="text-xs text-slate-500">환율</span>
          <input type="text" inputMode="decimal" value={rateShown}
                 className="border border-slate-300 rounded-md px-2 py-1 text-sm w-24 text-right font-mono outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500"
                 onChange={e => { const d = e.target.value.replace(/[^0-9.]/g, ''); setRateIn(d.includes('.') ? d : (d ? Number(d).toLocaleString('ko-KR') : '')); }}
                 onKeyDown={e => { if (e.key === 'Enter') saveRates(); }} />
          <span className="text-xs text-slate-500">원/달러 · 부가세</span>
          <input type="text" inputMode="decimal" value={vatShown}
                 className="border border-slate-300 rounded-md px-2 py-1 text-sm w-14 text-right font-mono outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500"
                 onChange={e => setVatIn(e.target.value.replace(/[^0-9.]/g, ''))}
                 onKeyDown={e => { if (e.key === 'Enter') saveRates(); }} />
          <span className="text-xs text-slate-500">%</span>
          <button className={`${btn} border-indigo-600 bg-indigo-600 text-white`} disabled={busy || (rateIn === null && vatIn === null)} onClick={saveRates}>
            <Save size={12} className="inline" /> 저장
          </button>
          <span className="text-[11px] text-slate-500">질문별 원화 비용과 통계·잔액의 원화 환산에 씁니다. [충전 기록]을 하면 환율은 카드값으로 자동 저장됩니다.</span>
        </div>
        <div className="text-[11px] text-slate-400">로그에 기록된 Claude 예상 비용 기준의 대략값입니다 (로그에 남지 않는 호출은 빠짐). 정확한 잔액은 콘솔 Billing 화면이 기준입니다.</div>
      </div>}
    </div>
  );
}
