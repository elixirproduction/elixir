/* coi-sw.js — Cross-Origin Isolation service worker
   Standard pattern: adds COOP + COEP + CORP headers to all same-origin responses.
   This makes crossOriginIsolated = true on every page, enabling SharedArrayBuffer. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET" && r.method !== "HEAD") return;

  const u = new URL(r.url);
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
