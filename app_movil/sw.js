// Service worker de la app: guarda los archivos de la app (no los datos) y muestra las notificaciones push.
// Las respuestas de la API nunca se guardan, así los datos de un usuario no quedan en el teléfono.
const CACHE = 'adapt-academy-v4';
const ARCHIVOS = ['./', './index.html', './config.js', './support.js', './image-slot.js', './manifest.webmanifest', './icon-192.png', './icon-512.png', './assets/adapt-logo.png', './assets/adapt-mark.png'];

self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.includes('/api/')) return;
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request).then(m => m || caches.match('./index.html'))));
});

// Notificación que llega desde el servidor (material nuevo, notas, foro, recordatorios)
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(Promise.all([
    self.registration.showNotification(d.title || 'Adapt Academy', {
      body: d.body || '',
      icon: 'icon-192.png',
      badge: 'icon-192.png',
      tag: d.tag || undefined,
      data: { url: d.url || './' }
    }),
    // Si la app está abierta, que actualice la campanita sin recargar
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(vs => vs.forEach(v => v.postMessage({ tipo: 'aviso' })))
  ]));
});

// Al tocar la notificación se abre (o se trae al frente) la app
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const destino = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ventanas => {
    const abierta = ventanas.find(v => v.url.startsWith(self.registration.scope));
    return abierta ? abierta.focus() : self.clients.openWindow(destino);
  }));
});
