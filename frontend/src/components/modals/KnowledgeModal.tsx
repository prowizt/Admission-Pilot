import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { X, Save, Database, FileText, ChevronLeft, ChevronRight, Upload, CheckCircle2, Lock, Trash2, List, RefreshCw } from 'lucide-react';
import CustomSwal from '@/utils/CustomSwal';

export default function KnowledgeModal({ isOpen, onClose, activeTab, editData, onSuccess }: any) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isEditMode = !!editData;
  const [isDragging, setIsDragging] = useState(false);
  
  const [availableViews, setAvailableViews] = useState<string[]>([]);
  const [columns, setColumns] = useState<any[]>([]); // [NEW] 컬럼 카탈로그 데이터
  const [isLoading, setIsLoading] = useState(false);

  const [formData, setFormData] = useState({
    doc_type: 'rule', year: new Date().getFullYear().toString(), title: '',
    is_public: 'Y', db_source: 'INTERNAL', table_name: '', description: ''
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const fetchViews = async () => {
    try {
      const res = await axios.get('http://127.0.0.1:8000/available-views');
      if (res.data.status === 'success') setAvailableViews(res.data.data);
    } catch (error) { console.error("뷰 목록 로딩 실패:", error); }
  };

  const fetchColumns = async (tableName: string) => {
    try {
      const res = await axios.get(`http://127.0.0.1:8000/columns/${tableName}`);
      if (res.data.status === 'success') setColumns(res.data.data);
    } catch (error) { console.error("컬럼 목록 로딩 실패:", error); }
  };

  useEffect(() => {
    if (isOpen) {
      if (isEditMode) {
        setFormData({
          doc_type: editData.doc_type || 'rule',
          year: editData.year || new Date().getFullYear().toString(),
          title: activeTab === 'documents' ? editData.title : editData.table_name_kr,
          is_public: editData.is_public || 'Y',
          db_source: editData.db_source || 'INTERNAL',
          table_name: editData.table_name || '',
          description: editData.description || ''
        });
        if (activeTab === 'tables') fetchColumns(editData.table_name);
      } else {
        setFormData({
          doc_type: 'rule', year: new Date().getFullYear().toString(), title: '',
          is_public: 'Y', db_source: 'INTERNAL', table_name: '', description: ''
        });
        setColumns([]);
      }
      setSelectedFile(null);
      if (activeTab === 'tables' && !isEditMode) fetchViews();
    }
  }, [isOpen, editData, isEditMode, activeTab]);

  if (!isOpen) return null;

  const handleYearChange = (delta: number) => {
    setFormData(prev => ({ ...prev, year: (parseInt(prev.year) + delta).toString() }));
  };

  const processFile = (file: File) => {
    if (activeTab === 'documents') {
      if (file.type === "application/pdf" || file.name.toLowerCase().endsWith('.pdf')) setSelectedFile(file);
      else CustomSwal.fire({ icon: 'error', title: '형식 오류', text: 'PDF 파일만 첨부 가능합니다.' });
    } else {
      if (file.name.toLowerCase().match(/\.(xlsx|xls)$/)) {
        setSelectedFile(file);
        const autoName = file.name.split('.')[0].replace(/[^a-zA-Z0-9_]/g, '_').toUpperCase();
        setFormData(prev => ({ ...prev, table_name: `EXCEL_${autoName}` }));
      } else {
        CustomSwal.fire({ icon: 'error', title: '형식 오류', text: '엑셀(.xlsx, .xls) 파일만 첨부 가능합니다.' });
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => { if (e.target.files && e.target.files.length > 0) processFile(e.target.files[0]); };
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) processFile(e.dataTransfer.files[0]);
  };

  const handleDelete = async () => {
    const isDoc = activeTab === 'documents';
    const result = await CustomSwal.fire({
      title: '데이터 삭제',
      text: isDoc ? "정말 삭제하시겠습니까?\nAI 지식에서 영구 파기됩니다." : "정말 연동을 해제하시겠습니까?\n엑셀 데이터인 경우 실제 테이블도 삭제됩니다.",
      icon: 'warning',
      showCancelButton: true, confirmButtonText: '삭제', cancelButtonText: '취소'
    });
    if (!result.isConfirmed) return;
    
    try {
      setIsLoading(true);
      if (isDoc) await axios.delete(`http://127.0.0.1:8000/documents/${editData.doc_type}/${editData.doc_id}`);
      else await axios.delete(`http://127.0.0.1:8000/tables/${editData.table_name}`);
      
      CustomSwal.fire({ icon: 'success', title: '성공', text: '안전하게 삭제되었습니다.', timer: 1500, showConfirmButton: false });
      if (onSuccess) onSuccess();
      onClose();
    } catch (error) {
      CustomSwal.fire({ icon: 'error', title: '오류', text: '삭제 중 오류가 발생했습니다.' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSyncView = async () => {
    const payload = new FormData();
    payload.append('table_name', formData.table_name);
    payload.append('table_name_kr', formData.title);
    if (formData.description) payload.append('description', formData.description);

    try {
      setIsLoading(true);
      const res = await axios.post('http://127.0.0.1:8000/sync-external-table', payload, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (res.data.status === 'success') {
        CustomSwal.fire({ icon: 'success', title: '동기화 완료', text: res.data.message, timer: 3000, showConfirmButton: false });
        fetchColumns(formData.table_name); // 동기화 후 컬럼 즉시 새로고침
        if (onSuccess) onSuccess();
      }
    } catch (error: any) {
      CustomSwal.fire({ icon: 'error', title: '동기화 실패', text: error.response?.data?.detail || error.message });
    } finally {
      setIsLoading(false);
    }
  };

  // [NEW] 컬럼 일괄 공개/비공개 안전장치 핸들러
  const handleBulkPublicToggle = async (status: 'Y' | 'N') => {
    const statusText = status === 'Y' ? '공개' : '비공개';
    const result = await CustomSwal.fire({
      title: `일괄 ${statusText} 변경`,
      text: `정말 모든 컬럼을 '${statusText}'로 변경하시겠습니까?\n기존에 개별적으로 설정한 보안 상태가 모두 덮어씌워집니다.`,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: '변경',
      cancelButtonText: '취소'
    });
    
    if (result.isConfirmed) {
      setColumns(columns.map(c => ({...c, is_public: status})));
    }
  };

  const handleSubmit = async () => {
    if (activeTab === 'documents') {
      const payload = new FormData();
      payload.append('doc_type', formData.doc_type);
      payload.append('year', formData.year);
      payload.append('title', formData.title);
      payload.append('is_public', formData.is_public);
      if (formData.description) payload.append('description', formData.description);

      try {
        setIsLoading(true);
        if (isEditMode) {
          const res = await axios.put(`http://127.0.0.1:8000/documents/${editData.doc_id}`, payload);
          if (res.data.status === 'success') {
            CustomSwal.fire({ icon: 'success', title: '성공', text: '문서 정보가 수정되었습니다.', timer: 1500, showConfirmButton: false });
            if (onSuccess) onSuccess();
            onClose();
          }
        } else {
          payload.append('file', selectedFile as Blob);
          const res = await axios.post('http://127.0.0.1:8000/upload-knowledge', payload, { headers: { 'Content-Type': 'multipart/form-data' } });
          if (res.data.status === 'success') {
            CustomSwal.fire({ icon: 'success', title: '성공', text: '문서가 임베딩되었습니다.', timer: 1500, showConfirmButton: false });
            if (onSuccess) onSuccess();
            onClose();
          }
        }
      } catch (error: any) {
        CustomSwal.fire({ icon: 'error', title: '저장 실패', text: error.response?.data?.detail || error.message });
      } finally { setIsLoading(false); }

    } else {
      const payload = new FormData();
      payload.append('table_name', formData.table_name);
      payload.append('table_name_kr', formData.title);
      if (formData.description) payload.append('description', formData.description);

      try {
        setIsLoading(true);
        if (isEditMode) {
          // 1. 테이블 메타데이터 수정 (Form Data)
          const res = await axios.put(`http://127.0.0.1:8000/tables/${editData.table_name}`, payload);
          
          // 2. 컬럼 메타데이터 일괄 수정 (JSON Data) - null 값 방지 전처리
          const cleanColumns = columns.map(c => ({
            id: c.id,
            ai_description: c.ai_description || "",
            is_public: c.is_public
          }));
          
          await axios.put(`http://127.0.0.1:8000/columns/${editData.table_name}`, { columns: cleanColumns }, {
            headers: { 'Content-Type': 'application/json' }
          });
          
          if (res.data.status === 'success') {
            CustomSwal.fire({ icon: 'success', title: '성공', text: '데이터 정보 및 컬럼 보안 설정이 저장되었습니다.', timer: 1500, showConfirmButton: false });
            if (onSuccess) onSuccess();
            onClose();
          }
        } else {
          if (formData.db_source === 'INTERNAL') {
            payload.append('file', selectedFile as Blob);
            const res = await axios.post('http://127.0.0.1:8000/upload-dynamic-statistics', payload, { headers: { 'Content-Type': 'multipart/form-data' } });
            if (res.data.status === 'success') {
              CustomSwal.fire({ icon: 'success', title: '성공', text: '엑셀 데이터가 DB에 연동되었습니다.', timer: 1500, showConfirmButton: false });
              if (onSuccess) onSuccess();
              onClose();
            }
          } else {
            const res = await axios.post('http://127.0.0.1:8000/sync-external-table', payload, { headers: { 'Content-Type': 'multipart/form-data' } });
            if (res.data.status === 'success') {
              CustomSwal.fire({ icon: 'success', title: '성공', text: res.data.message, timer: 2000, showConfirmButton: false });
              if (onSuccess) onSuccess();
              onClose();
            }
          }
        }
      } catch (error: any) {
        CustomSwal.fire({ icon: 'error', title: '저장 실패', text: error.response?.data?.detail || error.message });
      } finally { setIsLoading(false); }
    }
  };

  const handleBeforeSubmit = () => {
    if (activeTab === 'documents') {
      if (!formData.title.trim()) return CustomSwal.fire({ icon: 'warning', title: '입력 누락', text: '문서 제목을 입력해주세요.' });
      if (!isEditMode && !selectedFile) return CustomSwal.fire({ icon: 'warning', title: '파일 누락', text: 'PDF 파일을 첨부해주세요.' });
    } else {
      if (!formData.title.trim()) return CustomSwal.fire({ icon: 'warning', title: '입력 누락', text: '테이블 한글명을 입력해주세요.' });
      if (!formData.table_name.trim()) return CustomSwal.fire({ icon: 'warning', title: '입력 누락', text: '영문 뷰 이름을 지정/입력해주세요.' });
      if (formData.db_source === 'INTERNAL' && !isEditMode && !selectedFile) return CustomSwal.fire({ icon: 'warning', title: '파일 누락', text: '변환할 엑셀 파일을 첨부해주세요.' });
    }
    handleSubmit();
  };

  const labelClass = "block text-[11px] font-bold text-gray-600 mb-1.5";
  const inputClass = "w-full min-w-0 max-w-full text-xs md:text-sm px-3 py-2 appearance-none rounded-lg border border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition-all";

  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200 min-w-0">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh] min-w-0">
        
        {/* Header */}
        <div className="bg-indigo-900 px-5 py-4 text-white flex justify-between items-center shrink-0 min-w-0">
          <h3 className="font-bold text-sm tracking-wide flex items-center gap-1.5">
            {activeTab === 'documents' ? <FileText size={18} /> : <Database size={18} />}
            {activeTab === 'documents' ? `비정형 문서(PDF) ${isEditMode ? '수정' : '등록'}` : `정형 데이터 ${isEditMode ? '상세설정' : '연동'}`}
          </h3>
          <button onClick={onClose} className="hover:bg-white/20 p-1.5 rounded-full transition-colors"><X size={18} /></button>
        </div>

        {/* Form Body */}
        <div className="flex-1 overflow-y-auto p-5 custom-scrollbar bg-gray-50/50 min-w-0">
          <form className="space-y-4 min-w-0" onSubmit={(e) => e.preventDefault()}>
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm space-y-4 min-w-0">
              
              {activeTab === 'documents' ? (
                /* ================= [비정형 문서 모달] ================= */
                <>
                  <div className="grid grid-cols-2 gap-4 min-w-0">
                    <div>
                      <label className={labelClass}>문서 유형 *</label>
                      <div className="flex bg-gray-100 p-1 rounded-lg">
                        <button type="button" disabled={isEditMode} onClick={() => setFormData({ ...formData, doc_type: 'rule' })} className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-all active:scale-95 ${formData.doc_type === 'rule' ? 'bg-indigo-600 text-white shadow-md' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'} ${isEditMode ? 'opacity-70 cursor-not-allowed' : ''}`}>Rule (규정)</button>
                        <button type="button" disabled={isEditMode} onClick={() => setFormData({ ...formData, doc_type: 'reference' })} className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-all active:scale-95 ${formData.doc_type === 'reference' ? 'bg-indigo-600 text-white shadow-md' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'} ${isEditMode ? 'opacity-70 cursor-not-allowed' : ''}`}>Ref (양식)</button>
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>적용 연도</label>
                      <div className="flex items-center gap-1">
                        <button type="button" onClick={() => handleYearChange(-1)} className="p-1.5 bg-white border border-gray-300 rounded-md hover:bg-gray-100 active:scale-90 transition-transform"><ChevronLeft size={14} /></button>
                        <input type="text" value={formData.year} onChange={(e) => setFormData({...formData, year: e.target.value.replace(/[^0-9]/g, '')})} className="w-16 text-center font-bold text-sm bg-white border border-gray-300 py-1.5 rounded-md outline-none focus:ring-2 focus:ring-indigo-500" maxLength={4} />
                        <button type="button" onClick={() => handleYearChange(1)} className="p-1.5 bg-white border border-gray-300 rounded-md hover:bg-gray-100 active:scale-90 transition-transform"><ChevronRight size={14} /></button>
                      </div>
                    </div>
                  </div>
                  <div>
                    <label className={labelClass}>문서 제목 *</label>
                    <input type="text" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} className={inputClass} placeholder="예: 2026학년도 신입생 모집요강" />
                  </div>
                  <div>
                    <label className={labelClass}>공개 권한 *</label>
                    <div className="flex bg-gray-100 p-1 rounded-lg">
                      <button type="button" onClick={() => setFormData({ ...formData, is_public: 'Y' })} className={`flex-1 py-2 text-xs font-bold rounded-md transition-all active:scale-95 flex items-center justify-center gap-1 ${formData.is_public === 'Y' ? 'bg-emerald-500 text-white shadow-md' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'}`}>
                        <CheckCircle2 size={14} /> 대외 공개
                      </button>
                      <button type="button" onClick={() => setFormData({ ...formData, is_public: 'N' })} className={`flex-1 py-2 text-xs font-bold rounded-md transition-all active:scale-95 flex items-center justify-center gap-1 ${formData.is_public === 'N' ? 'bg-red-500 text-white shadow-md' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'}`}>
                        <Lock size={14} /> 직원 전용
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className={labelClass}>파일 첨부 (PDF) *</label>
                    {isEditMode ? (
                      <div className="w-full border border-gray-200 bg-gray-50 rounded-lg p-3 text-center">
                        <FileText size={20} className="mx-auto mb-2 text-gray-400" />
                        <p className="text-xs font-bold text-gray-700">{editData.filename}</p>
                        <p className="text-[10px] text-gray-400 mt-1">무결성을 위해 파일은 수정할 수 없습니다.</p>
                      </div>
                    ) : (
                      <div onClick={() => fileInputRef.current?.click()} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} className={`w-full border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${selectedFile || isDragging ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300 hover:bg-gray-50'}`}>
                        <input type="file" accept=".pdf" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
                        <Upload size={20} className={`mx-auto mb-2 ${selectedFile ? 'text-indigo-600' : 'text-gray-400'}`} />
                        {selectedFile ? <p className="text-xs font-bold text-indigo-700 truncate">{selectedFile.name}</p> : <p className="text-xs text-gray-500 font-medium">여기를 클릭하거나 PDF 파일을 끌어다 놓으세요.</p>}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                /* ================= [정형 데이터 모달] ================= */
                <>
                  <div>
                    <label className={labelClass}>DB 출처 *</label>
                    <div className="flex bg-gray-100 p-1 rounded-lg mb-4">
                      <button type="button" disabled={isEditMode} onClick={() => setFormData({ ...formData, db_source: 'INTERNAL', table_name: '' })} className={`flex-1 py-2 text-xs font-bold rounded-md transition-all active:scale-95 ${formData.db_source === 'INTERNAL' ? 'bg-orange-500 text-white shadow-md' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'} ${isEditMode ? 'opacity-70 cursor-not-allowed' : ''}`}>내부 엑셀 변환</button>
                      <button type="button" disabled={isEditMode} onClick={() => setFormData({ ...formData, db_source: 'EXTERNAL', table_name: '' })} className={`flex-1 py-2 text-xs font-bold rounded-md transition-all active:scale-95 ${formData.db_source === 'EXTERNAL' ? 'bg-teal-500 text-white shadow-md' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200'} ${isEditMode ? 'opacity-70 cursor-not-allowed' : ''}`}>외부 학사 시스템 연동</button>
                    </div>
                  </div>

                  {formData.db_source === 'EXTERNAL' ? (
                    <>
                      <div>
                        <label className={labelClass}>연동할 뷰(View) 선택 *</label>
                        <div className="relative">
                          <List className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                          <select disabled={isEditMode} value={formData.table_name} onChange={e => setFormData({ ...formData, table_name: e.target.value })} className={`${inputClass} pl-9 font-mono ${isEditMode ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''}`}>
                            <option value="">{isEditMode ? formData.table_name : '등록할 뷰를 선택하세요...'}</option>
                            {availableViews.map(v => <option key={v} value={v}>{v}</option>)}
                          </select>
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between items-end mb-1.5">
                          <label className="block text-[11px] font-bold text-gray-600">테이블 한글명 *</label>
                          {isEditMode && (
                            <button type="button" onClick={handleSyncView} className="px-2 py-1 bg-teal-50 text-teal-700 font-bold rounded border border-teal-200 hover:bg-teal-100 transition-colors text-[10px] flex items-center gap-1 shadow-sm">
                              <RefreshCw size={12} /> 뷰(View) 컬럼 재동기화
                            </button>
                          )}
                        </div>
                        <input type="text" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} className={inputClass} placeholder="대시보드에 표시될 이름을 적어주세요." />
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className={labelClass}>시스템 생성 영문명 *</label>
                          <input type="text" value={formData.table_name} onChange={e => setFormData({ ...formData, table_name: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '') })} className={`${inputClass} font-mono ${isEditMode ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : 'bg-white'}`} placeholder="영문명 (엑셀 첨부시 자동입력)" disabled={isEditMode} />
                        </div>
                        <div>
                          <label className={labelClass}>엑셀 파일 첨부 (.xlsx) *</label>
                          {isEditMode ? (
                            <div className="w-full border border-gray-200 bg-gray-50 rounded-lg p-2.5 text-center">
                              <p className="text-[10px] text-gray-400">등록된 엑셀 데이터는 업로드할 수 없습니다.</p>
                            </div>
                          ) : (
                            <div onClick={() => fileInputRef.current?.click()} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} className={`w-full border-2 border-dashed rounded-lg p-2 text-center cursor-pointer transition-colors ${selectedFile || isDragging ? 'border-orange-400 bg-orange-50' : 'border-gray-300 hover:bg-gray-50'}`}>
                              <input type="file" accept=".xlsx, .xls" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
                              {selectedFile ? <p className="text-xs font-bold text-orange-700 truncate">{selectedFile.name}</p> : <p className="text-[10px] text-gray-500 font-medium pt-1">엑셀(.xlsx) 파일 드래그</p>}
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <label className={labelClass}>테이블 한글명 *</label>
                        <input type="text" value={formData.title} onChange={e => setFormData({ ...formData, title: e.target.value })} className={inputClass} placeholder="예: 2026 부서 예산 내역" />
                      </div>
                    </>
                  )}
                </>
              )}
              
              <div>
                <label className={labelClass}>AI 및 관리자용 테이블 설명 (힌트)</label>
                <textarea rows={2} value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className={`${inputClass} resize-none`} placeholder="AI가 문맥을 파악할 수 있는 설명을 적어주세요." />
              </div>

              {/* [NEW] 컬럼 카탈로그 편집기 (수정 모드일 때만 표시) */}
              {isEditMode && activeTab === 'tables' && (
                <div className="border-t border-gray-200 mt-4 pt-4">
                  <div className="flex justify-between items-end mb-2">
                    <label className="block text-[11px] font-bold text-indigo-700">데이터 사전 (개별 컬럼 보안 설정)</label>
                    <div className="flex gap-1.5">
                      <button type="button" onClick={() => handleBulkPublicToggle('Y')} className="px-2 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 rounded text-[10px] font-bold transition-all active:scale-95 shadow-sm">전체 공개</button>
                      <button type="button" onClick={() => handleBulkPublicToggle('N')} className="px-2 py-1 bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 rounded text-[10px] font-bold transition-all active:scale-95 shadow-sm">전체 비공개</button>
                    </div>
                  </div>
                  <div className="bg-white border border-gray-200 rounded-lg overflow-hidden max-h-56 overflow-y-auto custom-scrollbar">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-gray-50 sticky top-0 border-b border-gray-200 shadow-sm z-10">
                        <tr>
                          <th className="px-3 py-2 font-bold text-gray-600">컬럼 영문명</th>
                          <th className="px-3 py-2 font-bold text-gray-600">한글명 (AI 힌트)</th>
                          <th className="px-3 py-2 font-bold text-gray-600 text-center w-20">보안(CLS)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {columns.length === 0 ? (
                          <tr><td colSpan={3} className="px-3 py-6 text-center text-gray-400">등록된 컬럼이 없습니다. 동기화를 진행하세요.</td></tr>
                        ) : (
                          columns.map((col, idx) => (
                            <tr key={col.id} className="hover:bg-indigo-50/30 transition-colors">
                              <td className="px-3 py-2 font-mono text-gray-700 font-bold truncate max-w-[120px]" title={col.column_name}>{col.column_name}</td>
                              <td className="px-3 py-1.5">
                                <input 
                                  type="text" 
                                  id={`col-input-${idx}`} // 엔터키 이동을 위한 고유 ID 부여
                                  value={col.ai_description || ''} 
                                  onChange={e => {
                                    const newCols = [...columns];
                                    newCols[idx].ai_description = e.target.value;
                                    setColumns(newCols);
                                  }} 
                                  onKeyDown={e => {
                                    // 엔터키를 누르면 다음 인풋창으로 포커스 이동
                                    if (e.key === 'Enter') {
                                      e.preventDefault();
                                      const nextInput = document.getElementById(`col-input-${idx + 1}`);
                                      if (nextInput) nextInput.focus();
                                    }
                                  }}
                                  className="w-full px-2 py-1.5 bg-white border border-gray-300 rounded outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-200 transition-all text-xs"
                                  placeholder="설명 입력 (엔터로 다음 이동)"
                                />
                              </td>
                              <td className="px-3 py-1.5 text-center">
                                <button 
                                  type="button" 
                                  onClick={() => {
                                    const newCols = [...columns];
                                    newCols[idx].is_public = newCols[idx].is_public === 'Y' ? 'N' : 'Y';
                                    setColumns(newCols);
                                  }}
                                  className={`w-full py-1.5 rounded font-bold text-[10px] transition-all active:scale-95 ${col.is_public === 'Y' ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200' : 'bg-red-100 text-red-700 hover:bg-red-200'}`}
                                >
                                  {col.is_public === 'Y' ? '공개' : '비공개'}
                                </button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1.5">비공개(N)로 설정된 컬럼은 일반 학생용 챗봇이 조회할 때 DB에서 원천 차단됩니다.</p>
                </div>
              )}

            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="bg-white px-5 py-4 border-t border-gray-200 flex justify-between items-center shrink-0 min-w-0">
          <div>
            {isEditMode && (
              <button type="button" onClick={handleDelete} disabled={isLoading} className="px-3 py-2 text-red-600 bg-white border border-red-200 hover:bg-red-50 hover:border-red-300 rounded-lg text-xs font-bold transition-colors flex items-center shadow-sm">
                <Trash2 size={16} className="mr-1" /> {activeTab === 'documents' ? '문서 삭제' : '연동 해제'}
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} disabled={isLoading} className="px-4 py-2 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg text-xs md:text-sm font-bold shadow-sm transition-colors">취소</button>
            <button type="button" onClick={handleBeforeSubmit} disabled={isLoading} className={`px-5 py-2 ${activeTab === 'documents' ? 'bg-indigo-600 hover:bg-indigo-700' : formData.db_source === 'INTERNAL' ? 'bg-orange-500 hover:bg-orange-600' : 'bg-teal-500 hover:bg-teal-600'} text-white rounded-lg text-xs md:text-sm font-bold shadow-md transition transform flex items-center gap-1.5 ${isLoading ? 'opacity-50 cursor-wait' : 'hover:-translate-y-0.5 active:scale-95'}`}>
              {isLoading ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span> : <Save size={16} />}
              {isEditMode ? '설정 및 컬럼 저장' : (activeTab === 'documents' ? '등록 및 AI 임베딩' : 'DB 연동하기')}
            </button>
          </div>
        </div>

      </div>
    </div>,
    document.body
  );
}