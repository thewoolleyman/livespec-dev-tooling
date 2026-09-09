// Minimal service worker — exists only to satisfy Chrome's PWA
// installability gate, which requires a registered SW with a fetch
// handler. We deliberately do NO caching here: Microsoft's serve-web
// streams large JS bundles and unique per-session secrets, and any
// cache we add would either bloat client storage or serve stale
// workbench code after a `code` package upgrade.
//
// If you change this file, bump the comment so browsers refetch it
// (Cache-Control: no-cache covers most cases, but the byte-identical
// check is the real cache key).
self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => { /* network passthrough */ });
