(function bootstrapLeafletMarkerCluster() {
  if (window.L && window.L.MarkerClusterGroup) return;
  var xhr = new XMLHttpRequest();
  xhr.open('GET', 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js', false);
  try {
    xhr.send(null);
    if (xhr.status >= 200 && xhr.status < 400 && xhr.responseText) {
      (0, eval)(xhr.responseText);
    }
  } catch (_) {}
})();
