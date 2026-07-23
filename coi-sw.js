/* coi-sw.js — Cross-Origin Isolation service worker
   Adds COOP + COEP + CORP headers to same-origin responses for SharedArrayBuffer.
   Skips /reactive/ and /scramjet/ paths so the proxy SW can handle those
   without COEP headers breaking SharedWorker connections. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(Promise.resolve()));

self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET" && r.method !== "HEAD") return;

  const u = new URL(r.url);

  // Skip external requests
  if (u.origin !== self.location.origin) return;

  // Skip proxy paths — COEP headers break bare-mux SharedWorker connections
  if (u.pathname.startsWith("/reactive/")) return;
  if (u.pathname.includes("/scramjet/")) return;

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
