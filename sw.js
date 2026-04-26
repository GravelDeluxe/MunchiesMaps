const STATIC_CACHE = 'munchiesmaps-static-v2';
const GEOJSON_CACHE = 'munchiesmaps-geojson-v1';

const SCOPE_URL = new URL(self.registration.scope);
const APP_SHELL_URL = new URL('./index.html', SCOPE_URL).toString();
const APP_ROOT_URL = new URL('./', SCOPE_URL).toString();


const VENDOR_ASSETS = [
  './vendor/leaflet/leaflet.css',
  './vendor/leaflet/leaflet.js',
  './vendor/leaflet/images/layers.png',
  './vendor/leaflet/images/layers-2x.png',
  './vendor/leaflet/images/marker-icon.png',
  './vendor/leaflet/images/marker-icon-2x.png',
  './vendor/leaflet/images/marker-shadow.png',
  './vendor/leaflet.markercluster/MarkerCluster.css',
  './vendor/leaflet.markercluster/MarkerCluster.Default.css',
  './vendor/leaflet.markercluster/leaflet.markercluster.js',
  './vendor/opening_hours/opening_hours.min.js',
  './vendor/fontawesome/css/all.min.css',
  './vendor/fontawesome/webfonts/.gitkeep'
];

const EXTERNAL_VENDOR_URLS = [
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css',
  'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css',
  'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js',
  'https://cdn.jsdelivr.net/npm/opening_hours@3.6.0/opening_hours.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css'
];

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
  './resources/icons/vending_snacks.svg',
  ...VENDOR_ASSETS
];

function isCacheableResponse(response, allowOpaque = false) {
  if (!response) return false;
  if (response.ok) return true;
  return allowOpaque && response.type === 'opaque';
}

function isStaticAssetRequest(requestUrl) {
  if (requestUrl.origin !== self.location.origin) return false;
  const pathname = requestUrl.pathname;
  return /\.(?:css|js|mjs|json|webmanifest|png|jpg|jpeg|svg|gif|webp|ico|woff2?|ttf)$/i.test(pathname);
}


function isExternalVendorRequest(requestUrl) {
  return EXTERNAL_VENDOR_URLS.includes(requestUrl.toString());
}

function isExternalMapTileRequest(requestUrl) {
  const host = requestUrl.hostname;
  return /(?:tile|tiles|basemaps?)\./i.test(host) || /(?:\/tiles?\/|\/tile\/)/i.test(requestUrl.pathname);
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
    if (isCacheableResponse(response, isExternalVendorRequest(new URL(request.url)))) {
      await cache.put(request, response);
    }
  } catch (error) {
    // Optional shell assets may not exist in every deployment.
  }
}

self.addEventListener('install', (event) => {
  console.log('[sw] install start');
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await Promise.all(APP_SHELL_CANDIDATES.map((asset) => safePrecache(cache, asset)));
    await Promise.all(EXTERNAL_VENDOR_URLS.map((asset) => safePrecache(cache, asset)));
    console.log('[sw] install done');
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  console.log('[sw] activate');
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
  console.log('[sw] navigation fetch intercepted', event.request.url);
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
      console.log('[sw] offline app shell fallback used');
      return cachedShell;
    }

    console.warn('[sw] app shell missing');
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
  if (isCacheableResponse(networkResponse, isExternalVendorRequest(new URL(event.request.url)))) {
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

  if (isExternalMapTileRequest(requestUrl)) {
    return;
  }

  if (isExternalVendorRequest(requestUrl) || isStaticAssetRequest(requestUrl)) {
    event.respondWith(handleStaticAssetRequest(event));
  }
});
