(function (global) {
  const DB_NAME = 'munchiesmaps-offline';
  const DB_VERSION = 1;
  const STORE_NAME = 'routes';
  const LEGACY_KEY = 'munchiesmaps.savedGpxRoute';

  let dbPromise = null;

  function hasIndexedDb() {
    return typeof indexedDB !== 'undefined';
  }

  function openDb() {
    if (!hasIndexedDb()) return Promise.resolve(null);
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error('IndexedDB open failed'));
    }).catch((err) => {
      console.warn('[offline-store] IndexedDB unavailable, using localStorage fallback.', err);
      return null;
    });
    return dbPromise;
  }

  function readFallbackMap() {
    try {
      const raw = localStorage.getItem('munchiesmaps.offlineRoutes');
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }

  function writeFallbackMap(map) {
    try {
      localStorage.setItem('munchiesmaps.offlineRoutes', JSON.stringify(map || {}));
      return true;
    } catch {
      return false;
    }
  }

  async function saveOfflineRoute(pkg) {
    if (!pkg || !pkg.id) throw new Error('Offline route package requires id');
    const db = await openDb();
    if (!db) {
      const map = readFallbackMap();
      map[pkg.id] = pkg;
      return writeFallbackMap(map);
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      tx.objectStore(STORE_NAME).put(pkg);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error || new Error('saveOfflineRoute failed'));
    });
  }

  async function loadOfflineRoute(id) {
    if (!id) return null;
    const db = await openDb();
    if (!db) {
      const map = readFallbackMap();
      return map[id] || null;
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).get(id);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error || new Error('loadOfflineRoute failed'));
    });
  }

  async function deleteOfflineRoute(id) {
    if (!id) return false;
    const db = await openDb();
    if (!db) {
      const map = readFallbackMap();
      if (!(id in map)) return false;
      delete map[id];
      return writeFallbackMap(map);
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      tx.objectStore(STORE_NAME).delete(id);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error || new Error('deleteOfflineRoute failed'));
    });
  }

  async function listOfflineRoutes() {
    const db = await openDb();
    if (!db) {
      const map = readFallbackMap();
      return Object.values(map || {}).sort((a, b) => (b?.createdAt || 0) - (a?.createdAt || 0));
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).getAll();
      req.onsuccess = () => {
        const rows = Array.isArray(req.result) ? req.result : [];
        rows.sort((a, b) => (b?.createdAt || 0) - (a?.createdAt || 0));
        resolve(rows);
      };
      req.onerror = () => reject(req.error || new Error('listOfflineRoutes failed'));
    });
  }

  async function migrateLegacySavedRoute(buildPackageFromRawGpx) {
    let rawLegacy = null;
    try {
      rawLegacy = localStorage.getItem(LEGACY_KEY);
    } catch {
      return null;
    }
    if (!rawLegacy) return null;
    let parsed = null;
    try {
      parsed = JSON.parse(rawLegacy);
    } catch {
      localStorage.removeItem(LEGACY_KEY);
      return null;
    }
    const rawText = typeof parsed?.rawText === 'string' ? parsed.rawText.trim() : '';
    if (!rawText || typeof buildPackageFromRawGpx !== 'function') return null;
    try {
      const pkg = await buildPackageFromRawGpx(rawText);
      if (pkg?.id) {
        await saveOfflineRoute(pkg);
      }
      localStorage.removeItem(LEGACY_KEY);
      return pkg || null;
    } catch (err) {
      console.warn('[offline-store] Legacy migration failed', err);
      return null;
    }
  }

  global.offlineRouteStore = {
    saveOfflineRoute,
    loadOfflineRoute,
    deleteOfflineRoute,
    listOfflineRoutes,
    migrateLegacySavedRoute
  };
})(window);
