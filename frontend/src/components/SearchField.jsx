import { useEffect, useRef, useState } from 'react';

// 출발지/목적지 검색창 하나. 백엔드의 /api/search를 통해 실제 카카오 장소
// 검색 결과를 받아 드롭다운으로 보여주고, 고른 장소를 onSelect로 올려보낸다.
export default function SearchField({ label, dotClass, placeholder, onSelect }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState('idle'); // idle | loading | error | results
  const [results, setResults] = useState([]);
  const [errorMsg, setErrorMsg] = useState('');
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
      </div>
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
