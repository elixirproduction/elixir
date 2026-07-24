// COI Service Worker - adds Cross-Origin Isolation headers for SharedArrayBuffer support
// Skips proxy paths (/reactive/, /scramjet/) so the proxy continues to work

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    const path = url.pathname.toLowerCase();

    if (path.startsWith('/reactive/') || path.startsWith('/scramjet/')) {
        return;
    }

    if (url.origin !== self.location.origin) {
        return;
    }

    event.respondWith((async () => {
        const response = await fetch(event.request);
        const ct = response.headers.get('content-type') || '';

        if (!ct.includes('text/html') && !ct.includes('javascript')) {
            return response;
        }

        const headers = new Headers(response.headers);
        headers.set('Cross-Origin-Opener-Policy', 'same-origin');
        headers.set('Cross-Origin-Embedder-Policy', 'credentialless');
        return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers
        });
    })());
});
