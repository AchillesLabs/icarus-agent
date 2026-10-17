# 01: Agent Persona and Dynamic System Instruction Injection

**What to build:** Every interactive chat turn and one-shot execution automatically builds and injects a structured system prompt into the model's message history. The prompt defines Icarus Agent's identity, core instructions, current operating system, working directory, and behavior rules. This anchors open-weights and cloud models into their assistant persona, preventing unconditioned autocomplete hallucinations or meme generation.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] System prompt builder module implemented under `icarus_core.agent.prompts` that dynamically gathers OS, working directory, and agent guidelines.
- [ ] `icarus chat` and `icarus run` prepend the structured system instruction to prompt message history before calling provider adapters.
- [ ] In-memory session message lists preserve user and assistant history cleanly while keeping system prompt updated with current runtime context.
- [ ] Unit and CLI tests verify system instructions are injected in all provider calls and tested against mock providers.
