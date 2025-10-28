# Advanced Realtime Deployment Checklist

Use this checklist when promoting the advanced realtime stack to a new environment. Tailor values for your delivery pipeline, but keep each control point in place to preserve reliability and security.

## 1. Pre-deployment Validation
- [ ] Confirm targeted commit/tag has passed the full `poetry run pytest -k advanced` suite in CI.
- [ ] Run `poetry check` and `poetry export --format=requirements.txt` to ensure dependency metadata is valid for the image build.
- [ ] Review the infrastructure-as-code change set (Terraform/Pulumi/CloudFormation) that provisions Redis, RabbitMQ, telemetry collectors, and networking rules.
- [ ] Verify service-level objectives (SLOs) and alert rules are updated for any new endpoints or metrics.

## 2. Secrets & Configuration
- [ ] Rotate `ADVANCED_REALTIME_TOKEN` and store the secret in the environment's secret manager (AWS Secrets Manager, Vault, etc.).
- [ ] Populate RabbitMQ and Redis credentials via secret references; never bake them into the container image.
- [ ] Set `ADVANCED_ALLOWED_ORIGINS` to the exact production domains—no wildcards.
- [ ] Provide OTLP collector URLs and headers for tracing via `ADVANCED_OTEL_EXPORTER_OTLP_*` variables.
- [ ] Record the deployment's HSTS, CSP, and permissions policy values for compliance review.

## 3. Infrastructure Readiness
- [ ] Redis cluster created with persistence enabled and latency alerts configured.
- [ ] RabbitMQ exchange, retry, and DLQ queues declared (names must match the defaults or the configured overrides).
- [ ] Load balancer or API gateway health checks point to `/healthz` and `/readyz`.
- [ ] Observability stack (Prometheus, Grafana, Jaeger) reachable from the application network segment.
- [ ] Automation account/service principal granted publish rights to deployment container registry.

## 4. Deployment Steps
- [ ] Build and scan the Docker image: `docker build -f projects/03-advanced/Dockerfile -t advanced-app:<tag> .` + container security scan.
- [ ] Push the image to the registry and tag it with the release identifier.
- [ ] Apply IaC changes and wait for Redis + RabbitMQ health checks to pass.
- [ ] Run database or schema migrations if downstream systems require them (not applicable by default for this project).
- [ ] Roll out the application pods/containers followed by the `advanced-worker` deployment to avoid message pile-up.

## 5. Post-deployment Verification
- [ ] Hit `/healthz` and `/readyz` to confirm the application is responsive and the event pipeline has initialised.
- [ ] Execute `scripts/advanced_pipeline_demo.py` against the environment to confirm end-to-end WebSocket → RabbitMQ → Redis → SSE delivery.
- [ ] Inspect Prometheus for new `advanced_board_events_published_total` samples and Grafana dashboards for pipeline latency trends.
- [ ] Check Jaeger for spans emitted by the Observability middleware when exercising `/ws` and `/sse` endpoints.
- [ ] Verify RabbitMQ queues (primary, retry, DLQ) are empty and that Redis pub/sub monitoring shows active subscribers.

## 6. Rollback Plan
- [ ] Maintain previous image tags and IaC state files for quick rollback.
- [ ] Document the command to pause consumer deployments (`kubectl scale deployment advanced-worker --replicas=0` or equivalent) to stop fan-out safely.
- [ ] Capture contact points for on-call SRE/Platform teams in case message backlogs or auth failures occur during rollback.
