
const swPath = self.location.pathname;
const basePath = swPath.substring(0, swPath.lastIndexOf('/') + 1);
self.basePath = self.basePath || basePath;

self.$scramjet = {
    files: {
        wasm: "https://cdn.jsdelivr.net/gh/Destroyed12121/Staticsj@main/JS/scramjet.wasm.wasm",
        sync: "https://cdn.jsdelivr.net/gh/Destroyed12121/Staticsj@main/JS/scramjet.sync.js",
    }
};

importScripts("https://cdn.jsdelivr.net/gh/Destroyed12121/Staticsj@main/JS/scramjet.all.js");
importScripts("https://cdn.jsdelivr.net/npm/@mercuryworkshop/bare-mux/dist/index.js");

const { ScramjetServiceWorker } = $scramjetLoadWorker();
const scramjet = new ScramjetServiceWorker({
    prefix: basePath + "scramjet/"
});

self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
    event.respondWith((async () => {
        await scramjet.loadConfig();
        let response;
        if (scramjet.route(event)) {
            response = await scramjet.fetch(event);
        } else {
            response = await fetch(event.request);
        }
        const ct = response.headers.get('content-type') || '';
        const h = new Headers(response.headers);
        if (event.request.mode === 'navigate' && ct.includes('text/html')) {
            // Add COEP/COOP/CORP to HTML navigations for SharedArrayBuffer support
            h.set('Cross-Origin-Opener-Policy', 'same-origin');
            h.set('Cross-Origin-Embedder-Policy', 'credentialless');
            h.set('Cross-Origin-Resource-Policy', 'cross-origin');
        } else {
            // Add CORP to all other responses so COEP doesn't block them
            h.set('Cross-Origin-Resource-Policy', 'cross-origin');
        }
        return new Response(response.body, {
            status: response.status,
            statusText: response.statusText,
            headers: h
        });
    })());
});

let wispConfig = {};
let resolveConfigReady;
const configReadyPromise = new Promise(resolve => resolveConfigReady = resolve);

self.addEventListener("message", ({ data }) => {
    if (data.type === "config" && data.wispurl) {
        wispConfig.wispurl = data.wispurl;
        console.log("SW: Received config", wispConfig);
        if (resolveConfigReady) {
            resolveConfigReady();
            resolveConfigReady = null;
        }
    }
});

// Fallback if config is never received (prevents 500 error)
setTimeout(() => {
    if (!wispConfig.wispurl && resolveConfigReady) {
        console.warn("SW: Config timeout, using anura's Wisp");
        wispConfig.wispurl = "wss://wisp.mercurywork.shop/wisp/";
        resolveConfigReady();
        resolveConfigReady = null;
    }
}, 1000);

scramjet.addEventListener("request", async (e) => {
    e.response = (async () => {
        if (!scramjet.client) {
            await configReadyPromise;
            if (!wispConfig.wispurl) return new Response("WISP URL missing", { status: 500 });

            const connection = new BareMux.BareMuxConnection(basePath + "bareworker.js");
            await connection.setTransport("https://cdn.jsdelivr.net/npm/@mercuryworkshop/epoxy-transport@2.1.28/dist/index.mjs", [{ wisp: wispConfig.wispurl }]);
            scramjet.client = connection;
        }
        const MAX_RETRIES = 2;
        let lastErr;

        for (let i = 0; i <= MAX_RETRIES; i++) {
            try {
                return await scramjet.client.fetch(e.url, {
                    method: e.method,
                    body: e.body,
                    headers: e.requestHeaders,
                    credentials: "include",
                    mode: e.mode === "cors" ? e.mode : "same-origin",
                    cache: e.cache,
                    redirect: "manual",
                    duplex: "half",
                });
            } catch (err) {
                lastErr = err;
                const errMsg = err.message.toLowerCase();
                const isRetryable = errMsg.includes("connect") ||
                    errMsg.includes("eof") ||
                    errMsg.includes("handshake") ||
                    errMsg.includes("reset");

                if (!isRetryable || i === MAX_RETRIES || e.method !== 'GET') break;

                console.warn(`Scramjet retry ${i + 1}/${MAX_RETRIES} for ${e.url} due to: ${err.message}`);
                await new Promise(r => setTimeout(r, 500 * (i + 1)));
            }
        }

        console.error("Scramjet Final Fetch Error:", lastErr);
        return new Response("Scramjet Fetch Error: " + lastErr.message, { status: 502 });
    })();
});