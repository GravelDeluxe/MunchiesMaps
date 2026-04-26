const STATIC_CACHE = 'munchiesmaps-static-v1';
const GEOJSON_CACHE = 'munchiesmaps-geojson-v1';

const SCOPE_URL = new URL(self.registration.scope);
const APP_SHELL_URL = new URL('./index.html', SCOPE_URL).toString();
const APP_ROOT_URL = new URL('./', SCOPE_URL).toString();

const APP_SHELL_CANDIDATES = [
  './',
  './index.html',
  './manifest.webmanifest',
  './favicon.ico',
  './favicon.png',
  './apple-touch-icon.png',
  './resources/icons/default.svg',
  './resources/icons/bakeries.svg',
  './resources/icons/cafes.svg',
  './resources/icons/drinking_water.svg',
  './resources/icons/fuel.svg',
  './resources/icons/kiosks.svg',
  './resources/icons/mcdonalds.svg',
  './resources/icons/burger_king.svg',
  './resources/icons/shelters.svg',
  './resources/icons/supermarkets.svg',
  './resources/icons/toilets_public.svg',
  './resources/icons/vending_snacks.svg'
];

function isCacheableResponse(response) {
  return response && response.ok && response.type !== 'opaque';
}

function isStaticAssetRequest(requestUrl) {
  if (requestUrl.origin !== self.location.origin) return false;
  const pathname = requestUrl.pathname;
  return /\.(?:css|js|mjs|json|webmanifest|png|jpg|jpeg|svg|gif|webp|ico|woff2?|ttf)$/i.test(pathname);
}

function isGeoJsonRequest(requestUrl) {
  if (requestUrl.origin !== self.location.origin) return false;
  const scopePath = SCOPE_URL.pathname;
  const geoBasePath = new URL('./resources/geojson/', SCOPE_URL).pathname;
  return requestUrl.pathname.startsWith(geoBasePath) || requestUrl.pathname.startsWith(`${scopePath}resources/geojson/`);
}

async function safePrecache(cache, urlLike) {
  try {
    const request = new Request(new URL(urlLike, SCOPE_URL).toString(), { cache: 'reload' });
    const response = await fetch(request);
    if (isCacheableResponse(response)) {
      await cache.put(request, response);
    }
  } catch (error) {
    // Optional shell assets may not exist in every deployment.
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await Promise.all(APP_SHELL_CANDIDATES.map((asset) => safePrecache(cache, asset)));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    await Promise.all(
      cacheNames
        .filter((name) => name !== STATIC_CACHE && name !== GEOJSON_CACHE)
        .map((name) => caches.delete(name))
    );

    if (self.registration.navigationPreload) {
      await self.registration.navigationPreload.enable();
    }

    await self.clients.claim();
  })());
});

async function handleNavigationRequest(event) {
  const staticCache = await caches.open(STATIC_CACHE);

  try {
    const preload = await event.preloadResponse;
    if (preload) {
      if (isCacheableResponse(preload)) {
        await staticCache.put(APP_SHELL_URL, preload.clone());
      }
      return preload;
    }

    const networkResponse = await fetch(event.request);
    if (isCacheableResponse(networkResponse)) {
      await staticCache.put(APP_SHELL_URL, networkResponse.clone());
    }
    return networkResponse;
  } catch (_) {
    const cachedShell =
      (await staticCache.match(APP_SHELL_URL)) ||
      (await staticCache.match(APP_ROOT_URL)) ||
      (await staticCache.match(APP_SHELL_URL, { ignoreSearch: true }));

    if (cachedShell) {
      return cachedShell;
    }

    return new Response('Offline', {
      status: 503,
      statusText: 'Service Unavailable',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' }
    });
  }
}

async function handleGeoJsonRequest(event) {
  const cache = await caches.open(GEOJSON_CACHE);
  try {
    const networkResponse = await fetch(event.request);
    if (isCacheableResponse(networkResponse)) {
      await cache.put(event.request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cached = await cache.match(event.request);
    if (cached) return cached;
    throw error;
  }
}

async function handleStaticAssetRequest(event) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(event.request);
  if (cached) return cached;

  const networkResponse = await fetch(event.request);
  if (isCacheableResponse(networkResponse)) {
    await cache.put(event.request, networkResponse.clone());
  }
  return networkResponse;
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const requestUrl = new URL(event.request.url);

  if (event.request.mode === 'navigate') {
    event.respondWith(handleNavigationRequest(event));
    return;
  }

  if (isGeoJsonRequest(requestUrl)) {
    event.respondWith(handleGeoJsonRequest(event));
    return;
  }

  if (isStaticAssetRequest(requestUrl)) {
    event.respondWith(handleStaticAssetRequest(event));
  }
});
