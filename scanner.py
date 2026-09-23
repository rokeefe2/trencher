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
DB = sqlite3.connect(os.path.join(HERE, "trencher.db"))
NOW = time.time()

DB.executescript("""
CREATE TABLE IF NOT EXISTS seen (chain TEXT, token TEXT, first_seen REAL, last_result TEXT, score REAL,
  PRIMARY KEY(chain, token));
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
    return sum(parts.values()), parts, {"turnover_1h": round(turnover, 2), "buy_ratio_1h": round(buy_ratio, 2),
                                        "price_change": c["pc"], "buyers_6h": b6, "liq_to_mcap": round(lm, 3)}

def holder_check(fails, s):
    if f(s.get("holders")) < CFG["min_holders"]:
        fails.append(f"only {int(f(s.get('holders')))} holders (too few, or data not ready)")
    return fails, s

def cmd_scan():
    cands = []
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
                continue
            d = dx.get(c["token"], {})
            total, parts, metrics = score(c, s, d)
            DB.execute("INSERT OR REPLACE INTO seen VALUES (?,?,?,?,?)", (chain, c["token"], NOW, "SCORED", total))
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
    rv = json.loads(blocks[-1])
    cands = {c["token"]: c for c in json.load(open(os.path.join(HERE, "candidates.json")))["candidates"]}
    slots = json.load(open(os.path.join(HERE, "candidates.json")))["slots_left_today"]
    for v in rv.get("verdicts", []):
        c = cands.get(v.get("token"))
        if not c: continue
        DB.execute("UPDATE seen SET last_result=? WHERE chain=? AND token=?", (f"{v.get('verdict')}: {v.get('reason','')[:300]}", c["chain"], c["token"]))
        if v.get("verdict") != "PICK" or slots <= 0: continue
        slots -= 1
        price = c["price_usd"]; stake = CFG["paper_stake"]
        DB.execute("INSERT INTO picks (chain,token,symbol,name,picked_at,entry_price,stake,score,reason,tokens_left,last_price,peak) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (c["chain"], c["token"], c["symbol"], c["name"], NOW, price, stake,
                   c["score"], v.get("reason", ""), stake / price, price, price))
        ntfy(f"PAPER PICK: {c['symbol']} ({c['chain']}) score {c['score']}",
             f"{v.get('reason','')[:300]}\nMcap ${c['mcap_usd']:,} | Liq ${c['liquidity_usd']:,} | Age {c['age_h']}h\n"
             f"Paper entry ${price:.8g} x ${stake}", c.get("dexscreener"), "high")
        log(f"PICK {c['symbol']} {c['token']} @ {price}")
    DB.commit()

def cmd_track():
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
        status = DB.execute("SELECT status FROM picks WHERE id=?", (pid,)).fetchone()[0]
        if status == "open":
            if not took and mult >= 2:          # take original stake out
                sell = stake / px; left -= sell; realized += stake; took = 1
                upd.update(tokens_left=left, realized=realized, took_stake=1)
                ntfy(f"{sym} hit 2x (paper)", f"Took the ${stake:.0f} stake back out. Riding the rest on house money.", prio="default")
            close = None
            if mult <= 1 - CFG["stop_loss_pct"] / 100: close = "stop loss"
            elif not took and age_h >= CFG["no_move_hours"] and mult < 1 + CFG["no_move_min_gain_pct"] / 100: close = "no move in 12h"
            elif age_h >= 72: close = "72h max hold"
            if close:
                upd.update(status="closed", realized=realized + left * px, tokens_left=0, closed_at=NOW, close_reason=close)
                log(f"CLOSE {sym}: {close} at {mult:.2f}x")
        sets = ",".join(f"{k}=?" for k in upd)
        DB.execute(f"UPDATE picks SET {sets} WHERE id=?", (*upd.values(), pid))
    # pools that vanished for >6h after 72h window: count as total loss
    DB.execute("UPDATE picks SET status='closed', close_reason='no price (pool gone)', closed_at=? "
               "WHERE status='open' AND picked_at<? AND (last_price IS NULL OR last_price=entry_price)", (NOW, NOW - 78 * 3600))
    DB.commit()

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
            "tokens_left", "realized", "took_stake", "p1h", "p6h", "p24h", "p72h", "last_price", "peak", "closed_at", "close_reason"]
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
    out = {"updated_at": NOW, "config": {k: v for k, v in CFG.items() if k not in ("ntfy_topic", "email")},
           "summary": {"picks": len(picks), "open": sum(p["status"] == "open" for p in picks),
                       "staked": sum(p["stake"] for p in picks), "value": round(sum(p["value_now"] for p in picks), 2),
                       "pnl": round(sum(p["pnl"] for p in picks), 2),
                       "win_rate": round(sum(p["pnl"] > 0 for p in closed) / len(closed), 2) if closed else None,
                       "scanned": sum(counts.values()), "outcomes": counts,
                       "incubating": DB.execute("SELECT COUNT(*) FROM incubator").fetchone()[0]},
           "reject_reasons": sorted(reasons.items(), key=lambda x: -x[1])[:15],
           "picks": picks, "recent": seen,
           "last_log": open(os.path.join(HERE, "logs", datetime.now().strftime("%Y-%m-%d") + ".log")).read()[-4000:]
                       if os.path.exists(os.path.join(HERE, "logs", datetime.now().strftime("%Y-%m-%d") + ".log")) else ""}
    json.dump(out, open(os.path.join(HERE, "dashboard.json"), "w"), default=str)
    # prune: seen >7d, logs >3d
    DB.execute("DELETE FROM seen WHERE first_seen<?", (NOW - 7 * 86400,)); DB.commit(); DB.execute("VACUUM")
    for fn in os.listdir(os.path.join(HERE, "logs")):
        fp = os.path.join(HERE, "logs", fn)
        if os.path.getmtime(fp) < NOW - 3 * 86400: os.remove(fp)

if __name__ == "__main__":
    {"scan": cmd_scan, "track": cmd_track, "record": cmd_record, "stats": cmd_stats, "export": cmd_export}[sys.argv[1]]()
