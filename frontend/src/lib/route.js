// 백엔드의 /api/route(ODsay 프록시)를 호출해 두 지점 사이 실제 대중교통 경로를 가져온다.
export async function fetchRoute(origin, dest) {
  const params = new URLSearchParams({
    sx: String(origin.lng),
    sy: String(origin.lat),
    ex: String(dest.lng),
    ey: String(dest.lat),
  });
  const res = await fetch(`/api/route?${params.toString()}`);
  const body = await res.json();
  if (!res.ok) {
    const message = body.detail || body.error || '경로를 가져오지 못했습니다.';
    throw new Error(message);
  }
  return body;
}

export function formatMinutes(min) {
  if (min == null) return '-';
  if (min < 60) return `${min}분`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h}시간 ${m}분` : `${h}시간`;
}

export function formatFare(won) {
  if (won == null) return '-';
  return `${won.toLocaleString('ko-KR')}원`;
}

const MODE_LABEL = { walk: '도보', bus: '버스', subway: '지하철' };

export function legLabel(leg) {
  const base = MODE_LABEL[leg.mode] || leg.mode;
  if (leg.routeName) return `${base} · ${leg.routeName}`;
  return base;
}
