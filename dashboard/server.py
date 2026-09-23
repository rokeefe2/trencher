#!/usr/bin/env python3
"""Local dashboard for the trencher (paper trading) + CEO Watcher trader.

Run: python3 server.py  ->  http://localhost:8799
Trencher data comes from the GitHub `data` branch (or ../dashboard.json before the cloud move);
CEO Watcher data is read from ~/ceo-trader on this Mac. Stdlib only.
"""
import glob, json, os, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = json.load(open(os.path.join(HERE, "settings.json"))) if os.path.exists(os.path.join(HERE, "settings.json")) else {}
REPO = SETTINGS.get("repo")  # e.g. "username/trencher"
CEO_DIR = os.path.expanduser("~/ceo-trader")
PORT = 8799
_cache = {}

def fetch(url, ttl=60, raw=False):
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < ttl: return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": "trencher-dashboard", "Accept": "application/json",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode()
    val = body if raw else json.loads(body)
    _cache[url] = (time.time(), val)
    return val

BASE = {"data": None}

def trencher():
    source, stale = "local file", False
    if REPO:
        try:  # raw file server: no API rate limit (the API allows only 60 requests/hour)
            data = fetch(f"https://raw.githubusercontent.com/{REPO}/data/dashboard.json", ttl=60)
            source = f"github.com/{REPO}"
        except Exception as e:
            data = None; source = f"couldn't reach GitHub ({e}) - showing an OLD local copy"; stale = True
    if not REPO or data is None:
        p = os.path.join(HERE, "..", "dashboard.json")
        data = json.load(open(p)) if os.path.exists(p) else {"summary": {}, "picks": [], "recent": []}
    data = json.loads(json.dumps(data))  # copy so live-price edits don't touch the cache
    # live prices for open picks
    open_picks = [p for p in data.get("picks", []) if p.get("status") == "open"]
    for chain in {p["chain"] for p in open_picks}:
        toks = [p["token"] for p in open_picks if p["chain"] == chain][:30]
        try:
            best = {}
            for pr in fetch(f"https://api.dexscreener.com/tokens/v1/{chain}/{','.join(toks)}", ttl=30):
                t = pr.get("baseToken", {}).get("address"); liq = float((pr.get("liquidity") or {}).get("usd") or 0)
                if t and liq >= best.get(t, (0, 0))[0]: best[t] = (liq, float(pr.get("priceUsd") or 0))
            for p in open_picks:
                if p["token"] in best and best[p["token"]][1]:
                    px = best[p["token"]][1]
                    p["live_price"] = px
                    p["mult_now"] = round(px / p["entry_price"], 3)
                    p["value_now"] = round(p["realized"] + (p["tokens_left"] or 0) * px, 2)
                    p["pnl"] = round(p["value_now"] - p["stake"], 2)
        except Exception:
            pass
    if open_picks:
        s = data["summary"]; s["value"] = round(sum(p["value_now"] for p in data["picks"]), 2)
        s["pnl"] = round(s["value"] - s.get("staked", 0), 2)
    data["source"] = source; data["stale"] = stale
    try:   # exit watcher heartbeat (raw file server may lag up to ~5 min)
        data["watcher"] = fetch(f"https://raw.githubusercontent.com/{REPO}/exits/heartbeat.json", ttl=60) if REPO else None
    except Exception:
        data["watcher"] = None
    BASE["data"] = data
    return data

def live():
    """Fast reprice of open picks from DexScreener (polled every ~5s by the page)."""
    d = BASE["data"] or trencher()
    picks = d.get("picks", []); out = []
    for chain in {p["chain"] for p in picks if p["status"] == "open"}:
        toks = [p["token"] for p in picks if p["status"] == "open" and p["chain"] == chain][:30]
        best = {}
        for pr in fetch(f"https://api.dexscreener.com/tokens/v1/{chain}/{','.join(toks)}", ttl=4):
            tk = pr.get("baseToken", {}).get("address"); liq = float((pr.get("liquidity") or {}).get("usd") or 0)
            if tk and liq >= best.get(tk, (0, 0))[0]: best[tk] = (liq, float(pr.get("priceUsd") or 0))
        for p in picks:
            if p["status"] == "open" and p["chain"] == chain and best.get(p["token"], (0, 0))[1]:
                px = best[p["token"]][1]; val = p["realized"] + (p["tokens_left"] or 0) * px
                out.append({"token": p["token"], "price": px, "mult": px / p["entry_price"], "value": val})
    live_vals = {o["token"]: o["value"] for o in out}
    value = sum(live_vals.get(p["token"], p["value_now"]) if p["status"] == "open" else p["value_now"] for p in picks)
    return {"t": time.time(), "value": round(value, 4), "staked": sum(p["stake"] for p in picks), "picks": out}

def spark(chain, token, since):
    """Price history for a pick's mini chart: DexScreener finds the main pool, GeckoTerminal gives candles."""
    pairs = fetch(f"https://api.dexscreener.com/tokens/v1/{chain}/{token}", ttl=600)
    pair = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))["pairAddress"]
    hrs = (time.time() - since) / 3600
    tf, agg = ("minute", 15) if hrs <= 24 else ("hour", 1)
    d = fetch(f"https://api.geckoterminal.com/api/v2/networks/{chain}/pools/{pair}/ohlcv/{tf}?aggregate={agg}&limit=300", ttl=300)
    pts = sorted([c[0], c[4]] for c in d["data"]["attributes"]["ohlcv_list"] if c[0] >= since - 3600)
    return {"points": pts}

def ceo():
    out = {"state": None, "briefings": []}
    sp = os.path.join(CEO_DIR, "state.json")
    if os.path.exists(sp):
        out["state"] = json.load(open(sp))
    for p in sorted(glob.glob(os.path.join(CEO_DIR, "logs", "20*.md")))[-10:][::-1]:
        out["briefings"].append({"date": os.path.basename(p)[:-3], "markdown": open(p).read()})
    return out

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                self.send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html; charset=utf-8")
            elif self.path.startswith("/api/trencher"):
                self.send(200, json.dumps(trencher(), default=str), "application/json")
            elif self.path.startswith("/api/live"):
                self.send(200, json.dumps(live()), "application/json")
            elif self.path.startswith("/api/spark"):
                from urllib.parse import urlparse, parse_qs
                q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                if q.get("chain") not in ("solana", "base") or not q.get("token", "").isalnum():
                    self.send(400, "bad request", "text/plain"); return
                self.send(200, json.dumps(spark(q["chain"], q["token"], float(q.get("since", 0)))), "application/json")
            elif self.path.startswith("/api/ceo"):
                self.send(200, json.dumps(ceo(), default=str), "application/json")
            else:
                self.send(404, "not found", "text/plain")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}), "application/json")

if __name__ == "__main__":
    print(f"Dashboard on http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
