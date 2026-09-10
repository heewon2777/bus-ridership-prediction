import { useEffect, useRef, useState } from 'react';
import { locateMe, formatDistance } from '../lib/geo.js';

// 이 정확도(미터)보다 나쁘면 사용자에게 경고한다. 정류장까지의 도보 시간이 확률
// 계산의 핵심 입력이라, 몇백 미터만 틀려도 결과가 의미를 잃는다.
const ACCURACY_WARN_METERS = 300;

// 출발지/목적지 검색창 하나. 백엔드의 /api/search를 통해 실제 카카오 장소
// 검색 결과를 받아 드롭다운으로 보여주고, 고른 장소를 onSelect로 올려보낸다.
// allowCurrentLocation이 켜져 있으면(출발지) "현재 위치" 버튼도 함께 보여준다.
export default function SearchField({ label, dotClass, placeholder, onSelect, allowCurrentLocation = false }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState('idle'); // idle | loading | error | results
  const [results, setResults] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');
  const [locating, setLocating] = useState(false);
  const [hint, setHint] = useState(null); // { kind: 'info' | 'error', text } — 검색창 아래 한 줄 안내
  const debounceRef = useRef(null);

  useEffect(() => () => clearTimeout(debounceRef.current), []);

  async function runSearch(q) {
    try {
      const res = await fetch(`/api/search?query=${encodeURIComponent(q)}`);
      const body = await res.json();
      if (!res.ok) {
        setStatus('error');
        setErrorMsg(body.detail || body.error || '검색에 실패했습니다.');
        return;
      }
      setResults(body.results || []);
      setStatus('results');
    } catch {
      setStatus('error');
      setErrorMsg('서버에 연결할 수 없습니다. FastAPI 백엔드(backend/main.py)가 실행 중인지 확인하세요.');
    }
  }

  function handleChange(e) {
    const q = e.target.value;
    setQuery(q);
    setHint(null);
    clearTimeout(debounceRef.current);
    if (!q.trim()) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setStatus('loading');
    debounceRef.current = setTimeout(() => runSearch(q.trim()), 300);
  }

  function pick(place) {
    setQuery(place.name);
    setOpen(false);
    onSelect(place);
  }

  // 현재 위치를 출발지로. 실패하면 이유를 안내하고 검색 입력은 그대로 열어둔다 —
  // 위치를 못 잡았다고 앱이 막히면 안 되고, 검색이 곧 대안이다.
  async function fillWithCurrentLocation() {
    setLocating(true);
    setHint({ kind: 'info', text: '현재 위치를 확인하는 중…' });
    try {
      const { lat, lng, accuracy } = await locateMe();
      pick({ name: '현재 위치', address: '', lat, lng });
      setHint(
        accuracy > ACCURACY_WARN_METERS
          ? {
              kind: 'error',
              text: `현재 위치를 ±${formatDistance(accuracy)} 정확도로만 잡았어요. 실내·건물 사이에서는 크게 틀릴 수 있으니, 지도의 파란 점이 어긋나 있으면 출발지를 검색으로 바꿔주세요.`
            }
          : { kind: 'info', text: `현재 위치 사용 중 (정확도 ±${formatDistance(accuracy)})` }
      );
    } catch (err) {
      setHint({ kind: 'error', text: err.message });
    } finally {
      setLocating(false);
    }
  }

  return (
    <div className="field search-field-wrap">
      <label>
        <span className={`dot ${dotClass}`}></span>
        {label}
      </label>
      <div className={`search-box${open ? ' focused' : ''}`}>
        <input
          type="text"
          value={query}
          placeholder={placeholder}
          autoComplete="off"
          onChange={handleChange}
          onFocus={() => query.trim() && setOpen(true)}
          onBlur={() => setOpen(false)}
        />
        {allowCurrentLocation && (
          <button type="button" className="locate-btn" onClick={fillWithCurrentLocation} disabled={locating}>
            {locating ? '확인 중…' : '📍 현재 위치'}
          </button>
        )}
      </div>
      {hint && <div className={`search-hint ${hint.kind}`}>{hint.text}</div>}
      {open && (
        <div className="search-dropdown">
          {status === 'loading' && <div className="search-loading">검색 중…</div>}
          {status === 'error' && <div className="search-error">{errorMsg}</div>}
          {status === 'results' && results.length === 0 && (
            <div className="search-empty">검색 결과가 없어요</div>
          )}
          {status === 'results' &&
            results.map((place, i) => (
              // onMouseDown은 input의 onBlur보다 먼저 발생하므로, 드롭다운을 닫기 전에
              // 클릭(선택)이 확실히 처리된다.
              <div className="search-item" key={i} onMouseDown={() => pick(place)}>
                <span className="name">{place.name}</span>
                <span className="addr">{place.address}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
