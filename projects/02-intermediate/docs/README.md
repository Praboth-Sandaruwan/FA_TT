# Intermediate project documentation assets

This directory stores supporting material referenced by the intermediate project README.

- `request-lifecycle.mmd` – Mermaid sequence diagram illustrating how SSR views interact with the
  session middleware, Redis cache, and Postgres when rendering pages and HTMX partials.
- `job-processing.mmd` – Mermaid sequence diagram covering the background job pipeline from the
  `/api/jobs/task-report` endpoint through the Redis-backed RQ queue and worker.
- `samples/task_reports.sample.json` – Example analytics payload that can be imported into MongoDB to
  demonstrate the document-store integration used by reporting dashboards.
