// 카카오맵 JavaScript SDK를 동적으로 불러오는 헬퍼.
//
// React 18의 StrictMode는 개발 중 effect를 일부러 두 번 실행하는데, 그때마다
// <script> 태그를 새로 추가하면 안 되므로 모듈 스코프의 loadingPromise로
// "한 번만 로드"를 보장한다.

let loadingPromise = null;

export function loadKakaoSdk(appkey) {
  if (window.kakao && window.kakao.maps) {
    return Promise.resolve(window.kakao);
  }
  if (loadingPromise) return loadingPromise;

  loadingPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(appkey)}&autoload=false`;
    script.onload = () => {
      window.kakao.maps.load(() => resolve(window.kakao));
    };
    script.onerror = () => {
      loadingPromise = null; // 실패하면 나중에 다시 시도할 수 있게 초기화
      reject(new Error('카카오맵 SDK 스크립트 로드에 실패했습니다.'));
    };
    document.head.appendChild(script);
  });

  return loadingPromise;
}
