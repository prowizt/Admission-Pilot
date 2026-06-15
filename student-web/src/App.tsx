import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, User, Bot, Loader2, Sparkles, HelpCircle } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// 유틸리티 함수: Tailwind 클래스 병합
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isError?: boolean;
}

const QUICK_REPLIES = [
  "올해 수시 1차 면접 일정이 언제야?",
  "간호학과 작년 합격 등급 알려줘",
  "기숙사 신청은 어떻게 해?",
  "정원외 특별전형 자격 요건이 뭐야?"
];

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'init',
      role: 'assistant',
      content: '안녕하세요! 대동대학교 입학처 AI 챗봇입니다. 🎓\n입시 요강, 학과 정보, 전형 일정 등 궁금한 점을 편하게 물어보세요!'
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 자동 스크롤
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'; // 리셋
    }
    setIsLoading(true);

    try {
      const response = await axios.post('http://127.0.0.1:8000/chat', {
        question: text,
        model_name: "gemini-3.5-flash", // 기본 모델
        user_role: "student", // ✅ 핵심: 학생 권한 강제 주입
        scraped_context: "", 
        scraped_file_name: ""
      });

      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.data.answer || "응답 내용이 없습니다."
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (error: any) {
      console.error('Chat API Error:', error);
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '죄송합니다. 통신 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. 😥',
        isError: true
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 font-sans">
      {/* Header */}
      <header className="flex justify-between items-center py-6 px-5 bg-indigo-900 text-white shadow-md z-10 relative overflow-hidden rounded-br-3xl">
        <div className="absolute inset-0 opacity-10 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-white via-transparent to-transparent"></div>
        
        {/* Left: Logo & Title */}
        <div className="flex items-center z-10">
          <div className="flex-shrink-0 bg-white rounded-full p-1 mr-3 flex items-center justify-center shadow-sm">
            <img src="/logo.png" alt="대동대학교 로고" className="w-7 h-7 object-contain" />
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold tracking-wide">대동대 입시 AI 도우미</h1>
            <p className="text-[10px] sm:text-xs text-indigo-200 font-medium mt-0.5">Student Mode</p>
          </div>
        </div>

        {/* Right: Online Indicator */}
        <div className="flex items-center gap-1.5 z-10">
          <span className="text-[10px] sm:text-xs text-indigo-300 font-medium">Online</span>
          <div className="w-2 h-2 bg-emerald-400 rounded-full shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse"></div>
        </div>
      </header>

      {/* Chat Container */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 scroll-smooth">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "flex w-full",
              msg.role === 'user' ? "justify-end" : "justify-start"
            )}
          >
            <div
              className={cn(
                "max-w-[85%] sm:max-w-[70%] rounded-2xl p-4 shadow-sm block flow-root",
                msg.role === 'user'
                  ? "bg-indigo-900 text-white rounded-tr-none"
                  : msg.isError 
                    ? "bg-red-50 text-red-800 border border-red-200 rounded-tl-none"
                    : "bg-white/70 backdrop-blur-md border border-white/40 shadow-lg text-slate-800 rounded-tl-none"
              )}
            >
              {msg.role === 'assistant' && (
                <div className="mb-2">
                  <div className="w-8 h-8 rounded-full bg-daedong-cyan/20 flex items-center justify-center border border-daedong-cyan/50">
                    <Bot className="w-5 h-5 text-daedong-navy" />
                  </div>
                </div>
              )}
              
              <div className="whitespace-pre-wrap leading-relaxed text-[15px]">
                {msg.content}
              </div>

              {msg.role === 'user' && (
                <div className="float-right ml-3 mt-1">
                  <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
                    <User className="w-5 h-5 text-white" />
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex w-full justify-start">
            <div className="bg-white/70 backdrop-blur-md border border-white/40 shadow-lg max-w-[85%] rounded-2xl rounded-tl-none p-4 flex gap-3 items-center">
              <div className="w-8 h-8 rounded-full bg-daedong-cyan/20 flex items-center justify-center border border-daedong-cyan/50">
                 <Loader2 className="w-5 h-5 text-daedong-navy animate-spin" />
              </div>
              <span className="text-slate-500 text-sm font-medium">대동대 지식창고를 검색하며 답변을 생성 중입니다...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      {/* Quick Replies */}
      {messages.length < 3 && !isLoading && (
        <div className="px-4 pb-2 sm:px-6 flex flex-wrap justify-start gap-2">
          {QUICK_REPLIES.map((reply, idx) => (
            <button
              key={idx}
              onClick={() => sendMessage(reply)}
              className="bg-indigo-50 hover:bg-indigo-100 text-indigo-900 border border-indigo-200 backdrop-blur-sm transition-all duration-300 flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium shadow-sm break-keep"
            >
              <HelpCircle className="w-4 h-4 flex-shrink-0" />
              <span>{reply}</span>
            </button>
          ))}
        </div>
      )}

      {/* Input Area */}
      <footer className="p-4 sm:p-6 bg-white border-t border-slate-100 shadow-[0_-4px_20px_-10px_rgba(0,0,0,0.05)] z-10">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage(input);
          }}
          className="flex max-w-4xl mx-auto relative bg-slate-50 border border-slate-200 rounded-2xl focus-within:ring-2 focus-within:ring-indigo-900/50 focus-within:bg-white transition-all shadow-sm"
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(input);
              }
            }}
            disabled={isLoading}
            placeholder="궁금한 점을 질문해 주세요."
            className="flex-1 bg-transparent pl-5 pr-16 py-4 min-h-[56px] max-h-[120px] resize-none focus:outline-none disabled:opacity-50 text-[15px] leading-relaxed no-scrollbar"
            style={{ overflowY: input.split('\n').length > 4 || (textareaRef.current && textareaRef.current.scrollHeight > 120) ? 'auto' : 'hidden' }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="absolute right-2 bottom-2 w-10 h-10 rounded-full bg-indigo-900 hover:bg-indigo-950 text-white flex items-center justify-center disabled:opacity-50 transition-colors shadow-md flex-shrink-0"
          >
            {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-4 h-4 ml-1" />}
          </button>
        </form>
        <p className="text-center text-xs text-slate-400 mt-3 font-medium">
          이 챗봇은 AI 모델에 의해 응답하므로, 중요 안내는 반드시 모집요강 원본을 확인해주세요.
        </p>
      </footer>
    </div>
  );
}

export default App;
