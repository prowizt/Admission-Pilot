import { useState } from 'react';
import { Link, useLocation, Outlet } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Database, Settings, Menu, LogOut, UserCircle } from 'lucide-react';
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

const SidebarItem = ({ icon: Icon, label, to, active }: any) => (
  <Link
    to={to}
    className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
      active ? 'bg-indigo-800 text-white shadow-md' : 'text-indigo-200 hover:bg-indigo-800 hover:text-white'
    }`}
  >
    <Icon size={20} />
    <span className="font-medium">{label}</span>
  </Link>
);

const SidebarContent = ({ pathname }: { pathname: string }) => {
  const menuItems = [
    { icon: LayoutDashboard, label: '지식 카탈로그', to: '/' },
    { icon: MessageSquare, label: 'AI 챗봇 테스트', to: '/chat' },
    { icon: Database, label: '시스템 로그', to: '/logs' },
    { icon: Settings, label: '환경 설정', to: '/settings' },
  ];

  return (
    <div className="flex flex-col h-full bg-indigo-900 text-white shadow-xl">
      {/* 4번 요청: 사이드바 헤더 색상을 푸터와 같은 950으로 변경 */}
      <div className="px-6 py-6 flex items-center justify-center border-b border-indigo-800 bg-indigo-950">
        <h1 className="text-xl font-black tracking-tight text-white bg-white/10 px-4 py-2 rounded-lg backdrop-blur-sm">
          Admission-Pilot
        </h1>
      </div>
      
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto custom-scrollbar">
        <div className="px-4 py-2 text-xs font-bold text-indigo-300 uppercase tracking-wider mb-2">Menu</div>
        {menuItems.map((item) => (
          <SidebarItem key={item.to} {...item} active={pathname === item.to} />
        ))}
      </nav>

      <div className="p-4 border-t border-indigo-800 bg-indigo-950">
        <div className="flex items-center gap-3 mb-4 bg-indigo-900/50 p-3 rounded-lg border border-indigo-800">
          <UserCircle size={32} className="text-indigo-300" />
          <div>
            <p className="text-sm font-bold text-white">최고 관리자님</p>
            <p className="text-xs text-indigo-300">입시홍보처 (Admin)</p>
          </div>
        </div>
        <Button variant="destructive" className="w-full flex gap-2 bg-red-600/20 text-red-100 hover:bg-red-600 hover:text-white border-none">
          <LogOut size={16} /> 로그아웃
        </Button>
      </div>
    </div>
  );
};

export default function MainLayout() {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 flex text-slate-900">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:block w-[260px] shrink-0 z-[100]">
        <SidebarContent pathname={location.pathname} />
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile Header (6번 요청: 햄버거 왼쪽, 타이틀 오른쪽 정렬) */}
        <header className="bg-white border-b border-slate-200 lg:hidden h-16 flex items-center px-4 justify-between sticky top-0 z-30 shadow-sm">
          <Sheet open={isOpen} onOpenChange={setIsOpen}>
            <SheetTrigger asChild>
              {/* 5번 요청: 부드럽게 열리는 햄버거 버튼 */}
              <Button variant="ghost" size="icon" className="text-slate-600 -ml-2">
                <Menu size={24} />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="p-0 w-[260px] border-none bg-indigo-900">
              <SheetTitle className="sr-only">모바일 네비게이션 메뉴</SheetTitle>
              <SidebarContent pathname={location.pathname} />
            </SheetContent>
          </Sheet>
          <div className="font-bold text-indigo-900 text-lg">Admission-Pilot</div>
        </header>

        {/* Dynamic Outlet */}
        <main className="flex-1 p-4 lg:p-8 overflow-y-auto">
          <div className="max-w-7xl mx-auto h-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
