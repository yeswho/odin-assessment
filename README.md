# Odin Technical Assessment: AI-Assisted Work Intake System

An operations application that receives work items, generates structured AI suggestions, and lets a human review and complete them.

**Stack:** Python 3.12 + FastAPI, React + TypeScript, PostgreSQL 17, SQLAlchemy 2, Alembic and pytest. The frontend uses Vite and plain CSS.

## Setup with Docker

Install Docker with Compose v2. From the project root:

```sh
cp .env.example .env
docker compose up --build
```

- App: http://localhost:3000
- API documentation: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

Compose starts PostgreSQL, waits for it to become healthy, runs Alembic in a one-off migration container, starts FastAPI, and then serves the built React app through nginx. Browser API traffic is proxied to FastAPI under `/api`. Records persist in the named PostgreSQL volume.

The example configuration runs without an API key. The header reports **Mock AI** and each processed item records its provider. This mock is deterministic keyword-based test behavior, not an LLM. The application starts with an empty queue so it never presents sample records as real work.

To stop while preserving records:

```sh
docker compose down
```

The default ports bind to localhost. The example database password is only for local development. Avoid putting this unauthenticated assessment deployment directly on a public network.

## Setup without Docker

Prerequisites: Python 3.12, Node.js 24 (or >=22.12), npm, and a running PostgreSQL server. Create a database/user matching your configuration first; the app does not create databases or users.

Backend, in one terminal:

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

or on windows - to create venv:
.\.venv\Scripts\Activate.ps1 (powershell)
.venv\Scripts\activate (cmd)

Frontend, in another terminal:

```sh
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Step instructions

1. Choose **New work item** and submit an external ID, title and description.
2. Select the request to open its details, then choose **Analyse request**.
3. Review the category, priority, summary and recommended action against the original text.
4. Choose **Complete work item**. Completed records are terminal.
5. In mock mode, start a description with `[fail-once]` to simulate one failed attempt. Analyse it, then choose **Retry analysis**. Its second attempt succeeds.
6. Submit an identical request again: it returns the existing record. Reuse its external ID with different content: it returns `409` and preserves the original.

## Project architecture

The project follows the requested assessment layout. Each backend directory has a small, specific responsibility:

| Location | Responsibility |
| --- | --- |
| `backend/app/api/routes.py` | HTTP routes, request/response types, dependency boundary |
| `backend/app/core/` | Settings, engine/session factory, application error type |
| `backend/app/models/work_item.py` | PostgreSQL-backed work item model and database constraints |
| `backend/app/schemas/work_item.py` | Pydantic input, output and AI validation schemas |
| `backend/app/repositories/work_items.py` | Parameterized SQLAlchemy reads and atomic writes |
| `backend/app/services/work_items.py` | Workflow orchestration, timeouts, AI validation and persistence |
| `backend/app/ai/providers.py` | Small provider protocol, mock and Anthropic HTTP adapter |
| `backend/app/workflow/states.py` | Allowed states and transition rules |
| `backend/app/main.py` | App construction, shared errors, request limits and CORS |
| `backend/alembic/` | Versioned schema migration |
| `backend/tests/` | Unit/API/provider tests and real PostgreSQL integration tests |
| `frontend/src/api/` | Typed fetch client |
| `frontend/src/hooks/` | Queue loading, polling and cancellation |
| `frontend/src/components/` | Creation form, request table, detail panel and status badge |
| `frontend/src/pages/WorkIntakePage.tsx` | Operations page and selection/filter state |

The frontend uses native controls, including a modal `<dialog>` with labels, escape handling and browser focus management. It has loading, empty, error and success states. Failed form submissions preserve the entered text. Polling uses abort signals and request generations to avoid stale results replacing more recent state. AI output is rendered as escaped text.

## API Architecture

| Method | Endpoint | Behavior |
| --- | --- | --- |
| POST | `/api/work-items` | Create: `201`; exact duplicate: `200`; changed duplicate: `409` |
| GET | `/api/work-items` | List, optionally filtered by `status`, with `limit` and `offset` |
| GET | `/api/work-items/{id}` | Read a work item |
| POST | `/api/work-items/{id}/analyse` | Analyse only a `RECEIVED` item |
| POST | `/api/work-items/{id}/retry` | Retry only `FAILED` AI processing |
| PATCH | `/api/work-items/{id}/status` | Complete an item ready for review |
| GET | `/api/health` | Check database connectivity and identify the configured provider |

Example creation:
```sh
curl -i http://localhost:8000/api/work-items \
  -H 'Content-Type: application/json' \
  -d '{"externalId":"CRM-12345","title":"Missing income document","description":"The applicant has not provided the latest payslip."}'
```

## AI configuration

| Setting | Meaning |
| --- | --- |
| `AI_MODE=auto` | Use Anthropic if a key is provided; otherwise use the mock |
| `AI_MODE=mock` | Always use the offline mock |
| `AI_MODE=anthropic` | Require a key |
| `ANTHROPIC_API_KEY` | Server provider credential |
| `ANTHROPIC_MODEL` | Configurable model ID; By default it uses `claude-haiku-4-5-20251001` |
| `AI_TIMEOUT_SECONDS` | Timeout per attempt; default 15 seconds |
| `ANALYSIS_LEASE_SECONDS` | Default 60 seconds |

For real AI, set `AI_MODE=anthropic` and the key in the root `.env` for Compose, or in `backend/.env` for local FastAPI. Restart the backend. Select a model available that supports the forced tool-output configuration. The adapter calls Anthropic's Messages API and requests one structured `submit_analysis` output; it never executes an external action. This follows the [provider's tool schema and forced-output documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools).

If a configured real provider times out or fails, the item becomes `FAILED`. It does not receive a fabricated successful mock result. Users can see the configured provider and the provider used for each attempt.

Returned data must contain a supported category (`DOCUMENT_REQUEST`, `BILLING`, `TECHNICAL_SUPPORT`, `GENERAL`), priority (`LOW`, `MEDIUM`, `HIGH`), and nonempty summary/recommended action strings (at most 2,000 characters each). Missing/extra fields and unexpected values are rejected. Validation happens after provider output, even with a supplied JSON schema. Provider responses are limited to 64 KiB. The prompt treats input as untrusted content; descriptions cannot authorize actions.

The integration is tested through a mocked HTTP transport.

## Technical decisions and trade offs

### 1. Preventing duplicate work items

When a new item is created, the system uses INSERT ... ON CONFLICT DO NOTHING instead of checking first and then inserting. This is safer when two requests arrive at almost the same time.
For analysis and completion, the system checks the current status before updating it. This ensures that only one request can process an item at a time.
The AI call is made outside the database transaction, so the database is not kept locked while waiting for the AI response. An attempt token is also used to prevent an older request from overwriting the result of a newer retry.

### 2. Keeping the workflow simple

The analyse/retry request waits for the AI response before returning. This keeps the implementation simple and avoids adding a separate queue and worker system for a small assessment.
The application uses asynchronous database and HTTP calls, so other requests can still be handled while an AI request is running.
Each AI attempt has a time limit stored in the database. If an attempt gets interrupted or takes too long, the system can detect the expired attempt and mark it as failed instead of leaving the work item stuck in ANALYSING.

For a production system, I would use a background job queue and scheduled recovery instead.

### 3. Mock AI and handling AI failures

The AI provider is separated behind a small interface, allowing the application to use either the real Anthropic provider or a mock provider.
The mock provider makes testing and evaluation predictable and can also simulate failures.
AI responses are treated as untrusted input and are validated before being used by the application. Invalid responses, timeouts, and provider failures are handled as failed attempts that can be retried.
The system does not guarantee exactly-once billing from the external AI provider, since an external request may already have been accepted before cancellation occurs.

## Tests and validation

The backend has unit, API, provider, and PostgreSQL integration tests.

Run Tests Locally
Run the fast tests without PostgreSQL:

cd backend
pytest -q -m "not integration"
ruff check .

To run the full test suite, including PostgreSQL integration tests:

docker compose --profile test run --build --rm tests

Or, if you already have PostgreSQL running locally:

cd backend
TEST_DATABASE_URL=postgresql+psycopg://odin:odin@localhost:5432/odin pytest -q

PostgreSQL integration tests are skipped when TEST_DATABASE_URL is not provided. When enabled, each test creates a temporary schema, runs the actual Alembic migrations, and removes the schema afterward.

The test suite covers:

- Duplicate deliveries and conflicting updates
- Work item lifecycle and invalid state transitions
- Request validation and malformed input
- Timeouts, failures, retries, and interrupted jobs
- API error handling and payload limits
- AI provider requests and HTTP failures
- Concurrent PostgreSQL inserts
- Concurrent database claims and completions
- Stale attempt protection
- Database constraints
- Frontend

Verify that the frontend builds successfully:

cd frontend
npm run build

For more details about the test cases and validation strategy, see VALIDATION.md.

## Production considerations

- Only AI processing has a `FAILED` domain state.
- Immutable received content, no deletion or reopening. 
- No application authentication/authorization is included. CORS is a browser integration setting, not authentication. Production needs authenticated CRM intake,operator access control, tenant separation and rate limiting.

## AI Usage

OpenAI Codex was used to implement parts of code and review the API, UI, tests and documentation. Verification included pytest, Python compilation, Alembic SQL generation, TypeScript checking and Vite production compilation.

- Name: Yeshu Anand Shah
- GitHub repository: https://github.com/yeswho/odin-assessment
- Backend language: Python / FastAPI
- LLM provider / mock: Anthropic adapter with explicit offline mock mode
- Approximate time spent: 3-4 hours

## Screenshots

### Dashboard: Work Items Added

<p align="center">
  <img src="https://github.com/user-attachments/assets/004a08ec-e5c7-45fd-96c0-a3b3488d89b5" alt="Dashboard with work items" width="900">
</p>

### Analyze Work Item

<p align="center">
  <img src="https://github.com/user-attachments/assets/a0ed645a-b449-4521-97ea-6d8fcceabed7" alt="Analyze work item" width="900">
</p>

### Analysis Failed: Anthropic

<p align="center">
  <img src="https://github.com/user-attachments/assets/3f039bd6-ab38-487d-84ee-1c6f375fe996" alt="Analysis failed with Anthropic" width="900">
</p>

### Analysis Completed: Anthropic

<p align="center">
  <img src="https://github.com/user-attachments/assets/0191db01-ba25-4b99-9b12-b3be985ecf0e" alt="Analysis completed with Anthropic" width="900">
</p>

### Analysis Completed: Mock Provider

<p align="center">
  <img src="https://github.com/user-attachments/assets/77aa118d-bf2f-4527-bbba-01b4f0c7030d" alt="Analysis completed with Mock Provider" width="450">
</p>
