**Notebook (as of 2026-10-12; 61 closed, P&L -$121.35, win 46%)**

**State:** Exits are the strongest part (actual avg 0.96x vs hold-24h 0.43x vs hold-72h 0.18x). Do NOT touch stop/trail/no-move. Safety rules are protective overall (rejects 73% rug, 5% doubled). The problem is entry quality: picks rug about 79% in 24h, worse than passes (62%). About 29 stop-losses at about -$22 (plus two gaps at -$49: SW, SOLgiving) eat the trailing wins. Last 3 weeks: -32 / -34 / -55. This past week, 21 picks netted -$4.77, a near-flat improvement.

**Weights:** momentum and holders set to 0.75 on 9-30 (by Ray). 38 post-change picks: -$88.95 (-$2.34/pick, 45% win) vs pre-change 23 picks -$32.40 (-$1.41/pick), no improvement. On 10-12 I cut holders to 0.5. Holders component inverted: high rugs 88% vs 56% low (n=1129). CHECK next week: stop-loss share of new picks (<45% = good), P&L/pick better than -$1; revert if no better. Momentum at 0.75; leave.

**Scoring:** buckets non-monotonic (70-79 best: rug 61%, median 0.12; 80+ rug 76%, median 0.04). Buyer_breadth maxed by 90% of coins (useless without a tighter threshold; owner). Liquidity is the only sensible component. Social high is worse (doubled 4% vs 13%, n=77); consider cutting social weight to 0.75 if still true next week. Survival has a slight edge, small n.

**Claude Stage 3:** picks median 24h 0.04 vs passes 0.10, rug 79% vs 62%, doubled 6% vs 14%. The review is not adding value (negative two weeks running). The control (random-pick) data is still null; need >=20 closed on each side. Suggest the owner revisit the review prompt: demand evidence of organic buying and no early sell pressure, and penalise 80+ score hype.

**Entry signals:** 5-min spike >20% shows no useful separation (n=134 yes; slightly worse: down40 50% vs 43%). Do not enable.

**Safety watchlist (no action):** contract not verified (rug 44%, doubled 23%, n=146); mint/freeze rules (rug 12-22%, doubled <5%, n~20-35, loosening gains nothing); honeypot (n=25, doubled 56%, but can't-sell is a real risk, do not loosen).

**Ideas for owner to build:**
1. Early-rug filter: many picks hit ~0.01x within 1h; add a first-hour sell-pressure or liquidity-drop check before entry.
2. Tighter buyer_breadth threshold so it discriminates.
3. Smaller stake or a size cut on 80+ scores (they do worse).
4. Gap-protection: cap stake on thin-liquidity coins, since two stops gapped to -$49.
5. Partial take-profit on fast spikes.

**Next week:** the holders=0.5 verdict, whether Claude control data accumulates, 80+ bucket recovery, stop-loss share, and the go-live P&L and weekly-profit checks.