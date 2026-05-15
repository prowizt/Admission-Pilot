import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { X, Save, Database, FileText, ChevronLeft, ChevronRight, Upload, CheckCircle2, Lock, Trash2 } from 'lucide-react';

export default function KnowledgeModal({ isOpen, onClose, activeTab, editData, onSuccess }: any) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isEditMode = !!editData;

  const [formData, setFormData] = useState({
    doc_type: 'rule',
    year: new Date().getFullYear().toString(),
    title: '',
    is_public: 'Y',
    db_source: 'INTERNAL',
    table_name: '',
    description: ''
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (isEditMode) {
        setFormData({
          doc_type: editData.doc_type || 'rule',
          year: editData.year || new Date().getFullYear().toString(),
          title: editData.title || '',
          is_public: editData.is_public || 'Y',
          db_source: editData.db_source || 'INTERNAL',
          table_name: editData.table_name || '',
          description: editData.description || ''
        });
      } else {
        setFormData({
          doc_type: 'rule',
          year: new Date().getFullYear().toString(),
          title: '',
          is_public: 'Y',
          db_source: 'INTERNAL',
          table_name: '',
          description: ''
        });
      }
      setSelectedFile(null);
    }
  }, [isOpen, editData, isEditMode]);

  if (!isOpen) return null;

  const handleYearChange = (delta: number) => {
    setFormData(prev => ({ ...prev, year: (parseInt(prev.year) + delta).toString() }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("정말 이 문서를 삭제하시겠습니까?\nMS-SQL 리스트와 ChromaDB(AI 지식)에서 영구적으로 파기됩니다.")) return;

    try {
      setIsLoading(true);
      await axios.delete(`http://127.0.0.1:8000/documents/${editData.doc_type}/${editData.doc_id}`);
      alert("문서가 안전하게 삭제되었습니다.");
      if (onSuccess) onSuccess();
      onClose();
    } catch (error) {
      alert("삭제 중 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (activeTab === 'documents') {
      if (!formData.title.trim()) return alert("문서 제목을 입력해주세요.");
      if (!isEditMode && !selectedFile) return alert("PDF 파일을 첨부해주세요.");

      const payload = new FormData();
      payload.append('doc_type', formData.doc_type);
      payload.append('year', formData.year);
      payload.append('title', formData.title);
      payload.append('is_public', formData.is_public);
      if (formData.description) payload.append('description', formData.description);

      try {
        setIsLoading(true);
        if (isEditMode) {
          // 수정(PUT) 로직
          const res = await axios.put(`http://127.0.0.1:8000/documents/${editData.doc_id}`, payload);
          if (res.data.status === 'success') {
            alert("문서 정보가 수정되었습니다.");
            if (onSuccess) onSuccess();
            onClose();
          }
        } else {
          // 신규 등록(POST) 로직
          payload.append('file', selectedFile as Blob);
          const res = await axios.post('http://127.0.0.1:8000/upload-knowledge', payload, {
            headers: { 'Content-Type': 'multipart/form-data' }
          });
          if (res.data.status === 'success') {
            alert("문서가 성공적으로 등록 및 임베딩되었습니다.");
            if (onSuccess) onSuccess();
            onClose();
          }
        }
      } catch (error: any) {
        console.error(error);
        alert(`저장 실패: ${error.response?.data?.detail || error.message}`);
      } finally {
        setIsLoading(false);
      }
    } else {
      alert("정형 데이터 연동 기능은 준비 중입니다.");
    }
  };

  const labelClass = "block text-[11px] font-bold text-gray-600 mb-1.5";
  const inputClass = "w-full min-w-0 max-w-full text-xs md:text-sm px-3 py-2 appearance-none rounded-lg border border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition-all";

  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200 min-w-0">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh] min-w-0">

        {/* Header */}
        <div className="bg-indigo-900 px-5 py-4 text-white flex justify-between items-center shrink-0 min-w-0">
          <h3 className="font-bold text-sm tracking-wide flex items-center gap-1.5">
            {activeTab === 'documents' ? <FileText size={18} /> : <Database size={18} />}
            {activeTab === 'documents' ? `비정형 문서(PDF) ${isEditMode ? '수정' : '등록'}` : `정형 데이터(뷰) ${isEditMode ? '수정' : '연동'}`}
          </h3>
          <button onClick={onClose} className="hover:bg-white/20 p-1.5 rounded-full transition-colors"><X size={18} /></button>
        </div>

        {/* Form Body */}
        <div className="flex-1 overflow-y-auto p-5 custom-scrollbar bg-gray-50/50 min-w-0">
          <form className="space-y-4 min-w-0" onSubmit={(e) => e.preventDefault()}>
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm space-y-4 min-w-0">

              {activeTab === 'documents' ? (
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
                        <input type="text" value={formData.year} onChange={(e) => setFormData({ ...formData, year: e.target.value.replace(/[^0-9]/g, '') })} className="w-28 text-center font-bold text-sm bg-white border border-gray-300 py-1.5 rounded-md outline-none focus:ring-2 focus:ring-indigo-500" maxLength={4} />
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
                    <label className={labelClass}>파일 첨부 *</label>
                    {isEditMode ? (
                      <div className="w-full border border-gray-200 bg-gray-50 rounded-lg p-3 text-center">
                        <FileText size={20} className="mx-auto mb-2 text-gray-400" />
                        <p className="text-xs font-bold text-gray-700">{editData.filename}</p>
                        <p className="text-[10px] text-gray-400 mt-1">파일 무결성을 위해 첨부 파일은 수정할 수 없습니다.<br />문서를 바꾸려면 삭제 후 다시 등록하세요.</p>
                      </div>
                    ) : (
                      <div
                        onClick={() => fileInputRef.current?.click()}
                        className={`w-full border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${selectedFile ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300 hover:bg-gray-50'}`}
                      >
                        <input type="file" accept=".pdf" className="hidden" ref={fileInputRef} onChange={handleFileChange} />
                        <Upload size={20} className={`mx-auto mb-2 ${selectedFile ? 'text-indigo-600' : 'text-gray-400'}`} />
                        {selectedFile ? (
                          <p className="text-xs font-bold text-indigo-700 truncate">{selectedFile.name}</p>
                        ) : (
                          <p className="text-xs text-gray-500 font-medium">여기를 클릭하여 PDF 파일을 첨부하세요</p>
                        )}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                /* 정형 데이터 폼 영역 (유지) */
                <div className="py-4 text-center text-gray-400 text-sm">정형 데이터는 준비 중입니다.</div>
              )}

              <div>
                <label className={labelClass}>AI 및 관리자용 설명 (힌트)</label>
                <textarea rows={2} value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} className={`${inputClass} resize-none`} placeholder="AI가 문맥을 파악할 수 있는 설명을 적어주세요." />
              </div>

            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="bg-white px-5 py-4 border-t border-gray-200 flex justify-between items-center shrink-0 min-w-0">
          <div>
            {isEditMode && (
              <button type="button" onClick={handleDelete} disabled={isLoading} className="px-3 py-2 text-red-600 bg-white border border-red-200 hover:bg-red-50 hover:border-red-300 rounded-lg text-xs font-bold transition-colors flex items-center shadow-sm">
                <Trash2 size={16} className="mr-1" /> 삭제
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={onClose} disabled={isLoading} className="px-4 py-2 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg text-xs md:text-sm font-bold shadow-sm transition-colors">
              취소
            </button>
            <button type="button" onClick={handleSubmit} disabled={isLoading} className={`px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs md:text-sm font-bold shadow-md transition transform flex items-center gap-1.5 ${isLoading ? 'opacity-50 cursor-wait' : 'hover:-translate-y-0.5 active:scale-95'}`}>
              {isLoading ? (
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              ) : (
                <Save size={16} />
              )}
              {isEditMode ? '변경사항 저장' : '등록 및 AI 임베딩'}
            </button>
          </div>
        </div>

      </div>
    </div>,
    document.body
  );
}