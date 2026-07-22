#!/usr/bin/env python3
"""elixer server: static host + live admin state + auto games data generation."""
import os, re, json, http.server, socketserver, urllib.parse, threading, time, functools, queue, hashlib, secrets

def _bv(v):
    """coerce a value (from query string or json) to bool, ignoring None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v).lower() in ("1", "true", "on", "yes")

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = {}
ENV_PATH = os.path.join(ROOT, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            ENV[k.strip()] = v.strip()

ADMIN_PASS = ENV.get("ADMIN_PASS", "changeme")
ADMIN_BYPASS = ENV.get("ADMIN_BYPASS", "bypass")
STATE_PATH = os.path.join(ROOT, "admin.json")
DATA_DIR = os.path.join(ROOT, "data")
GAMES_JS = os.path.join(DATA_DIR, "games.js")
MORE_JS = os.path.join(DATA_DIR, "more.js")
USERS_PATH = os.path.join(ROOT, "users.json")

# ----------------------------------------------------------------------------
# runtime state (dev-only mode + announcements). Lives in admin.json so the
# server restart survives, and so the admin menu can update it live.
# ----------------------------------------------------------------------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                s = json.load(f)
            s.setdefault("motd", "")
            s["started"] = int(time.time())
            return s
        except Exception:
            pass
    return {"devOnly": False, "announcements": [], "motd": "", "started": int(time.time()), "title": "elixer", "reloadSignal": 0, "announceColor": "good", "redTheme": True, "footer": "", "dark": False}

def save_state(s):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)

STATE = load_state()
STATE_LOCK = threading.Lock()
SSE_CLIENTS = []          # queued events for Server-Sent Events
SSE_LOCK = threading.Lock()

def broadcast_state():
    """Called whenever STATE changes; wake any SSE listeners."""
    with SSE_LOCK:
        dead = []
        for q in SSE_CLIENTS:
            try:
                q.put_nowait(json.dumps(STATE))
            except Exception:
                dead.append(q)
        for q in dead:
            SSE_CLIENTS.remove(q)

def load_users():
    if os.path.exists(USERS_PATH):
        try:
            with open(USERS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "sessions": {}}

def save_users(data):
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

USERS_LOCK = threading.Lock()

def hash_password(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def make_session(username):
    with USERS_LOCK:
        data = load_users()
        token = secrets.token_hex(32)
        data["sessions"][token] = username
        save_users(data)
    return token

def get_session_user(headers):
    cookie = headers.get("Cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("elixer_session="):
            token = part.split("=", 1)[1]
            data = load_users()
            return data["sessions"].get(token)
    return None

def clear_session(token):
    with USERS_LOCK:
        data = load_users()
        data["sessions"].pop(token, None)
        save_users(data)

# ----------------------------------------------------------------------------
# games data auto-generation
# ----------------------------------------------------------------------------
# Multi-word game titles are mashed into filenames (e.g. "minutestildawn").
# We recover spaces by matching a curated dictionary of REAL words. Only
# meaningful words (>=3 chars, unambiguous) are listed so we never break an
# unknown fragment apart (e.g. "grandmaster" stays whole, not "gr and master").
# Large dictionary of REAL words + game terms used to recover spaces from
# mashed filenames. Longer / less ambiguous entries are sorted to the front so
# the matcher prefers them. Unknown fragments are never broken apart.
WORD_SPLITS = [
    # multi-word / long brand & title terms (checked first)
    "tabletennis", "tetrisgrandmaster", "tonyhawks", "underground", "doodlejump",
    "loderunner", "polished", "ducklife", "ben10", "pokemon", "eaglercraft",
    "bejeweled", "bubbletanks", "summerrider", "trollface", "badpiggies",
    "cellularity", "ragdoll", "halflife", "dementium", "prehistoric",
    "undertale", "deadninja", "magic", "bloons", "hobo", "pacman",
    # games / franchises
    "mario", "luigi", "sonic", "zelda", "yoshi", "bowser", "peach", "wario",
    "pokemon", "dbz", "tetris", "pacman", "emerald", "imperium", "crystal",
    "warriors", "kart", "bros", "battle", "fighter", "kingdom", "king",
    "knight", "mighty", "master", "grand", "flash", "version",
    # common short words (>=3 chars to avoid breaking real words)
    "adventure", "aflac", "alone", "animal", "animals", "army", "arrow",
    "attack", "bacon", "ball", "balls", "band", "bear", "beat", "beef",
    "bird", "blob", "blood", "blue", "boat", "bomb", "bone", "bones",
    "book", "boost", "boss", "box", "brain", "brave", "break", "brick",
    "bug", "bugs", "bullet", "bullets", "burglar", "burn", "cake", "caliber",
    "candy", "capatalist", "capitalist", "car", "cars", "cat", "cave",
    "challenge", "champion", "chess", "chicken", "city", "class", "club",
    "coffee", "college", "color", "colors", "combat", "contractz", "cookie",
    "cool", "core", "cowboy", "craft", "crash", "crazy", "crew", "crime",
    "crisis", "cross", "crush", "cup", "cupcakes", "dark", "dash", "date",
    "dawn", "dead", "death", "deep", "defense", "demon", "desert", "devil",
    "diamond", "dino", "dirt", "dive", "dog", "dogs", "door", "dragon",
    "dream", "drift", "drive", "driver", "dungeon", "eagle", "earth",
    "easter", "edge", "enemies", "energy", "escape", "evil", "explore",
    "factory", "fall", "fantasy", "farm", "fast", "fear", "fever", "fight",
    "fire", "fish", "flag", "forest", "fort", "free", "frenzy", "frog",
    "future", "game", "gangster", "gem", "ghost", "giant", "glass", "goal",
    "gold", "golf", "gun", "guns", "halloween", "hammer", "hand", "happy",
    "hat", "hawk", "head", "heart", "heat", "heaven", "hell", "hero",
    "heroes", "hill", "hit", "hole", "home", "honey", "horror", "house",
    "hunter", "ice", "ill", "island", "jail", "jet", "jungle", "jump",
    "kart", "kid", "king", "lab", "laser", "leaf", "legend", "life", "light",
    "line", "lion", "lock", "logic", "lost", "love", "luck", "madness",
    "maze", "mazes", "meat", "medal", "metal", "midnight", "mind", "mini",
    "mission", "monster", "moon", "morning", "magic", "mansion", "mania",
    "mario", "match", "mayhem", "maze", "night", "nights", "ninja", "nova",
    "office", "oil", "orange", "paint", "panda", "pants", "park", "party",
    "past", "path", "peace", "penguin", "pet", "pigs", "pirate", "pixel",
    "plane", "planet", "plant", "play", "player", "poison", "police",
    "pool", "portal", "power", "princess", "prison", "puzzle", "queen",
    "quest", "race", "rain", "rainbow", "ramp", "rat", "red", "rider",
    "rocket", "room", "roof", "runner", "saga", "saint", "santa", "save",
    "school", "score", "sea", "secret", "shadow", "shark", "sheep", "shoot",
    "shooter", "shop", "sky", "slash", "sleep", "snake", "snow", "soccer",
    "space", "spike", "spin", "spirit", "splash", "sport", "star", "stars",
    "station", "stick", "stone", "storm", "story", "strange", "street",
    "sun", "super", "surf", "survival", "sword", "tactic", "tail", "tale",
    "tales", "tank", "tanks", "taxi", "team", "tower", "town", "toy",
    "trap", "treasure", "tree", "troll", "truck", "tundra", "turbo", "ultra",
    "under", "valley", "vampire", "victory", "virus", "volcano", "wars",
    "war", "water", "wave", "waves", "wizard", "world", "worm", "zombie",
    "zoo",
    # numbers as words (handled separately too, but keep a few)
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "minute", "minutes", "second", "seconds", "hour", "hours", "day",
    "days", "xmas", "neo", "retro", "cyber", "hyper", "mega", "until",
    "till", "stick", "blob", "sim", "simulator", "pal", "pals", "cat",
    "cats", "dog", "dogs", "egg", "eggs", "ant", "ants", "bee", "bees",
    "brazil", "pandas", "panda", "mine", "craft", "is", "key", "age", "of",
    "cade",     "basket", "basketball", "ball", "legend", "legends", "xtreme", "block", "cityblock",
    "moto", "racer", "arcade", "capitalist", "capatalist", "tower", "defense",
    "minecraft", "classic", "legends", "79", "snow", "grave", "office",
    "different", "snowgrave", "achievement", "achievment", "unlocked",
    "absolute", "madness", "ace", "combat", "gangster", "taxi", "chillies",
    "chillie", "adark", "darkroom", "room", "date", "death", "different",
    "the", "run", "runner", "tap", "tycoon", "wala", "bee",
    "brawl", "clash", "royale", "elimination", "surviv", "fury",
    "blitz", "epic", "classic", "remix", "dx", "rpg", "td", "rhythm",
    "puzzle", "platform", "sandbox", "rogue", "roguelike", "strategy",
    "tactic", "tactics", "wars", "saga", "odyssey", "chronicle", "arena",
    "duel", "brawl", "showdown", "show", "down", "blast", "smash",
]

# sort longest-first so the shortest substrings still match after longer ones
WORD_SPLITS = sorted(set(WORD_SPLITS), key=lambda w: (-len(w), w))

def _split_words(s):
    # Keep digit runs as their own tokens so a trailing plural "s" (e.g. "90s")
    # stays separate and can be merged back later.
    s2 = re.sub(r"(?<=\d)(?=\D)|(?<=\D)(?=\d)", " ", s)
    # Greedy longest-match. At each position, if a known word starts here we
    # split it off; otherwise we glue the character into the current unknown
    # token. Unknown tokens are NEVER broken apart. This keeps real words whole.
    i, out, buf = 0, [], ""
    while i < len(s2):
        matched = None
        for w in WORD_SPLITS:
            if s2[i:i + len(w)] == w and len(w) > (len(matched) if matched else 0):
                matched = w
        if matched:
            # avoid splitting a 1-char unknown prefix off a word it actually
            # belongs to (e.g. "z" + "one" from "zone") -> keep them glued.
            # Exception: a trailing plural "s" after a number (e.g. "90 s").
            _plural_s = (buf == "s" and out and out[-1].isdigit())
            if buf and len(buf) == 1 and buf not in WORD_SPLITS and not _plural_s:
                buf += matched; i += len(matched)
            else:
                if buf:
                    out.append(buf); buf = ""
                out.append(matched)
                i += len(matched)
        else:
            if s2[i].isspace():
                if buf:
                    out.append(buf); buf = ""
                i += 1
                continue
            buf += s2[i]
            i += 1
    if buf:
        out.append(buf)
    # second pass: try to re-split any still-glued unknown tokens (handles
    # cases where two unknown fragments sit next to each other)
    merged = []
    for tok in out:
        if " " in tok or len(tok) <= 3:
            merged.append(tok); continue
        sub = _split_once(tok)
        if sub != tok:
            merged.extend(sub.split(" "))
        else:
            merged.append(tok)
    # merge a lone plural "s" that trails a number (e.g. "90 s arcade" -> "90s arcade")
    fixed = []
    for idx, tok in enumerate(merged):
        if tok == "s" and idx > 0 and merged[idx - 1].isdigit():
            fixed[-1] += "s"
        else:
            fixed.append(tok)
    return " ".join(fixed)

def _split_once(tok):
    # attempt a single clean split of a glued token into two known words
    if tok in WORD_SPLITS:
        return tok
    for w in WORD_SPLITS:
        if len(w) >= len(tok) - 1:
            continue
        if tok.startswith(w):
            rest = tok[len(w):]
            if rest in WORD_SPLITS:
                return w + " " + rest
    return tok

def title_from(name):
    s = name[:-5] if name.lower().endswith(".html") else name
    s = re.sub(r"^cl", "", s)
    s = re.sub(r"\(\d+\)", "", s)
    s = s.replace("-", " ").replace("_", " ")
    s = s.replace("&", " and ")
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"(?<=[a-zA-Z])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[a-zA-Z])", " ", s)
    s = _split_words(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([0-9])", r" \1", s)
    return s.lower()

def slug(name):
    s = name[:-5] if name.lower().endswith(".html") else name
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s

def parse_gamesdata(path):
    """Parse an Osmium-style gamesData.js into a list of dicts with
    name / iframe / identifier / img. Strips the leading comment block and
    the `let games = [` / trailing `];` so we can json.load the array body."""
    if not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8", errors="ignore").read()
    # find the array assigned to `let games = [ ... ]` or `window.games = [ ... ]`;
    # avoid the '[' that may appear inside the leading comment block.
    m = re.search(r"(?:let|window\.)\s*\w+\s*=\s*\[", txt)
    if not m:
        return []
    start = txt.find("[", m.end() - 1)
    end = txt.rfind("]")
    if start < 0 or end < 0 or end < start:
        return []
    body = txt[start:end + 1]
    # convert unquoted JS keys to valid JSON (e.g. { name: "foo" } -> { "name": "foo" })
    body = re.sub(r"(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1 "\2" :', body)
    # tolerate trailing commas (Osmium files aren't strict JSON)
    body = re.sub(r",\s*([}\]])", r"\1", body)
    try:
        arr = json.loads(body)
    except Exception:
        return []
    out = []
    for g in arr:
        if not isinstance(g, dict):
            continue
        ident = g.get("identifier")
        if not ident:
            continue
        name = g.get("name") or ident
        # fix the few clearly-wrong names Osmium ships with
        if name in NAME_FIXES:
            name = NAME_FIXES[name]
        out.append({
            "name": name,
            "img": g.get("img", "") or "",
            "iframe": g.get("iframe", "") or "",
            "identifier": ident,
        })
    return out

# Corrections for names Osmium stores misspelled / without spaces.
NAME_FIXES = {
    "ChickenCS": "Chicken CS",
    "Riddleschool": "Riddle School",
    "SuperSmashFlash": "Super Smash Flash",
    "SuperSmashFlash v0.8": "Super Smash Flash v0.8",
    "SuperSmashFlash v0.9": "Super Smash Flash v0.9",
    "SuperSmashFlash v1.0": "Super Smash Flash v1.0",
    "SuperSmashFlash v1.1": "Super Smash Flash v1.1",
    "SuperSmashFlash v1.2": "Super Smash Flash v1.2",
    "SuperSmashFlash 2 Demo v0.9": "Super Smash Flash 2 Demo v0.9",
    "SuperSmashFlash 2 Demo v0.10": "Super Smash Flash 2 Demo v0.10",
    "SuperSmashFlash 2 Demo v1.0": "Super Smash Flash 2 Demo v1.0",
    "SuperSmashFlash 2 Demo v1.1": "Super Smash Flash 2 Demo v1.1",
    "SuperSmashFlash 2 Demo v1.2": "Super Smash Flash 2 Demo v1.2",
    "SuperSmashFlash 2": "Super Smash Flash 2",
    "MotoX3m": "Moto X3M",
    "MotoX3m2": "Moto X3M 2",
    "MotoX3m3": "Moto X3M 3",
    "MotoX3m Spooky Land": "Moto X3M Spooky Land",
    "MotoX3m Pool Party": "Moto X3M Pool Party",
    "Spongebob PowerKart Grand Prix": "Spongebob Power Kart Grand Prix",
    "PaRappa the Rapper": "PaRappa The Rapper",
    "EaglerCraft Odd Future": "Eaglercraft Odd Future",
    "EaglerCraftTech": "Eaglercraft Tech",
    "CoderCraft": "Coder Craft",
    "Clash N Slash": "Clash 'n' Slash",
    "PokePasta": "Poke Pasta",
    "BulletForce": "Bullet Force",
    "HitStunFly": "Hit Stun Fly",
    "UpSlash": "Up Slash",
    "HellroN": "Hellron",
    "GoBattle": "Go Battle",
    "HoleBattle": "Hole Battle",
}

GAMES_JSON = os.path.join(ROOT, "games.json")

def load_games():
    if not os.path.exists(GAMES_JSON):
        print("[games] games.json missing, run 'manage_games.py sync'")
        return []
    with open(GAMES_JSON, encoding="utf-8") as f:
        return json.load(f)

def regen_data():
    """Generate data/more.js from games.json (exclude curated entries to avoid dupes)."""
    curated_ids = {g.get("identifier") for g in parse_gamesdata(GAMES_JS)}
    all_games = load_games()
    more = [g for g in all_games if g.get("identifier") not in curated_ids]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MORE_JS, "w", encoding="utf-8") as out:
        out.write("window.more = " + json.dumps(more, indent=2) + ";\n")
    print(f"[games] data/more.js: {len(more)} entries (curated: {len(curated_ids)})")

# ----------------------------------------------------------------------------
# HTTP handler
# ----------------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def _mutate(self, devOnly=None, announce=None, announceDur=5, announceSticky=False, clearAnnounce=False, removeAnnounce=None, motd=None, title=None, reloadSignal=None, announceColor=None, redTheme=None, footer=None, dark=None):
        changed = False
        with STATE_LOCK:
            if devOnly is not None:
                STATE["devOnly"] = bool(devOnly); changed = True
            if motd is not None:
                STATE["motd"] = motd; changed = True
            if title is not None:
                STATE["title"] = title; changed = True
            if reloadSignal is not None:
                STATE["reloadSignal"] = int(time.time()); changed = True
            if announceColor is not None:
                STATE["announceColor"] = announceColor; changed = True
            if redTheme is not None:
                STATE["redTheme"] = bool(redTheme); changed = True
            if footer is not None:
                STATE["footer"] = footer; changed = True
            if dark is not None:
                STATE["dark"] = bool(dark); changed = True
            anns = STATE.setdefault("announcements", [])
            if announce:
                anns.insert(0, {"t": int(time.time()), "msg": announce, "dur": int(announceDur or 5), "sticky": bool(announceSticky)})
                STATE["announcements"] = anns[:50]; changed = True
            if clearAnnounce:
                STATE["announcements"] = []; changed = True
            if removeAnnounce is not None:
                try:
                    STATE["announcements"].pop(int(removeAnnounce))
                except Exception:
                    pass
                changed = True
            if changed:
                save_state(STATE)
        if changed:
            broadcast_state()
        return STATE

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/stream":
            self.serve_sse()
            return
        if u.path == "/api/state":
            self.json_reply(200, STATE)
            return
        if u.path == "/api/stream":
            self.serve_sse()
            return
        if u.path == "/api/games":
            self.json_reply(200, load_games())
            return
        if u.path == "/api/admin" and u.query:
            q = urllib.parse.parse_qs(u.query)
            if "checkBypass" in q:
                ok = q.get("bypass", [""])[0] == ADMIN_BYPASS
                self.json_reply(200, {"ok": ok})
                return
            if q.get("pass", [""])[0] != ADMIN_PASS:
                self.json_reply(403, {"error": "bad password"})
                return
            self.json_reply(200, self._mutate(
                devOnly=_bv(q.get("devOnly")),
                motd=(q.get("motd", [""])[0] or None),
                title=(q.get("title", [""])[0] or None),
                announceColor=q.get("announceColor", [""])[0] or None,
                redTheme=_bv(q.get("redTheme")),
                dark=_bv(q.get("dark")),
                footer=(q.get("footer", [""])[0] or None),
                announce=q.get("announce", [""])[0] or None,
                announceDur=(q.get("annDur", ["5"])[0] or "5"),
                announceSticky=("annSticky" in q),
                clearAnnounce="clearAnnounce" in q,
                reloadSignal=("reload" in q and 1) or None,
            ))
            return
        if u.path == "/api/user":
            user = get_session_user(self.headers)
            self.json_reply(200, {"user": user})
            return
        if u.path == "/api/user/data":
            user = get_session_user(self.headers)
            if not user:
                self.json_reply(401, {"error": "not logged in"})
                return
            with USERS_LOCK:
                data = load_users()
                ud = data["users"].get(user, {}).get("data", {})
            self.json_reply(200, {"data": ud})
            return
        super().do_GET()

    def serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = queue.Queue()
        with SSE_LOCK:
            SSE_CLIENTS.append(q)
        try:
            self.wfile.write(("data: " + json.dumps(STATE) + "\n\n").encode())
            while True:
                try:
                    payload = q.get(timeout=25)
                except Exception:
                    self.wfile.write(b": ping\n\n")
                    continue
                self.wfile.write(("data: " + payload + "\n\n").encode())
                self.wfile.flush()
        except Exception:
            pass
        finally:
            with SSE_LOCK:
                if q in SSE_CLIENTS:
                    SSE_CLIENTS.remove(q)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        
        if u.path == "/api/register":
            username = (body.get("username") or "").strip()
            password = body.get("password") or ""
            if len(username) < 3 or len(username) > 24:
                self.json_reply(400, {"error": "username must be 3-24 characters"})
                return
            if len(password) < 4:
                self.json_reply(400, {"error": "password must be at least 4 characters"})
                return
            with USERS_LOCK:
                data = load_users()
                if username in data["users"]:
                    self.json_reply(409, {"error": "username taken"})
                    return
                data["users"][username] = {"password": hash_password(password), "data": {}}
                save_users(data)
            token = make_session(username)
            self.json_reply_with_cookie(200, {"ok": True, "user": username}, "elixer_session", token)
            return

        if u.path == "/api/login":
            username = (body.get("username") or "").strip()
            password = body.get("password") or ""
            with USERS_LOCK:
                data = load_users()
                user = data["users"].get(username)
            if not user or user["password"] != hash_password(password):
                self.json_reply(401, {"error": "invalid username or password"})
                return
            token = make_session(username)
            self.json_reply_with_cookie(200, {"ok": True, "user": username}, "elixer_session", token)
            return

        if u.path == "/api/logout":
            cookie = self.headers.get("Cookie", "")
            for part in cookie.split(";"):
                part = part.strip()
                if part.startswith("elixer_session="):
                    token = part.split("=", 1)[1]
                    clear_session(token)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "elixer_session=; Path=/; Max-Age=0; SameSite=Lax; HttpOnly")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            return

        if u.path == "/api/user/data":
            user = get_session_user(self.headers)
            if not user:
                self.json_reply(401, {"error": "not logged in"})
                return
            ud = body.get("data", {})
            with USERS_LOCK:
                data = load_users()
                if user not in data["users"]:
                    self.json_reply(404, {"error": "user not found"})
                    return
                if not isinstance(data["users"][user].get("data"), dict):
                    data["users"][user]["data"] = {}
                data["users"][user]["data"].update(ud)
                save_users(data)
            self.json_reply(200, {"ok": True})
            return

        # original admin POST handler
        if u.path == "/api/admin":
            if body.get("pass") != ADMIN_PASS:
                self.json_reply(403, {"error": "bad password"})
                return
            self.json_reply(200, self._mutate(
                devOnly=body.get("devOnly"),
                motd=body.get("motd"),
                title=body.get("title"),
                announceColor=body.get("announceColor"),
                redTheme=body.get("redTheme"),
                dark=body.get("dark"),
                footer=body.get("footer"),
                announce=body.get("announce") or None,
                announceDur=body.get("announceDur", 5),
                announceSticky=body.get("announceSticky"),
                clearAnnounce=body.get("clearAnnounce"),
                removeAnnounce=body.get("removeAnnounce"),
                reloadSignal=(1 if body.get("reload") else None),
            ))
            return
        self.json_reply(404, {"error": "not found"})

    def json_reply(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json_reply_with_cookie(self, code, obj, cookie_name, cookie_value, max_age=86400*365):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Set-Cookie", f"{cookie_name}={cookie_value}; Path=/; Max-Age={max_age}; SameSite=Lax; HttpOnly")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def handle(self):
        # Silence expected client-disconnect noise (browser closing the tab,
        # SSE dropping, etc.) so the console stays clean.
        try:
            super().handle()
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

def main():
    regen_data()
    port = int(os.environ.get("PORT", "80"))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", port), Handler) as httpd:
        print("""\n========================================
  elixer - starting server...
  open:  http://localhost:%d
  (proxy only works over http, not file://)
========================================""" % port)
        print(f"admin password:      {ADMIN_PASS}")
        print(f"dev bypass password: {ADMIN_BYPASS}")
        print("(proxy only works over http, not file://)\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nshutting down.")

if __name__ == "__main__":
    main()
