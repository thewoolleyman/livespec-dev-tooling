// A fetch handler is the minimum Chrome requires for the VS Code web manifest
// to offer PWA installation. It intentionally caches nothing: serve-web sends
// large bundles and per-session state that must not become stale client data.
self.addEventListener('install', (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
