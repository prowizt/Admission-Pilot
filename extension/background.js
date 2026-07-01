// 서비스 워커 설치 시 사이드 패널 동작 강제 설정
chrome.runtime.onInstalled.addListener(() => {
  console.log("대동대 AI 헬퍼 확장프로그램이 설치/업데이트 되었습니다.");
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch((error) => console.error(error));
});

// 혹시 몰라서 확장프로그램 아이콘(action)을 클릭할 때도 명시적으로 사이드패널을 열도록 추가 시도
chrome.action.onClicked.addListener((tab) => {
  // 현재 탭에서 사이드 패널 열기
  chrome.sidePanel.open({ windowId: tab.windowId });
});
