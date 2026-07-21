# Elixer

Game portal server.

## Quick Start

```bash
cp .env.example .env
# edit ADMIN_PASS and ADMIN_BYPASS

serve.bat
```

Open http://localhost:80

## Variables

| Variable | Description |
|---|---|
| `ADMIN_PASS` | Admin panel password |
| `ADMIN_BYPASS` | Dev bypass password |
| `PORT` | HTTP port (default 80) |

## Adding Games

All game entries are in **`games.json`** in the root directory. Add a new entry like this:

```json
{ "name": "My Game", "img": "", "iframe": "n/mygame.html", "identifier": "mygame" }
```

Then restart the server.

## LFS

```bash
git lfs install
git lfs pull
```

Game content (`n/`, `g/`) is tracked via git LFS.
