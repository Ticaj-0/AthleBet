// Minimal service worker — requis pour l'installabilité PWA
const CACHE = 'athle-bet-v1';

self.addEventListener('install', e => {
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(clients.claim());
});

// Network-first : toujours récupérer le contenu frais depuis Streamlit
self.addEventListener('fetch', e => {
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
    );
});
