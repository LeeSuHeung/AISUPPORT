---
name: gupabal-game
description: Coordinate 구파발기획자, 구파발아트디자이너, 구파발클라이언트, and 구파발서버 through proposal, cross-review, agreement, implementation, and verification. Use when the user says 구파발게임 or requests game feature work spanning gameplay rules, balance, visual direction or assets, client behavior, and server APIs or authoritative state across two or more roles.
---

# 구파발게임

Act as the facilitator for four versatile roles: `구파발기획자`, `구파발아트디자이너`, `구파발클라이언트`, and `구파발서버`.

Use only actual project files and features explicitly provided by the user. Do not invent a sample feature, mockup, art asset, or implementation for testing. If no feature is in scope, stop after validating the role and conversation configuration.

## 1. Establish the brief

Inspect the repository before delegating. Summarize the feature goal, relevant files, constraints, unknowns, and completion criteria. Keep this phase read-only unless the user already requested implementation.

When the user requested implementation spanning two or more roles, read `references/decision-template.json` and `references/decision-policy.md`, then create `<repo>/.codex/gupabal/decision.json` with `enabled: true` and `agreement.status: planning` before delegating. Use only the current feature name and actual repository paths. Add a path to `planning_allow` only when the user asked to create that planning document. Do not create the decision file for a read-only review.

For a small task owned by only one role, use that role alone. For a feature crossing two or more roles, run the full workflow below.

## 2. Start the role discussion

Spawn the four user custom agents concurrently when capacity allows. If the thread limit is lower, run them in waves while preserving one shared discussion packet. If custom agent selection is unavailable, spawn default subagents and give each the matching role from `$HOME/.codex/agents/gupabal_*.toml`. The `SubagentStop` matcher cannot identify a generic fallback type, so manually verify its `GUPABAL_RESULT` block before accepting the handoff.

Ask each role for an independent first proposal containing:

- requirements and assumptions
- owned components and expected changes
- questions for the other roles
- risks and edge cases
- acceptance tests

Require every role's final handoff to end with the `GUPABAL_RESULT` block defined in its agent profile. The lifecycle Hook checks only that `scope`, `risks`, and `verification` are present; it does not judge whether the proposal is good.

Wait for all four proposals. Do not implement during this round.

## 3. Run cross-review

Create one compact discussion packet from the proposals. Send it back to all four existing agent threads. Ask each role to respond to the other roles by name and label every item as one of:

- `AGREE`: accepted as written
- `QUESTION`: more information is required
- `CONFLICT`: incompatible requirements or designs
- `PROPOSAL`: a concrete replacement

Route questions and answers between the existing threads. Prefer direct agent-to-agent messages when supported; otherwise relay them through the facilitator. Keep a visible record in the main thread. Limit discussion to two cross-review rounds unless the user asks for deeper exploration.

Do not silently resolve product tradeoffs. Ask the user when a conflict changes player experience, monetization, data compatibility, security, schedule, or another product decision.

## 4. Freeze the agreement

Before code changes, publish a shared agreement with:

1. player-facing behavior
2. system and balance rules, including formulas, units, bounds, and defaults
3. client/server contract, including request, response, errors, versioning, and ownership of authoritative state
4. visual direction, information hierarchy, required states, asset list, sizes, formats, animation notes, accessibility, and performance budget
5. the art/client handoff contract, including asset names, variants, fallback behavior, and ownership
6. failure, reconnect, retry, and duplicate-request behavior
7. planner-, art-, client-, and server-owned files
8. acceptance tests and telemetry needs
9. unresolved items and their owner

Require all participating roles to approve the agreement or record their remaining objection.

For an approved implementation spanning two or more roles, update the existing `<repo>/.codex/gupabal/decision.json` before editing implementation files. Fill it only with actual project paths and agreed limits. Set all four approvals to `AGREE` and `agreement.status` to `approved` only after the agreement is frozen. Do not create this file for read-only reviews or single-role tasks.

The decision file activates the installed Hooks only for that repository. Keep role ownership patterns non-overlapping. Assign every shared schema, lockfile, generated file, and common configuration file to one owner in `ownership.shared`. Leave engine-specific checks empty unless the current project proves they apply.

## 5. Implement safely

Assign non-overlapping files to `구파발아트디자이너`, `구파발클라이언트`, and `구파발서버`. Keep `구파발기획자` read-only and use it to review behavior and balance against the agreement. During implementation, let the art designer create only explicitly assigned visual specifications or assets; let the client engineer own runtime integration.

Avoid parallel edits to shared schemas, generated files, lockfiles, and common configuration. Give those files to one explicit owner or let the main agent integrate them after both implementation agents finish.

Treat Hook feedback as a guardrail, not a security boundary. `PreToolUse` blocks an explicit `apply_patch` when the decision is not approved. File ownership remains advisory because the tool event does not reliably identify the acting role. `PostToolUse` reports only deterministic problems in files changed by the current patch, such as invalid JSON, merge-conflict markers, or invalid declared image metadata; it cannot undo an edit. Run project-specific builds and tests at the normal verification stage instead of after every edit.

After implementation, ask each engineering role to run its relevant tests. Ask the planner to review the combined result for rule drift, exploitable loops, degenerate strategies, and missing edge cases. Ask the art designer to review visual hierarchy, state coverage, asset fidelity, accessibility, and performance constraints.

After verification and the combined role review finish, set `enabled` to `false` and `agreement.status` to `completed`. Do this before the final report so an approved decision from the previous feature cannot authorize the next feature.

## 6. Report the result

Return a beginner-friendly summary containing:

- the decision record
- each role's contribution
- files changed
- client/server contract
- balance assumptions
- tests and validation results
- unresolved risks and recommended next action

Include `.codex/gupabal/decision.json` in the changed-file summary when it was created. Explain that users must review newly installed command Hooks in `/hooks` once per exact Hook version before Codex runs them.

Explain unfamiliar terms the first time they appear.
