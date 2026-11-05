import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { format } from 'sql-formatter';
import { FaqRegisterModal, type Faq } from '@/components/FaqPanel';
import ClaudeStatsPanel from '@/components/ClaudeStatsPanel';
import { Activity, BrainCircuit, MessageSquare, Database, Sparkles, Search, Clock, RefreshCw, ChevronRight, X, TerminalSquare, BookOpen, ChevronLeft, ThumbsUp, ThumbsDown, Copy, Check, Download, ChevronDown, ChevronUp } from 'lucide-react';

const formatLatency = (ms: number | undefined) => {
  if (!ms) return '-';
  const totalSeconds = ms / 1000;
  if (totalSeconds >= 60) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = (totalSeconds % 60).toFixed(1);
    return `${mins}분 ${secs}초`;
  }
  return `${totalSeconds.toFixed(1)}초`;
};

export default function Logs() {
  const [activeTab, setActiveTab] = useState('logs');
  const [logs, setLogs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedLog, setSelectedLog] = useState<any>(null);
  const [faqDraft, setFaqDraft] = useState<Faq | null>(null); // [답변 등록] 입학처 Q&A 등록 창
  const [copiedScrap, setCopiedScrap] = useState(false);
  const [copiedSql, setCopiedSql] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedId, setCopiedId] = useState<number | null>(null); // [ID 복사] 방금 복사한 로그 ID

  // [ID 복사] '#525' 형태로 복사 → Claude 에 그대로 붙여 넣어 분석 요청
  // http(IP 접속)에서는 clipboard API 가 막혀 있어 예전 방식으로 대신 복사
  const copyLogId = async (id: number, e?: { stopPropagation: () => void }) => {
    e?.stopPropagation();
    const text = `#${id}`;
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
      else {
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
      }
      setCopiedId(id);
      setTimeout(() => setCopiedId(prev => (prev === id ? null : prev)), 1500);
    } catch { /* 복사 실패 시 조용히 무시 */ }
  };
  const idBadge = (id: number, dark = false) => (
    <button type="button" onClick={e => copyLogId(id, e)} title="누르면 ID 복사 (Claude 에게 붙여 넣어 분석 요청)"
            className={`inline-flex items-center gap-1 font-mono font-bold rounded px-1.5 py-0.5 text-[11px] transition-colors whitespace-nowrap ${
              dark ? 'bg-indigo-800 hover:bg-indigo-700 border border-indigo-700 text-white'
                   : copiedId === id ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 hover:bg-indigo-100 text-slate-600 hover:text-indigo-700 border border-slate-200'}`}>
      {copiedId === id ? <Check size={11} className={dark ? 'text-emerald-400' : ''} /> : <Copy size={11} className={dark ? 'text-indigo-300' : 'opacity-60'} />}
      #{id}{copiedId === id && <span className="font-sans">복사됨</span>}
    </button>
  );
  const [isExpandedScrap, setIsExpandedScrap] = useState(false);

  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const [hideTest, setHideTest] = useState(false);
  // [대화 로그 필터] 내용 검색·월·직군·모델·반응 속도 — 서버에서 거르고 페이지 단위로 받음
  const [showFilters, setShowFilters] = useState(false); // 검색·필터 줄 펼침
  const [qInput, setQInput] = useState('');
  const [filters, setFilters] = useState({ q: '', month: '', role: '', model: '', speed: '' });
  const [facets, setFacets] = useState<{ months: string[]; models: { name: string; count: number }[] }>({ months: [], models: [] });
  const [total, setTotal] = useState(0);
  const ITEMS_PER_PAGE = 10;

  useEffect(() => {
    axios.get('/api/logs/audit/facets').then(res => setFacets(res.data)).catch(() => {});
  }, []);
  useEffect(() => {
    fetchLogs();
  }, [currentPage, filters, hideTest]);

  const setFilter = (key: keyof typeof filters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setCurrentPage(1);
  };
  const resetFilters = () => {
    setQInput(''); setFilters({ q: '', month: '', role: '', model: '', speed: '' }); setCurrentPage(1);
  };
  const filterCount = Object.values(filters).filter(v => v !== '').length;
  const filterActive = filterCount > 0;

  const fetchLogs = async () => {
    try {
      setIsLoading(true);
      const res = await axios.get('/api/logs/audit', {
        params: { ...filters, exclude_test: hideTest, page: currentPage, size: ITEMS_PER_PAGE },
      });
      if (res.data.status === 'success') {
        setLogs(res.data.data);
        setTotal(res.data.total ?? res.data.data.length);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleFeedback = async (logId: number, currentFeedback: string | null, targetFeedback: 'UP' | 'DOWN') => {
    try {
      const newFeedback = currentFeedback === targetFeedback ? null : targetFeedback;
      const res = await axios.put(`/api/logs/audit/${logId}/feedback`, { feedback: newFeedback });
      if (res.data.status === 'success') {
        setLogs(prev => prev.map(l => l.id === logId ? { ...l, user_feedback: newFeedback } : l));
        if (selectedLog && selectedLog.id === logId) {
          setSelectedLog((prev: any) => ({ ...prev, user_feedback: newFeedback }));
        }
      }
    } catch (err) {
      console.error(err);
      alert('피드백 업데이트 실패');
    }
  };


  // Pagination Logic
  // [테스트] 시험 질문(질문에 '[테스트]' 표시)은 실제 비용이라 지우지 않고 표시·숨기기만 함
  const isTestLog = (l: any) => (l.question || '').includes('[테스트]');
  // 서버가 조건에 맞는 한 페이지만 보내줌 (총 건수는 total)
  const totalPages = Math.ceil(total / ITEMS_PER_PAGE) || 1;
  const paginatedLogs = logs;

  const renderPagination = () => {
    const startIdx = total === 0 ? 0 : (currentPage - 1) * ITEMS_PER_PAGE + 1;
    const endIdx = Math.min(currentPage * ITEMS_PER_PAGE, total);

    return (
      <div className="flex flex-col sm:flex-row justify-between items-center my-3 gap-3 min-w-0 px-2">
        <div className="text-[11px] md:text-xs text-gray-500 font-bold">
          총 {total.toLocaleString()}건 중 {startIdx.toLocaleString()} - {endIdx.toLocaleString()}건 표시
        </div>
        <div className="flex items-center gap-1.5">
          <button 
            onClick={() => setCurrentPage(Math.max(1, currentPage - 1))} 
            disabled={currentPage === 1} 
            className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 text-gray-500 disabled:opacity-30 hover:bg-gray-50 transition-colors"
          >
            <ChevronLeft size={16} />
          </button>
          <div className="flex gap-1 min-w-0">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(pageNum => {
              if (totalPages > 7) {
                if (pageNum !== 1 && pageNum !== totalPages && Math.abs(currentPage - pageNum) > 1) {
                  if (pageNum === 2 || pageNum === totalPages - 1) return <span key={pageNum} className="text-gray-400">...</span>;
                  return null;
                }
              }
              return (
                <button 
                  key={pageNum} 
                  onClick={() => setCurrentPage(pageNum)} 
                  className={`w-7 h-7 rounded-md text-xs font-bold transition-all ${currentPage === pageNum ? 'bg-indigo-600 text-white shadow-md' : 'text-gray-600 hover:bg-indigo-50 border border-transparent'}`}
                >
                  {pageNum}
                </button>
              );
            })}
          </div>
          <button 
            onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))} 
            disabled={currentPage === totalPages} 
            className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 text-gray-500 disabled:opacity-30 hover:bg-gray-50 transition-colors"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col min-w-0 pb-24 md:pb-6 overflow-y-auto bg-slate-50/50 p-1 md:p-6">
      
      {/* 1. Header & Tabs */}
      <div className="bg-gradient-to-br from-indigo-900 via-indigo-800 to-purple-900 rounded-t-xl shadow-md pt-3 px-3 md:pt-4 md:px-6 shrink-0 min-w-0 flex flex-col relative overflow-hidden text-white">
        <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
          <BrainCircuit size={120} />
        </div>
        
        <div className="relative z-10 flex justify-between items-center mb-4 min-w-0">
          <div className="min-w-0 flex items-center gap-3">
            <div className="bg-white/10 p-2 rounded-lg backdrop-blur-sm border border-white/10">
              <Activity className="text-amber-400" size={20} />
            </div>
            <h1 className="text-lg md:text-xl font-extrabold text-white tracking-tight flex items-center gap-2">
              시스템 로그 및 AI 품질관리
            </h1>
          </div>
          
          <div className="flex flex-wrap gap-2">
            <button 
              onClick={fetchLogs}
              disabled={isLoading}
              className="flex items-center gap-2 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors border border-white/20 text-xs font-bold shadow-sm"
            >
              <RefreshCw size={14} className={isLoading ? "animate-spin text-indigo-300" : "text-indigo-300"} />
              <span className="hidden md:inline">{isLoading ? '새로고침 중...' : '로그 새로고침'}</span>
            </button>
          </div>
        </div>

        {/* Custom Tab Menu (Dashboard와 동일한 스타일 적용) */}
        <div className="relative z-10 flex gap-1 overflow-x-auto min-w-0 mt-2">
          <button
            onClick={() => setActiveTab('logs')}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'logs' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <Database size={16} className="shrink-0" /> 
            <span className="hidden sm:inline">실시간 대화 로그</span>
            <span className="sm:hidden">대화 로그</span>
          </button>
          <button
            onClick={() => setActiveTab('usage')}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'usage' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <Activity size={16} className="shrink-0" />
            <span className="hidden sm:inline">Claude 사용 통계</span>
            <span className="sm:hidden">사용 통계</span>
          </button>
        </div>
      </div>

      {/* 2. Main Content Area */}
      <div className="flex-1 py-6 min-w-0">
        
        {/* === 탭 1: 실시간 대화 로그 === */}
        {activeTab === 'logs' && (
          <div className="animate-in fade-in duration-300 min-w-0">
            <div className="bg-white border border-slate-200 shadow-sm rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-100 flex justify-between items-center bg-slate-50/80">
                <h3 className="font-bold text-slate-800 flex items-center gap-2 text-sm">
                  <Activity className="text-slate-400" size={16} /> 실시간 대화 기록
                </h3>
                <div className="flex items-center gap-3">
                  <button onClick={() => setShowFilters(v => !v)}
                          className={`flex items-center gap-1 px-2.5 py-1 text-xs font-bold rounded-md border transition-colors ${showFilters || filterActive ? 'border-indigo-300 bg-indigo-50 text-indigo-700' : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'}`}>
                    <Search size={13} /> 검색·필터
                    {filterActive && <span className="ml-0.5 px-1.5 rounded-full bg-indigo-600 text-white text-[10px]">{filterCount}</span>}
                    {showFilters ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                  <label className="flex items-center gap-1.5 text-xs font-bold text-slate-600 cursor-pointer select-none">
                    <input type="checkbox" checked={hideTest} onChange={e => { setHideTest(e.target.checked); setCurrentPage(1); }} className="accent-indigo-600" />
                    테스트 숨기기
                  </label>
                  <span className="text-xs font-bold bg-white border border-slate-200 text-slate-600 px-2 py-1 rounded-full shadow-sm">{total.toLocaleString()} 건</span>
                </div>
              </div>
              {/* [대화 로그 필터] 자주 쓰지 않아 [검색·필터] 버튼으로 펼침. 접어도 걸린 조건은 그대로 적용 */}
              {showFilters && <div className="px-5 py-2.5 border-b border-slate-100 flex flex-wrap items-center gap-2 bg-white">
                <div className="flex items-center gap-1 flex-1 min-w-[200px] max-w-[360px]">
                  <input type="text" value={qInput} placeholder="질문·답변 내용 검색"
                         className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 flex-1 min-w-0"
                         onChange={e => setQInput(e.target.value)}
                         onKeyDown={e => { if (e.key === 'Enter') setFilter('q', qInput.trim()); }} />
                  <button onClick={() => setFilter('q', qInput.trim())}
                          className="px-2.5 py-1.5 text-xs font-bold rounded-md bg-indigo-600 text-white hover:bg-indigo-700 whitespace-nowrap">검색</button>
                </div>
                {/* 월 선택: 달이 쌓여도 목록이 길어지지 않게 달력(년·월) 선택 */}
                <div className="flex items-center gap-1">
                  <input type="month" value={filters.month} onChange={e => setFilter('month', e.target.value)}
                         min={facets.months[facets.months.length - 1] || undefined} max={facets.months[0] || undefined}
                         title="월 선택 (비우면 전체 기간)"
                         className="border border-slate-300 rounded-md px-2 py-1 text-xs bg-white text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500" />
                  {filters.month
                    ? <button onClick={() => setFilter('month', '')} title="전체 기간" className="text-slate-400 hover:text-slate-600"><X size={14} /></button>
                    : <span className="text-[11px] text-slate-400 whitespace-nowrap">전체 기간</span>}
                </div>
                <select value={filters.role} onChange={e => setFilter('role', e.target.value)} className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500">
                  <option value="">전체 직군</option>
                  <option value="student">수험생</option>
                  <option value="staff">교직원</option>
                </select>
                <select value={filters.model} onChange={e => setFilter('model', e.target.value)} className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 max-w-[200px]">
                  <option value="">전체 모델</option>
                  {facets.models.map(m => <option key={m.name} value={m.name}>{m.name} ({m.count.toLocaleString()})</option>)}
                </select>
                <select value={filters.speed} onChange={e => setFilter('speed', e.target.value)} className="border border-slate-300 rounded-md px-2 py-1.5 text-xs bg-white text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500">
                  <option value="">전체 반응 속도</option>
                  <option value="fast">10초 미만</option>
                  <option value="mid">10~30초</option>
                  <option value="slow">30~60초</option>
                  <option value="vslow">60초 이상</option>
                </select>
                {filterActive && (
                  <button onClick={resetFilters} className="px-2 py-1.5 text-xs font-bold rounded-md border border-slate-300 text-slate-600 hover:bg-slate-50 whitespace-nowrap">
                    <X size={12} className="inline" /> 필터 초기화
                  </button>
                )}
              </div>}
              
              {/* Desktop Table View */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-left border-collapse min-w-[800px]">
                  <thead>
                    <tr className="bg-white border-b border-slate-100">
                      <th className="px-4 py-3 text-xs font-bold text-slate-400 uppercase tracking-wider w-[140px]">ID · 일시</th>
                      <th className="px-4 py-3 text-xs font-bold text-slate-400 uppercase tracking-wider w-[120px]">직군 / 모델</th>
                      <th className="px-4 py-3 text-xs font-bold text-slate-400 uppercase tracking-wider">질문 요약</th>
                      <th className="px-4 py-3 text-xs font-bold text-slate-400 uppercase tracking-wider text-center w-[120px]">반응 속도</th>
                      <th className="px-4 py-3 text-xs font-bold text-slate-400 uppercase tracking-wider text-center w-[100px]">관리자 평가</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {paginatedLogs.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-16 text-center text-slate-400 font-medium text-sm bg-slate-50/50">
                          {filterActive ? '조건에 맞는 대화 로그가 없습니다.' : '아직 수집된 대화 로그가 없습니다.'}
                        </td>
                      </tr>
                    ) : (
                      paginatedLogs.map(log => (
                        <tr key={log.id} onClick={() => setSelectedLog(log)} className="hover:bg-indigo-50/40 transition-colors group cursor-pointer">
                          <td className="px-4 py-3 align-middle text-xs text-slate-500 font-medium whitespace-nowrap">
                            <div className="flex flex-col items-start gap-1">
                              {idBadge(log.id)}
                              {log.created_at}
                            </div>
                          </td>
                          <td className="px-4 py-3 align-middle">
                            <div className="flex flex-col gap-1">
                              <span className={`text-[11px] font-bold w-fit px-1.5 py-0.5 rounded border ${
                                log.user_role === 'staff' ? 'text-indigo-700 bg-indigo-50 border-indigo-200' : 'text-emerald-700 bg-emerald-50 border-emerald-200'
                              }`}>
                                {log.user_role === 'staff' ? '교직원' : '수험생'}
                              </span>
                              <span className="text-[10px] text-slate-400 truncate max-w-[100px]" title={log.model_name}>
                                {log.model_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 align-middle max-w-[300px] lg:max-w-[500px]">
                            <div className="flex flex-col gap-1">
                              <div className="font-semibold text-slate-800 text-sm truncate" title={log.question}>
                                <span className="text-indigo-400 font-bold mr-1">Q.</span>{isTestLog(log) && <span className="text-[10px] font-bold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded mr-1">테스트</span>} {log.question}
                              </div>
                              <div className="text-xs text-slate-500 truncate" title={log.answer}>
                                <span className="text-slate-400 font-bold mr-1">A.</span> {log.answer}
                              </div>
                              {log.total_tokens != null && (
                                <div className="text-[10px] text-slate-400 font-bold mt-0.5">
                                  🪙 총 {log.total_tokens.toLocaleString()} 토큰 (약 {Number(log.estimated_cost).toFixed(1)}원)
                                </div>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 align-middle text-center">
                            <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap ${
                              (log.latency_ms || 0) < 10000 ? 'bg-emerald-50 text-emerald-600 border-emerald-100' : 
                              (log.latency_ms || 0) < 30000 ? 'bg-amber-50 text-amber-600 border-amber-100' : 'bg-rose-50 text-rose-600 border-rose-100'
                            }`}>
                              {formatLatency(log.latency_ms)}
                            </span>
                          </td>
                          <td className="px-4 py-3 align-middle text-center" onClick={(e) => e.stopPropagation()}>
                            <div className="flex justify-center gap-1">
                              <button 
                                onClick={() => toggleFeedback(log.id, log.user_feedback, 'UP')}
                                className={`p-1.5 rounded-md transition-colors ${log.user_feedback === 'UP' ? 'bg-indigo-100 text-indigo-600' : 'text-slate-300 hover:bg-slate-100 hover:text-slate-500'}`}
                                title="분석 제외 (좋아요)"
                              >
                                <ThumbsUp size={16} className={log.user_feedback === 'UP' ? 'fill-current' : ''} />
                              </button>
                              <button 
                                onClick={() => toggleFeedback(log.id, log.user_feedback, 'DOWN')}
                                className={`p-1.5 rounded-md transition-colors ${log.user_feedback === 'DOWN' ? 'bg-rose-100 text-rose-600' : 'text-slate-300 hover:bg-slate-100 hover:text-slate-500'}`}
                                title="분석 포함 (싫어요)"
                              >
                                <ThumbsDown size={16} className={log.user_feedback === 'DOWN' ? 'fill-current' : ''} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                  {logs.length > 0 && (
                    <tfoot className="bg-slate-100 border-t border-slate-300">
                      <tr>
                        <td colSpan={5} className="py-1 px-4">
                          {renderPagination()}
                        </td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>

              {/* Mobile Card View */}
              <div className="block md:hidden divide-y divide-slate-100">
                {paginatedLogs.length === 0 ? (
                  <div className="py-16 text-center text-slate-400 font-medium text-sm bg-slate-50/50">
                    {filterActive ? '조건에 맞는 대화 로그가 없습니다.' : '아직 수집된 대화 로그가 없습니다.'}
                  </div>
                ) : (
                  paginatedLogs.map(log => (
                    <div key={log.id} onClick={() => setSelectedLog(log)} className="p-4 hover:bg-indigo-50/40 active:bg-indigo-50 transition-colors cursor-pointer flex flex-col gap-2">
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                            log.user_role === 'staff' ? 'text-indigo-700 bg-indigo-50 border-indigo-200' : 'text-emerald-700 bg-emerald-50 border-emerald-200'
                          }`}>
                            {log.user_role === 'staff' ? '교직원' : '수험생'}
                          </span>
                          {idBadge(log.id)}
                          <span className="text-[11px] text-slate-500 font-medium">{log.created_at}</span>
                        </div>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap ${
                          (log.latency_ms || 0) < 10000 ? 'bg-emerald-50 text-emerald-600 border-emerald-100' : 
                          (log.latency_ms || 0) < 30000 ? 'bg-amber-50 text-amber-600 border-amber-100' : 'bg-rose-50 text-rose-600 border-rose-100'
                        }`}>
                          {formatLatency(log.latency_ms)}
                        </span>
                      </div>
                      
                      <div className="font-semibold text-slate-800 text-sm line-clamp-2 mt-1 leading-snug" title={log.question}>
                        <span className="text-indigo-400 font-bold mr-1">Q.</span>{isTestLog(log) && <span className="text-[10px] font-bold bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded mr-1">테스트</span>} {log.question}
                      </div>
                      {log.total_tokens != null && (
                        <div className="text-[10px] text-slate-500 font-bold">
                          🪙 총 {log.total_tokens.toLocaleString()} 토큰 (약 {Number(log.estimated_cost).toFixed(1)}원)
                        </div>
                      )}
                      
                      <div className="flex justify-between items-center mt-2 pt-2 border-t border-slate-100/80 border-dashed">
                         <span className="text-[9px] text-slate-400 truncate font-mono bg-slate-50 px-1.5 py-0.5 rounded border border-slate-100 max-w-[150px]" title={log.model_name}>
                           {log.model_name}
                         </span>
                         <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                           <button 
                             onClick={() => toggleFeedback(log.id, log.user_feedback, 'UP')}
                             className={`p-1.5 rounded-md transition-colors ${log.user_feedback === 'UP' ? 'bg-indigo-100 text-indigo-600' : 'text-slate-300'}`}
                           >
                             <ThumbsUp size={14} className={log.user_feedback === 'UP' ? 'fill-current' : ''} />
                           </button>
                           <button 
                             onClick={() => toggleFeedback(log.id, log.user_feedback, 'DOWN')}
                             className={`p-1.5 rounded-md transition-colors ${log.user_feedback === 'DOWN' ? 'bg-rose-100 text-rose-600' : 'text-slate-300'}`}
                           >
                             <ThumbsDown size={14} className={log.user_feedback === 'DOWN' ? 'fill-current' : ''} />
                           </button>
                         </div>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Mobile Only Pagination */}
              <div className="md:hidden">
                {logs.length > 0 && renderPagination()}
              </div>
            </div>
          </div>
        )}

        {/* === 탭 3: Claude 사용 통계 === */}
        {activeTab === 'usage' && (
          <div className="animate-in fade-in duration-300 min-w-0 py-4"><ClaudeStatsPanel /></div>
        )}


      </div>

      {faqDraft && <FaqRegisterModal initial={faqDraft} onClose={() => setFaqDraft(null)} />}

      {/* Log Detail Modal */}
      {selectedLog && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-indigo-800 flex justify-between items-center bg-indigo-900 text-white shrink-0">
              <h3 className="font-bold flex items-center gap-2">
                <TerminalSquare size={18} className="text-indigo-400" />
                로그 상세 {idBadge(selectedLog.id, true)}
              </h3>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setFaqDraft({
                    topic: '',  // 주제는 직접 짧게 (질문 원문은 '실제 질문 예'에 들어감)
                    answer: selectedLog.answer || '',
                    apply_year: '',
                    sample_question: (selectedLog.question || '').trim().slice(0, 500),
                    is_active: 'Y',
                    source_log_id: selectedLog.id,
                  })}
                  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 border border-emerald-500 rounded-md text-xs font-bold transition-colors flex items-center gap-1.5 shadow-sm"
                  title="이 질문의 입학처 공식 답변을 Q&A 로 등록합니다 (다음 질문부터 챗봇이 참고)"
                >
                  <MessageSquare size={14} /> 답변 등록
                </button>
                <button
                  onClick={() => {
                    const text = `[Log ID: #${selectedLog.id}]
Question: ${selectedLog.question || ''}
Answer: ${selectedLog.answer || ''}

[Performance]
Total Latency: ${formatLatency(selectedLog.latency_ms)}
Router AI: ${formatLatency(selectedLog.router_latency_ms)}
DB/RAG: ${formatLatency(selectedLog.db_latency_ms)}
Final Chatbot AI: ${formatLatency(selectedLog.chat_latency_ms)}

[Models & Tokens]
Final Model: ${selectedLog.model_name || ''} (In: ${selectedLog.chat_in_tokens || 0}, Out: ${selectedLog.chat_out_tokens || 0})${selectedLog.chat_mode ? ` · ${selectedLog.chat_mode}` : ''}
Router Model: ${selectedLog.router_model_name || ''} (In: ${selectedLog.router_in_tokens || 0}, Out: ${selectedLog.router_out_tokens || 0})${selectedLog.router_mode ? ` · ${selectedLog.router_mode}` : ''}
Total Tokens: ${selectedLog.total_tokens || 0}
Estimated Cost: ₩${selectedLog.estimated_cost ? Number(selectedLog.estimated_cost).toFixed(1) : 0}

[RAG & SQL Context]
SQL Query:
${selectedLog.sql_query || 'NONE'}

RAG Query:
${selectedLog.rag_query || 'NONE'}

RAG Documents:
${selectedLog.rag_documents || 'NONE'}

Scraped Context:
${selectedLog.scraped_context || 'NONE'}`;
                    
                    // [널 바이트 제거] 윈도우 클립보드 복사 시 문자열 종단(Null-Terminator) 잘림 방지
                    const cleanText = text.replace(/\0/g, '');
                    navigator.clipboard.writeText(cleanText);
                    setCopiedAll(true);
                    setTimeout(() => setCopiedAll(false), 2000);
                  }}
                  className="px-3 py-1.5 bg-indigo-800 hover:bg-indigo-700 border border-indigo-700 rounded-md text-xs font-bold transition-colors flex items-center gap-1.5 shadow-sm"
                  title="전체 로그 내용을 클립보드에 복사합니다"
                >
                  {copiedAll ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} className="text-indigo-200" />}
                  {copiedAll ? '복사 완료' : '전체 복사'}
                </button>
                <div className="w-px h-4 bg-indigo-700/50 mx-1"></div>
                <button onClick={() => setSelectedLog(null)} className="p-1.5 hover:bg-white/20 rounded-md transition-colors" title="닫기">
                  <X size={18} />
                </button>
              </div>
            </div>
            
            <div className="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1 min-h-0 bg-slate-50 custom-scrollbar">
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* 1. 일시 및 전체 소요시간 (Left, 1 column) */}
                <div className="bg-white p-4 sm:p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center gap-3 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                    <Clock size={14} className="text-indigo-500" /> 일시 및 총 소요시간
                  </div>
                  <div>
                    <div className="font-bold text-slate-700 text-xs sm:text-sm mb-1">{selectedLog.created_at}</div>
                    <div className="text-indigo-600 text-sm font-bold">총 {formatLatency(selectedLog.latency_ms)} 소요</div>
                  </div>
                </div>

                {/* 2. 구간별 세부 소요시간 분석 (Right, 2 columns) */}
                <div className="md:col-span-2 bg-white p-4 sm:p-5 rounded-xl border border-slate-200 shadow-sm relative overflow-hidden flex flex-col justify-center">
                  <div className="absolute top-0 right-0 w-1 h-full bg-blue-500"></div>
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Activity size={14} className="text-blue-500" /> 구간별 세부 소요시간 분석
                  </div>
                  {(selectedLog.router_latency_ms != null || selectedLog.db_latency_ms != null || selectedLog.chat_latency_ms != null) ? (
                    <div className="grid grid-cols-3 gap-2 sm:gap-4">
                      <div className="flex flex-col">
                        <span className="text-[10px] sm:text-xs text-slate-500 mb-1">라우터 AI 검토</span>
                        <span className="font-bold text-slate-700 text-xs sm:text-sm">{selectedLog.router_latency_ms != null ? formatLatency(selectedLog.router_latency_ms) : '-'}</span>
                      </div>
                      <div className="flex flex-col border-l border-slate-100 pl-3 sm:pl-4">
                        <span className="text-[10px] sm:text-xs text-slate-500 mb-1">DB / RAG 검색</span>
                        <span className="font-bold text-slate-700 text-xs sm:text-sm">{selectedLog.db_latency_ms != null ? formatLatency(selectedLog.db_latency_ms) : '-'}</span>
                      </div>
                      <div className="flex flex-col border-l border-slate-100 pl-3 sm:pl-4">
                        <span className="text-[10px] sm:text-xs text-slate-500 mb-1">최종 답변 생성</span>
                        <span className="font-bold text-slate-700 text-xs sm:text-sm">{selectedLog.chat_latency_ms != null ? formatLatency(selectedLog.chat_latency_ms) : '-'}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-400 font-medium">이전 로그 데이터는 세부 소요시간 기록이 제공되지 않습니다.</div>
                  )}
                </div>
              </div>
              
              {selectedLog.total_tokens != null && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">총 소모 토큰 및 비용</div>
                    <div className="font-bold text-indigo-600 text-xl">{selectedLog.total_tokens.toLocaleString()} <span className="text-sm text-slate-500 font-medium">Tokens</span></div>
                    <div className="text-xs text-slate-500 font-bold mt-1">약 {Number(selectedLog.estimated_cost).toFixed(1)}원 과금됨</div>
                  </div>
                  <div className={`bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center ${!selectedLog.router_model_name || selectedLog.router_model_name === 'NONE' ? 'opacity-50' : ''}`}>
                    <div className="text-sm font-extrabold text-blue-600 uppercase tracking-wider mb-2 truncate flex items-center flex-wrap gap-1" title={selectedLog.router_model_name || 'NONE'}>
                      라우터 AI 
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200 tracking-normal">
                        {selectedLog.router_model_name || '사용 안함'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center text-sm mb-1">
                      <span className="text-slate-500">입력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.router_in_tokens?.toLocaleString() || 0}</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-slate-500">출력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.router_out_tokens?.toLocaleString() || 0}</span>
                    </div>
                    {selectedLog.router_mode && (
                      <div className="flex justify-between items-center text-sm mt-1">
                        <span className="text-slate-500">호출 설정:</span>
                        <span className="font-bold text-blue-700 text-xs">{selectedLog.router_mode}</span>
                      </div>
                    )}
                  </div>
                  <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center">
                    <div className="text-sm font-extrabold text-indigo-600 uppercase tracking-wider mb-2 truncate flex items-center flex-wrap gap-1" title={selectedLog.model_name}>
                      최종 챗봇 AI 
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 tracking-normal">
                        {selectedLog.model_name}
                      </span>
                    </div>
                    <div className="flex justify-between items-center text-sm mb-1">
                      <span className="text-slate-500">입력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.chat_in_tokens?.toLocaleString() || 0}</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-slate-500">출력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.chat_out_tokens?.toLocaleString() || 0}</span>
                    </div>
                    {selectedLog.chat_mode && (
                      <div className="flex justify-between items-center text-sm mt-1">
                        <span className="text-slate-500">호출 설정:</span>
                        <span className="font-bold text-indigo-700 text-xs">{selectedLog.chat_mode}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="bg-white p-5 rounded-xl border border-indigo-100 shadow-sm relative overflow-hidden">
                <h4 className="font-bold text-indigo-900 mb-3 flex items-center gap-2">
                  <MessageSquare size={16} className="text-indigo-500"/> 원본 질문 (Question)
                </h4>
                <p className="text-slate-800 whitespace-pre-wrap text-sm leading-relaxed font-medium">{selectedLog.question}</p>
                {selectedLog.scraped_context && (
                  <div className="mt-4 p-3 bg-slate-50 rounded-lg text-xs border border-slate-200 group relative">
                    <div className="flex justify-between items-center mb-1.5 flex-wrap gap-2">
                      <div className="font-bold text-slate-700 flex items-center gap-1.5">
                        <span>참고용 스크랩 원문</span>
                        <span className="text-[10px] text-slate-400 font-normal">({selectedLog.scraped_context.length.toLocaleString()}자)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button 
                          onClick={() => setIsExpandedScrap(!isExpandedScrap)}
                          className="text-slate-600 hover:text-indigo-600 transition-colors px-2 py-1 bg-white rounded shadow-sm border border-slate-200 flex items-center gap-1 text-[10px] font-bold"
                          title={isExpandedScrap ? "접기" : "전체 펼쳐보기"}
                        >
                          {isExpandedScrap ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                          <span>{isExpandedScrap ? '접기' : '전체보기'}</span>
                        </button>
                        <button 
                          onClick={() => { 
                            const cleanText = (selectedLog.scraped_context || '').replace(/\0/g, '');
                            const blob = new Blob([cleanText], { type: 'text/plain;charset=utf-8' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `Log_${selectedLog.id}_스크랩원문.txt`;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                            URL.revokeObjectURL(url);
                          }} 
                          className="text-slate-600 hover:text-indigo-600 transition-colors px-2 py-1 bg-white rounded shadow-sm border border-slate-200 flex items-center gap-1 text-[10px] font-bold"
                          title="스크랩 원문 전체를 .txt 파일로 다운로드합니다"
                        >
                          <Download size={12} className="text-indigo-500" />
                          <span>TXT 다운로드</span>
                        </button>
                        <button 
                          onClick={() => { 
                            const cleanText = (selectedLog.scraped_context || '').replace(/\0/g, '');
                            navigator.clipboard.writeText(cleanText); 
                            setCopiedScrap(true); 
                            setTimeout(() => setCopiedScrap(false), 2000); 
                          }} 
                          className="text-slate-600 hover:text-indigo-600 transition-colors px-2 py-1 bg-white rounded shadow-sm border border-slate-200 flex items-center gap-1 text-[10px] font-bold"
                          title="원문 전체 복사하기"
                        >
                          {copiedScrap ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                          <span>{copiedScrap ? '복사됨' : '복사'}</span>
                        </button>
                      </div>
                    </div>
                    <div className={`text-slate-600 leading-relaxed font-mono text-[11px] bg-white p-2.5 rounded border border-slate-100 ${isExpandedScrap ? 'max-h-96 overflow-y-auto whitespace-pre-wrap' : 'line-clamp-3'}`} title={selectedLog.scraped_context}>
                      {selectedLog.scraped_context}
                    </div>
                  </div>
                )}
              </div>

              {(() => {
                const hasSql = selectedLog.sql_query && selectedLog.sql_query !== 'NONE';
                const hasRag = (selectedLog.rag_query && selectedLog.rag_query !== 'NONE') || (selectedLog.rag_documents && selectedLog.rag_documents !== 'NONE');

                let formattedSql = '';
                if (hasSql) {
                  try {
                    formattedSql = format(selectedLog.sql_query, { language: 'tsql' });
                  } catch (e) {
                    formattedSql = selectedLog.sql_query;
                  }
                }

                const renderSqlBlock = () => (
                  <div className="bg-[#1e1e2e] p-5 rounded-xl shadow-inner overflow-hidden flex flex-col relative group h-full">
                    <div className="flex justify-between items-center mb-3">
                      <h4 className="font-bold text-blue-400 flex items-center gap-2 text-sm">
                        <Database size={16} /> 추출된 T-SQL 쿼리
                      </h4>
                      <button 
                        onClick={() => {
                          navigator.clipboard.writeText(formattedSql);
                          setCopiedSql(true);
                          setTimeout(() => setCopiedSql(false), 2000);
                        }}
                        className="text-slate-400 hover:text-white transition-colors p-1.5 bg-white/5 hover:bg-white/10 rounded-md shadow-sm border border-white/10 flex items-center gap-1 opacity-0 group-hover:opacity-100 focus:opacity-100"
                        title="SQL 복사하기"
                      >
                        {copiedSql ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                        <span className="text-[10px] font-bold">{copiedSql ? '복사됨' : '복사'}</span>
                      </button>
                    </div>
                    <div className="flex-1 overflow-auto custom-scrollbar">
                      <pre className="text-[#a6accd] text-xs whitespace-pre-wrap font-mono">
                        {formattedSql}
                      </pre>
                    </div>
                  </div>
                );

                if (hasSql && hasRag) {
                  return (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {renderSqlBlock()}
                      <div className="flex flex-col gap-4">
                        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col h-full">
                          <h4 className="font-bold text-emerald-600 mb-3 flex items-center gap-2 text-sm">
                            <BookOpen size={16} /> RAG (문서 검색) 키워드
                          </h4>
                          <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg font-medium text-sm border border-emerald-100 flex-1">
                            {selectedLog.rag_query}
                          </div>
                        </div>
                        {selectedLog.rag_documents && (
                          <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col h-full">
                            <h4 className="font-bold text-emerald-600 mb-3 flex items-center gap-2 text-sm">
                              <BookOpen size={16} /> 참고된 PDF 문서명
                            </h4>
                            <div className="p-3 bg-slate-50 text-slate-700 rounded-lg font-medium text-sm border border-slate-100 whitespace-pre-wrap flex-1">
                              {selectedLog.rag_documents}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                }

                if (hasSql && !hasRag) {
                  return renderSqlBlock();
                }

                if (!hasSql && hasRag) {
                  return (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                        <h4 className="font-bold text-emerald-600 mb-3 flex items-center gap-2 text-sm">
                          <BookOpen size={16} /> RAG (문서 검색) 키워드
                        </h4>
                        <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg font-medium text-sm border border-emerald-100 flex-1">
                          {selectedLog.rag_query}
                        </div>
                      </div>
                      {selectedLog.rag_documents && (
                        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                          <h4 className="font-bold text-emerald-600 mb-3 flex items-center gap-2 text-sm">
                            <BookOpen size={16} /> 참고된 PDF 문서명
                          </h4>
                          <div className="p-3 bg-slate-50 text-slate-700 rounded-lg font-medium text-sm border border-slate-100 whitespace-pre-wrap flex-1">
                            {selectedLog.rag_documents}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                }

                return null;
              })()}

              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm relative overflow-hidden">
                <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                  <Sparkles size={16} className="text-slate-600"/> 최종 AI 답변 (Answer)
                </h4>
                <div className="text-slate-700 whitespace-pre-wrap text-sm leading-relaxed bg-slate-50/50 p-4 rounded-lg border border-slate-100">
                  {selectedLog.answer ? selectedLog.answer.replace(/\$\\rightarrow\$/g, '→').replace(/\\rightarrow/g, '→') : ''}
                </div>
                
                <div className="mt-4 flex items-center justify-end gap-2 pt-4 border-t border-slate-100">
                  <span className="text-xs font-bold text-slate-400 mr-2">관리자 평가:</span>
                  <button 
                    onClick={() => toggleFeedback(selectedLog.id, selectedLog.user_feedback, 'UP')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-sm font-bold ${selectedLog.user_feedback === 'UP' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-50 text-slate-400 hover:bg-slate-100'}`}
                  >
                    <ThumbsUp size={16} className={selectedLog.user_feedback === 'UP' ? 'fill-current' : ''} />
                    분석 제외 (좋아요)
                  </button>
                  <button 
                    onClick={() => toggleFeedback(selectedLog.id, selectedLog.user_feedback, 'DOWN')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-sm font-bold ${selectedLog.user_feedback === 'DOWN' ? 'bg-rose-100 text-rose-700' : 'bg-slate-50 text-slate-400 hover:bg-slate-100'}`}
                  >
                    <ThumbsDown size={16} className={selectedLog.user_feedback === 'DOWN' ? 'fill-current' : ''} />
                    분석 포함 (싫어요)
                  </button>
                </div>
              </div>

            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
