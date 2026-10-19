# 07: AWS Cloud Pilot Deployment, Disaster Recovery, and Cost Control Runbooks

**GitHub Issue:** [#48](https://github.com/AchillesLabs/icarus-agent/issues/48)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Complete, copy-paste-ready operational runbooks for AWS Lightsail/EC2 cloud provisioning, Caddy Let's Encrypt TLS setup, emergency disaster recovery drills, automated rollback instructions, and AWS Budget/CloudWatch billing alarm setups.

**Blocked by:**
- #44 (03: Production Docker Compose Overlay and Reverse-Proxy Hardening)
- #46 (05: Automated Database Restoration Verification and Integrity Testing)
- #47 (06: CI/CD Automated Build
- Release
- and Rollback Workflow)

**Status:** ready-for-agent

- [ ] Author docs/runbooks/aws-deployment.md covering Lightsail and EC2 provisioning, security groups, firewall, and initial Docker deployment.
- [ ] Author docs/runbooks/disaster-recovery.md with emergency copy-paste procedures for host crash, volume replacement, database restoration, and rollback.
- [ ] Author docs/runbooks/cost-controls.md detailing AWS Budget threshold alarms, CloudWatch billing alerts, and pilot resource sizing.
- [ ] Execute end-to-end dry-run drill verifying that all commands in the runbooks execute without error.
- [ ] All Phase 6 acceptance criteria and operational documentation verified complete.
