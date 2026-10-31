**Notebook (as of 2026-10-26; 91 closed, P&L -$95.5, win 46%)**

**State:** Exits are the strongest part: actual avg 0.979x vs hold-24h 0.795x vs hold-72h 0.615x. Do NOT touch stop/trail/no-move. Safety rules protect overall (rejects 71% rug, 5% doubled). Problem is entry quality: picks rug 76% at 24h vs passes 63%; score 80+ is worse than 60-79 (rug 75% vs 62%). Stop-losses of about -$22 each and gap-downs of about -$48 (SW, SOLgiving, ALIVE, DOPEUS, Pikachu) eat the trailing wins. Weekly P&L: -55 / +32 / -5 / this week -5.5 (15 closed, 7 wins, 6 stops = 40%). This week only profitable because of KIMCHIBULL +$103; without it about -$109. Results are outlier-driven.

**Weights:** momentum 0.75, holders 0.5 (cut 10-12), social 0.75 (cut 10-19), survival 1.25 (raised 10-26). Holders test: 30 closed picks since 10-12, +$26.6 total (+$0.89/pick), stop-loss share 43% (<45% target): mild confirm, keep. Social test: only about 15 picks since the change, still pending; undo if doubled rate flips or stops rise. Survival test: confirm if next ~20 picks have stop share <40% and P&L/pick >0; undo if stop share >=45%. Momentum signal flipped (high now doubles 15% vs 12%): watch, no action. Three weight changes in two weeks, so attribution is muddy; do not change more weights next week.

**Scoring:** buckets non-monotonic. Buyer_breadth maxed by 89% (useless; owner should tighten threshold). Survival best component. Holders inverted (high rug 86% vs 56%). Social negative.

**Claude Stage 3:** picks median 0.04 vs passes 0.09, rug 76% vs 63% (go-live check fails). Control (n=30 each): Claude +$26.6 vs random -$83.4, win 47% vs 33%, stop 43% vs 53%. Direction favors Claude but driven by one outlier; without KIMCHIBULL, about equal to random. Alt exits (n=26 each): +21.4 vs -13.2; keep normal ladder. If random catches up, revise review prompt: demand organic buying, no early sell pressure, penalize 80+ hype.

**Entry signals:** 5-min spike >20%: down40 at 1h 54% vs 44% (n=191/1264), up50 8% vs 12%, doubled 13% vs 14%. Weak; do not enable yet. Re-check with more data.

**Safety watchlist (no action):** contract not verified (rug 51%, doubled 24%, n=238) is the only loosening candidate, need more evidence; LP unlocked / lp locked / top10 block 20-27% winners but 81-92% rug, don't loosen; honeypot doubled 48% but can't-sell risk; mint/freeze rules cost little.

**Data quirk:** many trailing-stop wins show ~0.01x at 1h checkpoint (QW, Send, CATBOT, PRIVACY 99.9x at 1h). Possible price-feed issue or fast pump-and-rug; owner could check checkpoint source.

**Ideas for owner to build:**
1. Early-rug filter: first-hour sell-pressure/liquidity-drop check.
2. Tighter buyer_breadth threshold.
3. Smaller stake on 80+ scores and on thin-liquidity coins (gap protection).
4. Partial take-profit on fast spikes.
5. Cap per-coin loss (limit-sell/liquidity-depth check) for gaps.

**Next week:** survival verdict, social verdict, whether Claude-vs-random holds ex-outlier, whether a 2nd-in-3 profitable week arrives, 80+ bucket.