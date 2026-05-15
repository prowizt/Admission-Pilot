import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainLayout from '@/layouts/MainLayout';
import Dashboard from '@/pages/Dashboard';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          {/* 향후 Chat, Settings 라우트 추가 예정 */}
          <Route path="chat" element={<div className="p-4">AI 챗봇 화면 준비 중...</div>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
