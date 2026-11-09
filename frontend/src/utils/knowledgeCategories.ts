// 사전지식 분류 · 적용 대상 공통 정의 (대시보드 목록 · 필터 · 등록 모달이 함께 사용)

// 분류는 5개로 고정 (2026-11-09 정리). 목록에 없는 분류는 필터에서 '그 외' 하나로 모음 → 버튼이 계속 늘어나지 않게.
export const KNOWLEDGE_CATEGORIES = [
  { value: '01_공문검토', label: '공문검토', desc: '결재선·인사/조직·공문 해석·지출 공문', badge: 'bg-purple-50 text-purple-600' },
  { value: '02_도메인룰', label: '도메인룰', desc: '입시 용어·학년도·정원·이월·조회 기준', badge: 'bg-teal-50 text-teal-600' },
  { value: '03_엑셀매핑', label: '엑셀매핑', desc: '엑셀 자동채우기 매핑·병합 셀 규칙', badge: 'bg-green-50 text-green-600' },
  { value: '04_성적산출', label: '성적산출', desc: '석차등급·환산점수 계산 규칙', badge: 'bg-rose-50 text-rose-600' },
  { value: '기타', label: '기타', desc: '', badge: 'bg-gray-50 text-gray-600' },
];

// 필터에서 '목록에 없는 분류'를 모아 보는 값
export const OTHER_CATEGORY_FILTER = '__other__';

const DEFAULT_BADGE = 'bg-gray-50 text-gray-600';

export const categoryLabel = (value: string) =>
  KNOWLEDGE_CATEGORIES.find(c => c.value === value)?.label || value;

export const categoryBadge = (value: string) =>
  KNOWLEDGE_CATEGORIES.find(c => c.value === value)?.badge || DEFAULT_BADGE;

export const isBaseCategory = (value: string) =>
  KNOWLEDGE_CATEGORIES.some(c => c.value === value);

// 적용 대상 (NULL = 기존 사전지식 = 교직원 전용)
export const KNOWLEDGE_SCOPES = [
  { value: 'staff', label: '교직원 전용', text: 'text-indigo-700', badge: 'bg-indigo-50 text-indigo-600' },
  { value: 'all', label: '공통', text: 'text-emerald-600', badge: 'bg-emerald-50 text-emerald-700' },
  { value: 'student', label: '학생 전용', text: 'text-orange-600', badge: 'bg-orange-50 text-orange-600' },
];
