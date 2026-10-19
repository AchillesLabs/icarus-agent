# 05: Automated Database Restoration Verification and Integrity Testing

**GitHub Issue:** [#46](https://github.com/AchillesLabs/icarus-agent/issues/46)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Automated database restoration utility that verifies checksums, executes restorations to clean or temporary databases, validates data round-trip fidelity, and logs restoration audit events, guaranteeing verifiable recovery readiness.

**Blocked by:**
- #45 (04: Automated Compressed Database Backup and Retention Pruning Tooling)

**Status:** ready-for-agent

- [ ] Implement restore utility accepting a backup archive, verifying its SHA-256 checksum before execution.
- [ ] Execute restoration against target PostgreSQL/SQLite database with safety confirmations preventing accidental production overwrites.
- [ ] Verify data round-trip integrity: sessions, messages, encrypted vault credentials, and tokens match pre-backup state identically.
- [ ] Emit structured audit log events recording restore operations and actor attribution.
- [ ] Automated tests verify backup-to-restore round-trip fidelity on a clean test database instance.
