import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Activity, BrainCircuit, MessageSquare, Database, Sparkles, AlertTriangle, Clock, RefreshCw, ChevronRight, X, TerminalSquare, BookOpen, Key, ChevronLeft, ThumbsUp, ThumbsDown } from 'lucide-react';

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
  const [analytics, setAnalytics] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedLog, setSelectedLog] = useState<any>(null);

  // Pagination states
  const [currentPage, setCurrentPage] = useState(1);
  const ITEMS_PER_PAGE = 10;

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      setIsLoading(true);
      const res = await axios.get('http://127.0.0.1:8000/logs/audit');
      if (res.data.status === 'success') {
        setLogs(res.data.data);
        setCurrentPage(1); // Reset page on refresh
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const runAnalytics = async () => {
    if (logs.length === 0) return alert('분석할 최근 로그가 없습니다.');
    const geminiKey = localStorage.getItem('gemini_api_key');
    if (!geminiKey) {
      return alert('AI 인사이트 분석을 실행하려면 [환경 설정] 또는 좌측 챗봇에서 Gemini API Key를 등록해야 합니다.');
    }

    try {
      setIsAnalyzing(true);
      const questions = logs.filter(l => l.user_feedback !== 'UP').slice(0, 50).map(l => l.question).filter(q => q && q.trim() !== '');
      if (questions.length === 0) return alert('유효한 질문 데이터가 없습니다.');
      
      const res = await axios.post('http://127.0.0.1:8000/logs/analytics', 
        { questions },
        { headers: { 'x-gemini-key': geminiKey } }
      );
      
      if (res.data.status === 'success') {
        setAnalytics(res.data.data);
      } else {
        alert('분석 중 오류 발생: ' + (res.data.message || '알 수 없는 오류'));
      }
    } catch (err) {
      console.error(err);
      alert('분석 서버와의 통신에 실패했습니다.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const toggleFeedback = async (logId: number, currentFeedback: string | null, targetFeedback: 'UP' | 'DOWN') => {
    try {
      const newFeedback = currentFeedback === targetFeedback ? null : targetFeedback;
      const res = await axios.put(`http://127.0.0.1:8000/logs/audit/${logId}/feedback`, { feedback: newFeedback });
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
  const totalPages = Math.ceil(logs.length / ITEMS_PER_PAGE) || 1;
  const paginatedLogs = logs.slice((currentPage - 1) * ITEMS_PER_PAGE, currentPage * ITEMS_PER_PAGE);

  const renderPagination = () => {
    const startIdx = logs.length === 0 ? 0 : (currentPage - 1) * ITEMS_PER_PAGE + 1;
    const endIdx = Math.min(currentPage * ITEMS_PER_PAGE, logs.length);

    return (
      <div className="flex flex-col sm:flex-row justify-between items-center my-3 gap-3 min-w-0 px-2">
        <div className="text-[11px] md:text-xs text-gray-500 font-bold">
          총 {logs.length}건 중 {startIdx} - {endIdx}건 표시
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
            onClick={() => setActiveTab('analytics')}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'analytics' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <Sparkles size={16} className="shrink-0" /> 
            <span className="hidden sm:inline">AI 로그 인사이트</span>
            <span className="sm:hidden">AI 인사이트</span>
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
                <span className="text-xs font-bold bg-white border border-slate-200 text-slate-600 px-2 py-1 rounded-full shadow-sm">{logs.length} 건</span>
              </div>
              
              {/* Desktop Table View */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-left border-collapse min-w-[800px]">
                  <thead>
                    <tr className="bg-white border-b border-slate-100">
                      <th className="px-4 py-3 text-xs font-bold text-slate-400 uppercase tracking-wider w-[140px]">일시</th>
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
                          아직 수집된 대화 로그가 없습니다.
                        </td>
                      </tr>
                    ) : (
                      paginatedLogs.map(log => (
                        <tr key={log.id} onClick={() => setSelectedLog(log)} className="hover:bg-indigo-50/40 transition-colors group cursor-pointer">
                          <td className="px-4 py-3 align-middle text-xs text-slate-500 font-medium whitespace-nowrap">
                            {log.created_at}
                          </td>
                          <td className="px-4 py-3 align-middle">
                            <div className="flex flex-col gap-1">
                              <span className="text-[11px] font-bold text-slate-700 bg-slate-100 w-fit px-1.5 py-0.5 rounded border border-slate-200">
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
                                <span className="text-indigo-400 font-bold mr-1">Q.</span> {log.question}
                              </div>
                              <div className="text-xs text-slate-500 truncate" title={log.answer}>
                                <span className="text-slate-400 font-bold mr-1">A.</span> {log.answer}
                              </div>
                              {log.total_tokens != null && (
                                <div className="text-[10px] text-slate-400 font-bold mt-0.5">
                                  🪙 총 {log.total_tokens.toLocaleString()} 토큰 (약 {Number(log.estimated_cost).toFixed(2)}원)
                                </div>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 align-middle text-center">
                            <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap ${
                              (log.latency_ms || 0) < 3000 ? 'bg-emerald-50 text-emerald-600 border-emerald-100' : 
                              (log.latency_ms || 0) < 8000 ? 'bg-amber-50 text-amber-600 border-amber-100' : 'bg-rose-50 text-rose-600 border-rose-100'
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
                    아직 수집된 대화 로그가 없습니다.
                  </div>
                ) : (
                  paginatedLogs.map(log => (
                    <div key={log.id} onClick={() => setSelectedLog(log)} className="p-4 hover:bg-indigo-50/40 active:bg-indigo-50 transition-colors cursor-pointer flex flex-col gap-2">
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-bold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                            {log.user_role === 'staff' ? '교직원' : '수험생'}
                          </span>
                          <span className="text-[11px] text-slate-500 font-medium">{log.created_at}</span>
                        </div>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap ${
                          (log.latency_ms || 0) < 3000 ? 'bg-emerald-50 text-emerald-600 border-emerald-100' : 
                          (log.latency_ms || 0) < 8000 ? 'bg-amber-50 text-amber-600 border-amber-100' : 'bg-rose-50 text-rose-600 border-rose-100'
                        }`}>
                          {formatLatency(log.latency_ms)}
                        </span>
                      </div>
                      
                      <div className="font-semibold text-slate-800 text-sm line-clamp-2 mt-1 leading-snug" title={log.question}>
                        <span className="text-indigo-400 font-bold mr-1">Q.</span> {log.question}
                      </div>
                      {log.total_tokens != null && (
                        <div className="text-[10px] text-slate-500 font-bold">
                          🪙 총 {log.total_tokens.toLocaleString()} 토큰 (약 {Number(log.estimated_cost).toFixed(2)}원)
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

        {/* === 탭 2: AI 로그 인사이트 === */}
        {activeTab === 'analytics' && (
          <div className="animate-in fade-in duration-300 min-w-0 h-full flex flex-col gap-4">
            
            {/* 분석 컨트롤 바 */}
            <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col md:flex-row justify-between items-center gap-4 text-center md:text-left">
              <div>
                <h2 className="text-lg font-bold text-slate-800 flex items-center justify-center md:justify-start gap-2">
                  <BrainCircuit className="text-indigo-600" size={20} /> AI 트렌드 및 취약점 분석
                </h2>
                <p className="text-sm text-slate-500 mt-1 font-medium">최근 50건의 교직원 질의응답을 분석하여 핫 키워드와 사전지식(RAG)의 맹점을 파악합니다.</p>
              </div>
              <button 
                onClick={runAnalytics}
                disabled={isAnalyzing}
                className={`flex items-center gap-2 px-5 py-3 rounded-lg font-bold text-sm transition-all shadow-sm shrink-0 ${
                  isAnalyzing ? 'bg-indigo-100 text-indigo-400 cursor-not-allowed border border-indigo-200' : 'bg-indigo-600 text-white hover:bg-indigo-700 hover:shadow-md hover:scale-105 active:scale-95'
                }`}
              >
                {isAnalyzing ? (
                  <><RefreshCw size={18} className="animate-spin" /> 분석 진행 중...</>
                ) : (
                  <><Sparkles size={18} /> 최근 50건 분석 시작하기</>
                )}
              </button>
            </div>

            {/* 분석 진행 중 뷰 */}
            {isAnalyzing && (
              <div className="flex-1 bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col items-center justify-center py-24 min-h-[400px]">
                <div className="w-12 h-12 border-4 border-indigo-100 border-t-indigo-600 rounded-full animate-spin mb-4"></div>
                <h3 className="text-lg font-bold text-slate-700 mb-2">데이터 수집 및 통계 분석 중</h3>
                <p className="text-slate-500 font-medium">Gemini AI가 최신 트렌드를 요약하고 있습니다. (약 10~20초 소요)</p>
              </div>
            )}

            {/* 분석 전 초기 뷰 */}
            {!analytics && !isAnalyzing && (
              <div className="flex-1 bg-slate-50/50 rounded-xl border border-dashed border-slate-300 flex flex-col items-center justify-center py-24 min-h-[400px]">
                <div className="bg-white p-4 rounded-full shadow-sm mb-4">
                  <Sparkles size={32} className="text-indigo-300" />
                </div>
                <h3 className="text-slate-600 font-bold mb-2">아직 분석된 데이터가 없습니다</h3>
                <p className="text-slate-500 text-sm">상단의 [분석 시작하기] 버튼을 눌러 리포트를 생성해 보세요.</p>
              </div>
            )}

            {/* 분석 완료 결과 리포트 뷰 */}
            {analytics && !isAnalyzing && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1">
                {/* Keywords Card */}
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col">
                  <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
                    <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                      <Key size={20} />
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-800 text-lg">최근 핫 키워드 Top</h3>
                      <p className="text-xs text-slate-500 font-medium">교직원들이 가장 많이 묻는 주제</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2.5">
                    {analytics.keywords?.map((kw: string, i: number) => (
                      <span key={i} className="px-3.5 py-1.5 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-lg text-sm font-bold shadow-sm">
                        #{kw}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Weak Points Card */}
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex flex-col">
                  <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-100">
                    <div className="p-2 bg-rose-50 text-rose-600 rounded-lg">
                      <AlertTriangle size={20} />
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-800 text-lg">지식 보완 필요 사항 (취약점)</h3>
                      <p className="text-xs text-slate-500 font-medium">RAG 검색 시 답변을 못했거나 불명확했던 패턴</p>
                    </div>
                  </div>
                  <div className="space-y-3 overflow-y-auto custom-scrollbar pr-2 max-h-[300px]">
                    {analytics.weak_points?.map((wp: any, i: number) => (
                      <div key={i} className="bg-rose-50/50 rounded-lg p-3 border border-rose-100/50">
                        <div className="font-bold text-rose-800 text-sm mb-1">{wp.topic}</div>
                        <div className="text-slate-600 text-xs font-medium leading-relaxed">{wp.reason}</div>
                      </div>
                    ))}
                    {(!analytics.weak_points || analytics.weak_points.length === 0) && (
                      <div className="text-slate-500 text-sm font-medium py-8 text-center bg-slate-50 rounded-lg border border-slate-100">
                        발견된 취약 질문 패턴이 없습니다! RAG가 잘 방어하고 있습니다. 🎉
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

      </div>

      {/* Log Detail Modal */}
      {selectedLog && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-indigo-800 flex justify-between items-center bg-indigo-900 text-white shrink-0">
              <h3 className="font-bold flex items-center gap-2">
                <TerminalSquare size={18} className="text-indigo-400" />
                로그 상세 (ID: #{selectedLog.id})
              </h3>
              <button onClick={() => setSelectedLog(null)} className="p-1.5 hover:bg-white/20 rounded-md transition-colors">
                <X size={18} />
              </button>
            </div>
            
            <div className="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1 min-h-0 bg-slate-50 custom-scrollbar">
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center gap-3">
                  <div className="p-2 bg-indigo-50 text-indigo-500 rounded-lg"><Clock size={20}/></div>
                  <div>
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">일시 및 성능</div>
                    <div className="font-bold text-slate-700 text-sm">{selectedLog.created_at} <span className="text-indigo-600 text-xs ml-1 font-medium">({formatLatency(selectedLog.latency_ms)} 소요)</span></div>
                  </div>
                </div>
                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center gap-3">
                  <div className="p-2 bg-purple-50 text-purple-500 rounded-lg"><BrainCircuit size={20}/></div>
                  <div className="min-w-0">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">사용 모델</div>
                    <div className="font-bold text-slate-700 text-sm truncate">{selectedLog.model_name}</div>
                  </div>
                </div>
              </div>
              
              {selectedLog.total_tokens != null && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-center">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">총 소모 토큰 및 비용</div>
                    <div className="font-bold text-indigo-600 text-xl">{selectedLog.total_tokens.toLocaleString()} <span className="text-sm text-slate-500 font-medium">Tokens</span></div>
                    <div className="text-xs text-slate-500 font-bold mt-1">약 {Number(selectedLog.estimated_cost).toFixed(2)}원 과금됨</div>
                  </div>
                  <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 truncate" title={selectedLog.model_name}>최종 챗봇 AI ({selectedLog.model_name})</div>
                    <div className="flex justify-between items-center text-sm mb-1">
                      <span className="text-slate-500">입력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.chat_in_tokens?.toLocaleString() || 0}</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-slate-500">출력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.chat_out_tokens?.toLocaleString() || 0}</span>
                    </div>
                  </div>
                  <div className={`bg-white p-4 rounded-xl border border-slate-200 shadow-sm ${!selectedLog.router_model_name || selectedLog.router_model_name === 'NONE' ? 'opacity-50' : ''}`}>
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 truncate" title={selectedLog.router_model_name || 'NONE'}>라우터 AI ({selectedLog.router_model_name || '사용 안함'})</div>
                    <div className="flex justify-between items-center text-sm mb-1">
                      <span className="text-slate-500">입력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.router_in_tokens?.toLocaleString() || 0}</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-slate-500">출력 토큰:</span>
                      <span className="font-bold text-slate-700">{selectedLog.router_out_tokens?.toLocaleString() || 0}</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="bg-white p-5 rounded-xl border border-indigo-100 shadow-sm relative overflow-hidden">
                <h4 className="font-bold text-indigo-900 mb-3 flex items-center gap-2">
                  <MessageSquare size={16} className="text-indigo-500"/> 원본 질문 (Question)
                </h4>
                <p className="text-slate-800 whitespace-pre-wrap text-sm leading-relaxed font-medium">{selectedLog.question}</p>
                {selectedLog.scraped_context && (
                  <div className="mt-4 p-3 bg-slate-50 rounded-lg text-xs border border-slate-100">
                    <div className="font-bold text-slate-500 mb-1">참고용 스크랩 원문</div>
                    <p className="text-slate-600 line-clamp-3 leading-relaxed" title={selectedLog.scraped_context}>{selectedLog.scraped_context}</p>
                  </div>
                )}
              </div>

              {(selectedLog.sql_query && selectedLog.sql_query !== 'NONE') || (selectedLog.rag_query && selectedLog.rag_query !== 'NONE') ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {selectedLog.sql_query && selectedLog.sql_query !== 'NONE' && (
                    <div className="bg-[#1e1e2e] p-5 rounded-xl shadow-inner overflow-hidden flex flex-col">
                      <h4 className="font-bold text-blue-400 mb-3 flex items-center gap-2 text-sm">
                        <Database size={16} /> 추출된 T-SQL 쿼리
                      </h4>
                      <div className="flex-1 overflow-auto custom-scrollbar">
                        <pre className="text-[#a6accd] text-xs whitespace-pre-wrap font-mono">
                          {selectedLog.sql_query}
                        </pre>
                      </div>
                    </div>
                  )}
                  {selectedLog.rag_query && selectedLog.rag_query !== 'NONE' && (
                    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                      <h4 className="font-bold text-emerald-600 mb-3 flex items-center gap-2 text-sm">
                        <BookOpen size={16} /> RAG (문서 검색) 키워드
                      </h4>
                      <div className="p-3 bg-emerald-50 text-emerald-800 rounded-lg font-medium text-sm border border-emerald-100">
                        {selectedLog.rag_query}
                      </div>
                    </div>
                  )}
                </div>
              ) : null}

              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm relative overflow-hidden">
                <h4 className="font-bold text-slate-800 mb-3 flex items-center gap-2">
                  <Sparkles size={16} className="text-slate-600"/> 최종 AI 답변 (Answer)
                </h4>
                <div className="text-slate-700 whitespace-pre-wrap text-sm leading-relaxed bg-slate-50/50 p-4 rounded-lg border border-slate-100">
                  {selectedLog.answer}
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
