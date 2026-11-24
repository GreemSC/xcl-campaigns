// Pages are always asked from the server. GitHub Pages lets browsers keep a page for 10 minutes without asking
// (Cache-Control: max-age=600), so the site menu showed old copies of the board. Asking costs little: the server
// answers "not modified" when nothing changed. The copy kept here is only used when the network is down.
var CACHE = 'xc-pages-v1';
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (e) {
  var r = e.request;
  if (r.method !== 'GET' || r.mode !== 'navigate') return;      // pages only; style.css is versioned, JSON uses no-store
  e.respondWith(fetch(r.url, {cache: 'no-cache', credentials: 'same-origin'}).then(function (res) {
    if (res.ok) { var copy = res.clone(); caches.open(CACHE).then(function (c) { return c.put(r.url, copy); }); }
    return res;
  }).catch(function () {
    return caches.match(r.url).then(function (m) { return m || Response.error(); });
  }));
});
