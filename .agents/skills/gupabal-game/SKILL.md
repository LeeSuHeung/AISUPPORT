---
name: gupabal-game
description: Use only when the user explicitly invokes $gupabal-game or says 구파발게임.
---

# 구파발게임

Act as the facilitator for four versatile roles: `구파발기획자`, `구파발아트디자이너`, `구파발클라이언트`, and `구파발서버`.

Use only actual project files and features explicitly provided by the user. Do not invent a sample feature, mockup, art asset, or implementation for testing. If no feature is in scope, stop after validating the role and conversation configuration.

## 1. Establish the brief

Inspect the repository before delegating. Summarize the feature goal, relevant files, constraints, unknowns, and completion criteria. Keep this phase read-only unless the user already requested implementation.

When the user requested implementation spanning two or more roles, read `references/decision-template.json` and `references/decision-policy.md`, then create `<repo>/.codex/gupabal/decision.json` as schema v2 with `enabled: true`, a new positive `agreement.revision`, `agreement.status: planning`, and PENDING approvals before delegating. Use only the current feature name and actual repository paths. Add a path to `planning_allow` only when the user asked to create that planning document. Do not create the decision file for a read-only review. An active schema v1 record must be migrated by a decision-only patch; do not carry its approvals into v2.

For a small task owned by only one role, use that role alone. For a feature crossing two or more roles, run the full workflow below.

## 2. Start the role discussion

Spawn the four user custom agents concurrently when capacity allows. If the thread limit is lower, run them in waves while preserving one shared discussion packet. If custom agent selection is unavailable, spawn default subagents and give each the matching role from `$CODEX_HOME/agents/gupabal_*.toml`; when `CODEX_HOME` is unset, use `~/.codex/agents/gupabal_*.toml`. The `SubagentStop` matcher cannot identify a generic fallback type, so manually verify its `GUPABAL_RESULT` block before accepting the handoff.

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

Require all participating roles to approve the agreement or record their remaining objection. A valid approval must explicitly include `APPROVAL: AGREE`, the exact `agreement_revision`, and the full lowercase `contract_digest`.

For an approved implementation spanning two or more roles, update the existing `<repo>/.codex/gupabal/decision.json` before editing implementation files. Fill `summary`, at least one `invariants` item, optional `spec_refs`, ownership, and checks only with actual project paths and agreed limits. Compute the canonical digest exactly as defined in `references/decision-policy.md`. If detailed contract text matters, bind its real file through `spec_refs`; do not leave it outside the digest. Ask all four roles to independently verify the same revision, spec hashes, and digest. Set all four approval objects to `AGREE` with that exact revision and digest, and set `agreement.status` to `approved`, only after every role agrees. Do not create this file for read-only reviews or single-role tasks.

The decision file activates the installed Hooks only for that repository. Every implementation path must resolve to exactly one owner; overlapping patterns are acceptable only when they name the same owner. Assign every shared schema, lockfile, generated file, and common configuration file to one owner in `ownership.shared`. Leave engine-specific checks empty unless the current project proves they apply.

## 5. Implement safely

Assign non-overlapping files to `구파발아트디자이너`, `구파발클라이언트`, and `구파발서버`. Keep `구파발기획자` read-only and use it to review behavior and balance against the agreement. During implementation, let the art designer create only explicitly assigned visual specifications or assets; let the client engineer own runtime integration.

Avoid parallel edits to shared schemas, generated files, lockfiles, and common configuration. Give those files to one explicit owner or let the main agent integrate them after both implementation agents finish.

Treat Hook feedback as a guardrail, not a security boundary. `PreToolUse` blocks an explicit `apply_patch` when the decision is not approved, stale, malformed, unowned, or owned by more than one role. It verifies path ownership but cannot identify which agent invoked the tool, so the facilitator must still enforce role assignments. An approved `spec_refs.path` is immutable: return to planning, increment revision, update the spec hash and contract digest, and collect four new approvals before changing it. `PostToolUse` reports only deterministic problems in files changed by the current patch, such as invalid JSON, merge-conflict markers, or invalid declared image metadata; it cannot undo an edit. Run project-specific builds and tests at the normal verification stage instead of after every edit.

After implementation, ask each engineering role to run its relevant tests. Ask the planner to review the combined result for rule drift, exploitable loops, degenerate strategies, and missing edge cases. Ask the art designer to review visual hierarchy, state coverage, asset fidelity, accessibility, and performance constraints.

After project-specific verification and the combined role review finish, verify the installed runtime, not only the AISUPPORT source checkout. First run the top-level `installer verify` from the canonical AISUPPORT checkout with the same custom `CODEX_HOME`, `--target`, and `--agents-file` values used for installation. On Windows use `powershell -ExecutionPolicy Bypass -File .\AISUPPORTinstall.ps1 -Verify -Target '<same-target>' -AgentsFile '<same-agents-file>'`; on macOS or Linux use `CODEX_HOME='<same-codex-home>' sh ./install.sh --verify --target '<same-target>' --agents-file '<same-agents-file>'`. Preserve the same `CODEX_HOME` environment on Windows too. This integrated verification must exit `0` and contain no `MISMATCH` anywhere in its output.

Next select an explicit Python 3.10+ command and retain it by running `<python> -X utf8 scripts/install_gupabal.py --target <exact> --agents-file <exact> --verify` in the same environment. Each `<exact>` means the corresponding installation value, passed as one correctly quoted shell argument. `-X utf8` must remain present, so `PYTHONUTF8=0` and Unicode (spaces, Korean, or emoji) paths do not change decoding or argument boundaries. This second verification must exit `0`, contain no `MISMATCH`, and print exactly one versioned Hook success line in the form `OK <absolute-path>/gupabal_hooks_<sha16>.py`. Missing or multiple matching `OK ` lines stop closure.

Use the complete path after that `OK ` prefix and the same successful Python 3.10+ command to run `<python> -X utf8 <verified-versioned-hook-path> --verify-project <exact-git-root>`. The `--verify-project` argument must name the exact Git root. Do not decode a Windows `EncodedCommand` to guess the interpreter or Hook path. Verifier exit `0` is required; exit `1` means deterministic findings and exit `2` means policy, input, or complete-verification failure. `checked: 0` only means no declared art targets were checked; it is not visual, build, import, or render approval. Run the project's actual visual review, build, tests, imports, and rendering checks separately when they apply. If source validation passes but runtime installation or any verification does not, report source ready and runtime pending; do not close the decision.

For normal completed closure, set `enabled: false`, `agreement.status: completed`, `agreement.unresolved: []`, and `agreement.contract_digest: null`. At the agreement level these values are `unresolved: []` and `contract_digest: null`. Set every approval status to `PENDING`, its `revision` to the current revision, and its `contract_digest` to `null`.

For intentional cancellation, ask the facilitator to update the file instead of telling the user to edit JSON manually. Keep the existing schema status vocabulary: set `enabled: false`, `agreement.status: planning`, and `agreement.contract_digest: null`; set every approval to `status: PENDING`, its `revision` to the current revision, and its `contract_digest` to `null`; put exactly one short cancellation reason in `agreement.unresolved`. Reopening either closure requires a higher revision. For cancellation, remove or resolve that reason, compute a new digest, and collect four new approvals before implementation.

## 6. Report the result

Return a beginner-friendly summary containing:

- the decision record
- each role's contribution
- files changed
- client/server contract
- balance assumptions
- tests and validation results
- unresolved risks and recommended next action

Include `.codex/gupabal/decision.json` in the changed-file summary when it was created. Explain that users must review newly installed command Hooks in Codex CLI's `/hooks` once per exact Hook version before Codex runs them.

Explain unfamiliar terms the first time they appear.
