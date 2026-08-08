#!/usr/bin/env node

import { mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..");
const installerPath = path.join(scriptDirectory, "install-aisupport.mjs");
const retiredSkillNames = Object.freeze([
  "caveman",
  "caveman-commit",
  "caveman-review",
  "ponytail",
  "ponytail-audit",
  "ponytail-debt",
  "ponytail-gain",
  "ponytail-help",
  "ponytail-review",
]);
const shortStartMarker = "<!-- BEGIN SHORT PORTABLE ALWAYS-ON -->";
const shortEndMarker = "<!-- END SHORT PORTABLE ALWAYS-ON -->";
const legacyStartMarker = "<!-- BEGIN CAVEMAN PORTABLE ALWAYS-ON -->";
const legacyEndMarker = "<!-- END CAVEMAN PORTABLE ALWAYS-ON -->";
const requiredBehaviorScenarioIds = Object.freeze([
  "information-request-is-read-only",
  "clear-modification-preserves-scope",
  "ambiguous-deletion-pauses-once",
  "secret-bearing-failure-keeps-evidence",
  "failed-verification-is-not-complete",
  "conversational-mode-transition-keeps-safety",
]);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function pathExists(targetPath) {
  try {
    await stat(targetPath);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

function runInstaller(argumentsList) {
  const result = spawnSync(process.execPath, [installerPath, ...argumentsList], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(["Installer failed", result.stdout, result.stderr].join("\n"));
  }
}

async function testShortSource() {
  const skillDirectory = path.join(repositoryRoot, ".agents", "skills", "short");
  const skill = await readFile(path.join(skillDirectory, "SKILL.md"), "utf8");
  const frontmatter = skill.match(/^---\n([\s\S]*?)\n---\n/)?.[1] ?? "";
  const frontmatterKeys = [...frontmatter.matchAll(/^([a-z-]+):/gm)].map(
    (match) => match[1],
  );
  assert(
    JSON.stringify(frontmatterKeys) === JSON.stringify(["name", "description"]),
    "Short frontmatter must contain only name and description",
  );
  for (const required of [
    "User scope, repository instructions, safety, and correctness outrank all Short rules.",
    "Treat information-only requests as read-only.",
    "Change state only when the user's execution intent, target, and scope are clear.",
    "When the user's latest instruction conflicts with earlier instructions, replace only the conflict and keep compatible constraints.",
    "Never undo completed work outside the currently authorized scope without an explicit request; report its state instead.",
    "Use secrets only for the user's authorized purpose and minimum necessary scope.",
    "Redact only the sensitive value; preserve the surrounding evidence.",
    "Modify only authorized targets and scope.",
    "Preserve out-of-scope content and existing user changes.",
    "Never return an empty response or claim completion when work failed",
    "Prefer, in order: existing code, standard library, native platform features, installed dependencies, then new code.",
    "Use the repository's existing test system and verify in proportion to risk.",
    "Persisted content follows the target format and repository or project conventions.",
    "Choose the narrowest command or query that can answer the question.",
    "Never hide an error or",
    "Do not add a dependency, background process, telemetry, or lifecycle Hook",
    "Redact secrets and sensitive values in every retained field without",
    "These are conversational directives, not Codex runtime modes.",
    "No mode may reduce requested implementation, scope, safety, correctness, necessary error handling, or required verification.",
  ]) {
    assert(skill.includes(required), `Short rule missing: ${required}`);
  }
  for (const excluded of [
    "short-guard",
    "official source verification",
    "Excel",
    "VBA",
    "Telegram",
    "Slack",
  ]) {
    assert(!skill.includes(excluded), `Short must stay domain-neutral: ${excluded}`);
  }

  const openai = await readFile(
    path.join(skillDirectory, "agents", "openai.yaml"),
    "utf8",
  );
  assert(openai.includes("$short"), "Short UI default prompt is missing");
  assert(
    openai.includes("allow_implicit_invocation: true"),
    "Short implicit invocation is disabled",
  );

  const skillNames = await readdir(path.join(repositoryRoot, ".agents", "skills"));
  for (const retiredName of retiredSkillNames) {
    assert(!skillNames.includes(retiredName), `Retired source skill remains: ${retiredName}`);
  }

  const guidance = await readFile(path.join(repositoryRoot, "AGENTS.md"), "utf8");
  assert(
    guidance.includes(shortStartMarker) && guidance.includes(shortEndMarker),
    "Short always-on block is missing",
  );
  assert(
    guidance.includes("Apply the available `short` skill to every response and coding task."),
    "Short automatic guidance is missing",
  );
  assert(!guidance.includes(legacyStartMarker), "Legacy always-on block remains");

  for (const removedPath of [
    "CAVEMAN.md",
    "PONYTAIL.md",
    "caveman-manifest.json",
    "ponytail-manifest.json",
    "scripts/install-caveman.mjs",
    "scripts/install-caveman.ps1",
    "scripts/install-caveman.sh",
  ]) {
    assert(
      !(await pathExists(path.join(repositoryRoot, removedPath))),
      `Retired distribution file remains: ${removedPath}`,
    );
  }
  assert(await pathExists(path.join(repositoryRoot, "SHORT.md")), "SHORT.md is missing");
  assert(
    await pathExists(path.join(repositoryRoot, "short-manifest.json")),
    "Short manifest is missing",
  );
  assert(
    await pathExists(path.join(scriptDirectory, "install-skills.mjs")),
    "Generic skill installer is missing",
  );

  const contract = JSON.parse(
    await readFile(path.join(repositoryRoot, "tests", "short-behavior-contract.json"), "utf8"),
  );
  assert(contract.version === 1, "Short behavior contract version must be 1");
  assert(
    contract.kind === "static-policy-contract",
    "Short behavior contract must identify itself as a static policy contract",
  );
  assert(
    contract.executesModel === false && contract.executesApi === false,
    "Short behavior contract must not claim to execute a model or API",
  );
  assert(
    typeof contract.description === "string" &&
      contract.description.includes("does not run or grade a model or API response"),
    "Short behavior contract must state its non-executing scope",
  );
  assert(Array.isArray(contract.scenarios), "Short behavior scenarios must be an array");
  assert(
    contract.scenarios.length >= requiredBehaviorScenarioIds.length,
    "Short behavior contract must contain at least six scenarios",
  );
  const scenarioIds = contract.scenarios.map((scenario) => scenario.id);
  assert(
    new Set(scenarioIds).size === scenarioIds.length,
    "Short behavior scenario IDs must be unique",
  );
  for (const requiredId of requiredBehaviorScenarioIds) {
    assert(scenarioIds.includes(requiredId), `Short behavior scenario missing: ${requiredId}`);
  }
  for (const scenario of contract.scenarios) {
    assert(
      typeof scenario.input === "string" && scenario.input.trim().length > 0,
      `Short behavior scenario input is missing: ${scenario.id}`,
    );
    for (const field of ["expected", "forbidden", "policyAnchors"]) {
      assert(
        Array.isArray(scenario[field]) && scenario[field].length > 0,
        `Short behavior scenario ${field} is missing: ${scenario.id}`,
      );
      assert(
        scenario[field].every((value) => typeof value === "string" && value.trim().length > 0),
        `Short behavior scenario ${field} contains an invalid value: ${scenario.id}`,
      );
    }
    for (const anchor of scenario.policyAnchors) {
      assert(
        skill.includes(anchor),
        `Short behavior scenario policy anchor is missing (${scenario.id}): ${anchor}`,
      );
    }
  }

  const lock = JSON.parse(
    await readFile(path.join(repositoryRoot, "skills-lock.json"), "utf8"),
  );
  assert(lock.skills.short, "Short lock entry is missing");
  for (const retiredName of retiredSkillNames) {
    assert(!lock.skills[retiredName], `Retired lock entry remains: ${retiredName}`);
  }
}

async function testLegacyMigration() {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "aisupport-short-test-"));
  try {
    const skillTarget = path.join(temporaryRoot, "skills");
    const agentsFile = path.join(temporaryRoot, "codex-home", "AGENTS.md");
    for (const retiredName of retiredSkillNames) {
      const retiredDirectory = path.join(skillTarget, retiredName);
      await mkdir(retiredDirectory, { recursive: true });
      await writeFile(
        path.join(retiredDirectory, "SKILL.md"),
        `---\nname: ${retiredName}\ndescription: legacy fixture\n---\n`,
        "utf8",
      );
    }
    await mkdir(path.dirname(agentsFile), { recursive: true });
    await writeFile(
      agentsFile,
      [
        "# Existing user guidance",
        "",
        legacyStartMarker,
        "legacy managed content",
        legacyEndMarker,
        "",
      ].join("\n"),
      "utf8",
    );

    const argumentsList = ["--target", skillTarget, "--agents-file", agentsFile];
    runInstaller(argumentsList);
    runInstaller([...argumentsList, "--verify"]);

    assert(
      await pathExists(path.join(skillTarget, "short", "SKILL.md")),
      "Short was not installed",
    );
    for (const retiredName of retiredSkillNames) {
      assert(
        !(await pathExists(path.join(skillTarget, retiredName))),
        `Retired runtime skill remains: ${retiredName}`,
      );
    }
    const migratedGuidance = await readFile(agentsFile, "utf8");
    assert(migratedGuidance.includes(shortStartMarker), "Short guidance was not installed");
    assert(!migratedGuidance.includes(legacyStartMarker), "Legacy guidance was not removed");

    const backupRoot = path.join(temporaryRoot, "skill-backups");
    const backups = await readdir(backupRoot);
    for (const retiredName of retiredSkillNames) {
      assert(
        backups.some((name) => name.startsWith(`${retiredName}.backup-`)),
        `Retired runtime skill backup missing: ${retiredName}`,
      );
    }
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

await testShortSource();
await testLegacyMigration();
console.log("Short policy and migration tests passed");
