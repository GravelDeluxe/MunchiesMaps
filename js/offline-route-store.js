(function (global) {
  const DB_NAME = 'munchiesmaps-offline';
  const DB_VERSION = 2;
  const STORE_NAME = 'routes';
  const LEGACY_KEY = 'munchiesmaps.savedGpxRoute';
  const OFFLINE_RESET_MESSAGE = 'Offline storage was reset. Please save the route again.';

  let dbPromise = null;
  let hasNotifiedReset = false;

  function hasIndexedDb() {
    return typeof indexedDB !== 'undefined';
  }

  function notifyOfflineReset() {
    if (hasNotifiedReset) return;
    hasNotifiedReset = true;
    console.warn(`[offline-store] ${OFFLINE_RESET_MESSAGE}`);
    if (typeof global.showMapToast === 'function') {
      global.showMapToast(OFFLINE_RESET_MESSAGE);
    }
  }

  function deleteOfflineDb() {
    if (!hasIndexedDb()) return Promise.resolve(false);
    return new Promise((resolve) => {
      const req = indexedDB.deleteDatabase(DB_NAME);
      req.onsuccess = () => resolve(true);
      req.onerror = () => resolve(false);
      req.onblocked = () => {
        console.warn('[offline-store] DB deletion blocked');
        resolve(false);
      };
    });
  }

  async function repairOfflineDb() {
    console.warn('[offline-store] Missing routes store. Resetting offline DB.');
    const deleted = await deleteOfflineDb();
    if (!deleted) {
      notifyOfflineReset();
    }
    return deleted;
  }

  async function ensureRoutesStore(db) {
    if (!db) return false;
    if (db.objectStoreNames.contains(STORE_NAME)) return true;
    db.close();
    dbPromise = null;
    await repairOfflineDb();
    notifyOfflineReset();
    return false;
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
      req.onsuccess = () => {
        const db = req.result;
        if (db.objectStoreNames.contains(STORE_NAME)) {
          resolve(db);
          return;
        }
        db.close();
        dbPromise = null;
        repairOfflineDb()
          .then(() => openDb())
          .then(resolve)
          .catch(reject);
      };
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
    if (!db || !(await ensureRoutesStore(db))) {
      const map = readFallbackMap();
      map[pkg.id] = pkg;
      return writeFallbackMap(map);
    }
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(pkg);
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error || new Error('saveOfflineRoute failed'));
      });
    } catch (err) {
      console.warn('[offline-store] saveOfflineRoute failed, using fallback.', err);
      notifyOfflineReset();
      const map = readFallbackMap();
      map[pkg.id] = pkg;
      return writeFallbackMap(map);
    }
  }

  async function loadOfflineRoute(id) {
    if (!id) return null;
    const db = await openDb();
    if (!db || !(await ensureRoutesStore(db))) {
      const map = readFallbackMap();
      return map[id] || null;
    }
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).get(id);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error || new Error('loadOfflineRoute failed'));
      });
    } catch (err) {
      console.warn('[offline-store] loadOfflineRoute failed, using fallback.', err);
      notifyOfflineReset();
      const map = readFallbackMap();
      return map[id] || null;
    }
  }

  async function deleteOfflineRoute(id) {
    if (!id) return false;
    const db = await openDb();
    if (!db || !(await ensureRoutesStore(db))) {
      const map = readFallbackMap();
      if (!(id in map)) return false;
      delete map[id];
      return writeFallbackMap(map);
    }
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).delete(id);
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error || new Error('deleteOfflineRoute failed'));
      });
    } catch (err) {
      console.warn('[offline-store] deleteOfflineRoute failed, using fallback.', err);
      notifyOfflineReset();
      const map = readFallbackMap();
      if (!(id in map)) return false;
      delete map[id];
      return writeFallbackMap(map);
    }
  }

  async function listOfflineRoutes() {
    const db = await openDb();
    if (!db || !(await ensureRoutesStore(db))) {
      const map = readFallbackMap();
      return Object.values(map || {}).sort((a, b) => (b?.createdAt || 0) - (a?.createdAt || 0));
    }
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).getAll();
        req.onsuccess = () => {
          const rows = Array.isArray(req.result) ? req.result : [];
          rows.sort((a, b) => (b?.createdAt || 0) - (a?.createdAt || 0));
          resolve(rows);
        };
        req.onerror = () => reject(req.error || new Error('listOfflineRoutes failed'));
      });
    } catch (err) {
      console.warn('[offline-store] listOfflineRoutes failed, returning empty list.', err);
      notifyOfflineReset();
      return [];
    }
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
