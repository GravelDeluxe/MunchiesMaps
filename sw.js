const APP_SHELL_CACHE = 'munchiesmaps-shell-v1';
const RUNTIME_CACHE = 'munchiesmaps-runtime-v1';
const TILE_CACHE = 'munchiesmaps-tiles-v1';
const MAX_TILE_ENTRIES = 400;

const APP_SHELL_URLS = [
  './',
  './index.html',
  './resources/geojson/manifest.json',
  './resources/icons/default.svg',
  './resources/icons/supermarkets.svg',
  './resources/icons/kiosks.svg',
  './resources/icons/vending_snacks.svg',
  './resources/icons/shelters.svg',
  './resources/icons/bakeries.svg',
  './resources/icons/cafes.svg',
  './resources/icons/burger_king.svg',
  './resources/icons/mcdonalds.svg',
  './resources/icons/toilets_public.svg',
  './resources/icons/drinking_water.svg',
  './resources/icons/fuel.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(APP_SHELL_CACHE);
    await cache.addAll(APP_SHELL_URLS);
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter((key) => ![APP_SHELL_CACHE, RUNTIME_CACHE, TILE_CACHE].includes(key))
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

function isTileRequest(url) {
  return url.hostname.includes('tile.openstreetmap.org') || url.hostname.includes('basemaps.cartocdn.com');
}

async function trimTileCache() {
  const cache = await caches.open(TILE_CACHE);
  const keys = await cache.keys();
  if (keys.length <= MAX_TILE_ENTRIES) return;
  const overflow = keys.length - MAX_TILE_ENTRIES;
  await Promise.all(keys.slice(0, overflow).map((entry) => cache.delete(entry)));
}

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (request.mode === 'navigate') {
      const shell = await caches.match('./index.html');
      if (shell) return shell;
    }
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) {
    cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  if (isTileRequest(url)) {
    event.respondWith((async () => {
      const response = await cacheFirst(event.request, TILE_CACHE);
      trimTileCache().catch(() => {});
      return response;
    })());
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(event.request, RUNTIME_CACHE));
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request, RUNTIME_CACHE));
  }
});
