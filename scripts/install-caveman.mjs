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

const SKILL_NAMES = Object.freeze([
  "caveman",
  "caveman-commit",
  "caveman-review",
]);

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..");
const sourceRoot = path.join(repositoryRoot, ".agents", "skills");
const lockPath = path.join(repositoryRoot, "skills-lock.json");
const manifestPath = path.join(repositoryRoot, "caveman-manifest.json");
const repositoryAgentsPath = path.join(repositoryRoot, "AGENTS.md");
const alwaysOnStartMarker = "<!-- BEGIN CAVEMAN PORTABLE ALWAYS-ON -->";
const alwaysOnEndMarker = "<!-- END CAVEMAN PORTABLE ALWAYS-ON -->";

function defaultCodexHome() {
  const configuredHome = process.env.CODEX_HOME?.trim();
  return configuredHome
    ? path.resolve(configuredHome)
    : path.join(os.homedir(), ".codex");
}

function printUsage() {
  console.log(`Usage: node scripts/install-caveman.mjs [options]

Copy the reviewed, repository-pinned Caveman skills into Codex's user-level
skill directory. The installer does not download or execute upstream code.

Options:
  --target <path>       Override the skill target ($HOME/.agents/skills)
  --agents-file <path>  Override the always-on file ($CODEX_HOME/AGENTS.md)
  --verify              Verify skills and the managed always-on block
  --dry-run             Show actions without writing files
  --force               Back up and replace conflicting managed content
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
        if (!target) {
          throw new Error("--target requires a path");
        }
        options.target = path.resolve(target);
        index += 1;
        break;
      }
      case "--agents-file": {
        const agentsFile = argumentsList[index + 1];
        if (!agentsFile) {
          throw new Error("--agents-file requires a path");
        }
        options.agentsFile = path.resolve(agentsFile);
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
    throw new Error(`Repository AGENTS.md must contain one Caveman managed block`);
  }

  const startIndex = contents.indexOf(alwaysOnStartMarker);
  const endIndex = contents.indexOf(alwaysOnEndMarker, startIndex);
  if (endIndex < startIndex) {
    throw new Error(`Invalid Caveman marker order in ${repositoryAgentsPath}`);
  }
  return contents
    .slice(startIndex, endIndex + alwaysOnEndMarker.length)
    .replace(/\r\n/g, "\n");
}

async function inspectAlwaysOnFile(agentsFile, expectedBlock) {
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
  const startCount = countOccurrences(contents, alwaysOnStartMarker);
  const endCount = countOccurrences(contents, alwaysOnEndMarker);
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

  const startIndex = contents.indexOf(alwaysOnStartMarker);
  const endMarkerIndex = contents.indexOf(alwaysOnEndMarker, startIndex);
  if (endMarkerIndex < startIndex) {
    return {
      ...sharedState,
      status: "conflict",
      reason: "marker order mismatch",
      replaceable: false,
    };
  }
  const endIndex = endMarkerIndex + alwaysOnEndMarker.length;
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

  if (guidanceState.status === "conflict") {
    if (!Number.isInteger(guidanceState.startIndex) || !Number.isInteger(guidanceState.endIndex)) {
      throw new Error(`Cannot safely replace malformed Caveman markers`);
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
    throw new Error(`Managed Caveman block differs in ${agentsFile}; use --force`);
  }

  await mkdir(path.dirname(agentsFile), { recursive: true });
  await assertAlwaysOnSnapshot(agentsFile, guidanceState);
  let backupPath = null;
  if (guidanceState.exists) {
    backupPath = await findBackupPath(
      path.dirname(agentsFile),
      `${path.basename(agentsFile)}.caveman`,
    );
    await copyFile(agentsFile, backupPath);
    if (hashBytes(await readFile(backupPath)) !== guidanceState.snapshotHash) {
      throw new Error(`Always-on target changed while backing it up: ${agentsFile}`);
    }
  }

  const temporaryDirectory = await mkdtemp(
    path.join(path.dirname(agentsFile), `.${path.basename(agentsFile)}-caveman-install-`),
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

async function hashDirectory(directoryPath) {
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
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  if (lock.version !== 1 || typeof lock.skills !== "object") {
    throw new Error(`Unsupported skills lock format: ${lockPath}`);
  }
  if (
    manifest.version !== 1 ||
    typeof manifest.files !== "object" ||
    !/^[0-9a-f]{40}$/.test(manifest.upstreamCommit ?? "")
  ) {
    throw new Error(`Unsupported Caveman manifest format: ${manifestPath}`);
  }

  const lockedNames = Object.keys(lock.skills).sort();
  const expectedNames = [...SKILL_NAMES].sort();
  if (JSON.stringify(lockedNames) !== JSON.stringify(expectedNames)) {
    throw new Error(
      `skills-lock.json must contain exactly: ${expectedNames.join(", ")}`,
    );
  }

  const lockedRefs = new Set();
  const sourceHashes = new Map();
  const manifestFiles = [];
  for (const skillName of SKILL_NAMES) {
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
    if (locked.source !== "JuliusBrussee/caveman") {
      throw new Error(`Unexpected source for ${skillName}: ${locked.source}`);
    }
    if (locked.skillPath !== `skills/${skillName}/SKILL.md`) {
      throw new Error(`Unexpected source path for ${skillName}: ${locked.skillPath}`);
    }
    if (!locked.ref || !locked.computedHash) {
      throw new Error(`Incomplete lock entry for ${skillName}`);
    }
    lockedRefs.add(locked.ref);
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

  if (lockedRefs.size !== 1) {
    throw new Error("All Caveman skills must use the same upstream release");
  }

  const release = [...lockedRefs][0];
  if (manifest.release !== release) {
    throw new Error(
      `Manifest release ${manifest.release} does not match lock release ${release}`,
    );
  }
  const declaredManifestFiles = Object.keys(manifest.files).sort();
  const actualManifestFiles = manifestFiles.sort();
  if (JSON.stringify(declaredManifestFiles) !== JSON.stringify(actualManifestFiles)) {
    throw new Error("Caveman manifest file list does not match vendored skill files");
  }

  return {
    release,
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

async function copySkillAtomically(source, destination, expectedHash, force) {
  let backupPath = null;
  const existing = await getPathState(destination);
  if (existing) {
    if (!force) {
      throw new Error(`Refusing to replace existing skill without --force: ${destination}`);
    }
    const backupRoot = path.join(path.dirname(path.dirname(destination)), "skill-backups");
    backupPath = await findBackupPath(backupRoot, path.basename(destination));
    await rename(destination, backupPath);
  }

  await mkdir(path.dirname(destination), { recursive: true });
  const temporaryParent = await mkdtemp(
    path.join(path.dirname(destination), `.${path.basename(destination)}-install-`),
  );
  const temporarySkill = path.join(temporaryParent, path.basename(destination));

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
    await rename(temporarySkill, destination);
    await rm(temporaryParent, { recursive: true, force: true });
  } catch (error) {
    await rm(temporaryParent, { recursive: true, force: true });
    if (backupPath && !(await getPathState(destination))) {
      await rename(backupPath, destination);
    }
    throw error;
  }

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
  const { release, sourceHashes } = await validateSources();
  const alwaysOnBlock = await readAlwaysOnBlock();
  const guidanceState = await inspectAlwaysOnFile(agentsFile, alwaysOnBlock);
  if (guidanceState.status === "conflict" && !guidanceState.replaceable) {
    throw new Error(
      `Cannot safely replace malformed Caveman markers in ${agentsFile}: ${guidanceState.reason}`,
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
    }
    states.push({ skillName, source, destination, exists: Boolean(destinationState), matches });
  }

  if (options.verify) {
    const failures = states.filter((state) => !state.matches);
    for (const state of states) {
      console.log(`${state.matches ? "OK" : "MISMATCH"} ${state.skillName}`);
    }
    const guidanceMatches = guidanceState.status === "current";
    console.log(`${guidanceMatches ? "OK" : "MISMATCH"} always-on ${agentsFile}`);
    if (failures.length > 0 || !guidanceMatches) {
      throw new Error(
        `Verification failed for ${failures.length} skill(s) and ${guidanceMatches ? 0 : 1} always-on file(s)`,
      );
    }
    console.log(
      `Verified ${SKILL_NAMES.length} Caveman skills and always-on guidance (${release})`,
    );
    return;
  }

  const conflicts = states.filter(
    (state) => state.conflict || (state.exists && !state.matches),
  );
  const guidanceConflicts = guidanceState.status === "conflict";
  if ((conflicts.length > 0 || guidanceConflicts) && !options.force) {
    for (const state of conflicts) {
      console.error(`CONFLICT ${state.destination}`);
    }
    if (guidanceConflicts) {
      console.error(`CONFLICT ${agentsFile}: ${guidanceState.reason}`);
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
    const guidanceAction = guidanceState.status === "current"
      ? "KEEP"
      : guidanceState.exists
        ? "BACKUP+UPDATE"
        : "INSTALL";
    console.log(`${guidanceAction} always-on -> ${agentsFile}`);
    console.log(`Dry run complete for Caveman ${release}`);
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

  console.log(`Installed Caveman ${release} into ${targetRoot}`);
  console.log("Start a new Codex task. Restart Codex if the always-on rule does not appear.");
}

main().catch((error) => {
  console.error(`Caveman installer failed: ${error.message}`);
  process.exitCode = 1;
});
