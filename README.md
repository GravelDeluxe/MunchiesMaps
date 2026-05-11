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

## PWA-Icons

Die App verwendet nun eigene PWA-/Homescreen-/Favicon-Icons aus `assets/icons/` (inkl. maskable Icons für Android und Apple Touch Icon für iOS).

## SEO-Basics (manuell gepflegt)

Basis-SEO-Metadaten in `index.html` sowie `robots.txt` und `sitemap.xml` werden aktuell manuell gepflegt.
Share-URLs mit Query-Parametern sollten per Canonical-URL auf `https://nightrides.cc/munchiesmaps/` verweisen.
