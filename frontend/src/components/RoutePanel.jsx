import {
  formatMinutes,
  formatFare,
  formatPercent,
  legLabel,
  pathLabel,
  pathBusNumbers,
  uniqueLanes
} from '../lib/route.js';

// ODsay가 돌려준 경로 목록을 보여준다. 첫 번째가 추천 경로, 나머지는 대안(기획서 4장) —
// 칩으로 골라 보면 요약·구간 목록과 지도 위 경로선이 함께 바뀐다.
// status: 'idle' | 'loading' | 'error' | 'done'
export default function RoutePanel({ status, route, selectedPath, onSelectPath, errorMsg }) {
  if (status === 'idle') return null;

  if (status === 'loading') {
    return <div className="route-panel route-loading">실제 경로를 찾는 중…</div>;
  }

  if (status === 'error') {
    return (
      <div className="route-panel route-error">
        실제 경로를 가져오지 못했습니다: {errorMsg}
        <div className="footnote inline route-error-hint">
          그 전까지는 출발-목적지 직선만 참고용으로 그려둡니다.
        </div>
      </div>
    );
  }

  if (status !== 'done' || !route) return null;

  if (route.found === false || !route.paths?.length) {
    return <div className="route-panel route-error">이 두 지점 사이의 대중교통 경로를 찾지 못했습니다.</div>;
  }

  const path = route.paths[Math.min(selectedPath, route.paths.length - 1)];
  const rideCount = path.legs.filter((l) => l.mode !== 'walk').length;

  return (
    <div className="route-panel route-done">
      {route.paths.length > 1 && (
        <div className="path-chips" role="tablist" aria-label="경로 선택">
          {route.paths.map((p, i) => (
            <button
              type="button"
              role="tab"
              aria-selected={i === selectedPath}
              key={i}
              className={`path-chip${i === selectedPath ? ' selected' : ''}`}
              onClick={() => onSelectPath(i)}
            >
              <span className="path-chip-title">
                {i === 0 ? '추천' : `대안 ${i}`} · {pathLabel(p)}
              </span>
              {pathBusNumbers(p) && <span className="path-chip-sub">{pathBusNumbers(p)}</span>}
            </button>
          ))}
        </div>
      )}

      <div className="route-summary">
        <span className="route-summary-time">{formatMinutes(path.totalTime)}</span>
        <span className="route-summary-sep">·</span>
        <span>{formatFare(path.payment)}</span>
        {rideCount > 1 && (
          <>
            <span className="route-summary-sep">·</span>
            <span>환승 {rideCount - 1}회</span>
          </>
        )}
      </div>

      <ol className="route-legs">
        {path.legs.map((leg, i) => (
          <li key={i} className={`route-leg route-leg-${leg.mode}`}>
            <span className="route-leg-dot" />
            <span className="route-leg-label">
              {/* 버스는 노선별 배지에 번호가 들어가므로 라벨은 "버스"만 */}
              {leg.lanes?.length ? '버스' : legLabel(leg)}
              {leg.lanes?.length > 0 && (
                <span className="lane-badges">
                  {uniqueLanes(leg.lanes).map((lane, j) => (
                    <span key={j} className={`lane-badge${lane.seatProbability == null ? ' nodata' : ''}`}>
                      {lane.busNo}
                      {lane.busType === '광역' && ' · 광역(입석금지)'}
                      {' · 좌석 '}
                      {formatPercent(lane.seatProbability) ?? '데이터 없음'}
                    </span>
                  ))}
                </span>
              )}
            </span>
            <span className="route-leg-time">{formatMinutes(leg.sectionTime)}</span>
          </li>
        ))}
      </ol>

      <p className="footnote inline">
        ODsay 추천 순서대로 보여줍니다(시간순이 아닐 수 있어요). "좌석"은 서울시 승하차 데이터로 학습한
        지금 시각의 좌석 여유 확률이며, 아직 402·143 노선만 학습돼 있어 나머지는 "데이터 없음"으로
        표시됩니다. 정시 도착 확률은 실시간 도착정보 연동 후 붙습니다.
      </p>
    </div>
  );
}
