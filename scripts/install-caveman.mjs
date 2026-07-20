#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  cp,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
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

function printUsage() {
  console.log(`Usage: node scripts/install-caveman.mjs [options]

Copy the reviewed, repository-pinned Caveman skills into Codex's user-level
skill directory. The installer does not download or execute upstream code.

Options:
  --target <path>  Override the default target ($HOME/.agents/skills)
  --verify         Check that target copies exactly match the repository
  --dry-run        Show actions without writing files
  --force          Back up and replace conflicting target skill directories
  --help           Show this help
`);
}

function parseArguments(argumentsList) {
  const options = {
    target: path.join(os.homedir(), ".agents", "skills"),
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
  const { release, sourceHashes } = await validateSources();

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
    if (failures.length > 0) {
      throw new Error(`Verification failed for ${failures.length} skill(s)`);
    }
    console.log(`Verified ${SKILL_NAMES.length} Caveman skills (${release}) in ${targetRoot}`);
    return;
  }

  const conflicts = states.filter(
    (state) => state.conflict || (state.exists && !state.matches),
  );
  if (conflicts.length > 0 && !options.force) {
    for (const state of conflicts) {
      console.error(`CONFLICT ${state.destination}`);
    }
    throw new Error("Existing skills differ. Re-run with --force to back up and replace them.");
  }

  if (options.dryRun) {
    for (const state of states) {
      const action = state.matches ? "KEEP" : state.exists ? "BACKUP+REPLACE" : "INSTALL";
      console.log(`${action} ${state.skillName} -> ${state.destination}`);
    }
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

  console.log(`Installed Caveman ${release} into ${targetRoot}`);
  console.log("Start a new Codex task, or restart Codex if the skills do not appear.");
}

main().catch((error) => {
  console.error(`Caveman installer failed: ${error.message}`);
  process.exitCode = 1;
});
