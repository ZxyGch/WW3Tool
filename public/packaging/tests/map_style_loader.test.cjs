// 验证网络请求数量、缓存复用和超时边界。
const { test } = require('node:test');
const assert = require('node:assert/strict');
require('../../globe_picker/map_style_loader.js');

const sources = {
  administrative: { style: 'https://example.test/style.json' },
  satellite: { type: 'raster', tiles: ['https://example.test/satellite/{z}/{x}/{y}'] },
  light: { type: 'raster', tiles: ['https://example.test/light/{z}/{x}/{y}'] },
  dark: { type: 'raster', tiles: ['https://example.test/dark/{z}/{x}/{y}'] }
};
const style = { version: 8, sources: {}, layers: [] };
const makeLoader = (timeout = 30) => createMapStyleLoader(sources, value => value, timeout);

test('栅格底图和极区启动不请求行政区样式', async () => {
  global.fetch = () => { throw new Error('不应发出请求'); };
  const loader = makeLoader();
  for (const id of ['satellite', 'dark', 'light', 'polar']) {
    const result = await loader.load(id);
    assert.equal(result.baseStyle, id);
    assert.equal(result.fallback, undefined);
  }
});

test('行政区并发请求合并且返回独立样式对象', async () => {
  let calls = 0;
  global.fetch = async (_, options) => {
    calls++;
    assert.equal(options.cache, 'force-cache');
    return { ok: true, json: async () => style };
  };
  const loader = makeLoader();
  const results = await Promise.all([loader.load('administrative'), loader.load('administrative')]);
  results[0].style.layers.push({ id: 'temporary' });
  assert.equal(results[1].style.layers.length, 0);
  await loader.load('administrative');
  assert.equal(calls, 1);
});

test('HTTP 失败使用亮色底图，后续请求可以恢复', async () => {
  let calls = 0;
  global.fetch = async () => ++calls === 1
    ? { ok: false, status: 403 }
    : { ok: true, json: async () => style };
  const loader = makeLoader();
  assert.equal((await loader.load('administrative')).fallback, true);
  assert.equal((await loader.load('administrative')).baseStyle, 'administrative');
  assert.equal(calls, 2);
});

for (const body of [null, {}, { version: 8, sources: {} }]) {
  test('无效样式使用可用的栅格底图：' + JSON.stringify(body), async () => {
    global.fetch = async () => ({ ok: true, json: async () => body });
    const result = await makeLoader().load('administrative');
    assert.equal(result.fallback, true);
    assert.equal(result.style.sources['base-tiles'], sources.light);
  });
}

test('请求挂起时按时退出并中止请求', async () => {
  let signal;
  global.fetch = (_, options) => {
    signal = options.signal;
    return new Promise(() => {});
  };
  const result = await makeLoader(10).load('administrative');
  assert.equal(result.fallback, true);
  assert.equal(signal.aborted, true);
});

test('响应正文挂起也受超时限制', async () => {
  global.fetch = async () => ({ ok: true, json: () => new Promise(() => {}) });
  assert.equal((await makeLoader(10).load('administrative')).fallback, true);
});
