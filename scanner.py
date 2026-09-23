#!/usr/bin/env python3
"""Meme-coin trencher: discover -> hard scam filters -> score -> (Claude review) -> alert + paper trade.

Usage:
  scanner.py scan        discover + filter + score; writes candidates.json (no alerts)
  scanner.py track       update open paper trades
  scanner.py record      read review.json (Claude's verdicts) -> log picks, send ntfy alerts
  scanner.py stats       print paper-trading stats as JSON
Stdlib only. All data from free public APIs (GeckoTerminal, DexScreener, RugCheck, GoPlus, Honeypot.is).
"""
import json, os, sqlite3, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone

CODE = os.path.dirname(os.path.abspath(__file__))
HERE = os.environ.get("DATA_DIR") or CODE          # data lives in DATA_DIR (the `data` branch in the cloud)
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)
CFG = json.load(open(os.path.join(CODE, "config.json")))
CFG["ntfy_topic"] = os.environ.get("NTFY_TOPIC") or CFG.get("ntfy_topic")  # secret in the cloud
TUNING_PATH = os.path.join(HERE, "tuning.json")   # self-tuning overrides live with the data, not the code
TUNING = json.load(open(TUNING_PATH)) if os.path.exists(TUNING_PATH) else {"overrides": {}, "changelog": [], "pending": []}
for _k, _v in TUNING.get("overrides", {}).items():
    if isinstance(_v, dict) and isinstance(CFG.get(_k), dict): CFG[_k] = {**CFG[_k], **_v}
    else: CFG[_k] = _v
DB = sqlite3.connect(os.path.join(HERE, "trencher.db"))
for _col, _typ in (("tokens0", "REAL"), ("ladder_hit", "INTEGER DEFAULT 0")):
    try: DB.execute(f"ALTER TABLE picks ADD COLUMN {_col} {_typ}")
    except sqlite3.OperationalError: pass
DB.execute("UPDATE picks SET tokens0=tokens_left WHERE tokens0 IS NULL AND ladder_hit=0 AND took_stake=0")
DB.execute("CREATE TABLE IF NOT EXISTS applied_events (id TEXT PRIMARY KEY)")
NOW = time.time()
COST = CFG.get("cost_pct_each_way", 1.5) / 100   # DEX fee + slippage per side, so paper P&L isn't flattering

DB.executescript("""
CREATE TABLE IF NOT EXISTS seen (chain TEXT, token TEXT, first_seen REAL, last_result TEXT, score REAL,
  PRIMARY KEY(chain, token));
CREATE TABLE IF NOT EXISTS shadow (chain TEXT, token TEXT, t0 REAL, stage TEXT, reason TEXT, score REAL,
  parts TEXT, metrics TEXT, entry REAL, liq0 REAL, p1h REAL, p6h REAL, p24h REAL, p72h REAL, liq24 REAL,
  PRIMARY KEY(chain, token));
CREATE TABLE IF NOT EXISTS equity (t REAL PRIMARY KEY, value REAL, staked REAL, open_n INTEGER);
CREATE TABLE IF NOT EXISTS incubator (chain TEXT, token TEXT, created_at REAL, PRIMARY KEY(chain, token));
CREATE TABLE IF NOT EXISTS picks (id INTEGER PRIMARY KEY, chain TEXT, token TEXT, symbol TEXT, name TEXT,
  picked_at REAL, entry_price REAL, stake REAL, score REAL, reason TEXT,
  status TEXT DEFAULT 'open', tokens_left REAL, realized REAL DEFAULT 0, took_stake INTEGER DEFAULT 0,
  p1h REAL, p6h REAL, p24h REAL, p72h REAL, last_price REAL, peak REAL, closed_at REAL, close_reason TEXT);
""")

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "trencher/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(30 if "429" in str(e) else 3)  # rate-limited: back off hard
    log(f"GET failed {url}: {err}")
    return None

def log(msg):
    with open(os.path.join(HERE, "logs", datetime.now().strftime("%Y-%m-%d") + ".log"), "a") as f:
        f.write(datetime.now().strftime("%H:%M:%S ") + msg + "\n")

def f(x, d=0.0):
    try: return float(x)
    except (TypeError, ValueError): return d

GT_NET = {"solana": "solana", "base": "base"}
BURN = {"0x000000000000000000000000000000000000dead", "0x0000000000000000000000000000000000000000"}

# ---------------------------------------------------------------- discovery
def discover(chain):
    pools = {}
    net = GT_NET[chain]
    for path in ["trending_pools?duration=1h", "trending_pools?duration=6h", "trending_pools?duration=1h&page=2",
                 "pools?sort=h24_tx_count_desc"]:
        d = get(f"https://api.geckoterminal.com/api/v2/networks/{net}/{path}")
        time.sleep(7)  # GeckoTerminal free tier is strict; stay well under it
        for p in (d or {}).get("data", []):
            a = p["attributes"]
            tok = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
            age_h = (NOW - datetime.fromisoformat(a["pool_created_at"].replace("Z", "+00:00")).timestamp()) / 3600
            liq = f(a.get("reserve_in_usd"))
            if not (CFG["min_age_h"] <= age_h <= CFG["max_age_h"]) or liq < CFG["min_liquidity"]:
                continue
            if tok not in pools or liq > pools[tok]["liq"]:
                pools[tok] = {"chain": chain, "token": tok, "pool": a["address"], "name": a["name"], "age_h": age_h,
                              "liq": liq, "mcap": f(a.get("market_cap_usd")) or f(a.get("fdv_usd")),
                              "pc": {k: f(v) for k, v in (a.get("price_change_percentage") or {}).items()},
                              "tx": a.get("transactions") or {}, "vol": {k: f(v) for k, v in (a.get("volume_usd") or {}).items()},
                              "price": f(a.get("base_token_price_usd"))}
    # Incubator: brand-new pools are saved now and re-checked once they're min_age_h old
    # (Base trending lists are all weeks-old coins, so this is the main Base discovery path).
    for page in range(1, CFG["new_pool_pages"].get(chain, 0) + 1):
        d = get(f"https://api.geckoterminal.com/api/v2/networks/{net}/new_pools?page={page}")
        time.sleep(7)
        for p in (d or {}).get("data", []):
            a = p["attributes"]
            tok = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
            ts = datetime.fromisoformat(a["pool_created_at"].replace("Z", "+00:00")).timestamp()
            DB.execute("INSERT OR IGNORE INTO incubator VALUES (?,?,?)", (chain, tok, ts))
    for feed in ("token-profiles/latest/v1", "token-boosts/latest/v1"):
        for t in get(f"https://api.dexscreener.com/{feed}") or []:
            if t.get("chainId") == chain and t.get("tokenAddress"):
                DB.execute("INSERT OR IGNORE INTO incubator VALUES (?,?,?)", (chain, t["tokenAddress"], 0))
    DB.commit()
    ripe = [r[0] for r in DB.execute("SELECT token FROM incubator WHERE chain=? AND created_at<?",
                                     (chain, NOW - CFG["min_age_h"] * 3600)) if r[0] not in pools]
    for i in range(0, len(ripe), 30):
        for p in get(f"https://api.dexscreener.com/tokens/v1/{chain}/{','.join(ripe[i:i+30])}") or []:
            tok = p.get("baseToken", {}).get("address"); liq = f((p.get("liquidity") or {}).get("usd"))
            age_h = (NOW - f(p.get("pairCreatedAt")) / 1000) / 3600
            if not tok or liq < CFG["min_liquidity"] or not (CFG["min_age_h"] <= age_h <= CFG["max_age_h"]):
                continue
            if tok in pools and liq <= pools[tok]["liq"]: continue
            tx = {k: {"buys": v.get("buys", 0), "sells": v.get("sells", 0), "buyers": v.get("buys", 0),
                      "sellers": v.get("sells", 0)} for k, v in (p.get("txns") or {}).items()}  # dexscreener has no unique-wallet counts
            pools[tok] = {"chain": chain, "token": tok, "pool": p.get("pairAddress"), "name": p.get("baseToken", {}).get("name"),
                          "age_h": age_h, "liq": liq, "mcap": f(p.get("marketCap")) or f(p.get("fdv")),
                          "pc": {k: f(v) for k, v in (p.get("priceChange") or {}).items()}, "tx": tx,
                          "vol": {k: f(v) for k, v in (p.get("volume") or {}).items()}, "price": f(p.get("priceUsd"))}
        DB.executemany("DELETE FROM incubator WHERE chain=? AND token=?", [(chain, t) for t in ripe[i:i+30]])
    DB.execute("DELETE FROM incubator WHERE created_at>0 AND created_at<?", (NOW - CFG["max_age_h"] * 3600,))
    DB.commit()
    return list(pools.values())

def dex_info(chain, tokens):
    out = {}
    for i in range(0, len(tokens), 30):
        d = get(f"https://api.dexscreener.com/tokens/v1/{chain}/{','.join(tokens[i:i+30])}") or []
        for p in d:
            t = p.get("baseToken", {}).get("address")
            if not t: continue
            liq = f((p.get("liquidity") or {}).get("usd"))
            if t in out and liq <= out[t]["liq"]: continue
            info = p.get("info") or {}
            out[t] = {"liq": liq, "price": f(p.get("priceUsd")), "symbol": p.get("baseToken", {}).get("symbol"),
                      "name": p.get("baseToken", {}).get("name"), "url": p.get("url"),
                      "socials": {s.get("type"): s.get("url") for s in info.get("socials", [])},
                      "websites": [w.get("url") for w in info.get("websites", [])],
                      "boosts": (p.get("boosts") or {}).get("active", 0)}
    return out

# ---------------------------------------------------------------- stage 1: hard filters
def safety_solana(c):
    r = get(f"https://api.rugcheck.xyz/v1/tokens/{c['token']}/report")
    time.sleep(1)
    if not r: return ["rugcheck unavailable"], {}
    fails = []
    if r.get("mintAuthority"): fails.append("creator can still mint new coins")
    if r.get("freezeAuthority"): fails.append("creator can freeze wallets")
    if r.get("rugged"): fails.append("flagged as rugged")
    if f((r.get("transferFee") or {}).get("pct")) > 0: fails.append("has a transfer fee")
    for risk in r.get("risks") or []:
        if risk.get("level") == "danger": fails.append("rugcheck danger: " + risk.get("name", "?"))
    pool_accts = {a for a, v in (r.get("knownAccounts") or {}).items() if v.get("type") in ("AMM", "LOCKER")}
    for m in r.get("markets") or []:
        pool_accts.update(x for x in (m.get("pubkey"), (m.get("lp") or {}).get("lpMint")) if x)
    top = [h for h in (r.get("topHolders") or []) if h.get("owner") not in pool_accts and h.get("address") not in pool_accts]
    top10 = sum(f(h.get("pct")) for h in top[:10])
    if top10 > CFG["max_top10_pct"]: fails.append(f"top 10 wallets hold {top10:.0f}%")
    supply = f((r.get("token") or {}).get("supply")) or 1
    creator_pct = 100 * f(r.get("creatorBalance")) / supply
    if creator_pct > CFG["max_creator_pct"]: fails.append(f"creator holds {creator_pct:.1f}%")
    # insiderNetworks.tokenAmount is cumulative transfers (not holdings), so judge by network size instead,
    # plus the % held by top holders RugCheck flags as insiders.
    linked = sum(int(f(n.get("activeAccounts") or n.get("size"))) for n in (r.get("insiderNetworks") or []))
    if linked > CFG["max_linked_wallets"]: fails.append(f"{linked} wallets linked by transfers (one holder split across many wallets)")
    insider_pct = sum(f(h.get("pct")) for h in (r.get("topHolders") or []) if h.get("insider"))
    if insider_pct > CFG["max_insider_pct"]: fails.append(f"flagged insiders hold {insider_pct:.0f}%")
    mk = max(r.get("markets") or [{}], key=lambda m: f((m.get("lp") or {}).get("quoteUSD")))
    lp_locked = f((mk.get("lp") or {}).get("lpLockedPct"), 100)
    if lp_locked < CFG["min_lp_locked_pct"]: fails.append(f"only {lp_locked:.0f}% of liquidity locked/burned")
    return fails, {"top10_pct": round(top10, 1), "creator_pct": round(creator_pct, 2), "insider_pct": round(insider_pct, 1),
                   "linked_wallets": linked,
                   "lp_locked_pct": lp_locked, "holders": r.get("totalHolders"), "rugcheck_score": r.get("score_normalised")}

def safety_base(c):
    g = get(f"https://api.gopluslabs.io/api/v1/token_security/8453?contract_addresses={c['token']}")
    h = get(f"https://api.honeypot.is/v2/IsHoneypot?address={c['token']}&chainID=8453")
    time.sleep(1)
    if not g or not g.get("result"): return ["goplus unavailable"], {}
    r = list(g["result"].values())[0]
    fails = []
    flag = lambda k: str(r.get(k)) == "1"
    if flag("is_honeypot") or (h and (h.get("honeypotResult") or {}).get("isHoneypot")): fails.append("honeypot (can't sell)")
    if flag("is_mintable"): fails.append("owner can mint new coins")
    if flag("hidden_owner") or flag("can_take_back_ownership"): fails.append("hidden/reclaimable ownership")
    if flag("transfer_pausable") or flag("is_blacklisted"): fails.append("owner can pause or blacklist sellers")
    if flag("slippage_modifiable"): fails.append("owner can change taxes")
    if str(r.get("is_open_source")) == "0": fails.append("contract not verified")
    sim = (h or {}).get("simulationResult") or {}
    tax = max(f(sim.get("sellTax")), 100 * f(r.get("sell_tax")))
    if tax > CFG["max_sell_tax_pct"]: fails.append(f"sell tax {tax:.0f}%")
    owner_pct = 100 * max(f(r.get("owner_percent")), f(r.get("creator_percent")))
    if owner_pct > CFG["max_creator_pct"]: fails.append(f"creator/owner holds {owner_pct:.1f}%")
    top = [x for x in r.get("holders", []) if str(x.get("is_contract")) != "1" and str(x.get("is_locked")) != "1"
           and x.get("address", "").lower() not in BURN]
    top10 = 100 * sum(f(x.get("percent")) for x in top[:10])
    if top10 > CFG["max_top10_pct"]: fails.append(f"top 10 wallets hold {top10:.0f}%")
    lps = r.get("lp_holders") or []
    lp_locked = 100 * sum(f(x.get("percent")) for x in lps
                          if str(x.get("is_locked")) == "1" or x.get("address", "").lower() in BURN) if lps else None
    if lp_locked is not None and lp_locked < CFG["min_lp_locked_pct"] and not any(str(x.get("is_contract")) == "1" for x in lps):
        fails.append(f"only {lp_locked:.0f}% of liquidity locked/burned")
    return fails, {"top10_pct": round(top10, 1), "creator_pct": round(owner_pct, 2), "sell_tax_pct": round(tax, 2),
                   "lp_locked_pct": lp_locked, "holders": f(r.get("holder_count"))}

# ---------------------------------------------------------------- stage 2: score /100
def score(c, s, dx):
    tx = c["tx"]; parts = {}
    turnover = c["vol"].get("h1", 0) / max(c["liq"], 1)
    h1 = tx.get("h1", {}); buyers, sellers = h1.get("buyers", 0), h1.get("sellers", 0)
    buy_ratio = buyers / max(buyers + sellers, 1)
    pch = c["pc"].get("h1", 0)
    parts["momentum"] = (10 if turnover >= 1 else 7 if turnover >= .5 else 4 if turnover >= .2 else 0) \
        + (8 if buy_ratio >= .6 else 5 if buy_ratio >= .52 else 0) \
        + (7 if 5 <= pch <= 100 else 3 if 0 <= pch < 5 or 100 < pch <= 300 else 0)
    holders = f(s.get("holders"))
    parts["holders"] = (10 if s.get("top10_pct", 99) < 15 else 6 if s.get("top10_pct", 99) < 22 else 2) \
        + (10 if holders >= 1000 else 7 if holders >= 500 else 4 if holders >= 250 else 0)
    lm = c["liq"] / max(c["mcap"], 1)
    parts["liquidity"] = 15 if lm >= .15 else 10 if lm >= .08 else 5 if lm >= .04 else 0
    b6 = tx.get("h6", {}).get("buyers", 0)
    parts["buyer_breadth"] = 15 if b6 >= 500 else 10 if b6 >= 200 else 5 if b6 >= 80 else 0
    soc = dx.get("socials", {})
    parts["social"] = (6 if soc.get("twitter") else 0) + (4 if soc.get("telegram") else 0) + (5 if dx.get("websites") else 0)
    a = c["age_h"]
    parts["survival"] = 10 if 3 <= a <= 24 else 6
    w = CFG.get("weights", {}); mx = {"momentum": 25, "holders": 20, "liquidity": 15, "buyer_breadth": 15, "social": 15, "survival": 10}
    total = round(100 * sum(parts[k] * w.get(k, 1) for k in parts) / sum(mx[k] * w.get(k, 1) for k in mx), 1)
    return total, parts, {"turnover_1h": round(turnover, 2), "buy_ratio_1h": round(buy_ratio, 2),
                                        "price_change": c["pc"], "buyers_6h": b6, "liq_to_mcap": round(lm, 3)}

def holder_check(fails, s):
    if f(s.get("holders")) < CFG["min_holders"]:
        fails.append(f"only {int(f(s.get('holders')))} holders (too few, or data not ready)")
    return fails, s

def shadow(chain, token, stage, reason, price, liq, score=None, parts=None, metrics=None):
    if not price: return
    DB.execute("INSERT OR IGNORE INTO shadow (chain,token,t0,stage,reason,score,parts,metrics,entry,liq0) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (chain, token, NOW, stage, reason, score, json.dumps(parts or {}), json.dumps(metrics or {}), price, liq))

def cmd_scan():
    cands = []; rejects_tracked = 0
    for chain in CFG["chains"]:
        pools = discover(chain)
        new = [p for p in pools if not DB.execute(
            "SELECT 1 FROM seen WHERE chain=? AND token=? AND first_seen>?", (chain, p["token"], NOW - 24 * 3600)).fetchone()]
        dx = dex_info(chain, [p["token"] for p in new])
        log(f"{chain}: {len(pools)} pools in window, {len(new)} not seen in 24h")
        for c in new:
            fails, s = holder_check(*(safety_solana if chain == "solana" else safety_base)(c))
            if fails:
                DB.execute("INSERT OR REPLACE INTO seen VALUES (?,?,?,?,?)", (chain, c["token"], NOW, "REJECT: " + "; ".join(fails), None))
                if rejects_tracked < CFG.get("shadow_rejects_per_run", 8):   # sample rejects to learn if the rule was right
                    shadow(chain, c["token"], "reject", "; ".join(fails), c["price"], c["liq"],
                           metrics={"age_h": round(c["age_h"], 1), "mcap": round(c["mcap"]), "pc": c["pc"]})
                    rejects_tracked += 1
                continue
            d = dx.get(c["token"], {})
            total, parts, metrics = score(c, s, d)
            DB.execute("INSERT OR REPLACE INTO seen VALUES (?,?,?,?,?)", (chain, c["token"], NOW, "SCORED", total))
            shadow(chain, c["token"], "scored" if total >= CFG["min_score"] else "low_score", "", d.get("price") or c["price"],
                   c["liq"], total, parts, {**metrics, "safety": s, "age_h": round(c["age_h"], 1), "mcap": round(c["mcap"]),
                                            "boosts": d.get("boosts")})
            if total >= CFG["min_score"]:
                cands.append({"chain": chain, "token": c["token"], "symbol": d.get("symbol"), "name": d.get("name") or c["name"],
                              "score": total, "score_parts": parts, "age_h": round(c["age_h"], 1), "liquidity_usd": round(c["liq"]),
                              "mcap_usd": round(c["mcap"]), "price_usd": d.get("price") or c["price"], "safety": s,
                              "metrics": metrics, "socials": d.get("socials"), "websites": d.get("websites"),
                              "dexscreener": d.get("url"), "paid_boosts": d.get("boosts")})
    DB.commit()
    cands.sort(key=lambda x: -x["score"])
    picks_today = DB.execute("SELECT COUNT(*) FROM picks WHERE picked_at>?", (NOW - 24 * 3600,)).fetchone()[0]
    slots = max(0, CFG["max_picks_per_day"] - picks_today)
    out = {"slots_left_today": slots, "candidates": cands[:CFG["max_reviews_per_run"]] if slots else []}
    json.dump(out, open(os.path.join(HERE, "candidates.json"), "w"), indent=1)
    log(f"scan done: {len(cands)} scored >= {CFG['min_score']}, {slots} pick slots left, sending {len(out['candidates'])} to review")
    print(json.dumps({"to_review": len(out["candidates"]), "slots": slots}))

# ---------------------------------------------------------------- paper trading
def ntfy(title, msg, url=None, prio="default"):
    headers = {"Title": title.encode("ascii", "ignore").decode(), "Priority": prio, "Tags": "moneybag"}
    if url: headers["Click"] = url
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{CFG['ntfy_topic']}", data=msg.encode(), headers=headers), timeout=15)
    except Exception as e:
        log(f"ntfy failed: {e}")

def cmd_record():
    import re
    txt = open(os.path.join(HERE, "review_out.txt")).read()
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", txt, re.S)
    if not blocks:
        log("record: no json verdict block in Claude output"); return
    rv = json.loads(blocks[-1], strict=False)
    cands = {c["token"]: c for c in json.load(open(os.path.join(HERE, "candidates.json")))["candidates"]}
    slots = json.load(open(os.path.join(HERE, "candidates.json")))["slots_left_today"]
    for v in rv.get("verdicts", []):
        c = cands.get(v.get("token"))
        if not c: continue
        DB.execute("UPDATE seen SET last_result=? WHERE chain=? AND token=?", (f"{v.get('verdict')}: {v.get('reason','')[:300]}", c["chain"], c["token"]))
        DB.execute("UPDATE shadow SET stage=?, reason=? WHERE chain=? AND token=?", (v.get("verdict", "").lower(), v.get("reason", "")[:300], c["chain"], c["token"]))
        if v.get("verdict") != "PICK" or slots <= 0: continue
        slots -= 1
        price = c["price_usd"]; stake = CFG["paper_stake"]
        tokens = stake * (1 - COST) / price
        DB.execute("INSERT INTO picks (chain,token,symbol,name,picked_at,entry_price,stake,score,reason,tokens_left,last_price,peak,tokens0,ladder_hit) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)", (c["chain"], c["token"], c["symbol"], c["name"], NOW, price, stake,
                   c["score"], v.get("reason", ""), tokens, price, price, tokens))
        ntfy(f"PAPER PICK: {c['symbol']} ({c['chain']}) score {c['score']}",
             f"{v.get('reason','')[:300]}\nMcap ${c['mcap_usd']:,} | Liq ${c['liquidity_usd']:,} | Age {c['age_h']}h\n"
             f"Paper entry ${price:.8g} x ${stake}", c.get("dexscreener"), "high")
        log(f"PICK {c['symbol']} {c['token']} @ {price}")
    DB.commit()

# ---------------------------------------------------------------- exits: profit-taking ladder (shared with watcher.py)
def decide_exit(p, px, now, cfg):
    """Pure decision. p needs entry_price, ladder_hit, peak_x, picked_at. Returns (ladder_levels_to_sell, close_reason, peak_x)."""
    mult = px / p["entry_price"]; peak_x = max(p.get("peak_x") or 1.0, mult)
    ladder = cfg.get("ladder", [[1.5, .3], [2.0, .3], [3.0, .2]]); hit = p.get("ladder_hit") or 0
    sells = []
    while hit < len(ladder) and mult >= ladder[hit][0]:
        sells.append(hit); hit += 1
    age_h = (now - p["picked_at"]) / 3600
    if hit == 0:
        stop_x, stop_name = 1 - cfg["stop_loss_pct"] / 100, "stop loss"
    else:
        trail = peak_x * (1 - cfg.get("trail_pct", 30) / 100)
        stop_x, stop_name = (trail, "trailing stop") if trail > cfg.get("breakeven_x", 1.0) else (cfg.get("breakeven_x", 1.0), "break-even stop")
    close = None
    if mult <= stop_x: close = stop_name
    elif hit == 0 and age_h >= cfg["no_move_hours"] and mult < 1 + cfg["no_move_min_gain_pct"] / 100: close = f"no move in {cfg['no_move_hours']}h"
    elif age_h >= 72: close = "72h max hold"
    return sells, close, peak_x

def apply_ladder(pid, level, px):
    row = DB.execute("SELECT stake, tokens0, tokens_left, realized, ladder_hit, status, symbol FROM picks WHERE id=?", (pid,)).fetchone()
    if not row or row[5] != "open" or (row[4] or 0) > level: return False   # already applied / closed
    stake, tokens0, left, realized, _, _, sym = row
    frac = CFG.get("ladder", [[1.5, .3], [2.0, .3], [3.0, .2]])[level][1]
    sell = min(left, frac * (tokens0 or left)); realized += sell * px * (1 - COST); left -= sell
    DB.execute("UPDATE picks SET tokens_left=?, realized=?, ladder_hit=?, took_stake=? WHERE id=?",
               (left, realized, level + 1, int(realized >= stake), pid))
    log(f"LADDER {sym}: sold {int(frac*100)}% at level {level+1}"); return True

def apply_close(pid, px, reason):
    row = DB.execute("SELECT tokens_left, realized, status, symbol FROM picks WHERE id=?", (pid,)).fetchone()
    if not row or row[2] != "open": return False
    DB.execute("UPDATE picks SET status='closed', realized=?, tokens_left=0, closed_at=?, close_reason=?, last_price=? WHERE id=?",
               (row[1] + row[0] * px * (1 - COST), NOW, reason, px, pid))
    log(f"CLOSE {row[3]}: {reason}"); return True

def watcher_healthy():
    d = os.environ.get("EXITS_DIR")
    try: return d and NOW - json.load(open(os.path.join(d, "heartbeat.json")))["t"] < 180
    except Exception: return False

def apply_watcher_events():
    d = os.environ.get("EXITS_DIR"); fp = os.path.join(d or "", "events.jsonl")
    if not d or not os.path.exists(fp): return
    for line in open(fp):
        try: e = json.loads(line)
        except ValueError: continue
        if DB.execute("SELECT 1 FROM applied_events WHERE id=?", (e["id"],)).fetchone(): continue
        if e["kind"] == "ladder": apply_ladder(e["pick_id"], e["level"], e["price"])
        elif e["kind"] == "close": apply_close(e["pick_id"], e["price"], e["reason"])
        if e.get("peak_price"): DB.execute("UPDATE picks SET peak=MAX(COALESCE(peak,0), ?) WHERE id=?", (e["peak_price"], e["pick_id"]))
        DB.execute("INSERT INTO applied_events VALUES (?)", (e["id"],))
    try:   # watcher's 30-second peaks feed the trailing stop
        for pid, pk in json.load(open(os.path.join(d, "heartbeat.json"))).get("peaks", {}).items():
            DB.execute("UPDATE picks SET peak=MAX(COALESCE(peak,0), ?) WHERE id=?", (pk, int(pid)))
    except Exception: pass
    DB.commit()

def cmd_track():
    apply_watcher_events()
    watcher_on = watcher_healthy()
    rows = DB.execute("SELECT id,chain,token,symbol,picked_at,entry_price,stake,tokens_left,realized,took_stake,peak,p1h,p6h,p24h,p72h "
                      "FROM picks WHERE status='open' OR p72h IS NULL").fetchall()
    by_chain = {}
    for r in rows: by_chain.setdefault(r[1], []).append(r[2])
    prices = {}
    for chain, toks in by_chain.items():
        for t, d in dex_info(chain, toks).items(): prices[(chain, t)] = d["price"]
    for (pid, chain, tok, sym, t0, entry, stake, left, realized, took, peak, p1, p6, p24, p72) in rows:
        px = prices.get((chain, tok))
        if not px: continue  # no price = pool gone; handled at 72h
        age_h = (NOW - t0) / 3600; mult = px / entry
        upd = {"last_price": px, "peak": max(peak or px, px)}
        for col, h, cur in (("p1h", 1, p1), ("p6h", 6, p6), ("p24h", 24, p24), ("p72h", 72, p72)):
            if cur is None and age_h >= h: upd[col] = mult
        sets = ",".join(f"{k}=?" for k in upd)
        DB.execute(f"UPDATE picks SET {sets} WHERE id=?", (*upd.values(), pid)); upd = {}
        prow = DB.execute("SELECT status, ladder_hit, peak FROM picks WHERE id=?", (pid,)).fetchone()
        if prow[0] == "open" and not watcher_on:   # the 30s watcher normally handles exits; this is the fallback
            sells, close, _ = decide_exit({"entry_price": entry, "ladder_hit": prow[1], "peak_x": (prow[2] or px) / entry,
                                           "picked_at": t0}, px, NOW, CFG)
            for lvl in sells:
                if apply_ladder(pid, lvl, px): ntfy(f"{sym} hit {CFG['ladder'][lvl][0]}x (paper)", f"Sold {int(CFG['ladder'][lvl][1]*100)}% of the position.")
            if close and apply_close(pid, px, close): ntfy(f"{sym} closed (paper): {close}", f"Exited at {mult:.2f}x.")
    # pools that vanished for >6h after 72h window: count as total loss
    DB.execute("UPDATE picks SET status='closed', close_reason='no price (pool gone)', closed_at=?, tokens_left=0 "
               "WHERE status='open' AND picked_at<? AND (last_price IS NULL OR last_price=entry_price)", (NOW, NOW - 78 * 3600))
    DB.commit()
    track_shadows()

def track_shadows():
    """Price non-picked coins at 1h/6h/24h/72h checkpoints (each coin fetched ~4 times total)."""
    due = DB.execute("SELECT chain,token,t0,entry,p1h,p6h,p24h,p72h FROM shadow WHERE "
                     "(p1h IS NULL AND t0<?) OR (p6h IS NULL AND t0<?) OR (p24h IS NULL AND t0<?) OR (p72h IS NULL AND t0<?) LIMIT 600",
                     (NOW - 3600, NOW - 6 * 3600, NOW - 24 * 3600, NOW - 72 * 3600)).fetchall()
    by_chain = {}
    for r in due: by_chain.setdefault(r[0], []).append(r[1])
    info = {}
    for chain, toks in by_chain.items():
        for tkn, d in dex_info(chain, toks).items(): info[(chain, tkn)] = d
    for chain, tok, t0, entry, p1, p6, p24, p72 in due:
        d = info.get((chain, tok)); age_h = (NOW - t0) / 3600
        mult = (d["price"] / entry) if d and d["price"] else 0.0   # no pair data any more = treated as dead
        upd = {}
        for col, h, cur in (("p1h", 1, p1), ("p6h", 6, p6), ("p24h", 24, p24), ("p72h", 72, p72)):
            if cur is None and age_h >= h: upd[col] = round(mult, 4)
        if "p24h" in upd: upd["liq24"] = d["liq"] if d else 0
        if upd:
            DB.execute(f"UPDATE shadow SET {','.join(k + '=?' for k in upd)} WHERE chain=? AND token=?", (*upd.values(), chain, tok))
    DB.execute("DELETE FROM shadow WHERE t0<?", (NOW - 35 * 86400,))
    DB.commit()

# ---------------------------------------------------------------- learning: rule report card
def _stats(rows):
    """rows: list of (p24h, best_mult, rugged). Returns outcome summary."""
    rows = [r for r in rows if r[0] is not None]
    if not rows: return {"n": 0}
    m = sorted(r[0] for r in rows)
    return {"n": len(rows), "median_24h": round(m[len(m) // 2], 2),
            "rug_pct": round(100 * sum(r[2] for r in rows) / len(rows)),
            "doubled_pct": round(100 * sum(r[1] >= 2 for r in rows) / len(rows)),
            "up50_pct": round(100 * sum(r[1] >= 1.5 for r in rows) / len(rows))}

def cmd_analyze():
    import re
    rows = DB.execute("SELECT stage,reason,score,parts,metrics,p1h,p6h,p24h,p72h,liq24,t0 FROM shadow").fetchall()
    recs = []
    for stage, reason, sc, parts, metrics, p1, p6, p24, p72, liq24, t0 in rows:
        ms = [x for x in (p1, p6, p24, p72) if x is not None]
        best = max(ms) if ms else None
        rug = int(p24 is not None and (p24 < 0.2 or (liq24 is not None and liq24 < 2000)))
        recs.append({"stage": stage, "reason": reason or "", "score": sc, "parts": json.loads(parts or "{}"),
                     "metrics": json.loads(metrics or "{}"), "p24": p24, "best": best or 0, "rug": rug, "t0": t0})
    out = {"generated_at": NOW, "tracked": len(recs), "with_24h_outcome": sum(r["p24"] is not None for r in recs)}
    # safety rules: did each rule block scams, or winners?
    by_rule = {}
    for r in recs:
        if r["stage"] != "reject": continue
        for part in r["reason"].split(";"):
            key = re.sub(r"\d+(\.\d+)?%", "X%", part.strip()); key = re.sub(r"^\d+ wallets linked.*", "many linked wallets", key)
            key = re.sub(r"only \d+ holders.*", "too few holders", key).replace("rugcheck danger: ", "")[:60]
            by_rule.setdefault(key, []).append((r["p24"], r["best"], r["rug"]))
    out["safety_rules"] = sorted(({"rule": k, **_stats(v)} for k, v in by_rule.items()), key=lambda x: -x["n"])
    # stages: rejected vs low score vs Claude PASS vs Claude PICK
    out["by_stage"] = {st: _stats([(r["p24"], r["best"], r["rug"]) for r in recs if r["stage"] == st])
                       for st in ("reject", "low_score", "scored", "pass", "pick")}
    # score buckets and each score component (does a higher component predict better outcomes?)
    scored = [r for r in recs if r["score"] is not None]
    out["score_buckets"] = {b: _stats([(r["p24"], r["best"], r["rug"]) for r in scored if lo <= r["score"] < hi])
                            for b, lo, hi in (("<50", 0, 50), ("50-59", 50, 60), ("60-69", 60, 70), ("70-79", 70, 80), ("80+", 80, 101))}
    comps = {}
    for k in ("momentum", "holders", "liquidity", "buyer_breadth", "social", "survival"):
        vals = [r for r in scored if k in r["parts"]]
        if len(vals) < 6: continue
        med = sorted(r["parts"][k] for r in vals)[len(vals) // 2]
        comps[k] = {"high": _stats([(r["p24"], r["best"], r["rug"]) for r in vals if r["parts"][k] > med]),
                    "low": _stats([(r["p24"], r["best"], r["rug"]) for r in vals if r["parts"][k] <= med]), "split_at": med}
    out["score_components"] = comps
    # exits: compare the live exit rules with simple alternatives on actual picks (checkpoint approximation)
    picks = DB.execute("SELECT pnl_x, p24h, p72h, stake FROM (SELECT (realized + tokens_left*last_price)/stake AS pnl_x, p24h, p72h, stake FROM picks WHERE status='closed')").fetchall()
    if picks:
        out["exits"] = {"n": len(picks), "actual_avg_x": round(sum(p[0] for p in picks) / len(picks), 3),
                        "hold_24h_avg_x": round(sum((p[1] or 0) for p in picks) / len(picks), 3),
                        "hold_72h_avg_x": round(sum((p[2] or 0) for p in picks) / len(picks), 3)}
    # go-live readiness
    closed = DB.execute("SELECT stake, realized + tokens_left*COALESCE(last_price,0), picked_at FROM picks WHERE status='closed'").fetchall()
    n = len(closed); pnl = sum(v - s for s, v, _ in closed)
    wins = sum(v > s for s, v, _ in closed)
    weeks = {}
    for s, v, ts in closed: weeks.setdefault(datetime.fromtimestamp(ts).strftime("%G-W%V"), []).append(v - s)
    last3 = [sum(x) for _, x in sorted(weeks.items())[-3:]]
    out["go_live"] = [
        {"check": "At least 30 closed paper picks", "ok": n >= 30, "value": n},
        {"check": "Total paper P&L positive (after fees and slippage)", "ok": pnl > 0, "value": round(pnl, 2)},
        {"check": "Win rate at least 35%", "ok": n > 0 and wins / n >= .35, "value": f"{round(100 * wins / n) if n else 0}%"},
        {"check": "Profitable in 2 of the last 3 weeks", "ok": sum(x > 0 for x in last3) >= 2 and len(last3) >= 3,
         "value": " / ".join(f"{x:+.0f}" for x in last3) or "-"},
        {"check": "Claude's picks beat its passes (median 24h)", "ok": (out["by_stage"]["pick"].get("median_24h") or 0) >
         (out["by_stage"]["pass"].get("median_24h") or 0) and out["by_stage"]["pick"].get("n", 0) >= 10,
         "value": f'{out["by_stage"]["pick"].get("median_24h", "-")} vs {out["by_stage"]["pass"].get("median_24h", "-")}'}]
    json.dump(out, open(os.path.join(HERE, "analysis.json"), "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))

def cmd_stats():
    rows = DB.execute("SELECT symbol,chain,picked_at,stake,realized,tokens_left,last_price,status,close_reason,p1h,p6h,p24h,p72h,score,reason,entry_price "
                      "FROM picks ORDER BY picked_at").fetchall()
    picks = []
    for r in rows:
        value = r[4] + (r[5] or 0) * (r[6] or 0)
        picks.append({"symbol": r[0], "chain": r[1], "picked": datetime.fromtimestamp(r[2]).strftime("%a %b %d %H:%M"),
                      "stake": r[3], "value_now": round(value, 2), "pnl": round(value - r[3], 2), "status": r[7],
                      "close_reason": r[8], "x_1h": r[9], "x_6h": r[10], "x_24h": r[11], "x_72h": r[12], "score": r[13]})
    staked = sum(p["stake"] for p in picks); val = sum(p["value_now"] for p in picks)
    rej = DB.execute("SELECT COUNT(*) FROM seen WHERE last_result LIKE 'REJECT%'").fetchone()[0]
    tot = DB.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    print(json.dumps({"picks": picks, "total_staked": staked, "total_value": round(val, 2), "total_pnl": round(val - staked, 2),
                      "open_picks": sum(p["status"] == "open" for p in picks),
                      "closed_win_rate": (round(sum(p["pnl"] > 0 for p in picks if p["status"] == "closed")
                                          / max(1, sum(p["status"] == "closed" for p in picks)), 2)
                                          if any(p["status"] == "closed" for p in picks) else None),
                      "coins_scanned": tot, "rejected_by_safety": rej}, indent=1, default=str))

def cmd_export():
    """Write dashboard JSON (dashboard.json) and prune old data so the data branch stays small."""
    cols = ["id", "chain", "token", "symbol", "name", "picked_at", "entry_price", "stake", "score", "reason", "status",
            "tokens_left", "realized", "took_stake", "p1h", "p6h", "p24h", "p72h", "last_price", "peak", "closed_at", "close_reason",
            "tokens0", "ladder_hit"]
    picks = []
    for r in DB.execute(f"SELECT {','.join(cols)} FROM picks ORDER BY picked_at DESC"):
        p = dict(zip(cols, r))
        p["value_now"] = round(p["realized"] + (p["tokens_left"] or 0) * (p["last_price"] or 0), 2)
        p["pnl"] = round(p["value_now"] - p["stake"], 2)
        p["mult_now"] = round((p["last_price"] or p["entry_price"]) / p["entry_price"], 3)
        p["dexscreener"] = f"https://dexscreener.com/{p['chain']}/{p['token']}"
        picks.append(p)
    seen = [dict(zip(["chain", "token", "first_seen", "result", "score"], r)) for r in
            DB.execute("SELECT chain,token,first_seen,last_result,score FROM seen ORDER BY first_seen DESC LIMIT 300")]
    counts = dict(DB.execute("SELECT substr(last_result,1,instr(last_result||':',':')-1), COUNT(*) FROM seen GROUP BY 1").fetchall())
    reasons = {}
    for (res,) in DB.execute("SELECT last_result FROM seen WHERE last_result LIKE 'REJECT%'"):
        for part in res[8:].split(";"):
            import re
            key = re.sub(r"\d+(\.\d+)?%", "X%", part.strip())
            key = re.sub(r"^\d+ wallets linked", "many wallets linked", key)
            key = re.sub(r"only \d+ holders.*", "too few holders", key).replace("rugcheck danger: ", "")[:60]
            reasons[key] = reasons.get(key, 0) + 1
    closed = [p for p in picks if p["status"] == "closed"]
    # equity curve: one point per scan (the dashboard's main chart)
    if not DB.execute("SELECT 1 FROM equity LIMIT 1").fetchone():   # first run: backfill a start point per pick
        for p in sorted(picks, key=lambda x: x["picked_at"]):
            st = sum(q["stake"] for q in picks if q["picked_at"] <= p["picked_at"])
            DB.execute("INSERT OR IGNORE INTO equity VALUES (?,?,?,?)", (p["picked_at"], st, st, 0))
    DB.execute("INSERT OR REPLACE INTO equity VALUES (?,?,?,?)", (NOW, sum(p["value_now"] for p in picks),
               sum(p["stake"] for p in picks), sum(p["status"] == "open" for p in picks)))
    eq = DB.execute("SELECT t, value, staked FROM equity WHERE t>? ORDER BY t", (NOW - 400 * 86400,)).fetchall()
    stride = max(1, len(eq) // 1500)
    eq = eq[::stride] + ([eq[-1]] if eq and (len(eq) - 1) % stride else [])
    out = {"updated_at": NOW,
           "equity": [[round(a), round(b, 2), round(c, 2)] for a, b, c in eq], "config": {k: v for k, v in CFG.items() if k not in ("ntfy_topic", "email")},
           "summary": {"picks": len(picks), "open": sum(p["status"] == "open" for p in picks),
                       "staked": sum(p["stake"] for p in picks), "value": round(sum(p["value_now"] for p in picks), 2),
                       "pnl": round(sum(p["pnl"] for p in picks), 2),
                       "win_rate": round(sum(p["pnl"] > 0 for p in closed) / len(closed), 2) if closed else None,
                       "scanned": sum(counts.values()), "outcomes": counts,
                       "incubating": DB.execute("SELECT COUNT(*) FROM incubator").fetchone()[0]},
           "reject_reasons": sorted(reasons.items(), key=lambda x: -x[1])[:15],
           "picks": picks, "recent": seen,
           "analysis": json.load(open(os.path.join(HERE, "analysis.json"))) if os.path.exists(os.path.join(HERE, "analysis.json")) else None,
           "tuning": {**TUNING, "effective": {k: _get(k) for k in TUNABLE}},
           "learnings": open(os.path.join(HERE, "learnings.md")).read() if os.path.exists(os.path.join(HERE, "learnings.md")) else "",
           "weekly": (lambda fs: {"name": fs[-1], "markdown": open(os.path.join(HERE, "weekly", fs[-1])).read()} if fs else None)(
               sorted(os.listdir(os.path.join(HERE, "weekly"))) if os.path.isdir(os.path.join(HERE, "weekly")) else []),
           "last_log": open(os.path.join(HERE, "logs", datetime.now().strftime("%Y-%m-%d") + ".log")).read()[-4000:]
                       if os.path.exists(os.path.join(HERE, "logs", datetime.now().strftime("%Y-%m-%d") + ".log")) else ""}
    json.dump(out, open(os.path.join(HERE, "dashboard.json"), "w"), default=str)
    # prune: seen >7d, logs >3d
    DB.execute("DELETE FROM seen WHERE first_seen<?", (NOW - 7 * 86400,)); DB.commit(); DB.execute("VACUUM")
    for fn in os.listdir(os.path.join(HERE, "logs")):
        fp = os.path.join(HERE, "logs", fn)
        if os.path.getmtime(fp) < NOW - 3 * 86400: os.remove(fp)

# ---------------------------------------------------------------- self-tuning with guardrails
# key: (min, max, max step per week, safety_dir). safety_dir: "down"/"up" = the STRICTER direction for a
# safety rule (auto-applied); the looser direction needs Ray's approval. None = tuning knob, auto both ways.
TUNABLE = {
    "min_score": (50, 85, 5, None), "max_picks_per_day": (1, 5, 1, None), "max_reviews_per_run": (2, 6, 1, None),
    "stop_loss_pct": (25, 60, 10, None), "trail_pct": (15, 50, 5, None), "no_move_hours": (6, 24, 6, None), "no_move_min_gain_pct": (10, 40, 10, None),
    "min_age_h": (0.5, 6, 1, None), "max_age_h": (12, 72, 12, None),
    "max_top10_pct": (15, 30, 5, "down"), "max_creator_pct": (1, 5, 1, "down"), "max_linked_wallets": (10, 40, 10, "down"),
    "max_insider_pct": (5, 15, 5, "down"), "max_sell_tax_pct": (0, 10, 5, "down"),
    "min_lp_locked_pct": (80, 100, 10, "up"), "min_liquidity": (20000, 100000, 20000, "up"), "min_holders": (100, 1000, 200, "up"),
    **{f"weights.{k}": (0.5, 1.5, 0.25, None) for k in ("momentum", "holders", "liquidity", "buyer_breadth", "social", "survival")},
}
MIN_EVIDENCE = 20   # outcomes needed behind any change

def _get(key):
    if key.startswith("weights."): return CFG.get("weights", {}).get(key.split(".", 1)[1], 1)
    return CFG.get(key)

def _set_override(key, val):
    ov = TUNING.setdefault("overrides", {})
    if key.startswith("weights."): ov.setdefault("weights", {})[key.split(".", 1)[1]] = val
    else: ov[key] = val

def cmd_tune():
    """Apply Claude's weekly proposals (weekly_out.txt) within guardrails; loosening safety -> pending for Ray."""
    import re
    txt = open(os.path.join(HERE, "weekly_out.txt")).read()
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", txt, re.S)
    prop = json.loads(blocks[-1], strict=False) if blocks else {}   # strict=False: tolerate raw newlines in notebook text
    if prop.get("notebook"):
        open(os.path.join(HERE, "learnings.md"), "w").write(prop["notebook"])
    report = re.sub(r"```json\s*\{.*?\}\s*```", "", txt, flags=re.S).strip()
    os.makedirs(os.path.join(HERE, "weekly"), exist_ok=True)
    open(os.path.join(HERE, "weekly", datetime.now().strftime("%Y-%m-%d") + ".md"), "w").write(report)
    applied, pending, refused = [], [], []
    for ch in prop.get("changes", []):
        key, reason, n = ch.get("key"), ch.get("reason", ""), int(f(ch.get("evidence_n")))
        if key not in TUNABLE: refused.append(f"{key}: not tunable"); continue
        lo, hi, step, sdir = TUNABLE[key]; cur = f(_get(key)); new = f(ch.get("value"))
        if n < MIN_EVIDENCE: refused.append(f"{key}: only {n} outcomes (need {MIN_EVIDENCE})"); continue
        new = max(lo, min(hi, new)); new = cur + max(-step, min(step, new - cur))   # clamp to bounds and weekly step
        if new == cur: refused.append(f"{key}: already at its limit ({cur})"); continue
        if isinstance(_get(key), int) and key != "min_age_h": new = int(round(new))
        entry = {"date": datetime.now().strftime("%Y-%m-%d"), "key": key, "from": cur, "to": new, "reason": reason, "evidence_n": n}
        loosening = sdir and ((sdir == "down" and new > cur) or (sdir == "up" and new < cur))
        if loosening: pending.append(entry); continue
        _set_override(key, new); applied.append(entry)
    TUNING.setdefault("changelog", []).extend(applied)
    TUNING["pending"] = [p for p in TUNING.get("pending", []) if p["key"] not in {x["key"] for x in pending}] + pending
    json.dump(TUNING, open(TUNING_PATH, "w"), indent=1)
    msg = (f"Applied {len(applied)} change(s): " + "; ".join(f"{a['key']} {a['from']}->{a['to']}" for a in applied) if applied else "No auto changes.")
    if pending: msg += f"\n{len(pending)} safety loosening(s) need YOUR approval: " + "; ".join(f"{p['key']} {p['from']}->{p['to']}" for p in pending)
    ntfy("Trencher weekly report ready", msg + "\nOpen the dashboard for details.", prio="high" if pending else "default")
    log(f"tune: applied={applied} pending={pending} refused={refused}")
    print(msg)

def cmd_approve():
    """scanner.py approve <key|all> — apply a pending safety change that Ray approved."""
    want = sys.argv[2]
    keep = []
    for p in TUNING.get("pending", []):
        if want in ("all", p["key"]):
            _set_override(p["key"], p["to"]); TUNING.setdefault("changelog", []).append({**p, "approved_by": "Ray"})
        else: keep.append(p)
    TUNING["pending"] = keep
    json.dump(TUNING, open(TUNING_PATH, "w"), indent=1); print("approved", want)

if __name__ == "__main__":
    {"scan": cmd_scan, "track": cmd_track, "record": cmd_record, "stats": cmd_stats, "export": cmd_export,
     "analyze": cmd_analyze, "tune": cmd_tune, "approve": cmd_approve}[sys.argv[1]]()
