// 사전지식 분류 · 적용 대상 공통 정의 (대시보드 목록 · 필터 · 등록 모달이 함께 사용)

export const KNOWLEDGE_CATEGORIES = [
  { value: '인사/조직', label: '인사/조직', desc: '부서원 변경, 퇴사/입사 등', badge: 'bg-blue-50 text-blue-600' },
  { value: '결재라인', label: '결재라인', desc: '특정 결재선 규정, 부서 협조 등', badge: 'bg-purple-50 text-purple-600' },
  { value: '예외규정', label: '예외규정', desc: '핵심 규칙 및 행정 지침 예외 등', badge: 'bg-amber-50 text-amber-600' },
  { value: '02_도메인룰', label: '도메인룰', desc: '입시 용어 정의, 문서 표 해석, 조회 기준 등', badge: 'bg-teal-50 text-teal-600' },
  { value: '03_엑셀매핑', label: '엑셀매핑', desc: '엑셀 자동채우기 매핑·병합 셀 규칙', badge: 'bg-green-50 text-green-600' },
  { value: '04_성적산출', label: '성적산출', desc: '석차등급·환산점수 계산 규칙', badge: 'bg-rose-50 text-rose-600' },
  { value: '기타', label: '기타', desc: '', badge: 'bg-gray-50 text-gray-600' },
];

const DEFAULT_BADGE = 'bg-gray-50 text-gray-600';

export const categoryLabel = (value: string) =>
  KNOWLEDGE_CATEGORIES.find(c => c.value === value)?.label || value;

export const categoryBadge = (value: string) =>
  KNOWLEDGE_CATEGORIES.find(c => c.value === value)?.badge || DEFAULT_BADGE;

// 기본 분류 + DB 에만 있는 분류 (기본 목록에 없는 분류도 필터·선택지에서 사라지지 않도록)
export const mergeCategories = (values: string[]) => {
  const base = KNOWLEDGE_CATEGORIES.map(c => c.value);
  const extra = Array.from(new Set(values.filter(v => v && !base.includes(v)))).sort();
  return [...base, ...extra];
};

// 적용 대상 (NULL = 기존 사전지식 = 교직원 전용)
export const KNOWLEDGE_SCOPES = [
  { value: 'staff', label: '교직원 전용', text: 'text-indigo-700', badge: 'bg-indigo-50 text-indigo-600' },
  { value: 'all', label: '공통', text: 'text-emerald-600', badge: 'bg-emerald-50 text-emerald-700' },
  { value: 'student', label: '학생 전용', text: 'text-orange-600', badge: 'bg-orange-50 text-orange-600' },
];
