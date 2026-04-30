# Release validation checklist

Use this checklist before cutting a release or opening a release PR for the trading app. The checks are intentionally local, read-only where possible, and biased toward paper/sandbox safety.

## Quick command

```bash
python release_validate.py
```

This runs:

1. Secret and artifact hygiene checks.
2. Targeted backend tests for trade ledger, broker manager, OANDA integration, and live automation safety gates.
3. Frontend typecheck/build via `npm run build`.
4. Read-only API smoke checks through FastAPI `TestClient`.

Run individual sections when iterating:

```bash
python release_validate.py --security
python release_validate.py --backend
python release_validate.py --backend --full-backend
python release_validate.py --full-backend
python release_validate.py --frontend
python release_validate.py --smoke
```

## Prerequisites

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"

cd frontend
npm ci
cd ..
```

Keep `.env` local. Never commit API keys, broker tokens, local databases, logs, generated screenshots, trained model artifacts, or frontend build output.

## Backend validation

Targeted release checks:

```bash
pytest \
  trading_bot/tests/test_trade_ledger.py \
  trading_bot/tests/test_broker_manager.py \
  trading_bot/tests/test_oanda_broker.py \
  trading_bot/tests/test_automation_safety.py
```

Full backend suite:

```bash
pytest trading_bot/tests
```

Expected result: targeted tests pass. Full-suite failures must be documented with the failing test, error, suspected cause, and whether the failure is release-blocking.

## Frontend validation

```bash
cd frontend
npm run build
```

Expected result: TypeScript compilation succeeds and Vite produces `frontend/dist/`. The build output must remain ignored by Git.

## API smoke validation

Automated smoke checks cover these read-only routes:

| Route | Expected result |
| --- | --- |
| `GET /api/health` | `200`, `status=healthy` |
| `GET /api/settings` | `200` JSON object |
| `GET /api/broker/list` | `200` broker list with sanitized status only |
| `GET /api/broker/active` | `200` active broker object or `null` |

For a running local server:

```bash
uvicorn trading_bot.api.server:app --reload
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/broker/list
curl -fsS http://127.0.0.1:8000/api/broker/active
```

## UI smoke validation

Start the backend and frontend:

```bash
uvicorn trading_bot.api.server:app --reload
cd frontend && npm run dev
```

Manual QA checklist:

- Dashboard loads without console errors and shows backend health as connected.
- Live Trading loads without placing orders automatically.
- Broker status displays sanitized connection state only.
- Settings loads broker list and app settings.
- Automation controls remain disabled or gated unless live mode, broker environment, account risk, and signal quality all pass safety checks.

Record the browser, viewport, pages checked, and any known limitations in release notes or the Linear issue.

## Security and artifact hygiene

Before release:

```bash
python release_validate.py --security
git status --short
git ls-files "*.png" "*.jpg" "*.jpeg" "*.webp" "logs/*" "data/*" "models/*" ".env" ".env.*"
```

Expected result:

- Only `.env.example` may be tracked from environment files.
- No tracked files under `data/`, `logs/`, or `models/`.
- No tracked local screenshots or generated frontend build artifacts.
- No obvious secret patterns in tracked source files.

## Release note template

```markdown
## ONE-14 release validation notes

- Backend targeted tests:
- Frontend build:
- API smoke checks:
- UI smoke checks:
- Secret/artifact hygiene:
- Known limitations:
- Release decision:
```