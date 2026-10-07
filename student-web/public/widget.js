(function() {
    // 위젯 스크립트가 로드된 도메인(챗봇 서버)을 자동으로 파악합니다.
    const scripts = document.getElementsByTagName('script');
    let scriptUrl = new URL(scripts[scripts.length - 1].src || window.location.href);
    let chatbotBaseUrl = scriptUrl.origin; 
    
    // 타 웹사이트에 삽입될 Iframe URL (위젯 모드 파라미터 추가)
    const CHATBOT_URL = `${chatbotBaseUrl}/?mode=widget`;

    // 전체 컨테이너
    const container = document.createElement('div');
    container.id = 'daedong-chatbot-widget-container';
    container.style.position = 'fixed';
    container.style.bottom = '20px';
    container.style.right = '20px';
    container.style.zIndex = '999999';
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.alignItems = 'flex-end';
    
    // Iframe 래퍼 (챗봇 창)
    const iframeWrapper = document.createElement('div');
    
    // 모바일 등 화면 크기에 맞춰 동적 사이즈 조절
    const isMobile = window.innerWidth < 600;
    iframeWrapper.style.width = isMobile ? 'calc(100vw - 40px)' : '380px';
    iframeWrapper.style.height = isMobile ? 'calc(100vh - 120px)' : '650px';
    iframeWrapper.style.maxHeight = 'calc(100vh - 100px)';
    iframeWrapper.style.backgroundColor = 'rgba(255, 255, 255, 0.70)';
    iframeWrapper.style.backdropFilter = 'blur(16px)';
    iframeWrapper.style.WebkitBackdropFilter = 'blur(16px)';
    iframeWrapper.style.borderRadius = '20px';
    iframeWrapper.style.boxShadow = '0 10px 40px -10px rgba(0,0,0,0.3)';
    iframeWrapper.style.overflow = 'hidden';
    iframeWrapper.style.marginBottom = '15px';
    iframeWrapper.style.display = 'none'; // 기본은 숨김 상태
    iframeWrapper.style.transition = 'opacity 0.4s ease, transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
    iframeWrapper.style.opacity = '0';
    iframeWrapper.style.transformOrigin = 'bottom right';
    iframeWrapper.style.transform = 'scale(0) translate(20%, 20%)';

    // 실제 챗봇 Iframe
    const iframe = document.createElement('iframe');
    iframe.src = CHATBOT_URL;
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';
    iframe.setAttribute('allowtransparency', 'true');
    
    iframeWrapper.appendChild(iframe);
    
    // 플로팅 버튼 (FAB)
    const fab = document.createElement('button');
    fab.style.width = '64px';
    fab.style.height = '64px';
    fab.style.borderRadius = '32px';
    fab.style.backgroundColor = '#312e81'; // 대동대 indigo-900 컬러
    fab.style.color = '#ffffff';
    fab.style.border = 'none';
    fab.style.boxShadow = '0 4px 15px rgba(49, 46, 129, 0.4)';
    fab.style.cursor = 'pointer';
    fab.style.display = 'flex';
    fab.style.alignItems = 'center';
    fab.style.justifyContent = 'center';
    fab.style.transition = 'transform 0.2s ease, background-color 0.2s ease';
    
    // 아이콘 SVG 및 텍스트 데이터 (챗봇 아이콘 + '상담' 텍스트)
    const chatIcon = `<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: -2px;">
        <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 3px;"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
        <span style="font-size: 12px; font-weight: bold; font-family: 'Pretendard', sans-serif; line-height: 1; letter-spacing: -0.5px;">상담</span>
    </div>`;
    const closeIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
    
    fab.innerHTML = chatIcon;
    
    // 토글 인터랙션
    let isOpen = false;
    fab.onclick = function() {
        isOpen = !isOpen;
        if (isOpen) {
            iframeWrapper.style.display = 'block';
            // 약간의 지연 후 애니메이션 적용 (렌더링 틱 확보)
            setTimeout(() => {
                iframeWrapper.style.opacity = '1';
                iframeWrapper.style.transform = 'scale(1) translate(0, 0)';
                // 리액트 앱(Iframe 내부)에 위젯이 열렸다는 신호 전송
                if (iframe.contentWindow) {
                    iframe.contentWindow.postMessage({ type: 'WIDGET_OPENED' }, '*');
                }
            }, 10);
            fab.innerHTML = closeIcon;
            fab.style.backgroundColor = '#1e1b4b'; // 열렸을 때 더 진한 색
            fab.style.transform = 'rotate(90deg)';
        } else {
            iframeWrapper.style.opacity = '0';
            iframeWrapper.style.transform = 'scale(0) translate(20%, 20%)';
            fab.innerHTML = chatIcon;
            fab.style.backgroundColor = '#312e81'; 
            fab.style.transform = 'rotate(0deg)';
            setTimeout(() => {
                iframeWrapper.style.display = 'none';
            }, 300);
        }
    };
    
    // 호버 애니메이션
    fab.onmouseover = function() {
        if (!isOpen) fab.style.transform = 'scale(1.08) translateY(-2px)';
        fab.style.boxShadow = '0 6px 20px rgba(49, 46, 129, 0.6)';
    };
    fab.onmouseout = function() {
        if (!isOpen) fab.style.transform = 'scale(1) translateY(0)';
        fab.style.boxShadow = '0 4px 15px rgba(49, 46, 129, 0.4)';
    };
    
    // 화면 크기 변경 시 대응
    window.addEventListener('resize', () => {
        if (window.innerWidth < 600) {
            iframeWrapper.style.width = 'calc(100vw - 40px)';
            iframeWrapper.style.height = 'calc(100vh - 120px)';
        } else {
            iframeWrapper.style.width = '380px';
            iframeWrapper.style.height = '650px';
        }
    });

    // DOM에 요소 부착
    container.appendChild(iframeWrapper);
    container.appendChild(fab);
    document.body.appendChild(container);
    
})();
