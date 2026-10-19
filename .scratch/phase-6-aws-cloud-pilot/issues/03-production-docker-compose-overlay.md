# 03: Production Docker Compose Overlay and Reverse-Proxy Hardening

**GitHub Issue:** [#44](https://github.com/AchillesLabs/icarus-agent/issues/44)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Hardened docker-compose.prod.yml specification incorporating non-root container users, CPU/memory resource ceilings, Docker JSON log file rotation, dependency-ordered health check conditions, and Caddy reverse-proxy TLS with standard security headers and unbuffered SSE streaming.

**Blocked by:**
- #42 (01: Tiered Health Probes (/health/live
- /health/ready) and Worker Heartbeat Tracking)

**Status:** ready-for-agent

- [ ] Create docker-compose.prod.yml extending base compose with non-root security contexts, resource limits (cpus, mem_limit), and restart: always.
- [ ] Configure Docker json-file logging options (max-size: 10m, max-file: 5) across all containers to prevent host disk exhaustion.
- [ ] Configure healthcheck conditions and service dependency order (PostgreSQL healthy -> migrations completed -> API healthy -> worker started -> Caddy proxy).
- [ ] Update Caddyfile with production security headers (HSTS, X-Content-Type-Options, X-Frame-Options) and unbuffered SSE proxying (flush_interval -1).
- [ ] Automated tests verify Compose file syntax, resource configurations, and health check definitions.
