**Notebook (as of 2026-11-09; 118 closed, P&L -$79.9, win 48%)**

**State:** Exits are the strongest part: actual avg 0.986x vs hold-24h 0.716x vs hold-72h 0.577x. Do NOT touch stop/trail/no-move. Safety rules protect overall (rejects 68% rug, 5% doubled). Weekly P&L: -5 / -78 / +93 (first green week in 3). Results are outlier-driven (KIMCHIBULL +103, QT +65, BTC +61). Gap-downs (~-$48: SW, SOLgiving, ALIVE, DOPEUS, Pikachu, LumiBot) and stop-losses (~-$22) are the main leakage.

**Weights:** momentum 0.75, holders 0.5 (since 10-12), social 0.75 (since 10-19), survival 1.25 (since 10-26). Survival test PASSED so far: 27 picks since change, stop share 33% (<40% target), P&L +$14.9 (+$0.55/pick). Keep at 1.25; reconsider only if stop share goes >=45% over next ~20 picks. Social test: ~50 picks since change, inconclusive, hold. Make at most one weight change per week for clean attribution.

**Scoring:** buckets non-monotonic; 60-69 is best (rug 47%), 80+ no better than 70-79 (rug 70%). Buyer_breadth maxed by 87%, liquidity by 66% (useless; owner should tighten thresholds). Survival best component; holders inverted (high rug 83% vs 51%); social mildly negative; momentum mildly positive.

**Claude Stage 3:** picks median 24h 0.02 vs passes 0.11 (go-live check fails, but metric is noisy: post-exit moves + feed quirk). Control (n=57 each): Claude +$41.5 vs random -$188.5, win 51% vs 40%, stop 39% vs 46%. Review appears to add value (n>=20 each) but verify ex-outlier. Alt exits (n=53): normal +$36.3 vs alt -$16.3; keep normal ladder.

**Entry signals:** 5-min spike >20%: down40 at 1h 56% vs 41% (n=114/874), up50 at 1h 5% vs 11%, median 24h same (0.07 vs 0.08). Mild; not enabling. Would only recommend as a size-reducer, not a block.

**Safety watchlist (no action):** contract not verified (rug 59%, doubled 25%, n=142) only loosening candidate, evidence insufficient; LP unlocked/top10 block 15-25% winners but 78-90% rug, don't loosen; honeypot doubled 45% but can't-sell risk (n=31).

**Data quirk:** many trailing-stop wins show ~0.01x at all checkpoints (TON, GAMBIT, HYPEDOG, TRACER, QW, Send, CATBOT, HODL; PRIVACY 99.9x at 1h). Likely price-feed/decimal issue in checkpoint source; owner should check. Checkpoint stats for those are unreliable.

**Ideas for owner to build:**
1. Early-rug filter: first-hour sell-pressure/liquidity-drop check.
2. Tighter buyer_breadth and liquidity thresholds so they discriminate.
3. Smaller stake on thin-liquidity coins (gap protection).
4. Per-coin loss cap via liquidity-depth check.
5. Fix checkpoint price source.

**Next week:** survival verdict continues (~20 more picks), social verdict, Claude vs random ex-outlier, whether a second profitable week arrives, 80+ bucket, spike-signal as a stake reducer.