import Swal from 'sweetalert2';

// 전역적으로 사용될 컴팩트 스타일 (모바일 최적화 및 인디고 테마)
const CustomSwal = Swal.mixin({
    width: '320px',
    padding: '1.25rem',
    confirmButtonColor: '#4f46e5', // Indigo-600
    cancelButtonColor: '#9ca3af',  // Gray-400
    customClass: {
        popup: 'rounded-2xl shadow-xl font-sans',
        title: 'text-lg font-bold text-gray-800',
        htmlContainer: 'text-sm text-gray-600',
        confirmButton: 'text-sm font-bold px-4 py-2 rounded-lg hover:bg-indigo-700 transition',
        cancelButton: 'text-sm font-bold px-4 py-2 rounded-lg hover:bg-gray-500 transition'
    },
    buttonsStyling: false
});

export default CustomSwal;
