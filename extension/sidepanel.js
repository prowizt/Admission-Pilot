const chatContainer = document.getElementById('chat-container');
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnScrap = document.getElementById('btn-scrap');
const scrapStatus = document.getElementById('scrap-status');

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

// 크롬 저장소 연동 (최근 설정 불러오기)
document.addEventListener('DOMContentLoaded', () => {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    chrome.storage.local.get(['customModels', 'activeModelId'], (result) => {
      if (result.customModels) {
        customModels = result.customModels;
      }
      let activeId = result.activeModelId || null;
      renderModelSelect(activeId);
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

// 모델 삭제 로직
btnDeleteModel.addEventListener('click', () => {
  if (!currentActiveModel || !currentActiveModel.id.startsWith("custom_")) return;
  if (confirm(`[${currentActiveModel.alias}] 모델 세트를 정말 삭제하시겠습니까?`)) {
    customModels = customModels.filter(m => m.id !== currentActiveModel.id);
    const nextActiveId = customModels.length > 0 ? customModels[customModels.length - 1].id : null;
    
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
  loadingDiv.innerHTML = `<span class="w-3 h-3 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></span>AI(${currentActiveModel.modelName})가 규정과 DB를 검토 중입니다...`;
  chatContainer.appendChild(loadingDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  const payload = {
    question: text,
    user_role: 'staff',
    model_name: currentActiveModel.modelName
  };

  if (scrapedContext) {
    payload.scraped_context = scrapedContext;
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
    document.getElementById(loadingId).remove();
    
    if (data.status === 'success') {
      addMessage(data.answer);
      scrapedContext = ""; 
      scrapStatus.classList.add('hidden');
      btnScrap.innerHTML = "📄 현재 화면 텍스트 스크랩";
      btnScrap.className = "text-[11px] font-bold px-2.5 py-1.5 bg-slate-100 text-slate-600 hover:bg-slate-200 rounded-md border border-slate-300 transition-colors flex items-center gap-1 shadow-sm active:scale-95";
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

// 스크랩 상태 초기화 헬퍼 함수
function resetScrapState() {
  scrapedContext = "";
  btnScrap.innerHTML = "📄 현재 화면 텍스트 스크랩";
  btnScrap.className = "text-[11px] font-bold px-2.5 py-1.5 bg-slate-100 text-slate-600 hover:bg-slate-200 rounded-md border border-slate-300 transition-colors flex items-center gap-1 shadow-sm active:scale-95";
  chatInput.placeholder = "질문을 입력하세요... (Shift+Enter로 줄바꿈)";
  scrapStatus.classList.add('hidden');
}

// 탭 활성화 감지하여 스크랩 상태 초기화
if (typeof chrome !== 'undefined' && chrome.tabs) {
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
      scrapedContext = combinedText.substring(0, 3000); 
      scrapStatus.classList.add('hidden'); // 기존 옆에 뜨는 텍스트는 숨김 유지
      btnScrap.innerHTML = "✅ 스크랩 완료 (클릭 시 취소)";
      btnScrap.className = "text-[11px] font-bold px-2.5 py-1.5 bg-emerald-100 text-emerald-700 hover:bg-emerald-200 rounded-md border border-emerald-300 transition-colors flex items-center gap-1 shadow-sm active:scale-95";
      chatInput.placeholder = "스크랩 완료! (내용이 AI에게 전달됨)";
      chatInput.focus();
    } else {
      alert("페이지의 텍스트를 가져올 수 없습니다.");
    }
  });
});