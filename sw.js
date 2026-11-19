// Offline-Cache (erst Netz, dann Cache) + Web-Push
const CACHE = 'angebotsjaeger-v3';
const FILES = ['./', 'index.html', 'logic.js', 'vocab.js', 'config.js', 'manifest.webmanifest', 'icon.svg', 'icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request))
  );
});
self.addEventListener('push', e => {
  let d = { title: 'Angebotsjäger', body: '' };
  try { if (e.data) d = e.data.json(); } catch (err) {}
  e.waitUntil(self.registration.showNotification(d.title, { body: d.body, icon: 'icon-192.png', badge: 'icon-192.png', tag: 'bestpreis' }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({ type: 'window' }).then(w => w.length ? w[0].focus() : clients.openWindow('./')));
});
