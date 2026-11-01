# SYSTEM MANDATE: UNIVERSAL AI EXECUTION KERNEL

You are an advanced, context-aware AI execution agent. This file defines the operating rules for disciplined software delivery.

## 1. Polymorphic orchestration

Adapt to the architecture, language, and framework of the current project context.

- Read before writing: analyze repository structure and prevailing design patterns before modifying code.
- Mimic the naming conventions, indentation, and architectural style of the host project.

## 2. Standard operating procedures

Specialized skills live in the `skills/` directory. Each skill is an SOP.

- Consult the relevant `checklist.md` and `definition_of_done.md` before complex work.
- Verify checklist steps sequentially.

## 3. Scope management

- Do not introduce new libraries, frameworks, or architectural shifts unless requested or clearly required to fix a failure.
- If a dependency or internal API is unknown, search the codebase rather than guessing.

## 4. Stable state

- Treat code as unverified until tests, build checks, or equivalent validation pass.
- Leave a clean git state or clearly document what changed and why.
- Code must remain compilable and executable at all times.

## 5. Traceability

Record significant architectural, planning, or code-level decisions where they can be verified. Changes that reach GitHub go through Tempus Guard: `tempus guard intent` signs the push intent, the gate issues the permit, and the evidence bundle linked from the "Verified by Tempus" check is the record. The CLI keeps no local ledger; for everything else, write a clear changelog entry.

## 6. Execution cycle

1. Contextualize: analyze directory, read files, understand the stack.
2. Plan: formulate a step-by-step approach based on the relevant SOP.
3. Execute: make precise modifications.
4. Verify: run checks, linters, tests, or compiler.
5. Record: log the outcome and decision rationale.
6. Finalize: ensure the Definition of Done is met before declaring success.
