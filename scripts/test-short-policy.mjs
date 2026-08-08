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
    "Never undo completed work without an explicit request; report its state instead.",
    "Use secrets only for the user's authorized purpose and minimum necessary scope.",
    "Redact secrets when exact reproduction would reveal them.",
    "Modify only authorized targets and scope.",
    "Preserve out-of-scope content and existing user changes.",
    "Never return an empty response or claim completion when work failed",
    "Prefer, in order: existing code, standard library, native platform features, installed dependencies, then new code.",
    "Use the repository's existing test system and verify in proportion to risk.",
    "Persisted content uses normal, complete prose.",
    "Choose the narrowest command or query that can answer the question.",
    "Never hide an error or",
    "Do not add a dependency, background process, telemetry, or lifecycle Hook",
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
