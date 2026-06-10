// ==========================================
// [웹 호스팅 대응] 크롬 확장 API가 없는 일반 웹 브라우저(iframe) 환경 지원을 위한 Mocking 로직
// ==========================================
if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
  window.chrome = {
    storage: {
      local: {
        get: (keys, callback) => {
          const result = {};
          keys.forEach(key => {
            const val = localStorage.getItem(key);
            try {
              result[key] = val ? JSON.parse(val) : null;
            } catch (e) {
              result[key] = val;
            }
          });
          callback(result);
        },
        set: (items, callback) => {
          Object.entries(items).forEach(([key, val]) => {
            localStorage.setItem(key, JSON.stringify(val));
          });
          if (callback) callback();
        }
      }
    },
    tabs: {
      query: (queryInfo, callback) => {
        // 일반 웹페이지 환경에서는 브라우저 탭 텍스트 스크랩을 수행할 수 없으므로 빈 결과를 반환합니다.
        callback([]);
      }
    }
  };
}

const chatContainer = document.getElementById('chat-container');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnScrap = document.getElementById('btn-scrap');
const scrapStatus = document.getElementById('scrap-status');
const btnClearChat = document.getElementById('btn-clear-chat'); // 대화 비우기 버튼

const btnUpload = document.getElementById('btn-upload');
const fileUploadInput = document.getElementById('file-upload-input');
const uploadStatus = document.getElementById('upload-status');
const uploadFilename = document.getElementById('upload-filename');
const btnClearUpload = document.getElementById('btn-clear-upload');
// 설정 DOM 요소
const btnToggleSettings = document.getElementById('btn-toggle-settings');
const settingsBody = document.getElementById('settings-body');
const settingsArrow = document.getElementById('settings-arrow');

const savedModelsSelect = document.getElementById('saved-models-select');
const btnEditModel = document.getElementById('btn-edit-model');
const btnDeleteModel = document.getElementById('btn-delete-model');
const btnCancelEdit = document.getElementById('btn-cancel-edit');
const editModelId = document.getElementById('edit-model-id');
const formTitle = document.getElementById('form-title');

const newModelAlias = document.getElementById('new-model-alias');
const newModelId = document.getElementById('new-model-id');
const newModelApiKey = document.getElementById('new-model-apikey');
const btnAddModel = document.getElementById('btn-add-model');

let scrapedContext = ""; 
let scrapedFileName = ""; // [NEW] 첨부 파일명 기록용 변수
let chatHistory = []; // 대화 기록 저장용 전역 배열

// 기본 제공되는 모델 세트 (요청에 따라 비움)
let defaultModels = [];

let customModels = []; // 사용자가 추가한 모델 세트
let currentActiveModel = null; // 현재 선택된 모델 객체 추적

// 설정창 토글
btnToggleSettings.addEventListener('click', () => {
  const isHidden = settingsBody.classList.contains('hidden');
  if (isHidden) {
    settingsBody.classList.remove('hidden');
    settingsArrow.innerText = "▲";
  } else {
    settingsBody.classList.add('hidden');
    settingsArrow.innerText = "▼";
  }
});

// 크롬 저장소 연동 (최근 설정 및 대화 기록 불러오기)
document.addEventListener('DOMContentLoaded', () => {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(['customModels', 'activeModelId', 'chatHistory'], (result) => {
      if (result.customModels) {
        customModels = result.customModels;
      }
      let activeId = result.activeModelId || null;
      renderModelSelect(activeId);

      // 대화 복구
      if (result.chatHistory && result.chatHistory.length > 0) {
        chatHistory = result.chatHistory;
        // 기존 환영 메시지 삭제
        chatContainer.innerHTML = "";
        
        chatHistory.forEach(msg => {
          addMessage(msg.text, msg.isUser, false, msg.logId, msg.userFeedback);
        });
      }
    });
  } else {
    console.warn("Chrome storage API is not available.");
    renderModelSelect(null);
  }
});

// 셀렉트 박스 렌더링 함수
function renderModelSelect(activeId) {
  savedModelsSelect.innerHTML = "";
  const allModels = [...defaultModels, ...customModels];
  
  allModels.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    const keyStatus = m.apiKey.length > 5 ? "🔑" : "⚠️키 없음";
    opt.innerText = `${m.alias} [${keyStatus}]`;
    if (m.id === activeId) {
      opt.selected = true;
      currentActiveModel = m;
    }
    savedModelsSelect.appendChild(opt);
  });

  if (!currentActiveModel && allModels.length > 0) {
    currentActiveModel = allModels[0];
    savedModelsSelect.value = currentActiveModel.id;
  }
  
  // 커스텀 모델일 때만 수정/삭제 버튼 노출
  if (currentActiveModel && currentActiveModel.id.startsWith("custom_")) {
    btnEditModel.classList.remove('hidden');
    btnDeleteModel.classList.remove('hidden');
  } else {
    btnEditModel.classList.add('hidden');
    btnDeleteModel.classList.add('hidden');
  }
}

// 모델 변경 시 자동 저장 및 버튼 상태 변경
savedModelsSelect.addEventListener('change', () => {
  const selectedId = savedModelsSelect.value;
  const allModels = [...defaultModels, ...customModels];
  currentActiveModel = allModels.find(m => m.id === selectedId);
  
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    chrome.storage.local.set({ activeModelId: selectedId });
  }
  
  if (currentActiveModel && currentActiveModel.id.startsWith("custom_")) {
    btnEditModel.classList.remove('hidden');
    btnDeleteModel.classList.remove('hidden');
  } else {
    btnEditModel.classList.add('hidden');
    btnDeleteModel.classList.add('hidden');
  }
  resetForm();
});

// 모델 삭제 로직 (수정)
btnDeleteModel.addEventListener('click', () => {
  if (!currentActiveModel || !currentActiveModel.id.startsWith("custom_")) return;
  
  if (confirm(`[${currentActiveModel.alias}] 모델 세트를 정말 삭제하시겠습니까?`)) {
    customModels = customModels.filter(m => m.id !== currentActiveModel.id);
    
    // 삭제 후 기본 모델 선택
    const nextActiveId = defaultModels[0]?.id || null;
    
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ 
        customModels: customModels,
        activeModelId: nextActiveId 
      }, () => {
        renderModelSelect(nextActiveId);
        resetForm();
      });
    } else {
      renderModelSelect(nextActiveId);
      resetForm();
    }
  }
});

// 모델 수정 준비 로직
btnEditModel.addEventListener('click', () => {
  if (!currentActiveModel || !currentActiveModel.id.startsWith("custom_")) return;
  
  newModelAlias.value = currentActiveModel.alias;
  newModelId.value = currentActiveModel.modelName;
  newModelApiKey.value = currentActiveModel.apiKey;
  editModelId.value = currentActiveModel.id;
  
  formTitle.innerText = "✏️ AI 모델 세트 수정";
  btnAddModel.innerText = "수정완료";
  btnCancelEdit.classList.remove('hidden');
  
  // 수정 시 설정창이 열려있어야 함
  settingsBody.classList.remove('hidden');
  settingsArrow.innerText = "▲";
});

// 수정 취소 로직
btnCancelEdit.addEventListener('click', () => {
  resetForm();
});

// 입력 폼 초기화 함수
function resetForm() {
  newModelAlias.value = "";
  newModelId.value = "";
  newModelApiKey.value = "";
  editModelId.value = "";
  formTitle.innerText = "➕ 나만의 AI 모델 세트 추가";
  btnAddModel.innerText = "저장";
  btnCancelEdit.classList.add('hidden');
}

// 신규 추가 및 수정 저장 로직
btnAddModel.addEventListener('click', () => {
  const alias = newModelAlias.value.trim();
  const modelId = newModelId.value.trim();
  const apiKey = newModelApiKey.value.trim();
  const editingId = editModelId.value;

  if (!alias || !modelId || !apiKey) {
    alert("구분용 이름, 실제 모델명, API Key를 모두 입력해주세요.");
    return;
  }

  let finalActiveId = "";

  if (editingId) {
    // 기존 데이터 업데이트
    const idx = customModels.findIndex(m => m.id === editingId);
    if (idx !== -1) {
      customModels[idx].alias = alias;
      customModels[idx].modelName = modelId;
      customModels[idx].apiKey = apiKey;
    }
    finalActiveId = editingId;
  } else {
    // 신규 등록
    const newModel = {
      id: "custom_" + Date.now(),
      alias: alias,
      modelName: modelId,
      apiKey: apiKey
    };
    customModels.push(newModel);
    finalActiveId = newModel.id;
  }
  
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    chrome.storage.local.set({ 
      customModels: customModels,
      activeModelId: finalActiveId 
    }, () => {
      resetForm();
      renderModelSelect(finalActiveId);
      alert(`모델 세트가 성공적으로 ${editingId ? '수정' : '등록'}되었습니다.`);
    });
  } else {
    // 임시 메모리 저장 처리
    resetForm();
    renderModelSelect(finalActiveId);
    alert(`모델 세트가 ${editingId ? '수정' : '추가'}되었으나, 확장 프로그램 환경이 아니어 영구 저장되지 않습니다.`);
  }
});

function addMessage(text, isUser = false, saveToStorage = true, logId = null, initialFeedback = null) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `flex ${isUser ? 'justify-end' : 'justify-start'}`;
  
  const innerDiv = document.createElement('div');
  innerDiv.className = `p-3 rounded-2xl shadow-sm max-w-[85%] leading-relaxed text-sm whitespace-pre-wrap word-break break-words ${
    isUser 
      ? 'bg-indigo-600 text-white rounded-tr-none' 
      : 'bg-white border border-gray-200 text-gray-700 rounded-tl-none'
  }`;
  innerDiv.innerText = text;
  
  if (!isUser && logId) {
    const feedbackDiv = document.createElement('div');
    feedbackDiv.className = 'mt-2 pt-2 border-t border-gray-100 flex justify-end gap-1';
    
    const getThumbSvg = (type, isActive) => {
      const fillClass = isActive ? 'fill-current' : 'fill-transparent';
      if (type === 'UP') {
        return `<svg class="w-3.5 h-3.5 ${fillClass}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>`;
      } else {
        return `<svg class="w-3.5 h-3.5 ${fillClass}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"/></svg>`;
      }
    };

    const upBtn = document.createElement('button');
    upBtn.className = `feedback-btn up p-1.5 rounded transition-colors text-xs ${initialFeedback === 'UP' ? 'bg-indigo-50 text-indigo-600 active' : 'text-gray-400 hover:bg-gray-100 hover:text-indigo-500'}`;
    upBtn.title = "이 답변이 도움이 되었습니다 (분석 제외)";
    upBtn.innerHTML = getThumbSvg('UP', initialFeedback === 'UP');
    
    const downBtn = document.createElement('button');
    downBtn.className = `feedback-btn down p-1.5 rounded transition-colors text-xs ${initialFeedback === 'DOWN' ? 'bg-rose-50 text-rose-600 active' : 'text-gray-400 hover:bg-gray-100 hover:text-rose-500'}`;
    downBtn.title = "이 답변이 부정확합니다 (분석 포함)";
    downBtn.innerHTML = getThumbSvg('DOWN', initialFeedback === 'DOWN');
    
    const handleFeedback = async (btn, type) => {
      try {
        const isActive = btn.classList.contains('active');
        const newType = isActive ? null : type;
        
        await fetch(`http://127.0.0.1:8000/logs/audit/${logId}/feedback`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feedback: newType })
        });
        
        // UI Reset
        upBtn.className = 'feedback-btn up p-1.5 rounded transition-colors text-xs text-gray-400 hover:bg-gray-100 hover:text-indigo-500';
        downBtn.className = 'feedback-btn down p-1.5 rounded transition-colors text-xs text-gray-400 hover:bg-gray-100 hover:text-rose-500';
        upBtn.innerHTML = getThumbSvg('UP', false);
        downBtn.innerHTML = getThumbSvg('DOWN', false);
        
        // Update new state
        if (newType === 'UP') {
          upBtn.className = 'feedback-btn up p-1.5 rounded transition-colors text-xs bg-indigo-50 text-indigo-600 active';
          upBtn.innerHTML = getThumbSvg('UP', true);
        } else if (newType === 'DOWN') {
          downBtn.className = 'feedback-btn down p-1.5 rounded transition-colors text-xs bg-rose-50 text-rose-600 active';
          downBtn.innerHTML = getThumbSvg('DOWN', true);
        }
        
        // Update local storage history
        const chatItem = chatHistory.find(c => c.logId === logId);
        if (chatItem) {
          chatItem.userFeedback = newType;
          if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
            chrome.storage.local.set({ chatHistory: chatHistory });
          }
        }
      } catch (e) {
        console.error("피드백 전송 실패:", e);
      }
    };
    
    upBtn.addEventListener('click', () => handleFeedback(upBtn, 'UP'));
    downBtn.addEventListener('click', () => handleFeedback(downBtn, 'DOWN'));
    
    feedbackDiv.appendChild(upBtn);
    feedbackDiv.appendChild(downBtn);
    innerDiv.appendChild(feedbackDiv);
  }
  
  msgDiv.appendChild(innerDiv);
  chatContainer.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // 대화 기록을 스토리지에 동기화
  if (saveToStorage) {
    chatHistory.push({ text, isUser, logId, userFeedback: initialFeedback });
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ chatHistory: chatHistory });
    }
  }
}

async function sendMessage() {
  const text = chatInput.value.trim();
  
  if (!text) return;
  if (!currentActiveModel || !currentActiveModel.apiKey) {
    alert("선택된 모델에 연결된 API Key가 없습니다.\n⚙️ 내 AI 모델 관리 패널에서 키가 포함된 모델을 추가하고 선택해주세요.");
    settingsBody.classList.remove('hidden');
    settingsArrow.innerText = "▲";
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
  loadingDiv.innerHTML = `
    <span class="w-3 h-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></span>
    <span>AI(${currentActiveModel.modelName})가 규정과 DB를 검토 중입니다... <span id="timer-${loadingId}" class="text-orange-500 ml-1">(0초 경과)</span></span>
  `;
  chatContainer.appendChild(loadingDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // [NEW] 로딩 타이머 시작
  let secondsPassed = 0;
  const timerInterval = setInterval(() => {
    secondsPassed++;
    const timerSpan = document.getElementById(`timer-${loadingId}`);
    if (timerSpan) {
      if (secondsPassed >= 60) {
        const mins = Math.floor(secondsPassed / 60);
        const secs = secondsPassed % 60;
        timerSpan.innerText = `(${mins}분 ${secs}초 경과)`;
      } else {
        timerSpan.innerText = `(${secondsPassed}초 경과)`;
      }
    }
  }, 1000);

  const payload = {
    question: text,
    user_role: 'staff',
    model_name: currentActiveModel.modelName,
    history: chatHistory.slice(-6)
  };

  if (scrapedContext) {
    payload.scraped_context = scrapedContext;
    if (scrapedFileName) {
      payload.scraped_file_name = scrapedFileName;
    }
  }

  try {
    const response = await fetch('http://127.0.0.1:8000/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-gemini-key': currentActiveModel.apiKey
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    
    if (data.status === 'success') {
      addMessage(data.answer, false, true, data.log_id);
      resetScrapState(); // 전송 성공 시 스크랩/업로드 상태 모두 초기화
    } else {
      addMessage("오류가 발생했습니다: " + data.detail, false, true);
    }
  } catch (error) {
    addMessage("서버 연결에 실패했습니다. 파이썬 백엔드 서버가 켜져 있는지 확인하세요.");
  } finally {
    clearInterval(timerInterval); // 타이머 안전 종료
    const ld = document.getElementById(loadingId);
    if (ld) ld.remove(); // 로딩 UI 제거
    
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

// 대화 내역 초기화(비우기)
btnClearChat.addEventListener('click', () => {
  if (confirm("이전 대화 기록을 모두 삭제하시겠습니까?")) {
    chatHistory = [];
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ chatHistory: [] }, () => {
        chatContainer.innerHTML = "";
        addDefaultWelcomeMessage();
      });
    } else {
      chatContainer.innerHTML = "";
      addDefaultWelcomeMessage();
    }
  }
});

// 기본 웰컴 메시지 출력 함수
function addDefaultWelcomeMessage() {
  const welcomeDiv = document.createElement('div');
  welcomeDiv.className = 'flex justify-start';
  welcomeDiv.innerHTML = `
    <div class="p-3 rounded-2xl shadow-sm max-w-[85%] leading-relaxed text-sm whitespace-pre-wrap word-break break-words bg-white border border-gray-200 text-gray-700 rounded-tl-none">
안녕하세요! 대동대학교 입시처 AI 부사수입니다.
상단의 톱니바퀴 아이콘을 클릭하여 작동할 AI 모델을 설정해 주시고,
궁금한 점(통계 조회, 규정 분석 등)을 입력해 주세요! 😊
    </div>
  `;
  chatContainer.appendChild(welcomeDiv);
}

// 상태 초기화 헬퍼 함수 (스크랩 및 업로드 파일 공통)
function resetScrapState() {
  scrapedContext = "";
  scrapedFileName = ""; // [NEW] 파일명 초기화
  
  // 스크랩 버튼 초기화
  btnScrap.innerHTML = "📄 스크랩";
  btnScrap.className = "text-[11px] font-bold px-2.5 py-1.5 bg-slate-100 text-slate-600 hover:bg-slate-200 rounded-md border border-slate-300 transition-colors flex items-center gap-1 shadow-sm active:scale-95";
  
  // 파일 첨부 버튼 초기화
  btnUpload.innerHTML = "📎 파일 첨부";
  btnUpload.className = "text-[11px] font-bold px-2.5 py-1.5 bg-indigo-100 text-indigo-700 hover:bg-indigo-200 rounded-md border border-indigo-300 transition-colors flex items-center gap-1 shadow-sm active:scale-95";

  chatInput.placeholder = "질문을 입력하세요... (Shift+Enter로 줄바꿈)";
  
  if (scrapStatus) {
    scrapStatus.classList.add('hidden');
  }
  
  uploadStatus.classList.add('hidden');
  uploadFilename.innerText = "";
  fileUploadInput.value = "";
}

// 파일 첨부 취소 버튼 동작
btnClearUpload.addEventListener('click', (e) => {
  e.stopPropagation();
  resetScrapState();
});

// 탭 활성화 감지하여 스크랩 상태 초기화
if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.onActivated && chrome.tabs.onUpdated) {
  chrome.tabs.onActivated.addListener((activeInfo) => {
    if (scrapedContext) resetScrapState();
  });
  
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'loading' && scrapedContext) {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs.length > 0 && tabs[0].id === tabId) {
          resetScrapState();
        }
      });
    }
  });
}

btnScrap.addEventListener('click', async () => {
  // 일반 웹 브라우저(iframe) 환경인 경우 브라우저 보안 제약 안내
  if (typeof chrome === 'undefined' || !chrome.tabs || !chrome.tabs.query || !chrome.scripting) {
    alert("ℹ️ 웹 테스트 대시보드 환경에서는 브라우저 보안 정책상 다른 탭 화면을 강제 스크랩할 수 없습니다.\n\n정확한 1:1 대조 및 검토 테스트를 원하시면 파일 첨부(📎) 기능을 이용하시거나, 실제 크롬 확장 프로그램을 구동하여 사용해 주시기 바랍니다!");
    return;
  }

  // 이미 스크랩된 상태라면 해제 (토글 오프)
  if (scrapedContext) {
    resetScrapState();
    return;
  }

  let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  chrome.scripting.executeScript({
    target: { tabId: tab.id, allFrames: true },
    func: () => {
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
            let cellText = cell.innerText.replace(/\s+/g, ' ').trim();
            rowText += ` ${cellText} |`;
          });
          markdownTable += rowText + '\n';
          
          if (rowIndex === 0 && rows.length > 1) {
            let separator = '|';
            cells.forEach(() => {
              separator += ' --- |';
            });
            markdownTable += separator + '\n';
          }
        });
        markdownTable += '\n';
        
        const placeholder = document.createElement('div');
        placeholder.innerText = markdownTable;
        
        originalPlaceholders.push({
          parent: table.parentNode,
          table: table,
          placeholder: placeholder
        });
        
        table.parentNode.replaceChild(placeholder, table);
      });

      let text = document.body.innerText;
      
      originalPlaceholders.forEach(item => {
        if (item.parent && item.placeholder.parentNode) {
          item.parent.replaceChild(item.table, item.placeholder);
        }
      });
      
      text = text.replace(/\n{3,}/g, '\n\n');
      return text.trim();
    }
  }, (results) => {
    if (results && results.length > 0) {
      const combinedText = results.map(r => r.result).filter(t => t && t.trim().length > 0).join('\n\n');
      resetScrapState(); // 기존 상태 모두 초기화
      
      scrapedContext = combinedText.substring(0, 50000); 
      btnScrap.innerHTML = "✅ 스크랩 완료";
      btnScrap.className = "text-[11px] font-bold px-2.5 py-1.5 bg-emerald-600 text-white hover:bg-emerald-700 rounded-md border border-emerald-700 transition-colors flex items-center gap-1 shadow-sm active:scale-95";
      chatInput.placeholder = "스크랩 화면에 대해 무엇이든 물어보세요!";
      chatInput.focus();
    } else {
      alert("페이지의 텍스트를 가져올 수 없습니다.");
    }
  });
});

// --- 파일 첨부 로직 ---
btnUpload.addEventListener('click', () => {
  fileUploadInput.click();
});

// 파일 업로드 처리 공통 함수
async function processFile(file) {
  if (!file) return;

  // 드래그 앤 드롭 시 확장자 필터링 안전 검증
  const filename = file.name.toLowerCase();
  if (!(filename.endsWith('.pdf') || filename.endsWith('.txt') || filename.endsWith('.csv') || filename.endsWith('.xlsx'))) {
    alert("현재는 PDF, TXT, CSV, XLSX 파일만 지원합니다.");
    fileUploadInput.value = ""; // 먹통 방지: 얼리 리턴 전에도 파일 선택 초기화
    return;
  }

  // 로딩 상태 표시
  uploadStatus.classList.remove('hidden');
  uploadFilename.innerText = "파싱 중...";
  chatInput.disabled = true;
  chatInput.placeholder = "파일에서 텍스트 및 표를 추출 중입니다...";

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('http://127.0.0.1:8000/parse-file', {
      method: 'POST',
      body: formData
    });

    const data = await response.json();
    
    if (data.status === 'success') {
      resetScrapState(); // 기존 상태 모두 초기화
      
      scrapedContext = data.text.substring(0, 50000); // 파싱된 텍스트 저장 (최대 50000자)
      scrapedFileName = file.name; // [NEW] 파일명 저장
      uploadFilename.innerText = file.name;
      uploadFilename.title = file.name;
      uploadStatus.classList.remove('hidden');
      
      // 파일 첨부 완료 시 눈에 띄는 형광색(lime)으로 버튼 스타일 변경
      btnUpload.innerHTML = "📎 파일 첨부 완료";
      btnUpload.className = "text-[11px] font-extrabold px-2.5 py-1.5 bg-lime-400 text-lime-950 hover:bg-lime-500 rounded-md border border-lime-500 transition-colors flex items-center gap-1 shadow-sm active:scale-95";
      chatInput.placeholder = "첨부된 파일 내용에 대해 무엇이든 물어보세요!";
    } else {
      resetScrapState();
      addMessage("⚠️ 파일 첨부 실패: " + data.detail + "\n(혹시 옛날 .xls 파일을 이름만 .xlsx로 바꾸셨다면 엑셀에서 '다른 이름으로 저장'을 해주세요!)", false, true);
    }
  } catch (error) {
    resetScrapState();
    addMessage("⚠️ 파일 파싱 서버 연결 실패: 파이썬 백엔드가 켜져 있는지 확인하세요.", false, true);
  } finally {
    chatInput.disabled = false;
    chatInput.focus();
    fileUploadInput.value = ""; // 동일 파일 다시 업로드 가능하도록 초기화
  }
}

fileUploadInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) {
    await processFile(file);
  }
});

// --- 질문 입력창 드래그 앤 드롭 이벤트 바인딩 ---
chatInput.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.stopPropagation();
  chatInput.classList.add('border-indigo-500', 'ring-2', 'ring-indigo-100');
});

chatInput.addEventListener('dragleave', (e) => {
  e.preventDefault();
  e.stopPropagation();
  chatInput.classList.remove('border-indigo-500', 'ring-2', 'ring-indigo-100');
});

chatInput.addEventListener('drop', async (e) => {
  e.preventDefault();
  e.stopPropagation();
  chatInput.classList.remove('border-indigo-500', 'ring-2', 'ring-indigo-100');
  
  const files = e.dataTransfer.files;
  if (files && files.length > 0) {
    await processFile(files[0]);
  }
});