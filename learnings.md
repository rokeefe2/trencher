**Notebook (as of 2026-11-16; 125 closed, P&L -$169.6, win 47%)**

**State:** Weekly P&L -78 / +93 / -89. The green week did not repeat; results are outlier-driven (KIMCHIBULL +103, QT +65, BTC +61). Exits remain the strongest part: actual avg 0.973x vs hold-24h 0.76x vs hold-72h 0.572x. Do NOT touch stop/trail/no-move. Main leakage: stop-losses (~-$22, ~42% of picks) and gap-down rugs (~-$48: ANT, LumiBot, ALIVE, DOPEUS, Pikachu, SW, SOLgiving). Last week 4 of 5 stop-losses were already <=0.5x at 1h (SPEED, SWIF, ANT near 0.005x), so early-dead coins are being entered.

**Weights:** momentum 0.75, holders 0.5 (floor), social 0.75 (since 10-19), survival 1.25 (since 10-26). Survival test now INCONCLUSIVE: 32 closed picks since change, stop share ~41%, P&L ~-$54 (-$1.7/pick); last week looked like a pass, this week it slipped. Undo only if stop share >=45% over next ~20 picks; confirm if <40% and P&L/pick >0. Social: inconclusive, hold. One weight change per week max.

**Scoring:** buckets non-monotonic; 60-69 best (rug 48%), 80+ worse (rug 70%). Holders strongly inverted (high rug 82% vs 48%), survival best separator. Buyer_breadth (87% at max) and liquidity (65%) are useless as scored; thresholds need tightening (owner). Social mildly negative.

**Claude Stage 3:** control (n=64 each): Claude -$47.5 vs random -$190.1, win 48% vs 44%, stop 42% vs 44%. Better than random but edge shrank vs last week (+$41.5 vs -$188.5) and win/ladder rates are near identical; value plausible, not proven. Picks median 24h 0.02 vs passes 0.11 (go-live fails, metric noisy). Alt exits (n=60): normal -$52.7 vs alt -$122.2; keep normal ladder.

**Entry signal (5-min spike >20%):** 1h down40 68% vs 43% (yes n=68), up50 4% vs 13%, median 24h same. Crashes early but no final-outcome difference; at most a stake-reducer, not a block.

**Safety watchlist (no action):** contract not verified (rug 65%, doubled 22%, n=103) only loosening candidate; LP unlocked/top10 block 14-22% winners but 76-88% rug, don't loosen. Mint-authority/creator-can-mint rules show ~6% rug but n<20; watch.

**Data quirk:** many trailing-stop wins show ~0.01x at all checkpoints; checkpoint feed unreliable for those.

**Ideas for owner to build:**
1. Early-rug filter: first-hour sell-pressure/liquidity-drop check before entry.
2. Tighter buyer_breadth and liquidity thresholds.
3. Smaller stake on thin-liquidity coins / spike coins (gap protection).
4. Liquidity-depth per-coin loss cap.
5. Fix checkpoint price source.
6. Prompt tweak for Claude review: penalize coins already down >40% from peak at entry.

**Next week:** survival verdict (~20 more picks), social verdict, Claude vs random ex-outlier, whether any week turns green, 80+ bucket underperformance.