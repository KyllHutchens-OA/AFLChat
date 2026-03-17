# AFLChat - To Do

## Features & UX

- [ ] **"Was this response an error?" button** — Add to the bottom of each AI chat response; pre-populate the share URL with the conversation context so bug reports are easy to triage

- [ ] **Improve in-chat error messages** — If SQL fails or returns an error, surface a friendly, informative message to the user instead of a generic failure

- [ ] **Handle users with the same name** — Investigate and fix how duplicate display names are resolved (session, visitor ID, UI display)

## Observability & Quality

- [ ] **Structured logging for AI chat concerns** — Add best-effort logging across the agent pipeline so concerns (bad SQL, unexpected responses, low-confidence answers) can be combed through after the fact

- [ ] **LLM stress-test script** — Write a script to query the LLM many times with varied inputs and surface weird/unexpected responses or broken charts automatically

## Infrastructure

- [ ] **Migrate DB to Railway** — Move the database over to Railway to improve load times and reduce latency between the API and the DB

- [ ] **Usage limits per user and per session** — Review and enforce rate/cost limits at both the session and visitor level; make sure limits are visible and enforced consistently
