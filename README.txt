Testkarte – Layer Dropdown + Symbole + Nutzerposition

Enthalten:
- index.html
- layer1_points.geojson  (Layer 1 – Wasser)
- layer2_points.geojson  (Layer 2 – Automat / Dummy, leicht versetzt)

Start:
1) Entpacken
2) Im Ordner:
   python -m http.server 8000
3) Öffnen:
   http://localhost:8000/
   oder Handy: http://<DEINE-PC-IP>:8000/

Features:
- Clustering erst ab 10 Punkten (Supercluster minPoints=10)
- Layer-Auswahl über Dropdown (Layer 1 / Layer 2 / Beide)
- Eigene Symbole je Layer (Wassertropfen / Automat – jeweils im Kreis)
- Nutzerposition per Button "Standort" (GPS), inkl. Genauigkeitskreis
