// 확장 프로그램 아이콘을 클릭하면 사이드 패널이 열리도록 설정합니다.
chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.error(error));