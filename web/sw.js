/**
 * TIANGONG FREE CLASSROOM — Service Worker
 *
 * 策略取向：**新鲜优先，离线兜底**。
 *
 * 这个站的全部价值就是"今天的空教室"。缓存如果不假思索地先回旧的，
 * 用户早上打开看到的是昨天的教室、却以为是今天 —— 这是本项目最不可接受的失败方式。
 * 所以同源请求一律先走网络；只有网络真的不可用时才回落到缓存，
 * 而缓存里的 today.json 自带 data_date，前端会据此显示真实日期与"非实时"横幅。
 *
 * 静态资源（HTML/CSS/JS/JSON）也走 network-first：
 * 文件名不带指纹，若用 stale-while-revalidate，发版后老用户会长期停在旧版本。
 */

const CACHE_VERSION = 'v3';
const CACHE_NAME = `tiangong-room-${CACHE_VERSION}`;

/* 预缓存只放本地一定存在的文件。
   过去这里混入过一份仓库源文件路径（发布目录里并没有它），
   而 cache.addAll 是原子的 —— 一个 404 就让整批 reject，离线能力实际为零。 */
const PRECACHE = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/apple-touch-icon.png'
];

const DATA_FILE = /\/data\/today\.json$/;

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    /* 逐个添加而不是 addAll：单个文件 404 不该拖垮整批，
       而且失败必须留下明确日志，不能像以前那样被吞成一行 warn。 */
    const results = await Promise.all(PRECACHE.map(async (path) => {
      try {
        await cache.add(new Request(path, { cache: 'reload' }));
        return null;
      } catch (err) {
        return `${path} (${err && err.message})`;
      }
    }));
    const failed = results.filter(Boolean);
    if (failed.length) {
      console.error('[SW] Pre-cache failed for:', failed.join(', '));
    } else {
      console.log('[SW] Pre-cached', PRECACHE.length, 'assets');
    }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.map((name) => {
      if (name.startsWith('tiangong-room-') && name !== CACHE_NAME) {
        console.log('[SW] Deleting old cache:', name);
        return caches.delete(name);
      }
      return null;
    }));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  /* 数据文件绝不先回缓存。
     命中网络时照常写回，这样离线还有人可看 —— 新鲜度由 network-first 保证，
     而缓存里的 data_date 会让前端如实标出"非实时"。 */
  if (DATA_FILE.test(url.pathname)) {
    event.respondWith(networkFirst(request));
    return;
  }

  /* 导航请求（地址栏直接进、刷新）同样要拿最新的 HTML */
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, { fallback: './index.html' }));
    return;
  }

  event.respondWith(networkFirst(request));
});

/**
 * 先网络、失败回落缓存。
 * @param {Request} request
 * @param {{fallback?: string}} [opts]
 *   fallback —— 网络与缓存都拿不到时改用的兜底资源
 */
async function networkFirst(request, opts = {}) {
  const cache = await caches.open(CACHE_NAME);

  try {
    const response = await fetch(request);
    /* 只缓存 200 的同源基本响应；no-cors 的 opaque 响应状态码是 0，缓存它没有意义 */
    if (response && response.status === 200 && response.type === 'basic') {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;

    if (opts.fallback) {
      const fallback = await cache.match(opts.fallback);
      if (fallback) return fallback;
    }

    /* 数据文件拿不到时必须让前端知道，而不是给一个空壳假装成功 */
    if (DATA_FILE.test(new URL(request.url).pathname)) {
      return new Response('', { status: 504, statusText: 'Offline and no cached data' });
    }

    return new Response('离线，且没有缓存副本。', {
      status: 503,
      statusText: 'Offline',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' }
    });
  }
}
