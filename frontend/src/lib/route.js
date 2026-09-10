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

export function formatPercent(p) {
  return p == null ? null : `${Math.round(p * 100)}%`;
}

const MODE_LABEL = { walk: '도보', bus: '버스', subway: '지하철' };

export function legLabel(leg) {
  const base = MODE_LABEL[leg.mode] || leg.mode;
  if (leg.routeName) return `${base} · ${leg.routeName}`;
  return base;
}

const PATH_TYPE_LABEL = { subway: '지하철', bus: '버스', mixed: '버스+지하철' };

// 경로 선택 칩의 첫 줄: "버스+지하철 · 67분"
export function pathLabel(path) {
  return `${PATH_TYPE_LABEL[path.pathType] || path.pathType} · ${formatMinutes(path.totalTime)}`;
}

// 같은 노선번호가 여러 번 나오면(ODsay는 방향·변형 노선을 따로 준다) 표시용으로는 하나만 남긴다.
export function uniqueLanes(lanes) {
  return (lanes || []).filter((lane, i, arr) => arr.findIndex((x) => x.busNo === lane.busNo) === i);
}

// 경로에 등장하는 버스 노선번호들 (칩 둘째 줄): "서초08, 동탄역1(퇴근), H12"
export function pathBusNumbers(path) {
  const numbers = path.legs.flatMap((leg) => uniqueLanes(leg.lanes).map((lane) => lane.busNo)).filter(Boolean);
  return [...new Set(numbers)].join(', ');
}
