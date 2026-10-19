# 04: Autocomplete Dropdowns and Context Mention Resolution (@file, @git:diff)

**GitHub Issue:** [#52](https://github.com/AchillesLabs/icarus-agent/issues/52)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Autocomplete dropdown menu popup triggered by typing @, fuzzy matching repository workspace files (ignoring .git, .venv, node_modules). Preprocesses user prompts to automatically read mentioned files and uncommitted @git:diff changes, injecting formatted context blocks directly into conversation turns.

**Blocked by:**
- #51 (03: Prompt Toolkit Interactive REPL Engine with Multi-Line and History)

**Status:** ready-for-agent

- [ ] Implement prompt_toolkit Completer providing live dropdown suggestions when user types @, listing workspace files with fuzzy filtering.
- [ ] Filter out noise directories (.git, .venv, __pycache__, node_modules) from completion candidates.
- [ ] Implement context mention preprocessor scanning inputs for @<path> and @git:diff.
- [ ] Attach resolved file contents and git diffs as formatted code blocks with token counts into message context.
- [ ] Automated tests verify file completion candidates, mention extraction, and context block generation.
