const chatContainer = document.getElementById('chat-container');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnScrap = document.getElementById('btn-scrap');
const scrapStatus = document.getElementById('scrap-status');
const apiKeyInput = document.getElementById('api-key-input');

let scrapedContext = ""; 

function addMessage(text, isUser = false) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `flex ${isUser ? 'justify-end' : 'justify-start'}`;
  
  const innerDiv = document.createElement('div');
  innerDiv.className = `p-3 rounded-2xl shadow-sm max-w-[85%] leading-relaxed text-sm whitespace-pre-wrap word-break break-words ${
    isUser 
      ? 'bg-indigo-600 text-white rounded-tr-none' 
      : 'bg-white border border-gray-200 text-gray-700 rounded-tl-none'
  }`;
  innerDiv.innerText = text;
  
  msgDiv.appendChild(innerDiv);
  chatContainer.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function sendMessage() {
  const text = chatInput.value.trim();
  const apiKey = apiKeyInput.value.trim();
  
  if (!text) return;
  if (!apiKey) {
    alert("Gemini API Key를 입력해주세요.");
    return;
  }

  addMessage(text, true);
  chatInput.value = '';
  btnSend.disabled = true;
  chatInput.disabled = true;

  const loadingId = 'loading-' + Date.now();
  const loadingDiv = document.createElement('div');
  loadingDiv.id = loadingId;
  loadingDiv.className = 'flex justify-start items-center gap-2 text-xs font-bold text-indigo-500 p-2 ml-1';
  loadingDiv.innerHTML = `<span class="w-3 h-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></span>AI가 규정과 DB를 검토 중입니다...`;
  chatContainer.appendChild(loadingDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  const payload = {
    question: text,
    user_role: 'staff',
    model_name: 'gemini-2.5-flash'
  };

  if (scrapedContext) {
    payload.scraped_context = scrapedContext;
  }

  try {
    const response = await fetch('http://127.0.0.1:8000/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-gemini-key': apiKey
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    document.getElementById(loadingId).remove();
    
    if (data.status === 'success') {
      addMessage(data.answer);
      scrapedContext = ""; 
      scrapStatus.classList.add('hidden');
      chatInput.placeholder = "질문을 입력하세요... (Shift+Enter로 줄바꿈)";
    } else {
      addMessage("오류가 발생했습니다: " + data.detail);
    }
  } catch (error) {
    document.getElementById(loadingId).remove();
    addMessage("서버 연결에 실패했습니다. 파이썬 백엔드 서버가 켜져 있는지 확인하세요.");
  } finally {
    btnSend.disabled = false;
    chatInput.disabled = false;
    chatInput.focus();
  }
}

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

btnSend.addEventListener('click', sendMessage);

btnScrap.addEventListener('click', async () => {
  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  chrome.scripting.executeScript({
    target: { tabId: tab.id, allFrames: true },
    func: () => {
      // 1. 페이지 내 모든 테이블을 마크다운 표 형식으로 변환하여 임시 대체
      const tables = Array.from(document.querySelectorAll('table'));
      const originalPlaceholders = [];
      
      tables.forEach((table) => {
        if (!table.parentNode) return;
        
        let markdownTable = '\n\n';
        const rows = table.querySelectorAll('tr');
        if (rows.length === 0) return;
        
        rows.forEach((row, rowIndex) => {
          const cells = row.querySelectorAll('th, td');
          if (cells.length === 0) return;
          
          let rowText = '|';
          cells.forEach(cell => {
            // 셀 안의 개행 및 연속 공백을 공백 하나로 치환
            let cellText = cell.innerText.replace(/\s+/g, ' ').trim();
            rowText += ` ${cellText} |`;
          });
          markdownTable += rowText + '\n';
          
          // 헤더 아래 마크다운 구분선 추가
          if (rowIndex === 0 && rows.length > 1) {
            let separator = '|';
            cells.forEach(() => {
              separator += ' --- |';
            });
            markdownTable += separator + '\n';
          }
        });
        markdownTable += '\n';
        
        // 테이블을 마크다운 텍스트를 담은 div로 임시 교체
        const placeholder = document.createElement('div');
        placeholder.innerText = markdownTable;
        
        originalPlaceholders.push({
          parent: table.parentNode,
          table: table,
          placeholder: placeholder
        });
        
        table.parentNode.replaceChild(placeholder, table);
      });

      // 2. 마크다운 표가 삽입된 상태의 렌더링 텍스트 추출
      let text = document.body.innerText;
      
      // 3. 원래 테이블 구조로 원상 복구 (사용자 화면 영향 없음)
      originalPlaceholders.forEach(item => {
        if (item.parent && item.placeholder.parentNode) {
          item.parent.replaceChild(item.table, item.placeholder);
        }
      });
      
      // 4. 불필요한 줄바꿈 제거
      text = text.replace(/\n{3,}/g, '\n\n');
      return text.trim();
    }
  }, (results) => {
    if (results && results.length > 0) {
      // [핵심] iframe 등 모든 프레임에서 가져온 텍스트를 하나로 병합
      const combinedText = results.map(r => r.result).filter(t => t && t.trim().length > 0).join('\n\n');
      
      // 5. 전체 길이를 3000자로 잘라 AI 토큰 제한 최적화 (프레임이 많을 수 있으므로 3000자로 여유)
      scrapedContext = combinedText.substring(0, 3000); 
      scrapStatus.classList.remove('hidden');
      chatInput.placeholder = "스크랩 완료! (내용이 AI에게 전달됨)";
      chatInput.focus();
    } else {
      alert("페이지의 텍스트를 가져올 수 없습니다.");
    }
  });
});
