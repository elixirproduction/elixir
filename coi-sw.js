/* coi-sw.js — Cross-Origin Isolation service worker
   Adds COOP + COEP + CORP headers to same-origin responses for SharedArrayBuffer.
   Registered from index.html/play.html. Does NOT use clients.claim() to avoid
   stealing control from the proxy SW at /reactive/. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(Promise.resolve()));

self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET" && r.method !== "HEAD") return;

  const u = new URL(r.url);

  // Only intercept same-origin requests
  if (u.origin !== self.location.origin) return;

  e.respondWith(
    fetch(r).then((res) => {
      if (res.status === 0 || res.type === "opaque") return res;

      const h = new Headers(res.headers);
      h.set("Cross-Origin-Opener-Policy", "same-origin");
      h.set("Cross-Origin-Embedder-Policy", "credentialless");
      h.set("Cross-Origin-Resource-Policy", "cross-origin");

      return new Response(res.body, {
        status: res.status,
        statusText: res.statusText,
        headers: h,
      });
    })
  );
});
