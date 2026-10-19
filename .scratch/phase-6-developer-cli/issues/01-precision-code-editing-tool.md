# 01: Precision Search-and-Replace File Editing Tool (edit_file)

**GitHub Issue:** [#49](https://github.com/AchillesLabs/icarus-agent/issues/49)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** A dedicated code-editing tool (edit_file) that replaces precise text blocks without overwriting entire files, supports exact and whitespace-tolerant matching to absorb minor indentation discrepancies from LLMs, and maintains an in-memory/transient backup stack for instant recovery.

**Blocked by:**
- None (can start immediately)

**Status:** ready-for-agent

- [ ] Implement EditFileTool registered in ToolRegistry supporting target_file, old_str, and new_str arguments.
- [ ] Implement exact string replacement with validation that old_str occurs uniquely in the target file.
- [ ] Implement fuzzy whitespace fallback matching to absorb minor indentation or line-ending differences.
- [ ] Record pre-edit file snapshot into an in-memory undo stack enabling byte-for-byte rollback.
- [ ] Automated unit tests verify exact replacement, unique match enforcement, whitespace tolerance, and error handling for missing files or ambiguous matches.
