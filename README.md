# MunchiesMaps

## Lokale Vendor-Dateien aktualisieren

```bash
npm install
npm run sync-vendor
npm run check-vendor
```

Danach den Ordner `vendor/` (inklusive erzeugter Binary-Assets aus npm-Paketen) committen.

## Alternative über GitHub Actions

1. GitHub → **Actions** → **Sync vendor assets**
2. **Run workflow** starten

Der Workflow installiert npm-Abhängigkeiten, synchronisiert echte lokale Vendor-Dateien aus `node_modules` nach `vendor/`, prüft sie und committet Änderungen automatisch.

## Wichtiger Hinweis

Keine Placeholder-Dateien, CDN-Wrapper oder synchrone XHR-Fallbacks für Vendor-Libraries verwenden.
