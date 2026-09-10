// 위도/경도 두 점 사이의 직선거리(미터)를 하버사인 공식으로 계산한다.
// 실제 도보+버스 경로(ODsay API 연동)가 붙기 전까지, 두 지점을 고른 뒤
// 보여줄 수 있는 가장 간단한 "거리 감각"용 근사치.
export function haversineMeters(a, b) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  return 2 * R * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

export function formatDistance(meters) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)}km` : `${Math.round(meters)}m`;
}

// 브라우저 Geolocation 실패 코드 → 사용자가 직접 고칠 수 있는 안내문.
// (아이폰 Safari는 위치 권한을 사이트별로 기억하므로, 한 번 거부하면 설정에서 풀어야 한다.)
const GEO_ERROR_MESSAGE = {
  1: '위치 권한이 거부됐습니다. 아이폰은 설정 > 개인정보 보호 및 보안 > 위치 서비스 > Safari 웹 사이트를 "앱을 사용하는 동안"으로 바꾸고, 주소창의 "가A"(AA) 버튼 > 웹 사이트 설정 > 위치를 "허용"으로 바꾼 뒤 다시 눌러주세요.',
  2: '지금 위치를 알 수 없습니다. 실내·지하에서는 GPS와 Wi-Fi 신호가 약할 수 있어요. 잠시 뒤 다시 시도하거나 출발지를 검색으로 입력하세요.',
  3: '위치를 찾는 데 시간이 너무 걸립니다. 다시 시도하거나 출발지를 검색으로 입력하세요.'
};

// 현재 위치를 {lat, lng, accuracy(미터)}로 돌려준다. 실패하면 위 안내문을 담은 Error를 던진다.
// 위치를 못 잡아도 앱이 막히면 안 되므로, 호출한 쪽은 그냥 검색 입력으로 되돌아가면 된다.
export async function locateMe() {
  // 브라우저는 https가 아니면 위치 정보를 아예 내주지 않는다(localhost만 예외).
  // 휴대폰에서 PC의 LAN IP(http://192.168.x.x:5173)로 접속하면 정확히 이 경우에 걸린다.
  if (!window.isSecureContext) {
    throw new Error(
      'HTTPS가 아니라서 브라우저가 위치 접근을 막았습니다. 휴대폰에서는 PC에서 `npm run dev:phone`으로 띄운 https:// 주소로 접속하세요.'
    );
  }
  if (!navigator.geolocation) {
    throw new Error('이 브라우저는 위치 기능을 지원하지 않습니다. 출발지를 검색으로 입력하세요.');
  }
  try {
    return await getPosition({ enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
  } catch (err) {
    // 실내에서는 GPS(고정밀)가 시간 초과되기 쉬운데, Wi-Fi·기지국 기반(저정밀)은
    // 바로 잡히는 경우가 많다. 권한 거부(1)는 다시 시도해도 같으니 그대로 던진다.
    if (err.code === 2 || err.code === 3) {
      return getPosition({ enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
    }
    throw err;
  }
}

function getPosition(options) {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy }),
      (err) => reject(Object.assign(new Error(GEO_ERROR_MESSAGE[err.code] || err.message), { code: err.code })),
      options
    );
  });
}
