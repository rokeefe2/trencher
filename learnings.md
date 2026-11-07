**Notebook (as of 2026-11-02; 105 closed, P&L -$172.7, win 47%)**

**State:** Exits are the strongest part: actual avg 0.967x vs hold-24h 0.706x vs hold-72h 0.625x. Do NOT touch stop/trail/no-move. Safety rules protect overall (rejects 70% rug, 5% doubled). Problem is entry quality: picks rug 75% at 24h vs passes 62%; 80+ scores are no better than 60-79. Stop-losses (~-$22) and gap-downs (~-$48: SW, SOLgiving, ALIVE, DOPEUS, Pikachu, LumiBot) eat the trailing wins. Weekly P&L: +32 / -5 / -78. Results are outlier-driven (KIMCHIBULL +$103).

**Weights:** momentum 0.75, holders 0.5 (since 10-12), social 0.75 (since 10-19), survival 1.25 (since 10-26). Survival test: only 14 picks since change, stop share 50% (undo threshold >=45%) but n<20; if next ~10 picks keep stop share >=45% and P&L/pick <=0, revert survival to 1.0. Social test still pending (~25 picks); undo if doubled rate flips or stops rise. Attribution is muddy: make no more than one weight change per week.

**Scoring:** buckets non-monotonic. Buyer_breadth maxed by 88% and liquidity by 68% (useless; owner should tighten thresholds). Survival best component. Holders inverted (high rug 84% vs 55%). Social negative. Momentum now mildly positive (doubled 15% vs 11%): watch.

**Claude Stage 3:** picks median 0.03 vs passes 0.10 (go-live check fails). Control (n=44 each): Claude -$51.4 vs random -$70.6, win 48% vs 41%, stop 45% vs 48%: near-equal, not proven. Alt exits (n=40): normal -$56.6 vs alt -$98.6; keep normal ladder. If random keeps matching Claude, revise review prompt: demand organic buying, no early sell pressure, penalize 80+ hype.

**Entry signals:** 5-min spike >20%: down40 at 1h 56% vs 42% (n=158/1070), up50 8% vs 11%, median 24h identical. Weak; do not enable yet.

**Safety watchlist (no action):** contract not verified (rug 55%, doubled 26%, n=199) is the only loosening candidate, need stronger evidence; LP unlocked / lp locked / top10 block 17-26% winners but 78-91% rug, don't loosen; honeypot doubled 47% but can't-sell risk; mint/freeze rules cost little (rug ~10%, doubled ~6%).

**Data quirk:** many trailing-stop wins show ~0.01x at all checkpoints (TON, GAMBIT, HYPEDOG, TRACER, QW, Send, CATBOT; PRIVACY 99.9x at 1h). Likely a price-feed/decimal-scaling issue in the checkpoint source; owner should check. Checkpoint stats for those coins are unreliable.

**Ideas for owner to build:**
1. Early-rug filter: first-hour sell-pressure/liquidity-drop check.
2. Tighter buyer_breadth and liquidity thresholds.
3. Smaller stake on 80+ scores and thin-liquidity coins (gap protection).
4. Partial take-profit on fast spikes.
5. Cap per-coin loss (liquidity-depth check) for gaps.

**Next week:** survival verdict (need ~20 picks), social verdict, Claude vs random ex-outlier, whether a profitable week arrives, the 80+ bucket.