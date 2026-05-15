import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Save, Database, FileText } from 'lucide-react';

export default function KnowledgeModal({ isOpen, onClose, activeTab }: any) {
  const [formData, setFormData] = useState({
    doc_type: 'rule', year: '2026', title: '', is_public: 'Y',
    db_source: 'INTERNAL', table_name: '', description: ''
  });

  useEffect(() => {
    if (isOpen) {
      setFormData({ doc_type: 'rule', year: '2026', title: '', is_public: 'Y', db_source: 'INTERNAL', table_name: '', description: '' });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const labelClass = "block text-[11px] font-bold text-gray-600 mb-1.5";
  const inputClass = "w-full min-w-0 max-w-full text-xs md:text-sm px-3 py-2 appearance-none rounded-lg border border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition-all";

  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200 min-w-0">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh] min-w-0">
        
        {/* Header */}
        <div className="bg-indigo-900 px-5 py-4 text-white flex justify-between items-center shrink-0 min-w-0">
          <h3 className="font-bold text-sm tracking-wide flex items-center gap-1.5">
            {activeTab === 'documents' ? <FileText size={18} /> : <Database size={18} />}
            {activeTab === 'documents' ? '비정형 문서(PDF) 등록' : '정형 데이터(뷰) 연동'}
          </h3>
          <button onClick={onClose} className="hover:bg-white/20 p-1.5 rounded-full transition-colors"><X size={18} /></button>
        </div>

        {/* Form Body */}
        <div className="flex-1 overflow-y-auto p-5 custom-scrollbar bg-gray-50/50 min-w-0">
          <form className="space-y-4 min-w-0">
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm space-y-4 min-w-0">
              
              {activeTab === 'documents' ? (
                <>
                  <div className="grid grid-cols-2 gap-3 min-w-0">
                    <div>
                      <label className={labelClass}>문서 유형 *</label>
                      <select value={formData.doc_type} onChange={e => setFormData({...formData, doc_type: e.target.value})} className={inputClass}>
                        <option value="rule">Rule (규정/팩트)</option>
                        <option value="reference">Reference (양식/톤앤매너)</option>
                      </select>
                    </div>
                    <div>
                      <label className={labelClass}>적용 연도</label>
                      <input type="text" value={formData.year} onChange={e => setFormData({...formData, year: e.target.value})} className={inputClass} placeholder="예: 2026" />
                    </div>
                  </div>
                  <div>
                    <label className={labelClass}>문서 제목 *</label>
                    <input type="text" value={formData.title} onChange={e => setFormData({...formData, title: e.target.value})} className={inputClass} placeholder="예: 2026학년도 신입생 모집요강" />
                  </div>
                  <div>
                    <label className={labelClass}>공개 권한 *</label>
                    <select value={formData.is_public} onChange={e => setFormData({...formData, is_public: e.target.value})} className={inputClass}>
                      <option value="Y">전체 공개 (대외용)</option>
                      <option value="N">직원 전용 (내부용)</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>파일 첨부 *</label>
                    <input type="file" className={`${inputClass} !py-1.5`} />
                  </div>
                </>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3 min-w-0">
                    <div>
                      <label className={labelClass}>DB 출처 *</label>
                      <select value={formData.db_source} onChange={e => setFormData({...formData, db_source: e.target.value})} className={inputClass}>
                        <option value="INTERNAL">내부 시스템 (엑셀 등)</option>
                        <option value="EXTERNAL">외부 종합 학사 시스템</option>
                      </select>
                    </div>
                    <div>
                      <label className={labelClass}>공개 권한 *</label>
                      <select value={formData.is_public} onChange={e => setFormData({...formData, is_public: e.target.value})} className={inputClass}>
                        <option value="Y">전체 뷰</option>
                        <option value="N">보안 뷰 (CLS 대상)</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className={labelClass}>테이블/뷰 영문명 *</label>
                    <input type="text" value={formData.table_name} onChange={e => setFormData({...formData, table_name: e.target.value})} className={inputClass} placeholder="예: UI_IPSI_M_V" />
                  </div>
                </>
              )}
              
              <div>
                <label className={labelClass}>AI 및 관리자용 설명 (힌트)</label>
                <textarea rows={2} value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} className={`${inputClass} resize-none`} placeholder="AI가 문맥을 파악할 수 있는 설명을 적어주세요." />
              </div>

            </div>
          </form>
        </div>

        {/* Footer */}
        <div className="bg-white px-5 py-4 border-t border-gray-200 flex justify-end gap-2 shrink-0 min-w-0">
          <button type="button" onClick={onClose} className="px-4 py-2 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg text-xs md:text-sm font-bold shadow-sm transition-colors">
            취소
          </button>
          <button type="button" className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs md:text-sm font-bold shadow-md transition transform hover:-translate-y-0.5 flex items-center gap-1.5">
            <Save size={16} /> 등록 및 AI 임베딩
          </button>
        </div>

      </div>
    </div>,
    document.body
  );
}
