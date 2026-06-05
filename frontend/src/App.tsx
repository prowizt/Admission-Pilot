import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainLayout from '@/layouts/MainLayout';
import Dashboard from '@/pages/Dashboard';
import Logs from '@/pages/Logs';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="chat" element={
            <div className="w-full h-[calc(100vh-100px)] min-h-[550px] border border-slate-200/80 rounded-2xl overflow-hidden shadow-lg bg-white flex flex-col transition-all duration-300 hover:shadow-xl">
              <iframe 
                src="/extension/sidepanel.html" 
                className="w-full flex-1 border-none m-0 p-0"
                title="대동대 AI 헬퍼 (웹 테스트 환경)"
              />
            </div>
          } />
          <Route path="logs" element={<Logs />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
