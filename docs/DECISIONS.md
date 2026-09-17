# Decision Log

Append-only record of decisions **explicitly approved by a founder**. Recommendations and assumptions don't belong here. Format and rules: `CLAUDE.md` section 10.

Newest entries at the bottom.

---

## D-001: Modular monolith on FastAPI
- Date: 2026-09-14
- Approved by: Founders
- Context: Choosing the backend shape for a two-person team that has to ship a pilot quickly.
- Options considered: A) Modular monolith (one FastAPI app) · B) Microservices
- Chosen: A
- Reason: One deployable app is simpler to build, test and operate; module boundaries keep a later split possible.
- Consequences / follow-ups: New services need both founders' approval.

## D-002: PostgreSQL + pgvector, Redis, Alembic
- Date: 2026-09-14
- Approved by: Founders
- Context: Data store for relational data and similarity matching.
- Options considered: A) Postgres + pgvector · B) Postgres plus a separate vector database
- Chosen: A, with Redis for cache, limits and jobs, and Alembic for migrations
- Reason: One database for relational data and vectors; fewer moving parts.
- Consequences / follow-ups: Every schema change goes through Alembic.

## D-003: slowapi for rate limiting
- Date: 2026-09-16
- Approved by: Adhi and Erode Harish
- Context: Every public endpoint must be rate limited (CLAUDE.md section 2).
- Options considered: A) slowapi · B) Custom middleware · C) Limit at the hosting proxy only
- Chosen: A, with an in-memory store for now and Redis before deploy
- Reason: FastAPI-native, small, well known.
- Consequences / follow-ups: Switch the storage to Redis before running more than one process.

## D-004: Backend first; UI/UX and frontend after the backend is complete
- Date: 2026-09-16
- Approved by: <founder name>
- Context: The earlier plan assumed a finished brand dashboard prototype to wire up. There isn't one.
- Options considered: A) Build backend and frontend in parallel · B) Complete the backend first, then UI/UX design, web dashboard and mobile app
- Chosen: B
- Reason: A stable, tested API lets the UI be designed against real data and contracts, with no rework.
- Consequences / follow-ups: No frontend code in this repo. The roadmap's dashboard integration moves to after backend completion.
