import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainLayout from '@/layouts/MainLayout';
import Dashboard from '@/pages/Dashboard';
import Logs from '@/pages/Logs';
import { MessageSquare } from 'lucide-react';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="chat" element={
            <div className="h-full flex flex-col min-w-0 pb-24 md:pb-6 overflow-y-auto bg-slate-50/50 p-4 md:p-6">
              
              {/* 1. Header */}
              <div className="bg-gradient-to-br from-indigo-900 via-indigo-800 to-purple-900 rounded-t-xl shadow-md pt-4 pb-4 px-6 shrink-0 min-w-0 flex flex-col relative overflow-hidden text-white">
                <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                  <MessageSquare size={120} />
                </div>
                
                <div className="relative z-10 flex justify-between items-center min-w-0">
                  <div className="min-w-0 flex items-center gap-3">
                    <div className="bg-white/10 p-2 rounded-lg backdrop-blur-sm border border-white/10">
                      <MessageSquare className="text-amber-400" size={20} />
                    </div>
                    <h1 className="text-lg md:text-xl font-extrabold text-white tracking-tight flex items-center gap-2">
                      AI 챗봇 테스트
                    </h1>
                  </div>
                </div>
              </div>

              {/* 2. Chat Container */}
              <div className="flex-1 min-h-[550px] border-x border-b border-slate-200/80 rounded-b-xl overflow-hidden shadow-sm bg-white flex flex-col transition-all duration-300">
                <iframe 
                  src="/extension/sidepanel.html" 
                  className="w-full flex-1 border-none m-0 p-0"
                  title="대동대 AI 헬퍼 (웹 테스트 환경)"
                />
              </div>
              
            </div>
          } />
          <Route path="logs" element={<Logs />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
