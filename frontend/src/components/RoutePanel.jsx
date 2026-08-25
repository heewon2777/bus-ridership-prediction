import { formatMinutes, formatFare, legLabel } from '../lib/route.js';

// 실제 ODsay 경로 조회 결과(도보+버스+지하철 구간, 총 소요시간·요금)를 보여준다.
// status: 'idle' | 'loading' | 'error' | 'done'
export default function RoutePanel({ status, route, errorMsg }) {
  if (status === 'idle') return null;

  if (status === 'loading') {
    return <div className="route-panel route-loading">실제 경로를 찾는 중…</div>;
  }

  if (status === 'error') {
    return (
      <div className="route-panel route-error">
        실제 경로를 가져오지 못했습니다: {errorMsg}
        <div className="footnote inline route-error-hint">
          ODsay API 키가 <code>backend/.env</code>의 <code>ODSAY_API_KEY</code>에 설정되어 있는지 확인하세요.
          그 전까지는 위 직선거리만 참고용으로 보여드려요.
        </div>
      </div>
    );
  }

  if (status === 'done' && route && route.found === false) {
    return <div className="route-panel route-error">이 두 지점 사이의 대중교통 경로를 찾지 못했습니다.</div>;
  }

  if (status === 'done' && route) {
    return (
      <div className="route-panel route-done">
        <div className="route-summary">
          <span className="route-summary-time">{formatMinutes(route.totalTime)}</span>
          <span className="route-summary-sep">·</span>
          <span>{formatFare(route.payment)}</span>
          {route.legs.filter((l) => l.mode !== 'walk').length > 1 && (
            <>
              <span className="route-summary-sep">·</span>
              <span>환승 {route.legs.filter((l) => l.mode !== 'walk').length - 1}회</span>
            </>
          )}
        </div>
        <ol className="route-legs">
          {route.legs.map((leg, i) => (
            <li key={i} className={`route-leg route-leg-${leg.mode}`}>
              <span className="route-leg-dot" />
              <span className="route-leg-label">{legLabel(leg)}</span>
              <span className="route-leg-time">{formatMinutes(leg.sectionTime)}</span>
            </li>
          ))}
        </ol>
        <p className="footnote inline">
          ODsay 대중교통 길찾기 API로 조회한 실제 추천 경로입니다. 노선 정체·실시간 배차는
          반영되지 않은 평시 기준 경로예요.
        </p>
      </div>
    );
  }

  return null;
}
