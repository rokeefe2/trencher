**Running notes (as of 2026-10-05, 40 closed picks, P&L -$116.58, win 45%)**

**State:** Exits are the strongest part (actual avg 0.94x vs hold-24h 0.24x vs hold-72h 0.075x). Do not touch stop/trail/no-move. Safety rules look protective overall (rejects: 75% rug, 5% doubled). Problem is entry quality: picks rug 76% within 24h, same as rejects. About 22 stop-losses at about -$22 each eat the trailing-stop wins (about 16 at +$20).

**Weights:** momentum and holders were both set to 0.75 on 9-30 (by Ray). Only 14-17 picks since, net negative. Do not judge until about 20+ post-change picks. Holders component is inverted: high holders rug 90% vs 58% low (n=730). If still bad next week with more data, cut holders to 0.5.

**Scoring:** buckets not monotonic (70-79 best: rug 61%, median 0.11; 80+ rug 79%, median 0.04). Buyer_breadth maxed by 91% of coins, useless without a tighter threshold (owner). Liquidity component is the only sensible one (low scores rug 86% vs 64%). Social high is worse (doubled 4% vs 14%, n=51). Survival slight edge, small n.

**Claude Stage 3:** picks median 24h 0.04 vs passes 0.08, rug 76% vs 65%, doubled 6% vs 15%. Review is not adding value. Watch; if still worse next week, suggest owner revisit the prompt or require stricter criteria.

**Entry signals:** 5-min spike >20% shows no separation (n=79 yes). Not worth enabling.

**Safety watchlist (no action):** 'contract not verified' rug 44%, doubled 19%, n=99 (weakest rug rate, still blocks real rugs). Mint/freeze authority rules: rug 12-16%, doubled about 5%, n about 20; loosening gains nothing. Honeypot (n=15) doubled 60%: likely false positives, need n>=20.

**Ideas for owner to build:**
1. Early-rug filter: many picks hit about 0.01x within 1h. Check for first-hour sell pressure or a liquidity-drop signal before entry.
2. Partial take-profit on fast spikes (SPLIT 2.3x then stopped).
3. Tighter buyer_breadth threshold so it discriminates.
4. A ladder-style size cut on 80+ scores (they do worse).

**Next week:** check whether post-9-30 picks improve, whether the 80+ bucket recovers, stop-loss frequency, and the go-live P&L check. Holding steady is right until about 20 new post-change picks exist.