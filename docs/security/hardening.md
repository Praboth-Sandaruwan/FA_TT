# Security automation and deployment hardening

The advanced realtime collaboration service now ships with automated security
checks, opinionated defaults, and documentation aimed at making secure
deployments the easy path. This guide summarises what runs automatically and the
steps platform owners should take to keep the controls effective in production.

## Runtime hardening

The FastAPI application exposes a narrow CORS policy and sends a consistent set
of security headers for every response.

- **CORS** – only origins listed in `ADVANCED_ALLOWED_ORIGINS` are permitted.
  Requests are restricted to `GET`, `HEAD`, and `OPTIONS` with an allow-listed
  header set (`Authorization`, content negotiation headers, cache hints, and
  `X-Requested-With`). `ADVANCED_CORS_*` environment variables can be used to
  extend the allow list for trusted clients but wildcards are deliberately
  rejected.
- **Security headers** – hardened defaults include `Strict-Transport-Security`,
  `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`, and the
  standard `X-Frame-Options`/`X-Content-Type-Options` pair. A minimal
  inline-friendly CSP is provided for the bundled HTML surface; customise the
  `ADVANCED_CONTENT_SECURITY_POLICY` variable if additional third-party origins
  are introduced.
- **Server header removal** – HTTP responses no longer leak the ASGI server
  signature. Set `ADVANCED_REMOVE_SERVER_HEADER=false` if an upstream proxy
  needs to inject its own value.

When promoting the service to production ensure:

1. TLS termination happens before requests reach the application (the HSTS
   header assumes HTTPS).
2. Websocket and SSE endpoints are exposed via the same trusted origin used for
   the HTML shell.
3. Secrets such as `ADVANCED_REALTIME_TOKEN` are provided via a secure secret
   manager instead of `.env` files checked into source control.

## Automated review guardrails

| Tool | Trigger | Purpose |
| ---- | ------- | ------- |
| **Bandit** (`poetry run bandit -r src`) | local + pre-commit | Static analysis for Python security flaws |
| **GitHub CodeQL** | push, pull request, weekly schedule | Deep semantic scanning with SARIF alerts |
| **Dependabot** | weekly | Automated dependency update PRs for Poetry and workflows |
| **CODEOWNERS** | pull requests | Mandatory review from platform and security owners |
| **PR template** | pull requests | Ensures regression, testing, and security checks are confirmed |

Developers should run the Bandit command locally before opening a pull request –
pre-commit will also refuse commits when high-severity findings are introduced.

## Branch protection checklist

Configure the `main` branch with the following defaults:

1. Require pull requests before merging with **at least two approvals**.
2. Enforce status checks for:
   - `pre-commit` (linting/type checks)
   - `pytest`
   - `codeql` (analysis workflow added in `.github/workflows/codeql.yml`).
3. Block force pushes and prevent branch deletion.
4. Require review from CODEOWNERS so changes to `.github/` or `docs/security/`
   automatically ping the security team.
5. Enable the "Require conversation resolution" option to ensure open review
   threads are addressed.

Documenting these settings keeps the organisation aligned when mirroring the
repository across environments.

## Deployment checklist

- [ ] Set explicit `ADVANCED_ALLOWED_ORIGINS` values for every environment
      (wildcards are not supported).
- [ ] Override the default realtime token with a secure random value.
- [ ] Configure observability exports (`ADVANCED_OTEL_EXPORTER_OTLP_ENDPOINT`)
      to trusted collectors only.
- [ ] Ensure Redis and RabbitMQ credentials referenced by the worker are stored
      in dedicated secret stores.
- [ ] Enable infrastructure-level DDoS protection and rate limiting in front of
      the application load balancer.

Keeping the checklist in version control creates a paper trail for security
reviews and gives teams a concrete starting point for new environments.
