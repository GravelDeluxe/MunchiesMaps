# Fetch Overpass Data

Dieses Verzeichnis enthält das Python-Skript zur Abfrage der Overpass API und zur Ablage der Ergebnisse als GeoJSON unterhalb von `resources/`.

## Installation

```bash
pip install -r requirements.txt
```

## Ausführung

```bash
python fetch_overpass.py
```

Die Konfiguration der Bundesländer, Kategorien sowie des Endpunkts erfolgt über `config.yml`.
