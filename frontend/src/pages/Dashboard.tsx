import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Plus, Database, FileText, Lock, Globe, Search, Eye, X, ShieldHalf, ChevronLeft, ChevronRight } from 'lucide-react';
import KnowledgeModal from '@/components/modals/KnowledgeModal';
import CustomSwal from '@/utils/CustomSwal';

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('documents');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  
  // 상태 관리 (검색, 다중 필터, 데이터)
  const [searchQuery, setSearchQuery] = useState('');
  const [docFilter, setDocFilter] = useState('all'); 
  const [tableFilter, setTableFilter] = useState('all'); 
  const [publicFilter, setPublicFilter] = useState('all');
  const [knowledgeFilter, setKnowledgeFilter] = useState('all');
  
  const [documents, setDocuments] = useState<any[]>([]);
  const [tables, setTables] = useState<any[]>([]);
  const [supplementalList, setSupplementalList] = useState<any[]>([]);
  // const [isLoading, setIsLoading] = useState(false);

  // [NEW] 페이지네이션 상태
  const [docPage, setDocPage] = useState(1);
  const [tablePage, setTablePage] = useState(1);
  const [knowledgePage, setKnowledgePage] = useState(1);
  const ITEMS_PER_PAGE = 10;

  // 검색/필터 변경 시 페이지를 1로 리셋
  useEffect(() => { setDocPage(1); }, [searchQuery, docFilter, publicFilter]);
  useEffect(() => { setTablePage(1); }, [searchQuery, tableFilter, publicFilter]);
  useEffect(() => { setKnowledgePage(1); }, [searchQuery, knowledgeFilter]);

  // 뷰어 상태 관리
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [previewTitle, setPreviewTitle] = useState('');

  const handlePreview = async (doc_type: string, doc_id: string, title: string) => {
    try {
      const res = await axios.get(`http://127.0.0.1:8000/documents/${doc_type}/${doc_id}`);
      if (res.data.status === 'success') {
        setPreviewContent(res.data.content);
        setPreviewTitle(title);
        setPreviewOpen(true);
      }
    } catch (error) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: '본문을 불러오지 못했습니다.' });
    }
  };

  // 백엔드 API에서 카탈로그 목록 Fetch
  const fetchCatalogs = async () => {
    try {
      setIsLoading(true);
      if (activeTab === 'documents') {
        const res = await axios.get('http://127.0.0.1:8000/catalog/documents');
        if (res.data.status === 'success') setDocuments(res.data.data);
      } else if (activeTab === 'knowledge') {
        const res = await axios.get('http://127.0.0.1:8000/catalog/supplemental-knowledge');
        if (res.data.status === 'success') setSupplementalList(res.data.data);
      } else {
        const res = await axios.get('http://127.0.0.1:8000/catalog/tables');
        if (res.data.status === 'success') setTables(res.data.data);
      }
    } catch (error) {
      console.error("데이터 목록 로딩 오류:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchCatalogs();
  }, [activeTab]);

  // 필터링 및 검색 로직 적용 (안전한 문자열 처리 및 다중 필터 반영)
  const filteredDocuments = documents.filter(doc => {
    const safeTitle = doc.title || '';
    const safeFilename = doc.filename || '';
    const matchSearch = safeTitle.toLowerCase().includes(searchQuery.toLowerCase()) || 
                        safeFilename.toLowerCase().includes(searchQuery.toLowerCase());
    const matchType = docFilter === 'all' || doc.doc_type === docFilter;
    const matchPublic = publicFilter === 'all' || doc.is_public === publicFilter;
    return matchSearch && matchType && matchPublic;
  });

  const filteredTables = tables.filter(table => {
    const safeName = table.table_name || '';
    const safeKr = table.table_name_kr || '';
    const matchSearch = safeName.toLowerCase().includes(searchQuery.toLowerCase()) || safeKr.toLowerCase().includes(searchQuery.toLowerCase());
    const matchType = tableFilter === 'all' || table.db_source === tableFilter;
    const matchPublic = publicFilter === 'all' || table.is_public === publicFilter;
    return matchSearch && matchType && matchPublic;
  });

  const filteredSupplemental = supplementalList.filter(item => {
    const safeContent = item.content || '';
    const safeCategory = item.category || '';
    const safeAuthor = item.author || '';
    const matchSearch = safeContent.toLowerCase().includes(searchQuery.toLowerCase()) ||
                        safeCategory.toLowerCase().includes(searchQuery.toLowerCase()) ||
                        safeAuthor.toLowerCase().includes(searchQuery.toLowerCase());
    const matchCategory = knowledgeFilter === 'all' || item.category === knowledgeFilter;
    return matchSearch && matchCategory;
  }).sort((a, b) => b.id - a.id);

  // [NEW] 페이지네이션 계산
  const docTotalPages = Math.ceil(filteredDocuments.length / ITEMS_PER_PAGE) || 1;
  const paginatedDocuments = filteredDocuments.slice((docPage - 1) * ITEMS_PER_PAGE, docPage * ITEMS_PER_PAGE);

  const tableTotalPages = Math.ceil(filteredTables.length / ITEMS_PER_PAGE) || 1;
  const paginatedTables = filteredTables.slice((tablePage - 1) * ITEMS_PER_PAGE, tablePage * ITEMS_PER_PAGE);

  const knowledgeTotalPages = Math.ceil(filteredSupplemental.length / ITEMS_PER_PAGE) || 1;
  const paginatedSupplemental = filteredSupplemental.slice((knowledgePage - 1) * ITEMS_PER_PAGE, knowledgePage * ITEMS_PER_PAGE);

  // [NEW] 공통 페이지네이션 렌더링 함수
  const renderPagination = (currentPage: number, totalPages: number, setPageFn: (page: number) => void, totalItems: number) => {
    const startIdx = totalItems === 0 ? 0 : (currentPage - 1) * ITEMS_PER_PAGE + 1;
    const endIdx = Math.min(currentPage * ITEMS_PER_PAGE, totalItems);

    return (
      <div className="flex flex-col sm:flex-row justify-between items-center my-3 gap-3 min-w-0 px-2">
        <div className="text-[11px] md:text-xs text-gray-500 font-bold">
          총 {totalItems}건 중 {startIdx} - {endIdx}건 표시
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setPageFn(Math.max(1, currentPage - 1))} disabled={currentPage === 1} className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 text-gray-500 disabled:opacity-30 hover:bg-gray-50 transition-colors">
            <ChevronLeft size={16} />
          </button>
          <div className="flex gap-1 min-w-0">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(pageNum => (
              <button key={pageNum} onClick={() => setPageFn(pageNum)} className={`w-7 h-7 rounded-md text-xs font-bold transition-all ${currentPage === pageNum ? 'bg-indigo-600 text-white shadow-md' : 'text-gray-600 hover:bg-indigo-50 border border-transparent'}`}>
                {pageNum}
              </button>
            ))}
          </div>
          <button onClick={() => setPageFn(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages} className="w-7 h-7 flex items-center justify-center rounded-md border border-gray-300 text-gray-500 disabled:opacity-30 hover:bg-gray-50 transition-colors">
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
          <Database size={120} />
        </div>

        <div className="relative z-10 flex justify-between items-center mb-4 min-w-0">
          <div className="min-w-0 flex items-center gap-3">
            <div className="bg-white/10 p-2 rounded-lg backdrop-blur-sm border border-white/10">
              <Database className="text-amber-400" size={20} />
            </div>
            <h1 className="text-lg md:text-xl font-extrabold text-white tracking-tight flex items-center gap-2">
              지식 카탈로그 관리
            </h1>
          </div>
        </div>

        {/* Custom Tab Menu */}
        <div className="relative z-10 flex gap-1 overflow-x-auto min-w-0 mt-2">
          <button
            onClick={() => { setActiveTab('documents'); setSearchQuery(''); }}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'documents' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <FileText size={16} className="shrink-0" /> 
            <span>
              <span className="inline md:hidden">비정형</span>
              <span className="hidden md:inline">비정형 문서</span>
            </span>
          </button>
          <button
            onClick={() => { setActiveTab('tables'); setSearchQuery(''); }}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'tables' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <Database size={16} className="shrink-0" /> 
            <span>
              <span className="inline md:hidden">정형</span>
              <span className="hidden md:inline">정형 데이터(DB)</span>
            </span>
          </button>
          <button
            onClick={() => { setActiveTab('knowledge'); setSearchQuery(''); }}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'knowledge' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <ShieldHalf size={16} className="shrink-0" /> 
            <span>
              <span className="inline md:hidden">지식</span>
              <span className="hidden md:inline">사전지식 (핵심규칙 및 예외)</span>
            </span>
          </button>
        </div>
      </div>

      {/* 2. Main Content Area */}
      <div className="flex-1 py-6 min-w-0">
        <div className="space-y-4 animate-in fade-in duration-300 min-w-0">
          
          {/* 3. Control Bar (Filters, Search, Add Button) */}
          <div className="bg-white p-3 md:p-4 rounded-xl shadow-sm border border-gray-200 flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 min-w-0">
            {/* Left: Filters */}
            <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto min-w-0">
              {/* Type Filter Buttons */}
              <div className="flex bg-slate-100 p-1 rounded-lg shrink-0 overflow-x-auto custom-scrollbar">
                {activeTab === 'documents' ? (
                  <>
                    <button onClick={() => setDocFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${docFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>전체</button>
                    <button onClick={() => setDocFilter('rule')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${docFilter === 'rule' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Rule (규정)</button>
                    <button onClick={() => setDocFilter('reference')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${docFilter === 'reference' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Ref (양식)</button>
                  </>
                ) : activeTab === 'knowledge' ? (
                  <>
                    <button onClick={() => setKnowledgeFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${knowledgeFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>전체</button>
                    <button onClick={() => setKnowledgeFilter('인사/조직')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${knowledgeFilter === '인사/조직' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>인사/조직</button>
                    <button onClick={() => setKnowledgeFilter('결재라인')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${knowledgeFilter === '결재라인' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>결재라인</button>
                    <button onClick={() => setKnowledgeFilter('예외규정')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${knowledgeFilter === '예외규정' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>사전지식</button>
                    <button onClick={() => setKnowledgeFilter('기타')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${knowledgeFilter === '기타' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>기타</button>
                  </>
                ) : (
                  <>
                    <button onClick={() => setTableFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${tableFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>전체</button>
                    <button onClick={() => setTableFilter('INTERNAL')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${tableFilter === 'INTERNAL' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>내부 (엑셀)</button>
                    <button onClick={() => setTableFilter('EXTERNAL')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${tableFilter === 'EXTERNAL' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>종합학사</button>
                  </>
                )}
              </div>
              
              {/* Public/Private Filter Buttons */}
              {activeTab !== 'knowledge' && (
                <div className="flex bg-slate-100 p-1 rounded-lg shrink-0 overflow-x-auto custom-scrollbar">
                  <button onClick={() => setPublicFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${publicFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>모든 권한</button>
                  <button onClick={() => setPublicFilter('Y')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap flex items-center gap-1 ${publicFilter === 'Y' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}><Globe size={12}/> {activeTab === 'documents' ? '대외공개' : '전체공개'}</button>
                  {activeTab === 'tables' && (
                    <button onClick={() => setPublicFilter('P')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap flex items-center gap-1 ${publicFilter === 'P' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}><ShieldHalf size={12}/> 부분공개</button>
                  )}
                  <button onClick={() => setPublicFilter('N')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap flex items-center gap-1 ${publicFilter === 'N' ? 'bg-white text-red-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}><Lock size={12}/> 직원전용</button>
                </div>
              )}
            </div>
            
            {/* Right: Search Bar & Add Button */}
            <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto shrink-0 items-center min-w-0">
              <div className="relative w-full sm:w-64 shrink-0">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input
                  type="text"
                  placeholder={
                    activeTab === 'documents' 
                      ? "제목, 파일명 검색..." 
                      : activeTab === 'knowledge' 
                        ? "내용, 분류, 등록자 검색..." 
                        : "테이블 한글명, 영문명 검색..."
                  }
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 outline-none transition-all"
                />
              </div>
              <button
                onClick={() => { setSelectedDoc(null); setIsModalOpen(true); }}
                className="w-full sm:w-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold shadow-md transition transform hover:-translate-y-0.5 flex items-center justify-center gap-1.5 shrink-0 whitespace-nowrap"
              >
                <Plus size={14} /> 신규 지식 등록
              </button>
            </div>
          </div>

          {/* TAB 1: Documents List */}
          {activeTab === 'documents' && (
            <>
              {/* PC Desktop View */}
              <div className="hidden md:block bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
                <div className="overflow-x-auto min-w-0">
                  <table className="w-full text-left border-collapse min-w-[600px]">
                    <thead>
                      <tr className="bg-slate-100 border-b border-slate-300">
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-20 text-center">유형</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-20 text-center">연도</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700">문서 제목</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-28 text-center">권한</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-28 text-center">등록일</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedDocuments.length === 0 ? (
                        <tr><td colSpan={5} className="py-12 text-center text-slate-400 font-medium">조건에 맞는 문서가 없습니다.</td></tr>
                      ) : (
                        paginatedDocuments.map(doc => (
                          <tr key={doc.doc_id} onClick={() => { setSelectedDoc(doc); setIsModalOpen(true); }} className="border-b border-gray-100 hover:bg-indigo-50/30 transition-colors cursor-pointer group">
                            <td className="px-4 py-4 min-w-0 text-center whitespace-nowrap">
                              <span className={`text-[10px] px-2 py-1 rounded font-bold inline-block ${(doc.doc_type || '').toLowerCase() === 'rule' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}`}>
                                {(doc.doc_type || 'UNKNOWN').toUpperCase()}
                              </span>
                            </td>
                            <td className="px-4 py-4 min-w-0 text-center whitespace-nowrap">
                              <span className="text-xs font-bold text-gray-500">{doc.year}</span>
                            </td>
                            <td className="px-4 py-4 min-w-0">
                              <div className="flex items-center gap-2">
                                <div className="font-bold text-gray-800 text-sm truncate">{doc.title}</div>
                                <button onClick={(e) => { e.stopPropagation(); handlePreview(doc.doc_type, doc.doc_id, doc.title); }} className="px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px] font-bold hover:bg-indigo-100 flex items-center gap-1 whitespace-nowrap shrink-0">
                                  <Eye size={10} /> 본문
                                </button>
                              </div>
                            </td>
                            <td className="px-4 py-4 text-center whitespace-nowrap">
                              {doc.is_public === 'Y' ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded whitespace-nowrap"><Globe size={12}/> 대외공개</span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-1 rounded whitespace-nowrap"><Lock size={12}/> 직원전용</span>
                              )}
                            </td>
                            <td className="px-4 py-4 text-center text-[11px] text-gray-500 font-mono whitespace-nowrap">
                              {doc.uploaded_at}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                    {filteredDocuments.length > 0 && (
                      <tfoot className="bg-slate-100 border-t border-slate-300">
                        <tr>
                          <td colSpan={5} className="py-1 px-4">
                            {renderPagination(docPage, docTotalPages, setDocPage, filteredDocuments.length)}
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>

              {/* Mobile View */}
              <div className="md:hidden bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0 divide-y divide-gray-100">
                {filteredDocuments.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 font-medium text-sm">조건에 맞는 문서가 없습니다.</div>
                ) : (
                  filteredDocuments.map(doc => (
                    <div key={doc.doc_id} onClick={() => { setSelectedDoc(doc); setIsModalOpen(true); }} className="p-3 hover:bg-indigo-50/50 active:bg-indigo-50 transition-colors cursor-pointer flex flex-col gap-1.5 min-w-0">
                      <div className="flex justify-between items-start min-w-0">
                        <div className="flex items-center gap-1.5 min-w-0 pr-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold shrink-0 ${(doc.doc_type || '').toLowerCase() === 'rule' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}`}>
                            {(doc.doc_type || 'UNKNOWN').toUpperCase()}
                          </span>
                          <span className="font-bold text-gray-800 text-sm truncate">{doc.title}</span>
                        </div>
                      </div>
                      <div className="text-[11px] text-gray-500 truncate mt-0.5">{doc.description}</div>
                      <div className="flex items-center justify-between text-[11px] text-gray-400 min-w-0 mt-1 pt-1 border-t border-gray-50">
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="font-bold">[{doc.year}]</span>
                          <span className="truncate">{doc.filename}</span>
                        </div>
                        <span className="shrink-0 font-bold">{doc.is_public === 'Y' ? '🟢 공개' : '🔴 보안'}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="md:hidden">
                {filteredDocuments.length > 0 && renderPagination(docPage, docTotalPages, setDocPage, filteredDocuments.length)}
              </div>
            </>
          )}

          {/* TAB 2: Tables List */}
          {activeTab === 'tables' && (
            <>
              {/* PC Desktop View */}
              <div className="hidden md:block bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
                <div className="overflow-x-auto min-w-0">
                  <table className="w-full text-left border-collapse min-w-[600px]">
                    <thead>
                      <tr className="bg-slate-100 border-b border-slate-300">
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-24">출처</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-1/3">데이터명 (View/Table 명)</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700">AI 참조 설명 (Hint)</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-28 text-center">권한</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-28 text-center">연동일</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedTables.length === 0 ? (
                        <tr><td colSpan={5} className="py-12 text-center text-slate-400 font-medium">조건에 맞는 데이터 뷰가 없습니다.</td></tr>
                      ) : (
                        paginatedTables.map(table => (
                          <tr key={table.table_name} onClick={() => { setSelectedDoc(table); setIsModalOpen(true); }} className="border-b border-gray-100 hover:bg-indigo-50/30 transition-colors cursor-pointer group">
                            <td className="px-4 py-3 min-w-0 text-center">
                              <span className={`text-[10px] px-2 py-1 rounded font-bold block ${table.db_source === 'INTERNAL' ? 'bg-orange-50 text-orange-600' : 'bg-teal-50 text-teal-600'}`}>
                                {table.db_source === 'INTERNAL' ? '내부(엑셀)' : '종합학사'}
                              </span>
                            </td>
                            <td className="px-4 py-3 min-w-0">
                              <div className="font-bold text-gray-800 text-sm truncate">{table.table_name_kr}</div>
                              <div className="text-[11px] text-gray-400 truncate mt-0.5">{table.table_name}</div>
                            </td>
                            <td className="px-4 py-3 min-w-0">
                              <p className="text-[11px] text-gray-500 truncate max-w-sm" title={table.description}>{table.description}</p>
                            </td>
                            <td className="px-4 py-3 text-center whitespace-nowrap">
                              {table.is_public === 'Y' && <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded whitespace-nowrap"><Globe size={12}/> 전체공개</span>}
                              {table.is_public === 'P' && <span className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded whitespace-nowrap"><ShieldHalf size={12}/> 부분공개</span>}
                              {table.is_public === 'N' && <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-1 rounded whitespace-nowrap"><Lock size={12}/> 직원전용</span>}
                            </td>
                            <td className="px-4 py-3 text-center text-[11px] text-gray-500 font-mono whitespace-nowrap">
                              {table.created_at}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                    {filteredTables.length > 0 && (
                      <tfoot className="bg-slate-100 border-t border-slate-300">
                        <tr>
                          <td colSpan={5} className="py-1 px-4">
                            {renderPagination(tablePage, tableTotalPages, setTablePage, filteredTables.length)}
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>

              {/* Mobile View */}
              <div className="md:hidden bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0 divide-y divide-gray-100">
                {filteredTables.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 font-medium text-sm">조건에 맞는 데이터 뷰가 없습니다.</div>
                ) : (
                  filteredTables.map(table => (
                    <div key={table.table_name} onClick={() => { setSelectedDoc(table); setIsModalOpen(true); }} className="p-3 hover:bg-indigo-50/50 active:bg-indigo-50 transition-colors cursor-pointer flex flex-col gap-1.5 min-w-0">
                      <div className="flex justify-between items-start min-w-0">
                        <div className="flex items-center gap-1.5 min-w-0 pr-2">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold shrink-0 ${table.db_source === 'INTERNAL' ? 'bg-orange-50 text-orange-600' : 'bg-teal-50 text-teal-600'}`}>
                            {table.db_source === 'INTERNAL' ? '엑셀' : '종합학사'}
                          </span>
                          <span className="font-bold text-gray-800 text-sm truncate">{table.table_name_kr}</span>
                        </div>
                      </div>
                      <div className="text-[11px] text-gray-500 truncate mt-0.5">{table.description}</div>
                      <div className="flex items-center justify-between text-[11px] text-gray-400 min-w-0 mt-1 pt-1 border-t border-gray-50">
                        <div className="truncate font-mono">{table.table_name}</div>
                        <span className="shrink-0 font-bold">
                          {table.is_public === 'Y' && '🟢 전체공개'}
                          {table.is_public === 'P' && '🔵 부분공개'}
                          {table.is_public === 'N' && '🔴 직원전용'}
                        </span>
                      </div>  
                    </div>
                  ))
                )}
              </div>
              <div className="md:hidden">
                {filteredTables.length > 0 && renderPagination(tablePage, tableTotalPages, setTablePage, filteredTables.length)}
              </div>
            </>
          )}

          {/* TAB 3: Knowledge (Supplemental Knowledge) List */}
          {activeTab === 'knowledge' && (
            <>
              {/* PC Desktop View */}
              <div className="hidden md:block bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0">
                <div className="overflow-x-auto min-w-0">
                  <table className="w-full text-left border-collapse min-w-[600px]">
                    <thead>
                      <tr className="bg-slate-100 border-b border-slate-300">
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-32 text-center">분류</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700">보완 지식 내용</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-28 text-center">등록자</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-28 text-center">등록일</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedSupplemental.length === 0 ? (
                        <tr><td colSpan={4} className="py-12 text-center text-slate-400 font-medium">등록된 사전지식이 없습니다.</td></tr>
                      ) : (
                        paginatedSupplemental.map(item => (
                          <tr key={item.id} onClick={() => { setSelectedDoc(item); setIsModalOpen(true); }} className="border-b border-gray-100 hover:bg-indigo-50/30 transition-colors cursor-pointer group">
                            <td className="px-4 py-3 text-center whitespace-nowrap">
                              <span className={`text-[10px] px-2 py-1 rounded font-bold ${
                                item.category === '인사/조직' ? 'bg-blue-50 text-blue-600' :
                                item.category === '결재라인' ? 'bg-purple-50 text-purple-600' :
                                item.category === '예외규정' ? 'bg-amber-50 text-amber-600' :
                                'bg-gray-50 text-gray-600'
                              }`}>
                                {item.category === '예외규정' ? '사전지식' : item.category}
                              </span>
                            </td>
                            <td className="px-4 py-3 min-w-0">
                              <p className="text-sm text-gray-800 font-medium whitespace-pre-line leading-relaxed truncate max-w-xl" title={item.content}>
                                {item.content}
                              </p>
                            </td>
                            <td className="px-4 py-3 text-center text-sm font-semibold text-gray-600 whitespace-nowrap">
                              {item.author || '시스템'}
                            </td>
                            <td className="px-4 py-3 text-center text-[11px] text-gray-500 font-mono whitespace-nowrap">
                              {item.created_at || '-'}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                    {filteredSupplemental.length > 0 && (
                      <tfoot className="bg-slate-100 border-t border-slate-300">
                        <tr>
                          <td colSpan={4} className="py-1 px-4">
                            {renderPagination(knowledgePage, knowledgeTotalPages, setKnowledgePage, filteredSupplemental.length)}
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>

              {/* Mobile View */}
              <div className="md:hidden bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden min-w-0 divide-y divide-gray-100">
                {filteredSupplemental.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 font-medium text-sm">등록된 사전지식이 없습니다.</div>
                ) : (
                  filteredSupplemental.map(item => (
                    <div key={item.id} onClick={() => { setSelectedDoc(item); setIsModalOpen(true); }} className="p-3 hover:bg-indigo-50/50 active:bg-indigo-50 transition-colors cursor-pointer flex flex-col gap-1.5 min-w-0">
                      <div className="flex justify-between items-start min-w-0">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold shrink-0 ${
                          item.category === '인사/조직' ? 'bg-blue-50 text-blue-600' :
                          item.category === '결재라인' ? 'bg-purple-50 text-purple-600' :
                          item.category === '예외규정' ? 'bg-amber-50 text-amber-600' :
                          'bg-gray-50 text-gray-600'
                        }`}>
                          {item.category === '예외규정' ? '사전지식' : item.category}
                        </span>
                        <span className="text-[11px] text-gray-400 font-mono">
                          {item.created_at ? new Date(item.created_at).toLocaleDateString('ko-KR') : ''}
                        </span>
                      </div>
                      <p className="text-xs text-gray-700 line-clamp-2 mt-0.5 leading-relaxed">{item.content}</p>
                      <div className="flex items-center justify-between text-[10px] text-gray-400 min-w-0 mt-1 pt-1 border-t border-gray-50">
                        <span>등록자: <span className="font-bold text-gray-600">{item.author || '시스템'}</span></span>
                      </div>
                    </div>
                  ))
                )}
              </div>
              <div className="md:hidden">
                {filteredSupplemental.length > 0 && renderPagination(knowledgePage, knowledgeTotalPages, setKnowledgePage, filteredSupplemental.length)}
              </div>
            </>
          )}

        </div>
      </div>

      <KnowledgeModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        activeTab={activeTab} 
        editData={selectedDoc}
        onSuccess={fetchCatalogs} 
      />

      {/* 미리보기 뷰어 팝업 */}
      {previewOpen && createPortal(
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[85vh]">
            <div className="bg-indigo-900 px-5 py-4 text-white flex justify-between items-center shrink-0">
              <h3 className="font-bold text-sm tracking-wide flex items-center gap-2">
                <FileText size={16}/> 본문 텍스트 추출 확인: {previewTitle}
              </h3>
              <button onClick={() => setPreviewOpen(false)} className="hover:bg-white/20 p-1.5 rounded-full transition-colors"><X size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 text-sm text-slate-700 whitespace-pre-wrap bg-slate-50 font-mono leading-relaxed custom-scrollbar">
              {previewContent ? previewContent : "추출된 텍스트가 없습니다."}
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
