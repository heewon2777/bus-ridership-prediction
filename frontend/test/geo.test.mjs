// locateMe()가 브라우저 위치 API의 실패 경로를 제대로 다루는지 확인한다.
// 브라우저 없이 돌리기 위해 window/navigator를 가짜로 심는다.
// 실행: npm test   (Node 내장 test runner — 별도 설치 없음)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { locateMe } from '../src/lib/geo.js';

// attempts: getCurrentPosition이 호출될 때마다 순서대로 소비하는 시나리오 목록.
// { error: code } 또는 { coords }. attempts가 null이면 geolocation이 없는 브라우저.
function fakeBrowser({ secure = true, attempts = [] }) {
  const calls = [];
  globalThis.window = { isSecureContext: secure };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: attempts === null
      ? {}
      : {
          geolocation: {
            getCurrentPosition(onOk, onFail, options) {
              calls.push(options);
              const next = attempts.shift();
              if (next.error) onFail({ code: next.error, message: `code ${next.error}` });
              else onOk({ coords: next.coords });
            }
          }
        }
  });
  return calls;
}

const HERE = { latitude: 37.4979, longitude: 127.0276, accuracy: 35 };

test('http(비보안) 컨텍스트에서는 위치 API를 부르지 않고 HTTPS 안내로 실패한다', async () => {
  const calls = fakeBrowser({ secure: false, attempts: [{ coords: HERE }] });
  await assert.rejects(locateMe(), /HTTPS/);
  assert.equal(calls.length, 0);
});

test('geolocation이 없는 브라우저는 검색으로 안내한다', async () => {
  fakeBrowser({ attempts: null });
  await assert.rejects(locateMe(), /검색/);
});

test('한 번에 성공하면 고정밀 옵션으로 한 번만 호출한다', async () => {
  const calls = fakeBrowser({ attempts: [{ coords: HERE }] });
  const pos = await locateMe();
  assert.deepEqual(pos, { lat: 37.4979, lng: 127.0276, accuracy: 35 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].enableHighAccuracy, true);
});

test('시간 초과(3)면 저정밀로 한 번 더 시도한다', async () => {
  const calls = fakeBrowser({ attempts: [{ error: 3 }, { coords: { ...HERE, accuracy: 900 } }] });
  const pos = await locateMe();
  assert.equal(pos.accuracy, 900);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].enableHighAccuracy, false);
});

test('권한 거부(1)는 재시도하지 않고 설정 안내로 실패한다', async () => {
  const calls = fakeBrowser({ attempts: [{ error: 1 }, { coords: HERE }] });
  await assert.rejects(locateMe(), /권한/);
  assert.equal(calls.length, 1);
});

test('저정밀 재시도까지 실패하면 그 이유로 실패한다', async () => {
  fakeBrowser({ attempts: [{ error: 2 }, { error: 2 }] });
  await assert.rejects(locateMe(), /위치를 알 수 없습니다/);
});
