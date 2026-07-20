#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..");
const installerPath = path.join(scriptDirectory, "install-aisupport.mjs");
const skillsLock = JSON.parse(
  await readFile(path.join(repositoryRoot, "skills-lock.json"), "utf8"),
);
const superpowersManifest = JSON.parse(
  await readFile(
    path.join(repositoryRoot, "superpowers-manifest.json"),
    "utf8",
  ),
);
const expectedSkillNames = Object.keys(skillsLock.skills).sort();
const startMarker = "<!-- BEGIN CAVEMAN PORTABLE ALWAYS-ON -->";
const endMarker = "<!-- END CAVEMAN PORTABLE ALWAYS-ON -->";

function digest(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

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

function runInstaller(argumentsList, shouldPass = true) {
  const result = spawnSync(process.execPath, [installerPath, ...argumentsList], {
    encoding: "utf8",
  });
  const passed = result.status === 0;
  if (passed !== shouldPass) {
    throw new Error(
      [
        `Installer ${shouldPass ? "failed" : "unexpectedly passed"}`,
        `status: ${result.status}`,
        result.stdout,
        result.stderr,
      ].join("\n"),
    );
  }
  return result;
}

async function listAgentBackups(agentsFile) {
  const directory = path.dirname(agentsFile);
  const prefix = `${path.basename(agentsFile)}.aisupport.backup-`;
  return (await readdir(directory))
    .filter((name) => name.startsWith(prefix))
    .sort()
    .map((name) => path.join(directory, name));
}

function encodeUtf16(contents, byteOrder) {
  const payload = Buffer.from(contents, "utf16le");
  if (byteOrder === "be") {
    payload.swap16();
    return Buffer.concat([Buffer.from([0xfe, 0xff]), payload]);
  }
  return Buffer.concat([Buffer.from([0xff, 0xfe]), payload]);
}

function decodeUtf16(buffer, byteOrder) {
  const payload = Buffer.from(buffer.subarray(2));
  if (byteOrder === "be") {
    payload.swap16();
  }
  return payload.toString("utf16le");
}

async function testPreservationAndConflicts(root) {
  const skillTarget = path.join(root, "skills");
  const agentsFile = path.join(root, "codex-home", "AGENTS.md");
  const unrelatedSkill = path.join(skillTarget, "user-owned", "SKILL.md");
  const unrelatedContents = Buffer.from(
    "---\nname: user-owned\ndescription: preserve me\n---\n",
    "utf8",
  );
  const original = Buffer.from(
    "## Existing guidance\r\n\r\nKeep this line.\r\n",
    "utf8",
  );
  await mkdir(path.dirname(agentsFile), { recursive: true });
  await mkdir(path.dirname(unrelatedSkill), { recursive: true });
  await writeFile(agentsFile, original);
  await writeFile(unrelatedSkill, unrelatedContents);

  const commonArguments = [
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
  ];
  runInstaller(commonArguments);

  for (const skillName of expectedSkillNames) {
    const skillFile = path.join(skillTarget, skillName, "SKILL.md");
    assert(
      (await readFile(skillFile, "utf8")).startsWith("---"),
      `Missing installed skill: ${skillName}`,
    );
  }
  assert(
    digest(await readFile(unrelatedSkill)) === digest(unrelatedContents),
    "Unrelated user skill changed",
  );
  if (process.platform !== "win32") {
    for (const repositoryPath of superpowersManifest.executables) {
      const relativePath = repositoryPath.replace(".agents/skills/", "");
      const installedExecutable = path.join(
        skillTarget,
        ...relativePath.split("/"),
      );
      assert(
        ((await stat(installedExecutable)).mode & 0o111) !== 0,
        `Installed executable mode missing: ${relativePath}`,
      );
    }
  }

  const installed = await readFile(agentsFile, "utf8");
  assert(installed.startsWith(original.toString("utf8")), "Existing guidance changed");
  assert(installed.includes(startMarker) && installed.includes(endMarker), "Managed block missing");
  assert(!/(^|[^\r])\n/.test(installed), "CRLF newline style was not preserved");

  let backups = await listAgentBackups(agentsFile);
  assert(backups.length === 1, "Initial AGENTS.md backup missing");
  assert(
    digest(await readFile(backups[0])) === digest(original),
    "Initial AGENTS.md backup differs",
  );

  runInstaller([...commonArguments, "--verify"]);
  runInstaller(commonArguments);
  backups = await listAgentBackups(agentsFile);
  assert(backups.length === 1, "Idempotent reinstall created another backup");

  const conflicting = installed.replace("`full` intensity", "`lite` intensity");
  assert(conflicting !== installed, "Conflict fixture was not created");
  await writeFile(agentsFile, conflicting, "utf8");
  const conflictingHash = digest(await readFile(agentsFile));
  runInstaller(commonArguments, false);
  assert(digest(await readFile(agentsFile)) === conflictingHash, "Conflict was overwritten without --force");

  runInstaller([...commonArguments, "--force"]);
  runInstaller([...commonArguments, "--verify"]);
  assert(
    digest(await readFile(unrelatedSkill)) === digest(unrelatedContents),
    "Forced update changed unrelated user skill",
  );
  backups = await listAgentBackups(agentsFile);
  assert(backups.length === 2, "Forced update did not create a backup");

  const skillFile = path.join(skillTarget, "caveman", "SKILL.md");
  const brokenSkill = Buffer.concat([
    await readFile(skillFile),
    Buffer.from("\nBROKEN FIXTURE\n", "utf8"),
  ]);
  await writeFile(skillFile, brokenSkill);
  const malformedAgents = (await readFile(agentsFile, "utf8")).replace(endMarker, "");
  await writeFile(agentsFile, malformedAgents, "utf8");
  runInstaller([...commonArguments, "--force"], false);
  assert(
    digest(await readFile(skillFile)) === digest(brokenSkill),
    "Malformed marker failure changed a skill before aborting",
  );
  assert(
    (await readFile(agentsFile, "utf8")) === malformedAgents,
    "Malformed marker failure changed AGENTS.md",
  );
  backups = await listAgentBackups(agentsFile);
  assert(backups.length === 2, "Malformed marker failure created a backup");
}

async function testSuperpowersConflictAndBackup(root) {
  const skillTarget = path.join(root, "skills");
  const agentsFile = path.join(root, "codex-home", "AGENTS.md");
  const conflictingSkill = path.join(skillTarget, "brainstorming");
  const conflictingSkillFile = path.join(conflictingSkill, "SKILL.md");
  const conflictingContents = Buffer.from(
    "---\nname: brainstorming\ndescription: user copy\n---\n",
    "utf8",
  );
  await mkdir(conflictingSkill, { recursive: true });
  await writeFile(conflictingSkillFile, conflictingContents);

  const argumentsList = [
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
  ];
  runInstaller(argumentsList, false);
  assert(
    digest(await readFile(conflictingSkillFile)) === digest(conflictingContents),
    "Superpowers conflict was overwritten without --force",
  );
  assert(
    !(await pathExists(path.join(skillTarget, "caveman"))),
    "Superpowers conflict preflight installed another managed skill",
  );

  runInstaller([...argumentsList, "--force"]);
  runInstaller([...argumentsList, "--verify"]);
  const backupRoot = path.join(root, "skill-backups");
  const backups = (await readdir(backupRoot)).filter((name) =>
    name.startsWith("brainstorming.backup-"),
  );
  assert(backups.length === 1, "Superpowers conflict backup missing");
  assert(
    digest(
      await readFile(path.join(backupRoot, backups[0], "SKILL.md")),
    ) === digest(conflictingContents),
    "Superpowers conflict backup differs",
  );
}

async function testUtf16(root, byteOrder) {
  const skillTarget = path.join(root, `${byteOrder}-skills`);
  const agentsFile = path.join(root, `${byteOrder}-home`, "AGENTS.md");
  const originalText = "## 기존 지침\r\n\r\n이 줄을 유지합니다.\r\n";
  const original = encodeUtf16(originalText, byteOrder);
  await mkdir(path.dirname(agentsFile), { recursive: true });
  await writeFile(agentsFile, original);

  const argumentsList = [
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
  ];
  runInstaller(argumentsList);
  runInstaller([...argumentsList, "--verify"]);

  const installed = await readFile(agentsFile);
  const expectedBom = byteOrder === "be" ? [0xfe, 0xff] : [0xff, 0xfe];
  assert(
    installed[0] === expectedBom[0] && installed[1] === expectedBom[1],
    `UTF-16${byteOrder.toUpperCase()} BOM changed`,
  );
  const decoded = decodeUtf16(installed, byteOrder);
  assert(decoded.startsWith(originalText), `UTF-16${byteOrder.toUpperCase()} guidance changed`);
  assert(decoded.includes(startMarker) && decoded.includes(endMarker), "UTF-16 managed block missing");
  assert(!/(^|[^\r])\n/.test(decoded), "UTF-16 CRLF newline style was not preserved");

  const backups = await listAgentBackups(agentsFile);
  assert(backups.length === 1, "UTF-16 backup missing");
  assert(
    digest(await readFile(backups[0])) === digest(original),
    "UTF-16 backup differs",
  );
}

async function testUnsupportedEncoding(root) {
  const skillTarget = path.join(root, "invalid-skills");
  const agentsFile = path.join(root, "invalid-home", "AGENTS.md");
  const original = Buffer.from([0x41, 0x00, 0x42, 0x00]);
  await mkdir(path.dirname(agentsFile), { recursive: true });
  await writeFile(agentsFile, original);
  runInstaller(
    ["--target", skillTarget, "--agents-file", agentsFile, "--force"],
    false,
  );
  assert(
    digest(await readFile(agentsFile)) === digest(original),
    "Unsupported encoding input was changed",
  );
}

const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "aisupport-installer-test-"));
try {
  await testPreservationAndConflicts(path.join(temporaryRoot, "main"));
  await testSuperpowersConflictAndBackup(
    path.join(temporaryRoot, "superpowers-conflict"),
  );
  await testUtf16(path.join(temporaryRoot, "utf16"), "le");
  await testUtf16(path.join(temporaryRoot, "utf16"), "be");
  await testUnsupportedEncoding(path.join(temporaryRoot, "invalid"));
  console.log("AISUPPORT installer tests passed");
} finally {
  await rm(temporaryRoot, { recursive: true, force: true });
}
