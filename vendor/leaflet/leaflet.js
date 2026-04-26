(function bootstrapLeaflet() {
  if (window.L) return;
  var xhr = new XMLHttpRequest();
  xhr.open('GET', 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', false);
  try {
    xhr.send(null);
    if (xhr.status >= 200 && xhr.status < 400 && xhr.responseText) {
      (0, eval)(xhr.responseText);
    }
  } catch (_) {}
})();
