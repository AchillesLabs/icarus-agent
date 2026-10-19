# 04: Automated Compressed Database Backup and Retention Pruning Tooling

**GitHub Issue:** [#45](https://github.com/AchillesLabs/icarus-agent/issues/45)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Automated CLI and daemon backup utility producing gzip-compressed, SHA-256 checksummed PostgreSQL snapshots with automated retention policy pruning and security audit trail emission.

**Blocked by:**
- None (can start immediately)

**Status:** ready-for-agent

- [ ] Implement backup utility supporting full PostgreSQL compressed binary/logical dumps with timestamped naming conventions.
- [ ] Generate SHA-256 checksum files alongside every backup archive to ensure verifiable integrity.
- [ ] Implement retention lifecycle manager that purges backup snapshots older than a configured threshold (ICARUS_BACKUP_RETENTION_DAYS).
- [ ] Emit structured security audit events upon successful backup completion or failure.
- [ ] Automated integration tests verify backup creation, gzip compression, checksum generation, and retention pruning.
