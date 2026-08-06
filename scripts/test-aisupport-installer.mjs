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
const skillInstallerPath = path.join(scriptDirectory, "install-skills.mjs");
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
const startMarker = "<!-- BEGIN SHORT PORTABLE ALWAYS-ON -->";
const endMarker = "<!-- END SHORT PORTABLE ALWAYS-ON -->";
const glifStartMarker = "# BEGIN AISUPPORT GLIF MCP";
const glifEndMarker = "# END AISUPPORT GLIF MCP";

function digest(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function frontmatterValue(contents, key) {
  const normalized = contents.replace(/\r\n/g, "\n");
  const closing = normalized.indexOf("\n---\n", 4);
  const frontmatter = normalized.slice(4, closing);
  const match = frontmatter.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
  return match?.[1].trim();
}

async function testSkillTriggers() {
  const shortSkill = await readFile(
    path.join(repositoryRoot, ".agents", "skills", "short", "SKILL.md"),
    "utf8",
  );
  assert(
    frontmatterValue(shortSkill, "description") ===
      "Apply automatically to every response and coding task unless the user says stop short or normal mode. Keep communication concise and coding changes small, correct, and maintainable.",
    "Short automatic trigger missing",
  );
  for (const required of [
    "Preserve negation, numbers, units, paths, commands, code and API names, and exact error text.",
    "Make the smallest maintainable change that satisfies the full request.",
    "Use the repository's existing test system and verify in proportion to risk.",
    "Persisted content uses normal, complete prose.",
  ]) {
    assert(
      shortSkill.includes(required),
      `Short rule missing: ${required}`,
    );
  }

  for (const skillName of expectedSkillNames.filter(
    (name) => name !== "short" && name !== "glif",
  )) {
    const skill = await readFile(
      path.join(repositoryRoot, ".agents", "skills", skillName, "SKILL.md"),
      "utf8",
    );
    const description = frontmatterValue(skill, "description");
    assert(
      description === `Use only when the user explicitly invokes $${skillName}.`,
      `Automatic trigger allowed: ${skillName}`,
    );
  }

  const glifSkill = await readFile(
    path.join(repositoryRoot, ".agents", "skills", "glif", "SKILL.md"),
    "utf8",
  );
  assert(
    frontmatterValue(glifSkill, "description") ===
      "Use only when the user explicitly invokes $glif or says Glif, Glyphs, or 글리프 for image, video, or audio generation and refinement through the Glif MCP server.",
    "Glif explicit trigger missing",
  );

  const gupabalSkill = await readFile(
    path.join(repositoryRoot, ".agents", "skills", "gupabal-game", "SKILL.md"),
    "utf8",
  );
  assert(
    frontmatterValue(gupabalSkill, "description") ===
      "Use only when the user explicitly invokes $gupabal-game or says 구파발게임.",
    "Automatic trigger allowed: gupabal-game",
  );

  const rootGuidance = await readFile(
    path.join(repositoryRoot, "AGENTS.md"),
    "utf8",
  );
  for (const forbidden of [
    "Apply the available `using-superpowers` skill at the start",
    "Invoke each relevant Superpowers process skill before implementation",
  ]) {
    assert(!rootGuidance.includes(forbidden), `Automatic guidance remains: ${forbidden}`);
  }
  for (const required of [
    "Apply the available `short` skill to every response and coding task.",
    "`short` is the only automatically invoked AISUPPORT skill.",
    "Do not invoke AISUPPORT skills other than `short` unless the",
    "Do not spawn subagents or delegate work unless the user explicitly requests",
    "Do not create or switch branches, create commits or pull requests, push,",
    "When the user does not request another branch, stay on `master`.",
    "Never schedule or repeat them in the background.",
    "commit or push completed skill or hook changes only when",
  ]) {
    assert(rootGuidance.includes(required), `Manual execution rule missing: ${required}`);
  }
}

async function testManualOnlyGitHubWorkflow() {
  const workflow = (
    await readFile(
      path.join(repositoryRoot, ".github", "workflows", "verify-aisupport.yml"),
      "utf8",
    )
  ).replace(/\r\n/g, "\n");
  const triggerBlock = workflow.match(/^on:\n([\s\S]*?)^jobs:\n/m)?.[1];
  assert(triggerBlock, "GitHub Actions trigger block is missing");
  const topLevelTriggers = [...triggerBlock.matchAll(/^  ([\w-]+):\s*$/gm)].map(
    (match) => match[1],
  );
  assert(
    topLevelTriggers.length === 1 && topLevelTriggers[0] === "workflow_dispatch",
    `Automatic GitHub trigger allowed: ${topLevelTriggers.join(", ") || "none"}`,
  );
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

function runInstaller(argumentsList, shouldPass = true, environment = process.env) {
  const result = spawnSync(process.execPath, [installerPath, ...argumentsList], {
    encoding: "utf8",
    env: environment,
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
  const configFile = path.join(root, "codex-home", "config.toml");
  const unrelatedSkill = path.join(skillTarget, "user-owned", "SKILL.md");
  const unrelatedContents = Buffer.from(
    "---\nname: user-owned\ndescription: preserve me\n---\n",
    "utf8",
  );
  const original = Buffer.from(
    "## Existing guidance\r\n\r\nKeep this line.\r\n",
    "utf8",
  );
  const originalConfig = Buffer.from('model = "gpt-test"\r\n', "utf8");
  await mkdir(path.dirname(agentsFile), { recursive: true });
  await mkdir(path.dirname(unrelatedSkill), { recursive: true });
  await writeFile(agentsFile, original);
  await writeFile(configFile, originalConfig);
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

  const installedConfig = await readFile(configFile, "utf8");
  assert(
    installedConfig.startsWith(originalConfig.toString("utf8")),
    "Existing config.toml content changed",
  );
  assert(
    installedConfig.includes(glifStartMarker) &&
      installedConfig.includes(glifEndMarker) &&
      installedConfig.includes('url = "https://glif.app/api/mcp"'),
    "Glif MCP managed block missing",
  );
  assert(
    !/(^|[^\r])\n/.test(installedConfig),
    "config.toml CRLF style was not preserved",
  );

  let backups = await listAgentBackups(agentsFile);
  let configBackups = await listAgentBackups(configFile);
  assert(backups.length === 1, "Initial AGENTS.md backup missing");
  assert(
    digest(await readFile(backups[0])) === digest(original),
    "Initial AGENTS.md backup differs",
  );
  assert(configBackups.length === 1, "Initial config.toml backup missing");
  assert(
    digest(await readFile(configBackups[0])) === digest(originalConfig),
    "Initial config.toml backup differs",
  );

  runInstaller([...commonArguments, "--verify"]);
  runInstaller(commonArguments);
  backups = await listAgentBackups(agentsFile);
  configBackups = await listAgentBackups(configFile);
  assert(backups.length === 1, "Idempotent reinstall created another backup");
  assert(configBackups.length === 1, "Idempotent reinstall created config backup");

  const conflicting = installed.replace(
    "Apply the available `short` skill to every response and coding task.",
    "Apply the available `short` skill to every other response and coding task.",
  );
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

  const skillFile = path.join(skillTarget, "short", "SKILL.md");
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

async function testExistingGlifMcpHandling(root) {
  const correctRoot = path.join(root, "correct");
  const correctTarget = path.join(correctRoot, "skills");
  const correctHome = path.join(correctRoot, "codex-home");
  const correctAgents = path.join(correctHome, "AGENTS.md");
  const correctConfig = path.join(correctHome, "config.toml");
  const customConfig = [
    "[mcp_servers.glif]",
    'url = "https://glif.app/api/mcp"',
    "enabled = false",
    "",
  ].join("\n");
  await mkdir(correctHome, { recursive: true });
  await writeFile(correctConfig, customConfig, "utf8");
  runInstaller(["--target", correctTarget, "--agents-file", correctAgents]);
  runInstaller([
    "--target",
    correctTarget,
    "--agents-file",
    correctAgents,
    "--verify",
  ]);
  assert(
    (await readFile(correctConfig, "utf8")) === customConfig,
    "Compatible user-managed Glif MCP config changed",
  );

  const wrongRoot = path.join(root, "wrong");
  const wrongTarget = path.join(wrongRoot, "skills");
  const wrongHome = path.join(wrongRoot, "codex-home");
  const wrongAgents = path.join(wrongHome, "AGENTS.md");
  const wrongConfig = path.join(wrongHome, "config.toml");
  const conflictingConfig = [
    "[mcp_servers.glif]",
    'url = "https://example.invalid/mcp"',
    "",
  ].join("\n");
  await mkdir(wrongHome, { recursive: true });
  await writeFile(wrongConfig, conflictingConfig, "utf8");
  runInstaller(
    ["--target", wrongTarget, "--agents-file", wrongAgents],
    false,
  );
  assert(
    (await readFile(wrongConfig, "utf8")) === conflictingConfig,
    "Conflicting user-managed Glif MCP config changed",
  );
  assert(
    !(await pathExists(path.join(wrongTarget, "glif"))),
    "Conflict installed Glif skill",
  );
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
    !(await pathExists(path.join(skillTarget, "short"))),
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

async function testOptionCannotBeConsumedAsAPath(root) {
  await mkdir(root, { recursive: true });
  const result = spawnSync(
    process.execPath,
    [installerPath, "--target", "--dry-run"],
    { cwd: root, encoding: "utf8" },
  );
  assert(result.status !== 0, "Option token was accepted as a target path");
  assert(
    !(await pathExists(path.join(root, "--dry-run"))),
    "Malformed arguments wrote to an option-named target",
  );
}

async function testIntegratedPythonUsesUtf8(root) {
  const unicodeRoot = path.join(root, "한글 경로 🚀");
  const skillTarget = path.join(unicodeRoot, "사용자 스킬");
  const agentsFile = path.join(unicodeRoot, "코덱스 홈", "AGENTS.md");
  const environment = { ...process.env, PYTHONUTF8: "0" };
  await mkdir(unicodeRoot, { recursive: true });

  const commonArguments = [
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
  ];
  runInstaller([...commonArguments, "--dry-run"], true, environment);
  runInstaller(commonArguments, true, environment);
  runInstaller([...commonArguments, "--verify"], true, environment);
}

async function testIntegratedPathsUseOneTildeExpansion(root) {
  const uniqueName = path.basename(root);
  const configuredHome = `~/.aisupport-tests/${uniqueName}/코덱스 홈`;
  const configuredTarget = `~/.aisupport-tests/${uniqueName}/사용자 스킬`;
  const expectedHome = path.join(
    os.homedir(),
    ".aisupport-tests",
    uniqueName,
    "코덱스 홈",
  );
  const expectedTarget = path.join(
    os.homedir(),
    ".aisupport-tests",
    uniqueName,
    "사용자 스킬",
  );
  const wrongHome = path.resolve(configuredHome);
  const wrongTarget = path.resolve(configuredTarget);
  const environment = { ...process.env, CODEX_HOME: configuredHome };
  await mkdir(root, { recursive: true });

  const result = runInstaller(
    ["--target", configuredTarget, "--dry-run"],
    true,
    environment,
  );
  assert(result.stdout.includes(expectedHome), "Expanded CODEX_HOME was not used");
  assert(result.stdout.includes(expectedTarget), "Expanded skill target was not used");
  assert(!result.stdout.includes(wrongHome), "CODEX_HOME kept a literal tilde");
  assert(!result.stdout.includes(wrongTarget), "Skill target kept a literal tilde");

  const explicitAgentsFile = `~/.aisupport-tests/${uniqueName}/명시 경로/AGENTS.md`;
  const explicitExpected = path.join(
    os.homedir(),
    ".aisupport-tests",
    uniqueName,
    "명시 경로",
    "AGENTS.md",
  );
  const explicitResult = runInstaller(
    [
      "--target",
      configuredTarget,
      "--agents-file",
      explicitAgentsFile,
      "--dry-run",
    ],
    true,
    environment,
  );
  assert(
    explicitResult.stdout.includes(explicitExpected),
    "Explicit --agents-file did not override CODEX_HOME",
  );

  const directResult = spawnSync(
    process.execPath,
    [
      skillInstallerPath,
      "--target",
      configuredTarget,
      "--agents-file",
      explicitAgentsFile,
      "--dry-run",
    ],
    { encoding: "utf8", env: environment },
  );
  assert(directResult.status === 0, "Direct Node installer rejected tilde paths");
  assert(
    directResult.stdout.includes(expectedTarget)
      && directResult.stdout.includes(explicitExpected),
    "Direct Node installer did not expand tilde paths",
  );
  assert(
    !directResult.stdout.includes(wrongTarget),
    "Direct Node installer kept a literal tilde",
  );

  runInstaller(
    [
      "--target",
      "~another-user/skills",
      "--agents-file",
      explicitAgentsFile,
      "--dry-run",
    ],
    false,
    environment,
  );
}

async function testGupabalFallbackUsesCodexHome() {
  const skill = await readFile(
    path.join(repositoryRoot, ".agents", "skills", "gupabal-game", "SKILL.md"),
    "utf8",
  );
  assert(
    skill.includes("$CODEX_HOME/agents/gupabal_*.toml"),
    "Gupabal fallback does not use CODEX_HOME",
  );
  assert(
    !skill.includes("$HOME/.codex/agents/gupabal_*.toml"),
    "Gupabal fallback still hardcodes HOME/.codex",
  );
}

async function testIntegratedHookOptIn(root) {
  const skillTarget = path.join(root, "skills");
  const agentsFile = path.join(root, "codex-home", "AGENTS.md");
  runInstaller([
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
    "--with-hooks",
  ]);
  const hooks = await readFile(
    path.join(root, "codex-home", "hooks.json"),
    "utf8",
  );
  assert(hooks.includes("gupabal_hooks_"), "Integrated installer dropped --with-hooks");
}

async function testIntegratedTelegramOptIn(root) {
  const skillTarget = path.join(root, "skills");
  const codexHome = path.join(root, "codex-home");
  const agentsFile = path.join(codexHome, "AGENTS.md");
  await mkdir(codexHome, { recursive: true });
  await writeFile(
    path.join(codexHome, "config.toml"),
    'notify = ["existing-notifier", "turn-ended"]\n\n[features]\nhooks = false\n',
    "utf8",
  );
  runInstaller([
    "--target",
    skillTarget,
    "--agents-file",
    agentsFile,
    "--with-telegram",
  ]);
  const config = await readFile(path.join(codexHome, "config.toml"), "utf8");
  assert(config.includes("telegram_notify_"), "Telegram notifier was not installed");
  assert(config.includes("existing-notifier"), "Existing notifier was not preserved");
}

const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "aisupport-installer-test-"));
try {
  await testSkillTriggers();
  await testManualOnlyGitHubWorkflow();
  await testPreservationAndConflicts(path.join(temporaryRoot, "main"));
  await testExistingGlifMcpHandling(path.join(temporaryRoot, "glif-mcp"));
  await testSuperpowersConflictAndBackup(
    path.join(temporaryRoot, "superpowers-conflict"),
  );
  await testUtf16(path.join(temporaryRoot, "utf16"), "le");
  await testUtf16(path.join(temporaryRoot, "utf16"), "be");
  await testUnsupportedEncoding(path.join(temporaryRoot, "invalid"));
  await testOptionCannotBeConsumedAsAPath(
    path.join(temporaryRoot, "invalid-arguments"),
  );
  await testIntegratedPythonUsesUtf8(
    path.join(temporaryRoot, "integrated-python-utf8"),
  );
  await testIntegratedPathsUseOneTildeExpansion(
    path.join(temporaryRoot, "integrated-path-normalization"),
  );
  await testGupabalFallbackUsesCodexHome();
  await testIntegratedHookOptIn(path.join(temporaryRoot, "integrated-hook-opt-in"));
  await testIntegratedTelegramOptIn(
    path.join(temporaryRoot, "integrated-telegram-opt-in"),
  );
  console.log("AISUPPORT installer tests passed");
} finally {
  await rm(temporaryRoot, { recursive: true, force: true });
}
