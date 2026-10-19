# 06: CI/CD Automated Build, Release, and Rollback Workflow

**GitHub Issue:** [#47](https://github.com/AchillesLabs/icarus-agent/issues/47)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** GitHub Actions continuous deployment pipeline that runs linting/tests, builds immutable container images tagged by commit SHA, executes pre-flight database migrations in a one-off container, deploys services, runs post-deployment smoke tests against /health/ready, and triggers automated rollback on failure.

**Blocked by:**
- #42 (01: Tiered Health Probes (/health/live
- /health/ready) and Worker Heartbeat Tracking)
- #44 (03: Production Docker Compose Overlay and Reverse-Proxy Hardening)

**Status:** ready-for-agent

- [ ] Create .github/workflows/deploy.yml triggered on releases, tags, or workflow_dispatch.
- [ ] Execute code formatting, linting, and full test suite as blocking prerequisite gates.
- [ ] Build and tag multi-platform Docker images labeled with commit SHA and release tag.
- [ ] Execute automated pre-flight database migrations before switching application containers.
- [ ] Run post-deployment HTTP smoke test against /health/ready; automatically rollback to previous container tag if smoke test fails.
- [ ] Validate workflow schema, environment variable secrets, and rollback triggers in automated tests.
