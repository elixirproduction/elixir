# elixir

Fully static games portal with a built-in proxy. No backend, no database, no user accounts — everything is stored in your browser's local storage.

## Quick Start

```bash
serve.bat                          # Windows — double-click to start on http://localhost:80
# or
python -m http.server 80           # cross-platform (requires Python)
```

`serve.bat` uses Python's built-in HTTP server — no install needed beyond Python itself.

## Deploy

**Netlify**: Connect the repo, leave the build command empty, set publish directory to root. Headers (cross-origin isolation + per-asset caching) are in `netlify.toml`.

**Any static host / VPS**: Upload the entire directory as-is and serve it with `python -m http.server`, nginx, Caddy, or any static file server. No build step needed. If using another web server, replicate these headers:
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Embedder-Policy: credentialless`
- `Cross-Origin-Resource-Policy: cross-origin`

These three are required for Portal (and anything else using `SharedArrayBuffer`/WASM threads) to work — without them `crossOriginIsolated` stays `false` and those games fail to load.

## Cross-Origin Isolation (COI)

For local development, a **COI service worker** (`coi-sw.js`) is registered automatically on every page load. It injects the required COOP/COEP headers into same-origin responses so `crossOriginIsolated` is `true` even without a server that sets those headers.

- `coi-sw.js` — service worker that adds COEP/COOP/CORP headers locally
- `netlify.toml` — handles the same headers for production deploys on Netlify

## Performance

The games/apps grid uses event delegation (one listener instead of one per tile), `content-visibility: auto` on tiles, and infinite scroll (`IntersectionObserver`) instead of rendering the entire game list up front — the grid starts with 120 items and loads more automatically as you scroll.

## Adding Games

Edit `data/games.js` or `data/apps.js` to add entries:

```json
{ "name": "My Game", "img": "", "url": "n/mygame.html" }
```

## Project Structure

```
├── index.html         # Main portal (games, apps, proxy, settings)
├── play.html          # Game player page
├── coi-sw.js          # COI service worker (cross-origin isolation for SharedArrayBuffer)
├── data/games.js      # Game definitions (static, committed)
├── data/apps.js       # App definitions (static, committed)
├── netlify.toml       # Netlify deployment config (headers + caching)
├── serve.bat          # Windows launcher (python -m http.server on port 80)
├── assets/            # Cloak icons
├── builtinads/        # Sidebar ad images
├── reactive/          # Scramjet proxy bundle
├── scramjet/          # Proxy worker bundle
├── games/             # Game content (Portal, etc.)
├── g/                 # Game content (git LFS)
└── n/                 # Game content (git LFS)
```

## LFS

```bash
git lfs install
git lfs pull
```

Game content (`n/`, `g/`, `games/`) is tracked via git LFS.
