# Spec 0006: Phase 6 - Production AWS Cloud Pilot, Docker Compose Deployment, Automated Backup/Restore, CloudWatch Observability, and Disaster Recovery Runbooks

- **GitHub Issue**: [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)
- **Status**: ready-for-agent
- **Target**: Phase 6 of Icarus Agent Architecture Roadmap
- **Estimated Scope**: Production-grade Docker Compose orchestration overlays, automated database backup and verified point-in-time restoration tooling, AWS CloudWatch structured logging and metric alarms, deep readiness and liveness health probes, CI/CD automated release pipeline with smoke tests and rollback, and disaster recovery operator runbooks.

---

## Problem Statement

With Phase 4 (FastAPI, PostgreSQL persistence, and autonomous workers) and Phase 5 (security hardening, encrypted BYOK vault, token revocation, rate limiting, and audit logging) completed, the core platform is secure and functional. However, the platform cannot yet be safely deployed for production pilot users or external teams on cloud infrastructure:

1. **Lack of Automated, Tested Backup and Recovery**: Database state, tenant accounts, conversation histories, and encrypted BYOK credentials reside in a persistent PostgreSQL volume. If the instance experiences host degradation, disk corruption, or accidental deletion, there is no automated off-instance backup script or verified recovery mechanism to restore operations with zero data loss.
2. **Missing Production Container Hardening and Reverse-Proxy TLS Enforcement**: While a basic development Compose file exists, it relies on default credentials, open local ports, unpinned container layers, and lacks explicit restart policies, resource memory/CPU caps, log rotation limits, and production health-check dependencies required for continuous cloud operation.
3. **Absence of Centralized Cloud Observability and Alarms**: Operators currently have no centralized visibility into container crashes, error spikes, request latency degradations, background worker task starvation, or database connection pool exhaustion. Without AWS CloudWatch metric alarms and structured log aggregation, incident detection is purely reactive.
4. **Lack of Automated CI/CD Release Pipeline and Safe Rollback**: Releases currently require manual building and container restarts. There is no automated GitHub Actions workflow that executes the test suite, builds immutable container images tagged by commit SHA, applies database schema migrations in a controlled sequence, verifies post-deployment readiness via smoke tests, and executes a rollback if health checks fail.
5. **No Documented Disaster Recovery or Operational Runbooks**: If the production server crashes, certificates expire, or database migrations fail midway, there are no step-by-step operator runbooks to diagnose and resolve outages quickly under pressure.

---

## Solution

Deliver a complete, production-grade cloud pilot infrastructure and operations suite for AWS (EC2/Lightsail) powered by Docker Compose, automated backup/restore validation, CloudWatch observability, CI/CD deployment automation, and disaster recovery runbooks:

1. **Production Docker Compose Overlay (`docker-compose.prod.yml`)**: An immutable, production-hardened compose specification incorporating non-root containers, container health dependencies, resource limits, Docker json-file log rotation, automatic Caddy HTTPS certificate renewals, and isolated network bridges.
2. **Automated Database Backup and Verified Restoration Tooling**: CLI and daemon scripts that generate compressed, checksummed database snapshots, securely stream them to remote cloud object storage (or persistent backup volumes), prune aged snapshots based on retention policies, and verify restore integrity against clean databases.
3. **Deep Health and Metrics Probes**: Comprehensive `/health`, `/health/ready`, and `/health/live` endpoints exposing PostgreSQL pool saturation, Alembic migration currency, worker task claiming heartbeats, and runtime memory consumption, complemented by CloudWatch-compatible structured JSON logging.
4. **Automated CI/CD Release and Rollback Pipeline**: GitHub Actions workflows executing linting, formatting, tests, automated container image building, registry publishing, SSH/SSM deployment orchestration, pre-flight migration checks, post-deployment smoke validation, and zero-downtime rollback.
5. **Disaster Recovery and Deployment Runbooks**: Exhaustive, battle-tested Markdown operational runbooks providing exact commands for initial cloud provisioning, TLS configuration, certificate renewal, database backup and restoration drills, zero-downtime upgrades, and incident response triage.

---

## User Stories

1. As a cloud operator, I want a production Docker Compose overlay, so that my services run with hardened security configurations, container resource limits, and automatic restart policies.
2. As a cloud operator, I want automated periodic database backups, so that tenant data and encrypted credentials can be recovered in the event of hardware failure.
3. As a site reliability engineer, I want a restore script that validates backup archives against a temporary database, so that I can guarantee backup integrity before an actual disaster occurs.
4. As an operator, I want backup archives to be compressed and timestamped, so that storage consumption is minimized and recovery points are unambiguous.
5. As an operator, I want a backup retention policy that automatically prunes archives older than a configured threshold, so that disks do not fill up over time.
6. As a security engineer, I want all backup archives containing encrypted tenant secrets to remain protected with symmetric encryption, so that backups at rest cannot be compromised.
7. As a developer, I want a `/health/ready` endpoint that checks PostgreSQL connectivity and pending migrations, so that traffic is only routed to fully initialized instances.
8. As a developer, I want a `/health/live` endpoint that responds with 200 OK as long as the process event loop is unblocked, so that orchestrators can distinguish between hung processes and startup delays.
9. As an operator, I want the worker process to update a heartbeat timestamp in the database, so that health probes can detect if the autonomous scheduler daemon has crashed.
10. As a DevOps engineer, I want structured JSON log output with request IDs, tenant IDs, and scrubbed secrets, so that AWS CloudWatch Logs can ingest and index log events seamlessly.
11. As a cloud operator, I want CloudWatch metric alarms for high 5xx error rates, elevated response latency, and worker task backlog, so that our team is notified via email/SNS before users experience prolonged downtime.
12. As a developer, I want an automated GitHub Actions release workflow, so that merging to `main` builds, tests, and deploys the application without error-prone manual commands.
13. As a developer, I want container images to be tagged with commit SHAs, so that every production deployment is immutable and traceable to Git history.
14. As an operator, I want the deployment pipeline to run database migrations as an isolated step before starting new API containers, so that schema changes take effect before new traffic arrives.
15. As a release engineer, I want the deployment workflow to execute post-deployment smoke tests, so that regressions are caught immediately after service restart.
16. As an operator, I want an automated rollback procedure that restores the previous container image tag and database state if smoke tests fail, so that service outages are minimized.
17. As an operator, I want Caddy to manage and automatically renew Let's Encrypt TLS certificates, so that HTTPS traffic is always encrypted without manual certificate installations.
18. As a security engineer, I want the reverse proxy to send standard security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`), so that common web vulnerabilities are mitigated at the network edge.
19. As a developer, I want SSE event streaming to remain unbuffered through the reverse proxy, so that remote CLI users experience real-time token streaming without latency.
20. As a cloud operator, I want an AWS deployment runbook, so that I have a clear, reproducible guide to provision an EC2 or Lightsail instance from scratch.
21. As an on-call engineer, I want a disaster recovery runbook with exact copy-paste commands, so that I can restore the database, replace a corrupted volume, or roll back a failed migration under emergency conditions.
22. As a cost manager, I want documented AWS cost control recommendations (budget alarms, resource reservations), so that our pilot hosting costs remain strictly bounded.
23. As a CLI user, I want `icarus doctor` to support a `--remote` probe, so that I can diagnose connectivity, TLS validity, and server version compatibility from my local machine.
24. As an operator, I want Docker container log sizes to be capped with `max-size` and `max-file` rotation options, so that log files never exhaust host disk space.
25. As an auditor, I want all deployment events, backup executions, and restore drills to produce structured records in the security audit stream, so that operational actions are fully traceable.

---

## Implementation Decisions

### 1. Production Docker Compose Overlay

- Provide a dedicated production compose overlay that extends the baseline definition for production cloud environments.
- Enforce non-root execution across all containers with dedicated service user IDs.
- Define container resource constraints (memory limits and CPU quotas) to prevent runaway agent loops from crashing the host operating system.
- Configure Docker logging drivers with explicit size-based log rotation policies to prevent unconstrained disk exhaustion.
- Introduce health-check conditions on all service dependencies ensuring services start strictly in dependency order (PostgreSQL healthy -> migrations complete -> API healthy -> worker started -> Caddy proxy).

### 2. Automated Database Backup, Retention, and Restoration Tooling

- Implement automated backup utilities supporting full PostgreSQL binary and logical dumps.
- Enforce gzip compression, SHA-256 checksum generation, and standardized timestamped naming conventions for all backup archives.
- Implement an automated retention lifecycle manager that purges snapshots exceeding configured retention windows while preserving daily/weekly baselines.
- Build an automated restoration utility that verifies archive checksums, drops or initializes temporary schema targets, and verifies data integrity against clean databases before confirming recovery readiness.
- Ensure backup and restoration operations record structured events in the security audit logger.

### 3. Deep Health and Telemetry Probes

- Enhance health routing to provide tiered diagnostic endpoints:
  - Liveness probe: lightweight endpoint confirming the web server event loop is actively accepting connections.
  - Readiness probe: deep dependency check confirming PostgreSQL connectivity, connection pool saturation, Alembic migration currency, and worker daemon heartbeats.
- Provide a worker heartbeat mechanism where background scheduler daemons write periodic status records to a dedicated table or cache, allowing the API readiness probe to detect silent worker stalls.
- Structure all application logs as JSON Lines containing correlation request IDs, tenant IDs, timestamps, and log levels, directly ingestible by AWS CloudWatch Logs agents and FluentBit.

### 4. CI/CD Release and Automated Rollback Workflow

- Construct a continuous integration and deployment workflow for GitHub Actions triggered on release tags and commits to the primary branch.
- Execute linting, formatting, static analysis, and the full test suite as blocking prerequisite gates.
- Build and tag immutable Docker images labeled with the commit SHA and semantic release version.
- Implement a sequential deployment runner:
  1. Pull new container image.
  2. Execute database migrations in an isolated one-off container.
  3. Swap container images with minimal downtime.
  4. Perform post-deployment HTTP smoke tests against `/health/ready` and basic API endpoints.
  5. If smoke tests fail or timeout, trigger automated rollback to the previous image tag and notify operators.

### 5. Cloud Infrastructure Automation and Disaster Recovery Runbooks

- Document comprehensive operational runbooks:
  - Provisioning Runbook: Step-by-step instructions for AWS Lightsail and EC2 instance sizing, firewall/security group configuration (ports 80/443 only), Docker/uv installation, and environment configuration.
  - Disaster Recovery Runbook: Emergency response procedures for host failure, database volume recovery, snapshot restoration, certificate renewal failure, and rollbacks.
  - Cost Control Runbook: Setting up AWS Budgets, CloudWatch billing alarms, and instance downsizing guidelines for pilot operations.

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise external operational contracts, status codes, script exit codes, and backup archive formats rather than internal implementation details.
- Deployment and backup tests must run reliably in local and CI environments using isolated in-memory or containerized SQLite and PostgreSQL without incurring AWS billing costs or requiring live AWS credentials.
- Restoration tests must verify data round-trip fidelity: data inserted prior to backup must be completely identical and verifiable after restoration.
- Health probe tests must verify predictable failure degradation (e.g. returning HTTP 503 Service Unavailable when the database is unreachable or migrations are pending).

### Modules Tested

- Production Compose configuration and health-check dependencies.
- Database backup creation, compression, checksumming, and retention pruning utilities.
- Database restoration utility and round-trip data verification.
- Health routing probes (`/health`, `/health/live`, `/health/ready`).
- Worker daemon heartbeat tracking and stall detection.
- Structured CloudWatch JSON logging formatter.
- Smoke test verification scripts.

### Prior Art

- Phase 4 self-hosting and Docker Compose configuration (`docker-compose.yml`, `Caddyfile`, `docs/self-hosting.md`).
- Migration runner and database management tests (`tests/test_migrations.py`, `tests/test_database.py`).
- API health and error handling tests (`tests/test_api_health.py`, `tests/test_api_errors_and_cors.py`).
- Security CLI and doctor tests (`tests/test_doctor.py`, `tests/test_remote_cli.py`).

---

## Out of Scope

- Multi-node Kubernetes or Amazon ECS Fargate cluster orchestration (planned for Phase 8 enterprise scale).
- Multi-region active-active Aurora PostgreSQL replication (single-instance RDS or persistent volume is standard for Phase 6 pilot).
- Desktop GUI client packaging and OS notarization (planned for Phase 7).
- Enterprise SAML 2.0 / Okta SSO integration (planned for Phase 8).
- Hardware Security Module (HSM) or AWS KMS remote hardware key derivation (local master key derivation remains the standard for Phase 6; AWS KMS integration is an optional future plugin).

---

## Further Notes

- Phase 6 completes the foundational server operations milestone of the Icarus architecture roadmap, providing everything needed to transition from local testing to hosted cloud pilot user evaluations.
- All deployment artifacts, scripts, and runbooks will reside directly within the repository to ensure reproducible infrastructure-as-code.
