// Guarda la app (no los datos) para que abra rápido. Las respuestas de la API nunca se guardan,
// así los datos de un usuario no quedan en el teléfono después de cerrar sesión.
const CACHE = 'adapt-academy-v2';
const ARCHIVOS = ['./', './index.html', './config.js', './support.js', './image-slot.js', './manifest.webmanifest', './icon-192.png', './icon-512.png', './assets/adapt-logo.png', './assets/adapt-mark.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request).then(m => m || caches.match('./index.html'))));
});
