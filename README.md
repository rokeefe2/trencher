# Trencher

A **paper-trading** meme-coin scanner for Solana and Base. No wallet, no real money.

Every 15 minutes GitHub Actions:
1. **Discovers** coins 1–48h old (GeckoTerminal trending + an incubator of new pools, DexScreener feeds).
2. **Rejects anything unsafe**: mint/freeze authority, unlocked liquidity, top-10 wallets > 30%, creator > 5%,
   linked-wallet networks, honeypots/sell taxes, < 100 holders, < $20k liquidity (RugCheck, GoPlus, Honeypot.is).
3. **Scores** survivors /100 on momentum, holder health, liquidity depth, buyer breadth, socials, survival.
4. **Claude reviews** the top candidates (no tools, data only) and picks at most 3 per day.
5. Sends a phone alert (ntfy) and tracks each pick as a $50 paper trade: take stake out at 2×, stop at −40%,
   exit if < +20% after 12h, max hold 72h.

State lives on the `data` branch (a single force-pushed commit). `dashboard/` is a local viewer.
Tunables are in `config.json`.

*Paper trading only. Not financial advice.*
