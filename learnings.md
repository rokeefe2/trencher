**Notebook (as of 2026-11-23; 134 closed, P&L -$270.6, win 46%)**

**State:** Weekly P&L +93 / -89 / -102. Results are outlier-driven (KIMCHIBULL +103, QT +65, BTC +61). Exits are the strongest part: actual 0.96x vs hold-24h 0.75x vs hold-72h 0.56x. Do NOT touch stop/trail/no-move. Leakage: stop-losses (~45% of picks, ~-$22) and gap-down rugs (~-$48: ANT, VICEDORD, LumiBot, ALIVE, DOPEUS, Pikachu, SW, SOLgiving). This week 6 of 9 picks stopped out, and 5 of those were already <=0.6x at 1h (SI, UrAnus ~0.005x): early-dead coins are being entered.

**Weights:** momentum 0.75, holders 0.5 (floor), social 0.75 (since 10-19), survival reverted 1.25 -> 1.0 on 11-23 (the 1.25 test failed: ~41 picks, stop share ~46%, -$3.8/pick). Confirm the revert if the next ~20 picks have stop share <40%; if it stays >=45%, weights aren't the driver and the problem is the entry filters. Social: inconclusive, hold. One weight change at a time.

**Scoring:** buckets non-monotonic; 60-69 best (rug 48%), 80+ worse (rug 67%). Holders inverted (high rug 78% vs 42%), momentum inverted (69% vs 52%), survival the only mild positive separator (54% vs 65%). Buyer_breadth (87% at max) and liquidity (60%) are useless as scored; thresholds need tightening (owner).

**Claude Stage 3:** control (n=73 each): Claude -$149 vs random -$317, win 47% vs 41%, stop 45% vs 48%. Better than random on P&L but ladder/stop rates nearly the same; outlier-driven, value plausible not proven. Picks median 24h 0.02 vs passes 0.15 (go-live fails; picks rug 68% vs passes 55%). Alt exits (n=69): normal -$154 vs alt -$254; keep normal ladder.

**Entry signal (5-min spike >20%):** yes n=42 vs no n=522: 1h down40 74% vs 44%, rug 81% vs 59%, doubled 10% vs 13%, up50 1h 7% vs 12%. Meets the >=40 on each side bar. RECOMMEND owner enable it as a block (or half stake): few winners lost.

**Safety watchlist (no action):** all rules protect (rug 54-90%). LP unlocked (84% rug/23% doubled), contract not verified (73/18), LP locked (79/15) don't loosen. Mint-authority/creator-can-mint (~6-8% rug, n<20), honeypot (doubled 43%, n=14) watch until n>=20.

**Data quirk:** many trailing-stop wins show ~0.01x at all checkpoints; checkpoint feed unreliable.

**Ideas for owner to build:**
1. Early-rug filter: first-hour sell-pressure/liquidity-drop check before entry.
2. Tighter buyer_breadth and liquidity thresholds.
3. Smaller stake on thin-liquidity/spike coins (gap protection).
4. Per-coin loss cap by liquidity depth.
5. Fix checkpoint price source.
6. Claude prompt: penalize coins already down >40% from peak at entry, and cap score trust above ~85 (80+ underperforms).
7. Cap min_score at upper bound or prefer 60-79 band.

**Next week:** survival revert verdict (~20 picks), social verdict, Claude vs random ex-outlier, whether 80+ bucket keeps underperforming, whether any week turns green.