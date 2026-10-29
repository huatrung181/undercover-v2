# Status

The claims pilot, built in phases from `docs/PLAN.md`.

## Built

- `backend/`: FastAPI on SQLite. The database is `backend/undercover.db` (or `UNDERCOVER_DB`), created from `data/` on first start. Read operations for the queue, a claim, a policy with its plan and add-ons, a customer's claim history, the policy wording, the agent's instructions (`backend/instructions.md`) and the handlers
- The claim workflow in the backend: `run_agent` sets a waiting claim in progress and runs the agent as a background task; `record_step` and `list_steps`; `record_decision`, `pay_claim` and `sign_off_claim`. Statuses are waiting, in progress, waiting for sign-off and decided. The status settles when the agent's run ends: from its decision, or back to waiting with an error step if there is none. A payment over $1,000 is refused with a 403 until a handler signs off, and the sign-off pays the approved payout
- `agent/`: the UnderCover Agent, `run(claim_id, thread_id)`, built with `create_agent` on OpenRouter (GPT-6 Luna at low reasoning effort, or `MODEL_NAME`). It reads its instructions from the backend and has six tools, each one API call: `get_claim`, `get_policy`, `get_claim_history`, `get_policy_wording`, `record_decision` and `pay_claim`. It posts each step to the backend as it works
- `dashboard/`: React and Vite, in the UnderCover brand with light and dark modes. The queue, with a count of claims in each status and a table that refreshes every 3 seconds, and the agent's instructions, read only. Pages are switched on the URL hash: `#/`, `#/claims/<id>`, `#/instructions`
- `e2e/`: one test that the queue loads

## Running it

- `npm run dev` starts the backend on port 8000 and the dashboard on port 5173
- `npm run reset` recreates the database from `data/`, putting every claim back to waiting
- `uv run -m agent CLM-1001` runs the agent on one claim through the running backend and prints its steps and decision
- `npm run check` runs every check
