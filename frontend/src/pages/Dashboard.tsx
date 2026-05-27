import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Plus, Database, FileText, Lock, Globe, Search, Filter, Eye, X, ShieldHalf, ChevronLeft, ChevronRight } from 'lucide-react';
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
  
  const [documents, setDocuments] = useState<any[]>([]);
  const [tables, setTables] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // [NEW] 페이지네이션 상태
  const [docPage, setDocPage] = useState(1);
  const [tablePage, setTablePage] = useState(1);
  const ITEMS_PER_PAGE = 10;

  // 검색/필터 변경 시 페이지를 1로 리셋
  useEffect(() => { setDocPage(1); }, [searchQuery, docFilter, publicFilter]);
  useEffect(() => { setTablePage(1); }, [searchQuery, tableFilter, publicFilter]);

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

  // [NEW] 페이지네이션 계산
  const docTotalPages = Math.ceil(filteredDocuments.length / ITEMS_PER_PAGE) || 1;
  const paginatedDocuments = filteredDocuments.slice((docPage - 1) * ITEMS_PER_PAGE, docPage * ITEMS_PER_PAGE);

  const tableTotalPages = Math.ceil(filteredTables.length / ITEMS_PER_PAGE) || 1;
  const paginatedTables = filteredTables.slice((tablePage - 1) * ITEMS_PER_PAGE, tablePage * ITEMS_PER_PAGE);

  // [NEW] 공통 페이지네이션 렌더링 함수
  const renderPagination = (currentPage: number, totalPages: number, setPageFn: (page: number) => void) => (
    <div className="flex justify-center items-center mt-6 mb-2 gap-1.5 min-w-0">
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
  );

  return (
    <div className="h-full flex flex-col min-w-0 pb-24 md:pb-6">
      
      {/* 1. Header & Tabs */}
      <div className="bg-indigo-900 rounded-t-xl shadow-md pt-4 px-6 shrink-0 min-w-0 flex flex-col">
        <div className="flex justify-between items-center mb-4 min-w-0">
          <div className="min-w-0">
            <h1 className="text-lg md:text-xl font-extrabold text-white tracking-tight flex items-center gap-2">
              <Database className="text-indigo-300" size={20} /> 지식 카탈로그 관리
            </h1>
          </div>
        </div>

        {/* Custom Tab Menu */}
        <div className="flex gap-1 overflow-x-auto min-w-0">
          <button
            onClick={() => { setActiveTab('documents'); setSearchQuery(''); }}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'documents' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <FileText size={16} className="shrink-0" /> 
            <span>비정형 문서</span>
          </button>
          <button
            onClick={() => { setActiveTab('tables'); setSearchQuery(''); }}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors whitespace-nowrap flex items-center gap-2 ${
              activeTab === 'tables' ? 'bg-slate-50 text-indigo-900 font-bold' : 'bg-indigo-800/50 text-indigo-200 hover:bg-indigo-800 hover:text-white'
            }`}
          >
            <Database size={16} className="shrink-0" /> 
            <span>정형 데이터(DB)</span>
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
                ) : (
                  <>
                    <button onClick={() => setTableFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${tableFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>전체</button>
                    <button onClick={() => setTableFilter('INTERNAL')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${tableFilter === 'INTERNAL' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>내부 (엑셀)</button>
                    <button onClick={() => setTableFilter('EXTERNAL')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${tableFilter === 'EXTERNAL' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>종합학사</button>
                  </>
                )}
              </div>
              
              {/* Public/Private Filter Buttons */}
              <div className="flex bg-slate-100 p-1 rounded-lg shrink-0 overflow-x-auto custom-scrollbar">
                <button onClick={() => setPublicFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap ${publicFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>모든 권한</button>
                <button onClick={() => setPublicFilter('Y')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap flex items-center gap-1 ${publicFilter === 'Y' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}><Globe size={12}/> {activeTab === 'documents' ? '대외공개' : '전체공개'}</button>
                {activeTab === 'tables' && (
                  <button onClick={() => setPublicFilter('P')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap flex items-center gap-1 ${publicFilter === 'P' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}><ShieldHalf size={12}/> 부분공개</button>
                )}
                <button onClick={() => setPublicFilter('N')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all whitespace-nowrap flex items-center gap-1 ${publicFilter === 'N' ? 'bg-white text-red-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}><Lock size={12}/> 직원전용</button>
              </div>
            </div>
            
            {/* Right: Search Bar & Add Button */}
            <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto shrink-0 items-center min-w-0">
              <div className="relative w-full sm:w-64 shrink-0">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                <input
                  type="text"
                  placeholder="제목, 파일명, 뷰 검색..."
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
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-24">유형/연도</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-1/3">문서 제목 (파일명)</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700">AI 참조 설명 (Hint)</th>
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
                            <td className="px-4 py-3 min-w-0 text-center">
                              <span className={`text-[10px] px-2 py-1 rounded font-bold block mb-1 ${doc.doc_type === 'rule' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}`}>
                                {doc.doc_type.toUpperCase()}
                              </span>
                              <span className="text-[11px] font-bold text-gray-400">{doc.year}</span>
                            </td>
                            <td className="px-4 py-3 min-w-0">
                              <div className="flex items-center gap-2">
                                <div className="font-bold text-gray-800 text-sm truncate">{doc.title}</div>
                                <button onClick={(e) => { e.stopPropagation(); handlePreview(doc.doc_type, doc.doc_id, doc.title); }} className="px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px] font-bold hover:bg-indigo-100 flex items-center gap-1 whitespace-nowrap">
                                  <Eye size={10} /> 본문
                                </button>
                              </div>
                              <div className="text-[11px] text-gray-400 truncate mt-0.5">{doc.filename}</div>
                            </td>
                            <td className="px-4 py-3 min-w-0">
                              <p className="text-[11px] text-gray-500 truncate max-w-sm" title={doc.description}>{doc.description}</p>
                            </td>
                            <td className="px-4 py-3 text-center whitespace-nowrap">
                              {doc.is_public === 'Y' ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded whitespace-nowrap"><Globe size={12}/> 대외공개</span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-1 rounded whitespace-nowrap"><Lock size={12}/> 직원전용</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-center text-[11px] text-gray-500 font-mono whitespace-nowrap">
                              {doc.uploaded_at}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
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
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold shrink-0 ${doc.doc_type === 'rule' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}`}>
                            {doc.doc_type.toUpperCase()}
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
              {filteredDocuments.length > 0 && renderPagination(docPage, docTotalPages, setDocPage)}
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
              {filteredTables.length > 0 && renderPagination(tablePage, tableTotalPages, setTablePage)}
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
