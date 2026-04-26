/*
 * Leaflet vendor placeholder.
 *
 * NOTE: This file intentionally avoids any network/bootstrap logic (XHR/eval/fetch/importScripts)
 * so the app stays offline-safe and non-blocking.
 *
 * To fully enable maps, replace this file with the official Leaflet 1.9.4 dist build.
 */
(function initLeafletPlaceholder(global) {
  if (global.L) return;
  global.L = {
    __placeholder: true,
    version: '1.9.4-placeholder'
  };
  if (global.console && typeof global.console.warn === 'function') {
    global.console.warn('[Leaflet] Placeholder loaded: vendor/leaflet/leaflet.js must be replaced with official Leaflet 1.9.4 dist file.');
  }
})(typeof window !== 'undefined' ? window : globalThis);
