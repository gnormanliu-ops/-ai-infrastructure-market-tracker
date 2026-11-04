# AI Infrastructure Market Tracker

[![Tests](https://github.com/gnormanliu-ops/-ai-infrastructure-market-tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/gnormanliu-ops/-ai-infrastructure-market-tracker/actions/workflows/tests.yml)

An independent Financial Data Analytics course project tracking 15 publicly traded companies in energy, electrical equipment, construction, servers, and physical infrastructure. Not the Job Watcher project.

## Tracking

Each UTC run saves Stooq daily OHLCV CSV responses as compressed raw files, then rebuilds `data/history.csv` from raw inputs. Primary numerical columns are `close_usd` (USD per share) and `volume_shares` (shares). `open_usd`, `high_usd`, and `low_usd` are additional daily prices (USD/share); `market_date` is the actual trading day. `date` is the collection UTC date. `item_id` is the stock ticker, `item` is the company name, `source` is Stooq, and `sector` is the tracked industrial category.

## Pages

`index.html` (Today), `browse.html` (Browse, filters, sorting, persistent favorites), and `trends.html` (Trends with browser-calculated analyses) share `style.css` and `app.js`. `manifest.webmanifest` and `sw.js` provide installable offline access.

## Pipeline

- `companies.json`: 15 named tracking items.
- `pipeline.py`: downloads, validates, compresses source responses, rebuilds history and generates status + daily issue report.
- `data/raw/YYYY-MM-DD/*.csv.gz`: source-native compressed snapshots (created on valid downloads).
- `data/history.csv`: deterministic normalized history. Rebuild with `python pipeline.py --build-only`.
- `data/status.json`: UTC run time, earliest successful raw day, successful dates count, current items, entrants/exits, individual source statuses.
- `.github/workflows/daily.yml`: scheduled and manually triggered pipeline, git commit, Issues and GitHub Pages deployment.
- `.github/workflows/tests.yml`: pytest on push.
- `tests/test_pipeline.py`: source conversion, movement calculations, repeated-date rebuild tests.
- `requirements.txt`: test dependencies.

**Move rule:** rank tracked items by absolute percentage change in closing price between their two most recent collected UTC dates, display top five and show old/new close. Daily Issues include new/gone items, including no-move days.

**Source:** Stooq, CSV (`https://stooq.com/q/d/l/`), fetched separately for each of the 15 tickers with no login. Only the last available daily trading row up to each UTC run date is kept when building a normalized row; compressed raw responses are retained for reproducibility. Data availability is not guaranteed; failing sources must be reported without aborting the daily run. No demo prices are published as live history.

The source and seven-day run requirement must be verified using GitHub Actions. The first-run and due dates are posted on Blackboard. This repository is a course project, not investment advice.
