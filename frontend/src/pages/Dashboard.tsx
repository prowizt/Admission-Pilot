import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Plus, Database, FileText, Lock, Globe, Search, Filter, Eye, X } from 'lucide-react';
import KnowledgeModal from '@/components/modals/KnowledgeModal';

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('documents');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<any>(null); // [NEW] 수정 모드용 선택 데이터
  
  // 상태 관리 (검색, 필터, 데이터)
  const [searchQuery, setSearchQuery] = useState('');
  const [docFilter, setDocFilter] = useState('all'); 
  const [tableFilter, setTableFilter] = useState('all'); 
  
  const [documents, setDocuments] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

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
      alert("본문을 불러오지 못했습니다.");
    }
  };

  // 정형 데이터는 아직 API가 없으므로 임시 Mock 유지
  const mockTables = [
    { table_name: 'UI_IPSI_M_V', table_name_kr: '종합학사 신입생 마스터 뷰', db_source: 'EXTERNAL', description: '실시간 지원자 통계 및 수치 데이터 제공용', is_public: 'Y', created_at: '2026-05-12' },
  ];

  // 백엔드 API에서 비정형 문서 목록 Fetch
  const fetchDocuments = async () => {
    try {
      setIsLoading(true);
      const res = await axios.get('http://127.0.0.1:8000/catalog/documents');
      if (res.data.status === 'success') {
        setDocuments(res.data.data);
      }
    } catch (error) {
      console.error("문서 목록을 불러오는 중 오류 발생:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'documents') {
      fetchDocuments();
    }
  }, [activeTab]);

  // 필터링 및 검색 로직 적용 (안전한 문자열 처리 반영)
  const filteredDocuments = documents.filter(doc => {
    const safeTitle = doc.title || '';
    const safeFilename = doc.filename || '';
    const matchSearch = safeTitle.toLowerCase().includes(searchQuery.toLowerCase()) || 
                        safeFilename.toLowerCase().includes(searchQuery.toLowerCase());
    const matchFilter = docFilter === 'all' || doc.doc_type === docFilter;
    return matchSearch && matchFilter;
  });

  const filteredTables = mockTables.filter(table => {
    const matchSearch = table.table_name.toLowerCase().includes(searchQuery.toLowerCase()) || table.table_name_kr.toLowerCase().includes(searchQuery.toLowerCase());
    const matchFilter = tableFilter === 'all' || table.db_source === tableFilter;
    return matchSearch && matchFilter;
  });

  return (
    <div className="h-full flex flex-col min-w-0 pb-24 md:pb-6">
      
      {/* 1. Header & Tabs */}
      <div className="bg-indigo-900 rounded-xl shadow-md pt-6 px-6 shrink-0 min-w-0 flex flex-col">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 mb-6 min-w-0">
          <div className="min-w-0">
            <h1 className="text-xl md:text-2xl font-extrabold text-white tracking-tight flex items-center gap-2">
              <Database className="text-indigo-300" size={24} /> 지식 카탈로그 관리
            </h1>
            <p className="text-xs text-indigo-200 mt-1">AI 챗봇이 참조할 비정형 문서와 정형 DB 뷰(View)를 통합 관리합니다.</p>
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
            <div className="flex flex-col sm:flex-row gap-3 w-full lg:w-auto min-w-0">
              {/* Filter Buttons */}
              <div className="flex bg-slate-100 p-1 rounded-lg shrink-0">
                {activeTab === 'documents' ? (
                  <>
                    <button onClick={() => setDocFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${docFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>전체</button>
                    <button onClick={() => setDocFilter('rule')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${docFilter === 'rule' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Rule (규정)</button>
                    <button onClick={() => setDocFilter('reference')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${docFilter === 'reference' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Ref (양식)</button>
                  </>
                ) : (
                  <>
                    <button onClick={() => setTableFilter('all')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${tableFilter === 'all' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>전체</button>
                    <button onClick={() => setTableFilter('INTERNAL')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${tableFilter === 'INTERNAL' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>내부 (엑셀 등)</button>
                    <button onClick={() => setTableFilter('EXTERNAL')} className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${tableFilter === 'EXTERNAL' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>종합학사 (외부 뷰)</button>
                  </>
                )}
              </div>
              
              {/* Search Bar */}
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
            </div>
            
            <button
              onClick={() => { setSelectedDoc(null); setIsModalOpen(true); }}
              className="w-full lg:w-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold shadow-md transition transform hover:-translate-y-0.5 flex items-center justify-center gap-1.5 shrink-0"
            >
              <Plus size={14} /> 신규 지식 등록
            </button>
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
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-24 text-center">권한</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-24 text-center">등록일</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDocuments.length === 0 ? (
                        <tr><td colSpan={5} className="py-12 text-center text-slate-400 font-medium">조건에 맞는 문서가 없습니다.</td></tr>
                      ) : (
                        filteredDocuments.map(doc => (
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
                            <td className="px-4 py-3 text-center">
                              {doc.is_public === 'Y' ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded"><Globe size={12}/> 대외공개</span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-1 rounded"><Lock size={12}/> 직원전용</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-center text-[11px] text-gray-500 font-mono">
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
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-24 text-center">권한</th>
                        <th className="px-4 py-3 text-[12px] font-extrabold text-slate-700 w-24 text-center">연동일</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTables.length === 0 ? (
                        <tr><td colSpan={5} className="py-12 text-center text-slate-400 font-medium">조건에 맞는 데이터 뷰가 없습니다.</td></tr>
                      ) : (
                        filteredTables.map(table => (
                          <tr key={table.table_name} className="border-b border-gray-100 hover:bg-indigo-50/30 transition-colors cursor-pointer group">
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
                            <td className="px-4 py-3 text-center">
                              {table.is_public === 'Y' ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded"><Globe size={12}/> 대외공개</span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-1 rounded"><Lock size={12}/> 직원전용</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-center text-[11px] text-gray-500 font-mono">
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
                    <div key={table.table_name} className="p-3 hover:bg-indigo-50/50 active:bg-indigo-50 transition-colors cursor-pointer flex flex-col gap-1.5 min-w-0">
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
                        <span className="shrink-0 font-bold">{table.is_public === 'Y' ? '🟢 공개' : '🔴 보안'}</span>
                      </div>
                    </div>
                  ))
                )}
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
        onSuccess={fetchDocuments} 
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
