# API client

Hand-written, typed client for the DD Cafe API (not generated from OpenAPI).

- `types.ts` — request/response and SSE `ChatEvent` types.
- `client.ts` — REST calls, image upload, and SSE stream parsing (`parseSseEvent` / `extractSseEvents`).
- `client.test.ts` — unit tests for SSE parsing.

The client resolves the base URL from `VITE_API_BASE_URL` (default `http://localhost:8000`); in the Docker deployment it is empty so requests stay same-origin and nginx proxies `/api/` to the API service.
