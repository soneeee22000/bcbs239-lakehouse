# bcbs239-lakehouse · dashboard

Next.js 16 + React 19 + Tailwind 4 portfolio dashboard for the
bcbs239-lakehouse reference implementation. Renders the live Bronze /
Silver / Gold layer state, the BCBS 239 DQ scorecard with clean-vs-dirty
drift comparison, and the top RWA aggregations from
`bcbs239_lakehouse.gold.fact_rwa_aggregation`.

## Routes

- `/` — overview: hero, dimension averages, drift table, layer counts,
  architecture flow, BCBS 239 scope table.
- `/scorecard` — full per-(source, dimension) breakdown of the latest
  snapshot + drift comparison + scorer definitions.
- `/pipeline` — Bronze / Silver / Gold stage details, reproduce-locally
  commands.
- `/exposures` — top-N RWA aggregation rows with totals.

## Data flow

```
Databricks workspace (Free Edition)
    │
    │  scripts/export_dashboard_data.py — runs locally, queries the
    │  Databricks SQL warehouse via databricks-sdk
    ▼
dashboard/lib/data/snapshot.json   ← committed to git
    │
    │  Next.js imports snapshot.json statically (no runtime DB calls)
    ▼
Vercel build → live site (no Databricks credentials needed in deploy)
```

The snapshot is committed so Vercel builds work without any Databricks
credentials. Refresh from the repo root after `make refresh`:

```bash
uv run python dashboard/scripts/export_dashboard_data.py
```

## Local dev

```bash
cd dashboard
pnpm install        # or npm install / yarn install
pnpm dev            # Turbopack on http://localhost:3000
pnpm build          # production build
pnpm typecheck      # tsc --noEmit
```

## Deploy

Vercel — point at the `dashboard/` subdirectory:

1. Import the `bcbs239-lakehouse` repo into Vercel
2. Set **Root directory** to `dashboard`
3. Framework preset auto-detects as Next.js
4. No env vars needed — snapshot is committed JSON

## Synthetic-data discipline

Every page surfaces a synthetic-only banner. The repository's
killed-phrase regression test (`tests/test_repo_hygiene.py`) covers
markdown / SQL / Python files; **the dashboard's TypeScript and JSX is
not currently scanned by that test**. If you add copy here, keep it
honest:

- No vendor-displacement language ("replaces X" / "X alternative").
- No "production-grade" / "regulator-ready" framing.
- Approved: "reference implementation", "portfolio piece", "synthetic
  data only".

See [`docs/PRD.md`](../docs/PRD.md) Appendix B for the full killed-
phrase set.
