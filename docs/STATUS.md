# Status

The claims pilot, built in phases from `docs/PLAN.md`.

## Built

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db` (or `UNDERCOVER_DB`), created from `data/` on first start. Read operations for the queue, a claim, a policy with its plan and add-ons, a customer's claim history, the policy wording, the agent's instructions (`backend/instructions.md`) and the handlers
- `agent/`: the hello-world skeleton, `run(claim_id, thread_id)` with one tool that calls the health route
- `dashboard/`: one page that shows whether the backend is up
- `e2e/`: one test of that page

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173
- `npm run reset` recreates the database from `data/`, putting every claim back to waiting
- `npm run check` runs every check
