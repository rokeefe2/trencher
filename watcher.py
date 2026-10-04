#!/usr/bin/env python3
"""Exit watcher: checks open paper picks every few seconds (config watch_tick_s) and fires ladder sells / stops immediately.

Runs inside a GitHub Actions job for up to WATCH_MINUTES, then exits (the next scheduled run picks up).
It never writes the main data branch. Sells go to the `exits` branch (events.jsonl + heartbeat.json);
the 15-minute scanner applies them to the database. Decisions use scanner.decide_exit, so both agree.
"""
import json, os, subprocess, time, urllib.request, uuid

EXITS = os.environ["EXITS_DIR"]
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
RUN_FOR = float(os.environ.get("WATCH_MINUTES", "345")) * 60

import scanner as S   # shared config + decide_exit + ntfy (scanner opens its own DB copy; we don't write it)

# Seconds between price checks. Each check is one DexScreener request per chain with open picks (their limit is
# 300/min), so 5s is ~24/min at most; the floor keeps a bad config value from hammering the API.
TICK = max(2.0, float(S.CFG.get("watch_tick_s", 5)))
# GitHub skips scheduled runs when it's busy (Oct 3: 39 of 96 scans ran, with gaps up to 7.5h). The watcher runs
# around the clock, so it starts a scan itself when the data is older than this. Normal cron cadence keeps data
# under ~20 min old, so this only fires when a scheduled run was dropped.
SCAN_STALE = float(S.CFG.get("scan_stale_min", 22)) * 60
KICK_COOLDOWN = 10 * 60

def gh_raw(path, ref):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{path}?ref={ref}",
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.raw",
                                          "User-Agent": "trencher-watcher"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def gh_api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "trencher-watcher"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw) if raw else None

def kick_scan(age_s):
    """Start the scan workflow unless one is already queued or running. True if it dispatched one."""
    for status in ("in_progress", "queued", "pending", "waiting"):
        if gh_api("GET", f"actions/workflows/scan.yml/runs?status={status}&per_page=1").get("total_count"):
            return False
    # workflow_dispatch is one of the two events a GITHUB_TOKEN may trigger (needs actions: write in watch.yml)
    gh_api("POST", "actions/workflows/scan.yml/dispatches", {"ref": os.environ.get("GITHUB_REF_NAME") or "main"})
    S.log(f"watcher started a scan: data was {age_s / 60:.0f} min old (scheduled run skipped)")
    return True

def git(*a):
    subprocess.run(["git", "-C", EXITS, *a], check=True, capture_output=True)

def push(msg):
    git("add", "-A")
    git("commit", "-qm", msg, "--allow-empty")
    git("push", "-qf", "origin", "HEAD:exits")

def load_events():
    fp = os.path.join(EXITS, "events.jsonl")
    return [json.loads(l) for l in open(fp)] if os.path.exists(fp) else []

def main():
    git("config", "user.name", "trencher-watcher"); git("config", "user.email", "trencher-watcher@users.noreply.github.com")
    git("checkout", "-q", "--orphan", "w")   # keep the exits branch to a single commit
    events = [e for e in load_events() if e["t"] > time.time() - 7 * 86400]   # older ones were applied long ago
    with open(os.path.join(EXITS, "events.jsonl"), "w") as f:
        for e in events: f.write(json.dumps(e) + "\n")
    applied = set()          # (pick_id, level) / (pick_id, "close") already fired by any watcher run
    for e in events:
        applied.add((e["pick_id"], e["level"]) if e["kind"] == "ladder" else (e["pick_id"], "close"))
    peaks, picks, last_sync, last_push, last_kick, start = {}, [], 0, 0, 0, time.time()
    S.log("watcher started")
    while time.time() - start < RUN_FOR:
        now = time.time()
        if now - last_sync > 30:   # refresh the pick list (new picks, closes applied by the scanner); ~120 API calls/hour
            try:
                dash = gh_raw("dashboard.json", "data")
                picks = [p for p in dash.get("picks", []) if p["status"] == "open"]
                last_sync = now
                age = now - (dash.get("updated_at") or now)
                if age > SCAN_STALE and now - last_kick > KICK_COOLDOWN:
                    last_kick = now   # also after a failed or skipped attempt, so we don't retry every 30s
                    print("data", round(age / 60), "min old; scan started:", kick_scan(age))
            except Exception as ex:
                print("sync failed:", ex)
        new_events = []
        for chain in {p["chain"] for p in picks}:
            toks = [p["token"] for p in picks if p["chain"] == chain]
            prices = {t: d["price"] for t, d in S.dex_info(chain, toks).items() if d["price"]}
            for p in picks:
                if p["chain"] != chain or p["token"] not in prices or (p["id"], "close") in applied: continue
                px = prices[p["token"]]
                pk = max(peaks.get(p["id"], 0), p.get("peak") or 0, px); peaks[p["id"]] = pk
                hit = max([p.get("ladder_hit") or 0] + [lvl + 1 for (pid, lvl) in applied if pid == p["id"] and lvl != "close"])
                sells, close, _ = S.decide_exit({"entry_price": p["entry_price"], "ladder_hit": hit, "peak_x": pk / p["entry_price"],
                                                 "picked_at": p["picked_at"]}, px, now, S.CFG)
                for lvl in sells:
                    if (p["id"], lvl) in applied: continue
                    applied.add((p["id"], lvl))
                    new_events.append({"id": uuid.uuid4().hex, "t": now, "pick_id": p["id"], "kind": "ladder", "level": lvl,
                                       "price": px, "peak_price": pk})
                    lx, frac = S.CFG["ladder"][lvl]
                    S.ntfy(f"{p['symbol']} hit {lx}x - sold {int(frac*100)}% (paper)",
                           f"Now {px/p['entry_price']:.2f}x. Locked in profit; the rest keeps riding.", p.get("dexscreener"), "high")
                if close:
                    applied.add((p["id"], "close"))
                    new_events.append({"id": uuid.uuid4().hex, "t": now, "pick_id": p["id"], "kind": "close", "reason": close,
                                       "price": px, "peak_price": pk})
                    S.ntfy(f"{p['symbol']} closed (paper): {close}", f"Exited at {px/p['entry_price']:.2f}x "
                           f"(peak {pk/p['entry_price']:.2f}x).", p.get("dexscreener"), "high")
        if new_events:
            with open(os.path.join(EXITS, "events.jsonl"), "a") as f:
                for e in new_events: f.write(json.dumps(e) + "\n")
        if new_events or now - last_push > 60:   # heartbeat every minute; immediately on a sell
            json.dump({"t": now, "open": len(picks), "peaks": {str(k): v for k, v in peaks.items()}},
                      open(os.path.join(EXITS, "heartbeat.json"), "w"))
            try:
                push("exit" if new_events else "heartbeat"); last_push = now
            except subprocess.CalledProcessError as ex:
                print("push failed:", ex.stderr[-300:] if ex.stderr else ex)
        time.sleep(max(1, TICK - (time.time() - now)))
    S.log("watcher finished its shift")

if __name__ == "__main__":
    main()
