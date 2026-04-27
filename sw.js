const STATIC_CACHE = 'munchiesmaps-static-v6';
const GEOJSON_CACHE = 'munchiesmaps-geojson-v2';
const OFFLINE_TILE_CACHE_NAME = 'munchiesmaps-offline-tiles-v1';

const SCOPE_URL = new URL(self.registration.scope);
const APP_SHELL_URL = new URL('./index.html', SCOPE_URL).toString();
const APP_ROOT_URL = new URL('./', SCOPE_URL).toString();
const GEOJSON_BASE_PATH = new URL('./resources/geojson/', SCOPE_URL).pathname;

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
  './vendor/fontawesome/webfonts/fa-solid-900.woff2',
  './vendor/fontawesome/webfonts/fa-regular-400.woff2',
  './vendor/fontawesome/webfonts/fa-brands-400.woff2'
];

const APP_SHELL_CANDIDATES = [
  './',
  './index.html',
  './js/offline-route-store.js',
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

function isGeoJsonRequest(requestUrl) {
  if (requestUrl.origin !== self.location.origin) return false;
  const scopePath = SCOPE_URL.pathname;
  return requestUrl.pathname.startsWith(GEOJSON_BASE_PATH) || requestUrl.pathname.startsWith(`${scopePath}resources/geojson/`);
}

function toNormalizedGeoJsonRequest(inputRequest) {
  const url = new URL(inputRequest.url);
  return new Request(`${url.origin}${url.pathname}`);
}

function createOfflineGeoJsonFallback(requestUrl) {
  const isManifest = requestUrl.pathname.endsWith('/manifest.json');
  if (isManifest) {
    console.warn('[sw] manifest.json unavailable offline:', requestUrl.toString());
    return new Response(JSON.stringify({ regions: [], bundeslaender: [], categories: [] }), {
      status: 503,
      statusText: 'Service Unavailable',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store'
      }
    });
  }

  console.warn('[sw] GeoJSON unavailable offline:', requestUrl.toString());
  return new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), {
    status: 503,
    statusText: 'Service Unavailable',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store'
    }
  });
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
  console.log('[sw] install start');
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await Promise.all(APP_SHELL_CANDIDATES.map((asset) => safePrecache(cache, asset)));
    console.log('[sw] install done');
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  console.log('[sw] activate');
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    const KEEP_CACHES = new Set([
      STATIC_CACHE,
      GEOJSON_CACHE,
      OFFLINE_TILE_CACHE_NAME
    ]);
    await Promise.all(
      cacheNames
        .filter((name) => !KEEP_CACHES.has(name))
        .map((name) => caches.delete(name))
    );

    if (self.registration.navigationPreload) {
      await self.registration.navigationPreload.disable();
    }

    await self.clients.claim();
  })());
});

async function handleNavigationRequest(event) {
  console.log('[sw] navigation intercepted', event.request.url);
  const staticCache = await caches.open(STATIC_CACHE);

  try {
    const networkResponse = await fetch(event.request);
    if (isCacheableResponse(networkResponse)) {
      await staticCache.put(APP_SHELL_URL, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    console.warn('[sw] navigation network failed, using cache', err);

    const cachedShell =
      (await staticCache.match(APP_SHELL_URL)) ||
      (await staticCache.match(APP_ROOT_URL)) ||
      (await caches.match(APP_SHELL_URL)) ||
      (await caches.match(APP_ROOT_URL));

    if (cachedShell) {
      console.log('[sw] offline app shell fallback used');
      return cachedShell;
    }

    return new Response(
      '<!doctype html><title>Munchies Maps offline</title><h1>Munchies Maps offline shell missing</h1><p>Please open the app once while online.</p>',
      {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
      }
    );
  }
}

async function matchGeoJsonFromCache(cache, request, normalizedRequest) {
  const byRequest = await cache.match(request);
  if (byRequest) return byRequest;

  const byNormalized = await cache.match(normalizedRequest);
  if (byNormalized) return byNormalized;

  const keys = await cache.keys();
  const path = new URL(request.url).pathname;
  const fallbackMatch = keys.find((key) => {
    try {
      return new URL(key.url).pathname === path;
    } catch (_) {
      return false;
    }
  });
  return fallbackMatch ? cache.match(fallbackMatch) : undefined;
}

async function handleGeoJsonRequest(event) {
  const cache = await caches.open(GEOJSON_CACHE);
  const normalizedRequest = toNormalizedGeoJsonRequest(event.request);
  const requestUrl = new URL(event.request.url);

  try {
    const networkResponse = await fetch(event.request);
    if (isCacheableResponse(networkResponse)) {
      await cache.put(event.request, networkResponse.clone());
      await cache.put(normalizedRequest, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cached = await matchGeoJsonFromCache(cache, event.request, normalizedRequest);
    if (cached) return cached;

    return createOfflineGeoJsonFallback(requestUrl);
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
