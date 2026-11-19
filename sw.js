const C = "aj-v1", FILES = ["./", "index.html", "config.js", "manifest.json"];
self.addEventListener("install", e => e.waitUntil(caches.open(C).then(c => c.addAll(FILES))));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (u.pathname.includes("/data/")) { // Daten: erst Netz, sonst Cache
    e.respondWith(fetch(e.request).then(r => { const x = r.clone(); caches.open(C).then(c => c.put(e.request, x)); return r; }).catch(() => caches.match(e.request)));
  } else e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
self.addEventListener("push", e => {
  const d = e.data ? e.data.json() : {title: "Angebotsjäger", body: ""};
  e.waitUntil(self.registration.showNotification(d.title, {body: d.body, icon: "icon-192.png"}));
});
self.addEventListener("notificationclick", e => { e.notification.close(); e.waitUntil(clients.openWindow("./")); });
