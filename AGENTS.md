# Project Working Agreement

These rules apply to all work in this repository.

## 1. Think Before Coding

- Inspect the relevant files and existing conventions before making changes.
- State assumptions explicitly. Do not silently choose an interpretation when requirements are ambiguous.
- Present materially different interpretations and their tradeoffs.
- Push back when a simpler or safer approach satisfies the requirement.
- If an unresolved ambiguity could change behavior, architecture, data, or scope, stop and ask before coding.

## 2. Simplicity First

- Write the minimum code needed to satisfy the current request.
- Do not add unrequested features, speculative abstractions, or configurability.
- Do not add dependencies without a concrete need tied to the current task.
- Do not handle impossible scenarios.
- Prefer the smallest clear implementation; if the same result can be achieved substantially more simply, simplify it.

## 3. Surgical Changes

- Touch only files and lines required by the current request.
- Do not refactor, reformat, rename, or clean up unrelated code.
- Match the existing project style and conventions.
- Mention unrelated dead code or problems without changing them.
- Remove only imports, variables, functions, or files made unused by the current change.
- Every changed line must trace directly to the requested outcome.

## 4. Goal-Driven Execution

- Define concrete success criteria before implementation.
- For multi-step work, state a brief plan in this form:

  1. `[step]` -> verify: `[check]`
  2. `[step]` -> verify: `[check]`
  3. `[step]` -> verify: `[check]`

- When changing behavior, add or update a test that proves the required behavior, then make it pass.
- When fixing a bug, first reproduce it with a test or a deterministic check.
- When refactoring, verify the relevant tests before and after the change.
- Continue iterating until the stated success criteria are verified.

