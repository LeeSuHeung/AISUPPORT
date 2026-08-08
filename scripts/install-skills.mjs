#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  cp,
  copyFile,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SKILL_BUNDLES = Object.freeze([
  Object.freeze({
    displayName: "Short",
    source: "LeeSuHeung/AISUPPORT",
    ref: "v2",
    sourceType: "local",
    manifestFile: "short-manifest.json",
    executables: Object.freeze([]),
    skillNames: Object.freeze(["short"]),
  }),
  Object.freeze({
    displayName: "Superpowers",
    source: "obra/superpowers",
    ref: "v6.1.1",
    sourceType: "github",
    manifestFile: "superpowers-manifest.json",
    executables: Object.freeze([
      ".agents/skills/brainstorming/scripts/start-server.sh",
      ".agents/skills/brainstorming/scripts/stop-server.sh",
      ".agents/skills/subagent-driven-development/scripts/review-package",
      ".agents/skills/subagent-driven-development/scripts/sdd-workspace",
      ".agents/skills/subagent-driven-development/scripts/task-brief",
      ".agents/skills/systematic-debugging/find-polluter.sh",
      ".agents/skills/writing-skills/render-graphs.js",
    ]),
    skillNames: Object.freeze([
      "brainstorming",
      "dispatching-parallel-agents",
      "executing-plans",
      "finishing-a-development-branch",
      "receiving-code-review",
      "requesting-code-review",
      "subagent-driven-development",
      "systematic-debugging",
      "test-driven-development",
      "using-git-worktrees",
      "using-superpowers",
      "verification-before-completion",
      "writing-plans",
      "writing-skills",
    ]),
  }),
  Object.freeze({
    displayName: "Glif",
    source: "LeeSuHeung/AISUPPORT",
    ref: "v1",
    sourceType: "local",
    manifestFile: "glif-manifest.json",
    executables: Object.freeze([]),
    skillNames: Object.freeze(["glif"]),
  }),
]);

const SKILL_NAMES = Object.freeze(
  SKILL_BUNDLES.flatMap((bundle) => bundle.skillNames),
);

const RETIRED_SKILL_NAMES = Object.freeze([
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

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..");
const sourceRoot = path.join(repositoryRoot, ".agents", "skills");
const lockPath = path.join(repositoryRoot, "skills-lock.json");
const repositoryAgentsPath = path.join(repositoryRoot, "AGENTS.md");
const alwaysOnStartMarker = "<!-- BEGIN SHORT PORTABLE ALWAYS-ON -->";
const alwaysOnEndMarker = "<!-- END SHORT PORTABLE ALWAYS-ON -->";
const legacyAlwaysOnStartMarker = "<!-- BEGIN CAVEMAN PORTABLE ALWAYS-ON -->";
const legacyAlwaysOnEndMarker = "<!-- END CAVEMAN PORTABLE ALWAYS-ON -->";
const glifMcpStartMarker = "# BEGIN AISUPPORT GLIF MCP";
const glifMcpEndMarker = "# END AISUPPORT GLIF MCP";
const glifMcpBlock = `${glifMcpStartMarker}
[mcp_servers.glif]
url = "https://glif.app/api/mcp"
auth = "oauth"
default_tools_approval_mode = "writes"
${glifMcpEndMarker}`;

function resolveUserPath(value, label) {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(`${label} requires a path`);
  }
  let expanded = trimmed;
  if (trimmed === "~") {
    expanded = os.homedir();
  } else if (trimmed.startsWith("~/") || trimmed.startsWith("~\\")) {
    expanded = path.join(os.homedir(), trimmed.slice(2));
  } else if (trimmed.startsWith("~")) {
    throw new Error(`${label} supports only ~, ~/, or ~\\ user-home paths`);
  }
  return path.resolve(expanded);
}

function defaultCodexHome() {
  const configuredHome = process.env.CODEX_HOME?.trim();
  return configuredHome
    ? resolveUserPath(configuredHome, "CODEX_HOME")
    : path.join(os.homedir(), ".codex");
}

function printUsage() {
  console.log(`Usage: node scripts/install-aisupport.mjs [options]

Copy the reviewed, repository-pinned AISUPPORT skill suite into Codex's
user-level skill directory and configure the Glif MCP server. The installer
does not download or execute upstream code.

Options:
  --target <path>       Override the skill target ($HOME/.agents/skills)
  --agents-file <path>  Override the always-on file ($CODEX_HOME/AGENTS.md)
  --verify              Verify skills, guidance, and Glif MCP configuration
  --dry-run             Show actions without writing files
  --force               Back up and replace conflicting managed content
  --with-hooks          Install opt-in Gupabal command Hooks
  --with-telegram       Install opt-in Telegram completion notifications
  --help                Show this help
`);
}

function parseArguments(argumentsList) {
  const options = {
    target: path.join(os.homedir(), ".agents", "skills"),
    agentsFile: path.join(defaultCodexHome(), "AGENTS.md"),
    verify: false,
    dryRun: false,
    force: false,
  };

  for (let index = 0; index < argumentsList.length; index += 1) {
    const argument = argumentsList[index];
    switch (argument) {
      case "--target": {
        const target = argumentsList[index + 1];
        if (!target || target.startsWith("-")) {
          throw new Error("--target requires a path");
        }
        options.target = resolveUserPath(target, "--target");
        index += 1;
        break;
      }
      case "--agents-file": {
        const agentsFile = argumentsList[index + 1];
        if (!agentsFile || agentsFile.startsWith("-")) {
          throw new Error("--agents-file requires a path");
        }
        options.agentsFile = resolveUserPath(agentsFile, "--agents-file");
        index += 1;
        break;
      }
      case "--verify":
        options.verify = true;
        break;
      case "--dry-run":
        options.dryRun = true;
        break;
      case "--force":
        options.force = true;
        break;
      case "--help":
      case "-h":
        printUsage();
        process.exit(0);
        break;
      default:
        throw new Error(`Unknown option: ${argument}`);
    }
  }

  if (options.verify && options.force) {
    throw new Error("--verify and --force cannot be used together");
  }
  if (options.verify && options.dryRun) {
    throw new Error("--verify and --dry-run cannot be used together");
  }

  return options;
}

async function getPathState(targetPath) {
  try {
    return await lstat(targetPath);
  } catch (error) {
    if (error?.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function countOccurrences(contents, marker) {
  let count = 0;
  let offset = 0;
  while (true) {
    const index = contents.indexOf(marker, offset);
    if (index < 0) {
      return count;
    }
    count += 1;
    offset = index + marker.length;
  }
}

function hashBytes(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

function decodeTextBuffer(buffer, filePath) {
  let encoding = "utf8";
  let bom = false;
  let payload = buffer;

  if (buffer.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf]))) {
    bom = true;
    payload = buffer.subarray(3);
  } else if (buffer.subarray(0, 2).equals(Buffer.from([0xff, 0xfe]))) {
    encoding = "utf16le";
    bom = true;
    payload = buffer.subarray(2);
  } else if (buffer.subarray(0, 2).equals(Buffer.from([0xfe, 0xff]))) {
    encoding = "utf16be";
    bom = true;
    payload = buffer.subarray(2);
  } else if (buffer.includes(0)) {
    throw new Error(
      `Unsupported text encoding in ${filePath}; UTF-16 files require a byte-order mark`,
    );
  }

  try {
    const decoder = new TextDecoder(encoding.replace("utf16", "utf-16"), {
      fatal: true,
      ignoreBOM: true,
    });
    return {
      contents: decoder.decode(payload),
      format: { encoding, bom },
    };
  } catch (error) {
    throw new Error(`Invalid ${encoding.toUpperCase()} text in ${filePath}`, {
      cause: error,
    });
  }
}

function encodeTextBuffer(contents, format) {
  let encoded;
  let marker = Buffer.alloc(0);
  if (format.encoding === "utf8") {
    encoded = Buffer.from(contents, "utf8");
    if (format.bom) {
      marker = Buffer.from([0xef, 0xbb, 0xbf]);
    }
  } else if (format.encoding === "utf16le") {
    encoded = Buffer.from(contents, "utf16le");
    marker = Buffer.from([0xff, 0xfe]);
  } else if (format.encoding === "utf16be") {
    encoded = Buffer.from(contents, "utf16le");
    encoded.swap16();
    marker = Buffer.from([0xfe, 0xff]);
  } else {
    throw new Error(`Unsupported output encoding: ${format.encoding}`);
  }
  return format.bom ? Buffer.concat([marker, encoded]) : encoded;
}

async function readTextFile(filePath) {
  const bytes = await readFile(filePath);
  return {
    bytes,
    ...decodeTextBuffer(bytes, filePath),
  };
}

async function readAlwaysOnBlock() {
  const { contents } = await readTextFile(repositoryAgentsPath);
  const startCount = countOccurrences(contents, alwaysOnStartMarker);
  const endCount = countOccurrences(contents, alwaysOnEndMarker);
  if (startCount !== 1 || endCount !== 1) {
    throw new Error(`Repository AGENTS.md must contain one AISUPPORT managed block`);
  }

  const startIndex = contents.indexOf(alwaysOnStartMarker);
  const endIndex = contents.indexOf(alwaysOnEndMarker, startIndex);
  if (endIndex < startIndex) {
    throw new Error(`Invalid Short marker order in ${repositoryAgentsPath}`);
  }
  return contents
    .slice(startIndex, endIndex + alwaysOnEndMarker.length)
    .replace(/\r\n/g, "\n");
}

async function inspectAlwaysOnFile(
  agentsFile,
  expectedBlock,
  startMarker = alwaysOnStartMarker,
  endMarker = alwaysOnEndMarker,
) {
  const state = await getPathState(agentsFile);
  if (!state) {
    return {
      exists: false,
      status: "missing",
      contents: "",
      format: { encoding: "utf8", bom: false },
      snapshotHash: null,
      mode: 0o666,
    };
  }
  if (!state.isFile()) {
    throw new Error(`Always-on target must be a regular file: ${agentsFile}`);
  }

  const { bytes, contents, format } = await readTextFile(agentsFile);
  const sharedState = {
    exists: true,
    contents,
    format,
    snapshotHash: hashBytes(bytes),
    mode: state.mode & 0o777,
  };
  const startCount = countOccurrences(contents, startMarker);
  const endCount = countOccurrences(contents, endMarker);
  if (startCount === 0 && endCount === 0) {
    return { ...sharedState, status: "missing" };
  }
  if (startCount !== 1 || endCount !== 1) {
    return {
      ...sharedState,
      status: "conflict",
      reason: "marker count mismatch",
      replaceable: false,
    };
  }

  const startIndex = contents.indexOf(startMarker);
  const endMarkerIndex = contents.indexOf(endMarker, startIndex);
  if (endMarkerIndex < startIndex) {
    return {
      ...sharedState,
      status: "conflict",
      reason: "marker order mismatch",
      replaceable: false,
    };
  }
  const endIndex = endMarkerIndex + endMarker.length;
  const existingBlock = contents
    .slice(startIndex, endIndex)
    .replace(/\r\n/g, "\n");

  return {
    ...sharedState,
    status: existingBlock === expectedBlock ? "current" : "conflict",
    startIndex,
    endIndex,
    replaceable: true,
    reason: existingBlock === expectedBlock ? undefined : "managed block differs",
  };
}

async function inspectManagedAlwaysOnFile(agentsFile, expectedBlock) {
  const current = await inspectAlwaysOnFile(agentsFile, expectedBlock);
  const legacyStartCount = countOccurrences(
    current.contents,
    legacyAlwaysOnStartMarker,
  );
  const legacyEndCount = countOccurrences(
    current.contents,
    legacyAlwaysOnEndMarker,
  );

  if (current.status !== "missing") {
    if (legacyStartCount > 0 || legacyEndCount > 0) {
      return {
        ...current,
        status: "conflict",
        reason: "current and legacy managed blocks both exist",
        replaceable: false,
      };
    }
    return current;
  }
  if (legacyStartCount === 0 && legacyEndCount === 0) {
    return current;
  }

  const legacy = await inspectAlwaysOnFile(
    agentsFile,
    expectedBlock,
    legacyAlwaysOnStartMarker,
    legacyAlwaysOnEndMarker,
  );
  if (legacy.status === "conflict" && legacy.replaceable) {
    return {
      ...legacy,
      status: "legacy",
      reason: "legacy managed block requires migration",
    };
  }
  return legacy;
}

function findGlifMcpSection(contents) {
  const header = /^\s*\[mcp_servers\.glif\]\s*(?:#.*)?$/m;
  const match = header.exec(contents);
  if (!match) {
    return null;
  }
  const sectionStart = match.index;
  const remainderStart = sectionStart + match[0].length;
  const nextHeader = /^\s*\[[^\]]+\]\s*(?:#.*)?$/m.exec(
    contents.slice(remainderStart),
  );
  const sectionEnd = nextHeader
    ? remainderStart + nextHeader.index
    : contents.length;
  return contents.slice(sectionStart, sectionEnd);
}

async function inspectGlifMcpFile(configFile) {
  const state = await inspectAlwaysOnFile(
    configFile,
    glifMcpBlock,
    glifMcpStartMarker,
    glifMcpEndMarker,
  );
  if (state.status !== "missing" || !state.exists) {
    return state;
  }

  const section = findGlifMcpSection(state.contents);
  if (!section) {
    return state;
  }
  const correctUrl = /^\s*url\s*=\s*["']https:\/\/glif\.app\/api\/mcp["']\s*(?:#.*)?$/m.test(
    section,
  );
  if (correctUrl) {
    return { ...state, status: "external" };
  }
  return {
    ...state,
    status: "conflict",
    reason: "existing unmanaged mcp_servers.glif has a different URL",
    replaceable: false,
  };
}

function buildAlwaysOnContents(guidanceState, expectedBlock) {
  const newline = guidanceState.contents.includes("\r\n") ? "\r\n" : "\n";
  const localizedBlock = expectedBlock.replace(/\n/g, newline);

  if (guidanceState.status === "missing") {
    if (guidanceState.contents.length === 0) {
      return `${localizedBlock}${newline}`;
    }
    const separator = guidanceState.contents.endsWith(`${newline}${newline}`)
      ? ""
      : guidanceState.contents.endsWith(newline)
        ? newline
        : `${newline}${newline}`;
    return `${guidanceState.contents}${separator}${localizedBlock}${newline}`;
  }

  if (["conflict", "legacy"].includes(guidanceState.status)) {
    if (!Number.isInteger(guidanceState.startIndex) || !Number.isInteger(guidanceState.endIndex)) {
      throw new Error(`Cannot safely replace malformed AISUPPORT markers`);
    }
    return `${guidanceState.contents.slice(0, guidanceState.startIndex)}${localizedBlock}${guidanceState.contents.slice(guidanceState.endIndex)}`;
  }

  return guidanceState.contents;
}

async function assertAlwaysOnSnapshot(agentsFile, guidanceState) {
  const state = await getPathState(agentsFile);
  if (!guidanceState.exists) {
    if (state) {
      throw new Error(`Always-on target changed during installation: ${agentsFile}`);
    }
    return;
  }
  if (!state?.isFile()) {
    throw new Error(`Always-on target changed during installation: ${agentsFile}`);
  }
  const currentHash = hashBytes(await readFile(agentsFile));
  if (currentHash !== guidanceState.snapshotHash) {
    throw new Error(`Always-on target changed during installation: ${agentsFile}`);
  }
}

async function installAlwaysOnFile(agentsFile, guidanceState, expectedBlock, force) {
  if (guidanceState.status === "current") {
    return null;
  }
  if (guidanceState.status === "conflict" && !force) {
    throw new Error(`Managed AISUPPORT block differs in ${agentsFile}; use --force`);
  }

  await mkdir(path.dirname(agentsFile), { recursive: true });
  await assertAlwaysOnSnapshot(agentsFile, guidanceState);
  let backupPath = null;
  if (guidanceState.exists) {
    backupPath = await findBackupPath(
      path.dirname(agentsFile),
      `${path.basename(agentsFile)}.aisupport`,
    );
    await copyFile(agentsFile, backupPath);
    if (hashBytes(await readFile(backupPath)) !== guidanceState.snapshotHash) {
      throw new Error(`Always-on target changed while backing it up: ${agentsFile}`);
    }
  }

  const temporaryDirectory = await mkdtemp(
    path.join(path.dirname(agentsFile), `.${path.basename(agentsFile)}-aisupport-install-`),
  );
  const temporaryFile = path.join(temporaryDirectory, path.basename(agentsFile));
  try {
    const updatedContents = buildAlwaysOnContents(guidanceState, expectedBlock);
    await writeFile(
      temporaryFile,
      encodeTextBuffer(updatedContents, guidanceState.format),
      { flag: "wx", mode: guidanceState.mode },
    );
    await assertAlwaysOnSnapshot(agentsFile, guidanceState);
    await rename(temporaryFile, agentsFile);
    await rm(temporaryDirectory, { recursive: true, force: true });
    return backupPath;
  } catch (error) {
    await rm(temporaryDirectory, { recursive: true, force: true });
    throw error;
  }
}

async function collectFiles(rootPath, currentPath = rootPath) {
  const entries = await readdir(currentPath, { withFileTypes: true });
  entries.sort((left, right) => left.name.localeCompare(right.name, "en"));

  const files = [];
  for (const entry of entries) {
    const entryPath = path.join(currentPath, entry.name);
    if (entry.isSymbolicLink()) {
      throw new Error(`Symbolic links are not allowed in vendored skills: ${entryPath}`);
    }
    if (entry.isDirectory()) {
      files.push(...(await collectFiles(rootPath, entryPath)));
      continue;
    }
    if (!entry.isFile()) {
      throw new Error(`Unsupported filesystem entry: ${entryPath}`);
    }
    files.push(path.relative(rootPath, entryPath));
  }
  return files;
}

export async function hashDirectory(directoryPath) {
  const state = await getPathState(directoryPath);
  if (!state?.isDirectory()) {
    throw new Error(`Expected directory: ${directoryPath}`);
  }

  const digest = createHash("sha256");
  const files = await collectFiles(directoryPath);
  for (const relativePath of files) {
    const normalizedPath = relativePath.split(path.sep).join("/");
    const contents = await readFile(path.join(directoryPath, relativePath));
    digest.update(normalizedPath, "utf8");
    digest.update("\0");
    digest.update(String(contents.length), "utf8");
    digest.update("\0");
    digest.update(contents);
    digest.update("\0");
  }
  return digest.digest("hex");
}

async function hashCanonicalTextDirectory(directoryPath) {
  const state = await getPathState(directoryPath);
  if (!state?.isDirectory()) {
    throw new Error(`Expected directory: ${directoryPath}`);
  }

  const digest = createHash("sha256");
  for (const relativePath of await collectFiles(directoryPath)) {
    const normalizedPath = relativePath.split(path.sep).join("/");
    const canonicalContents = (await readFile(
      path.join(directoryPath, relativePath),
      "utf8",
    )).replace(/\r\n/g, "\n");
    const contents = Buffer.from(canonicalContents, "utf8");
    digest.update(normalizedPath, "utf8");
    digest.update("\0");
    digest.update(String(contents.length), "utf8");
    digest.update("\0");
    digest.update(contents);
    digest.update("\0");
  }
  return digest.digest("hex");
}

function executableRelativePaths(skillName) {
  const prefix = `.agents/skills/${skillName}/`;
  return SKILL_BUNDLES.flatMap((bundle) => bundle.executables)
    .filter((repositoryPath) => repositoryPath.startsWith(prefix))
    .map((repositoryPath) => repositoryPath.slice(prefix.length));
}

async function hasExpectedExecutableModes(skillDirectory, skillName) {
  if (process.platform === "win32") {
    return true;
  }
  for (const relativePath of executableRelativePaths(skillName)) {
    const state = await getPathState(
      path.join(skillDirectory, ...relativePath.split("/")),
    );
    if (!state?.isFile() || (state.mode & 0o111) === 0) {
      return false;
    }
  }
  return true;
}

function readFrontmatterName(contents, skillPath) {
  const normalized = contents.replace(/\r\n/g, "\n");
  if (!normalized.startsWith("---\n")) {
    throw new Error(`Missing YAML frontmatter: ${skillPath}`);
  }
  const closingMarker = normalized.indexOf("\n---\n", 4);
  if (closingMarker < 0) {
    throw new Error(`Unclosed YAML frontmatter: ${skillPath}`);
  }
  const frontmatter = normalized.slice(4, closingMarker);
  const match = frontmatter.match(/^name:\s*["']?([^"'\r\n]+?)["']?\s*$/m);
  if (!match) {
    throw new Error(`Missing skill name: ${skillPath}`);
  }
  return match[1].trim();
}

async function validateSources() {
  const lock = JSON.parse(await readFile(lockPath, "utf8"));
  if (lock.version !== 1 || typeof lock.skills !== "object") {
    throw new Error(`Unsupported skills lock format: ${lockPath}`);
  }

  const lockedNames = Object.keys(lock.skills).sort();
  const expectedNames = [...SKILL_NAMES].sort();
  if (JSON.stringify(lockedNames) !== JSON.stringify(expectedNames)) {
    throw new Error(
      `skills-lock.json must contain exactly: ${expectedNames.join(", ")}`,
    );
  }

  const sourceHashes = new Map();
  const releases = [];

  for (const bundle of SKILL_BUNDLES) {
    const manifestPath = path.join(repositoryRoot, bundle.manifestFile);
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    const invalidUpstreamCommit =
      bundle.sourceType === "github" &&
      !/^[0-9a-f]{40}$/.test(manifest.upstreamCommit ?? "");
    if (
      manifest.version !== 1 ||
      typeof manifest.files !== "object" ||
      invalidUpstreamCommit
    ) {
      throw new Error(
        `Unsupported ${bundle.displayName} manifest format: ${manifestPath}`,
      );
    }
    if (manifest.release !== bundle.ref) {
      throw new Error(
        `${bundle.displayName} manifest release ${manifest.release} does not match ${bundle.ref}`,
      );
    }
    const declaredExecutables = Array.isArray(manifest.executables)
      ? [...manifest.executables].sort()
      : [];
    const expectedExecutables = [...bundle.executables].sort();
    if (
      JSON.stringify(declaredExecutables) !==
      JSON.stringify(expectedExecutables)
    ) {
      throw new Error(
        `${bundle.displayName} executable manifest does not match expected files`,
      );
    }

    const manifestFiles = [];
    for (const skillName of bundle.skillNames) {
      const skillDirectory = path.join(sourceRoot, skillName);
      const skillFile = path.join(skillDirectory, "SKILL.md");
      const declaredName = readFrontmatterName(
        await readFile(skillFile, "utf8"),
        skillFile,
      );
      if (declaredName !== skillName) {
        throw new Error(
          `Skill name mismatch: directory ${skillName}, frontmatter ${declaredName}`,
        );
      }

      const locked = lock.skills[skillName];
      if (
        locked.source !== bundle.source ||
        locked.ref !== bundle.ref ||
        locked.sourceType !== bundle.sourceType
      ) {
        throw new Error(`Unexpected source lock for ${skillName}`);
      }
      if (locked.skillPath !== `skills/${skillName}/SKILL.md`) {
        throw new Error(
          `Unexpected source path for ${skillName}: ${locked.skillPath}`,
        );
      }
      if (!/^[0-9a-f]{64}$/.test(locked.computedHash ?? "")) {
        throw new Error(`Incomplete lock entry for ${skillName}`);
      }
      const canonicalDirectoryHash = await hashCanonicalTextDirectory(
        skillDirectory,
      );
      if (locked.computedHash !== canonicalDirectoryHash) {
        throw new Error(`Lock hash mismatch: ${skillName}`);
      }
      if (!(await hasExpectedExecutableModes(skillDirectory, skillName))) {
        throw new Error(`Executable mode mismatch: ${skillName}`);
      }
      sourceHashes.set(skillName, await hashDirectory(skillDirectory));

      for (const relativePath of await collectFiles(skillDirectory)) {
        const repositoryPath = [
          ".agents",
          "skills",
          skillName,
          ...relativePath.split(path.sep),
        ].join("/");
        manifestFiles.push(repositoryPath);
        const expectedHash = manifest.files[repositoryPath];
        const canonicalContents = (await readFile(
          path.join(skillDirectory, relativePath),
          "utf8",
        )).replace(/\r\n/g, "\n");
        const actualHash = createHash("sha256")
          .update(canonicalContents, "utf8")
          .digest("hex");
        if (!expectedHash || actualHash !== expectedHash) {
          throw new Error(`Manifest hash mismatch: ${repositoryPath}`);
        }
      }
    }

    const declaredManifestFiles = Object.keys(manifest.files).sort();
    const actualManifestFiles = manifestFiles.sort();
    if (
      JSON.stringify(declaredManifestFiles) !==
      JSON.stringify(actualManifestFiles)
    ) {
      throw new Error(
        `${bundle.displayName} manifest file list does not match vendored skill files`,
      );
    }
    releases.push(`${bundle.displayName} ${bundle.ref}`);
  }

  return {
    release: releases.join(", "),
    sourceHashes,
  };
}

function backupSuffix() {
  return new Date().toISOString().replace(/[-:.TZ]/g, "");
}

async function findBackupPath(backupRoot, skillName) {
  await mkdir(backupRoot, { recursive: true });
  const base = path.join(backupRoot, `${skillName}.backup-${backupSuffix()}`);
  let candidate = base;
  let counter = 1;
  while (await getPathState(candidate)) {
    candidate = `${base}-${counter}`;
    counter += 1;
  }
  return candidate;
}

export async function copySkillAtomically(
  source,
  destination,
  expectedHash,
  force,
  renamePath = rename,
  removePath = rm,
  getStatePath = getPathState,
) {
  let backupPath = null;
  const existing = await getStatePath(destination);
  if (existing) {
    if (!force) {
      throw new Error(`Refusing to replace existing skill without --force: ${destination}`);
    }
  }

  await mkdir(path.dirname(destination), { recursive: true });
  const temporaryParent = await mkdtemp(
    path.join(path.dirname(destination), `.${path.basename(destination)}-install-`),
  );
  const temporarySkill = path.join(temporaryParent, path.basename(destination));
  let originalMoved = false;
  let operationError = null;

  try {
    await cp(source, temporarySkill, {
      recursive: true,
      force: false,
      errorOnExist: true,
    });
    const copiedHash = await hashDirectory(temporarySkill);
    if (copiedHash !== expectedHash) {
      throw new Error(`Verification failed while copying ${path.basename(destination)}`);
    }

    if (existing) {
      const backupRoot = path.join(
        path.dirname(path.dirname(destination)),
        "skill-backups",
      );
      backupPath = await findBackupPath(backupRoot, path.basename(destination));
      await renamePath(destination, backupPath);
      originalMoved = true;
    }

    await renamePath(temporarySkill, destination);
    originalMoved = false;
  } catch (error) {
    operationError = error;
    let destinationMissing = false;
    if (originalMoved) {
      try {
        destinationMissing = !(await getStatePath(destination));
      } catch (stateError) {
        operationError = new AggregateError(
          [operationError, stateError],
          `Failed to replace ${path.basename(destination)}: ${operationError.message}; destination inspection before backup restoration also failed: ${stateError.message}`,
        );
      }
    }
    if (originalMoved && destinationMissing) {
      try {
        await renamePath(backupPath, destination);
        originalMoved = false;
      } catch (restoreError) {
        operationError = new AggregateError(
          [error, restoreError],
          `Failed to replace ${path.basename(destination)}: ${error.message}; backup restoration also failed: ${restoreError.message}`,
        );
      }
    }
  }

  let cleanupError = null;
  try {
    await removePath(temporaryParent, { recursive: true, force: true });
  } catch (error) {
    cleanupError = error;
  }

  if (operationError && cleanupError) {
    throw new AggregateError(
      [operationError, cleanupError],
      `${operationError.message}; staging cleanup also failed: ${cleanupError.message}`,
    );
  }
  if (operationError) {
    throw operationError;
  }
  if (cleanupError) {
    throw cleanupError;
  }

  return backupPath;
}

async function retireSkill(destination) {
  if (!(await getPathState(destination))) {
    return null;
  }
  const backupRoot = path.join(
    path.dirname(path.dirname(destination)),
    "skill-backups",
  );
  const backupPath = await findBackupPath(backupRoot, path.basename(destination));
  await rename(destination, backupPath);
  return backupPath;
}

async function main() {
  const nodeMajor = Number.parseInt(process.versions.node.split(".")[0], 10);
  if (!Number.isInteger(nodeMajor) || nodeMajor < 18) {
    throw new Error(`Node.js 18 or newer is required; found ${process.versions.node}`);
  }

  const options = parseArguments(process.argv.slice(2));
  const targetRoot = path.resolve(options.target);
  const agentsFile = path.resolve(options.agentsFile);
  const configFile = path.join(path.dirname(agentsFile), "config.toml");
  const { release, sourceHashes } = await validateSources();
  const alwaysOnBlock = await readAlwaysOnBlock();
  const guidanceState = await inspectManagedAlwaysOnFile(agentsFile, alwaysOnBlock);
  const glifMcpState = await inspectGlifMcpFile(configFile);
  if (guidanceState.status === "conflict" && !guidanceState.replaceable) {
    throw new Error(
      `Cannot safely replace malformed AISUPPORT markers in ${agentsFile}: ${guidanceState.reason}`,
    );
  }
  if (glifMcpState.status === "conflict" && !glifMcpState.replaceable) {
    throw new Error(
      `Cannot safely configure Glif MCP in ${configFile}: ${glifMcpState.reason}`,
    );
  }

  const states = [];
  for (const skillName of SKILL_NAMES) {
    const source = path.join(sourceRoot, skillName);
    const destination = path.join(targetRoot, skillName);
    const destinationState = await getPathState(destination);
    let matches = false;
    if (destinationState) {
      if (!destinationState.isDirectory()) {
        states.push({ skillName, source, destination, conflict: "not a directory" });
        continue;
      }
      matches = (await hashDirectory(destination)) === sourceHashes.get(skillName);
      matches =
        matches &&
        (await hasExpectedExecutableModes(destination, skillName));
    }
    states.push({ skillName, source, destination, exists: Boolean(destinationState), matches });
  }
  const retiredStates = [];
  for (const skillName of RETIRED_SKILL_NAMES) {
    const destination = path.join(targetRoot, skillName);
    retiredStates.push({
      skillName,
      destination,
      exists: Boolean(await getPathState(destination)),
    });
  }

  if (options.verify) {
    const failures = states.filter((state) => !state.matches);
    const retiredFailures = retiredStates.filter((state) => state.exists);
    for (const state of states) {
      console.log(`${state.matches ? "OK" : "MISMATCH"} ${state.skillName}`);
    }
    for (const state of retiredStates) {
      console.log(`${state.exists ? "MISMATCH" : "OK"} retired ${state.skillName}`);
    }
    const guidanceMatches = guidanceState.status === "current";
    const glifMcpMatches = ["current", "external"].includes(glifMcpState.status);
    console.log(`${guidanceMatches ? "OK" : "MISMATCH"} always-on ${agentsFile}`);
    console.log(`${glifMcpMatches ? "OK" : "MISMATCH"} Glif MCP ${configFile}`);
    if (
      failures.length > 0 ||
      retiredFailures.length > 0 ||
      !guidanceMatches ||
      !glifMcpMatches
    ) {
      throw new Error(
        `Verification failed for ${failures.length} skill(s), ${retiredFailures.length} retired skill(s), ${guidanceMatches ? 0 : 1} always-on file(s), and ${glifMcpMatches ? 0 : 1} Glif MCP file(s)`,
      );
    }
    console.log(
      `Verified ${SKILL_NAMES.length} AISUPPORT skills and always-on guidance (${release})`,
    );
    return;
  }

  const conflicts = states.filter(
    (state) => state.conflict || (state.exists && !state.matches),
  );
  const guidanceConflicts = guidanceState.status === "conflict";
  const glifMcpConflicts = glifMcpState.status === "conflict";
  if ((conflicts.length > 0 || guidanceConflicts || glifMcpConflicts) && !options.force) {
    for (const state of conflicts) {
      console.error(`CONFLICT ${state.destination}`);
    }
    if (guidanceConflicts) {
      console.error(`CONFLICT ${agentsFile}: ${guidanceState.reason}`);
    }
    if (glifMcpConflicts) {
      console.error(`CONFLICT ${configFile}: ${glifMcpState.reason}`);
    }
    throw new Error(
      "Existing managed content differs. Re-run with --force to back up and replace it.",
    );
  }

  if (options.dryRun) {
    for (const state of states) {
      const action = state.matches ? "KEEP" : state.exists ? "BACKUP+REPLACE" : "INSTALL";
      console.log(`${action} ${state.skillName} -> ${state.destination}`);
    }
    for (const state of retiredStates) {
      if (state.exists) {
        console.log(`BACKUP+REMOVE retired ${state.skillName} -> ${state.destination}`);
      }
    }
    const guidanceAction = guidanceState.status === "current"
      ? "KEEP"
      : guidanceState.exists
        ? "BACKUP+UPDATE"
        : "INSTALL";
    console.log(`${guidanceAction} always-on -> ${agentsFile}`);
    const glifMcpAction = ["current", "external"].includes(glifMcpState.status)
      ? "KEEP"
      : glifMcpState.exists
        ? "BACKUP+UPDATE"
        : "INSTALL";
    console.log(`${glifMcpAction} Glif MCP -> ${configFile}`);
    console.log(`Dry run complete for AISUPPORT skills (${release})`);
    return;
  }

  await mkdir(targetRoot, { recursive: true });
  for (const state of states) {
    if (state.matches) {
      console.log(`UP-TO-DATE ${state.skillName}`);
      continue;
    }
    const backupPath = await copySkillAtomically(
      state.source,
      state.destination,
      sourceHashes.get(state.skillName),
      options.force,
    );
    console.log(`INSTALLED ${state.skillName}`);
    if (backupPath) {
      console.log(`BACKUP ${backupPath}`);
    }
  }
  for (const state of retiredStates) {
    if (!state.exists) {
      continue;
    }
    const backupPath = await retireSkill(state.destination);
    console.log(`REMOVED retired ${state.skillName}`);
    console.log(`BACKUP ${backupPath}`);
  }

  if (guidanceState.status === "current") {
    console.log(`UP-TO-DATE always-on ${agentsFile}`);
  } else {
    const guidanceBackup = await installAlwaysOnFile(
      agentsFile,
      guidanceState,
      alwaysOnBlock,
      options.force,
    );
    console.log(`INSTALLED always-on ${agentsFile}`);
    if (guidanceBackup) {
      console.log(`BACKUP ${guidanceBackup}`);
    }
  }

  if (["current", "external"].includes(glifMcpState.status)) {
    console.log(`UP-TO-DATE Glif MCP ${configFile}`);
  } else {
    const glifMcpBackup = await installAlwaysOnFile(
      configFile,
      glifMcpState,
      glifMcpBlock,
      options.force,
    );
    console.log(`INSTALLED Glif MCP ${configFile}`);
    if (glifMcpBackup) {
      console.log(`BACKUP ${glifMcpBackup}`);
    }
  }

  console.log(`Installed AISUPPORT skills (${release}) into ${targetRoot}`);
  console.log("Restart Codex, then authenticate Glif in Settings > MCP servers.");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(`AISUPPORT installer failed: ${error.message}`);
    process.exitCode = 1;
  });
}
