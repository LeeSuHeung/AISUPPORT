#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { lstatSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const skillInstaller = path.join(scriptDirectory, "install-skills.mjs");
const gupabalInstaller = path.join(scriptDirectory, "install_gupabal.py");
const telegramInstaller = path.join(scriptDirectory, "install-telegram-notify.py");
const telegramNotifier = path.join(
  scriptDirectory,
  "..",
  ".codex",
  "hooks",
  "telegram_notify.py",
);

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

function assertSupportedNode() {
  const major = Number.parseInt(process.versions.node.split(".")[0], 10);
  if (!Number.isInteger(major) || major < 18) {
    throw new Error(
      `Node.js 18 or newer is required; found ${process.versions.node}`,
    );
  }
}

function pythonCandidates() {
  const candidates = [];
  if (process.platform === "win32") {
    candidates.push({ command: "py", prefixArguments: ["-3"] });
  }
  candidates.push(
    { command: "python3", prefixArguments: [] },
    { command: "python", prefixArguments: [] },
  );
  return candidates;
}

function findPython() {
  for (const candidate of pythonCandidates()) {
    const result = spawnSync(
      candidate.command,
      [...candidate.prefixArguments, "--version"],
      {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
        timeout: 10_000,
        windowsHide: true,
      },
    );
    if (result.error || result.status !== 0) {
      continue;
    }

    const versionOutput = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
    const match = versionOutput.match(/Python\s+(\d+)\.(\d+)(?:\.\d+)?/i);
    if (!match) {
      continue;
    }
    const major = Number.parseInt(match[1], 10);
    const minor = Number.parseInt(match[2], 10);
    if (major > 3 || (major === 3 && minor >= 10)) {
      return candidate;
    }
  }

  throw new Error("Python 3.10 or newer is required");
}

function runChild(
  command,
  argumentsList,
  displayName,
  environment = process.env,
) {
  const result = spawnSync(command, argumentsList, {
    env: environment,
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error) {
    throw new Error(`${displayName} could not be started`);
  }
  if (result.status !== 0) {
    throw new Error(`${displayName} failed with a non-zero exit status`);
  }
}

function runInstallers(python, argumentsList) {
  const withTelegram =
    argumentsList.includes("--with-telegram") ||
    argumentsList.includes("--configure-telegram");
  const sharedArguments = argumentsList.filter(
    (argument) =>
      argument !== "--with-telegram" && argument !== "--configure-telegram",
  );
  const skillArguments = sharedArguments.filter(
    (argument) => argument !== "--with-hooks",
  );
  runChild(
    process.execPath,
    [skillInstaller, ...skillArguments],
    "Skill installer",
  );
  runChild(
    python.command,
    [
      ...python.prefixArguments,
      "-X",
      "utf8",
      gupabalInstaller,
      ...sharedArguments,
    ],
    "Gupabal installer",
  );
  if (
    withTelegram &&
    !sharedArguments.includes("--help") &&
    !sharedArguments.includes("-h")
  ) {
    const agentsFileIndex = sharedArguments.indexOf("--agents-file");
    const codexHome = path.dirname(sharedArguments[agentsFileIndex + 1]);
    const telegramArguments = ["--codex-home", codexHome];
    for (const mode of ["--verify", "--dry-run"]) {
      if (sharedArguments.includes(mode)) {
        telegramArguments.push(mode);
      }
    }
    runChild(
      python.command,
      [
        ...python.prefixArguments,
        "-X",
        "utf8",
        telegramInstaller,
        ...telegramArguments,
      ],
      "Telegram notifier installer",
    );
  }
}

function telegramCodexHome(argumentsList) {
  const agentsFileIndex = argumentsList.indexOf("--agents-file");
  if (agentsFileIndex < 0 || !argumentsList[agentsFileIndex + 1]) {
    throw new Error("Telegram setup requires --agents-file");
  }
  return path.dirname(argumentsList[agentsFileIndex + 1]);
}

function telegramCredentialsExist(codexHome) {
  const token = process.env.TELEGRAM_BOT_TOKEN?.trim();
  const chatId = process.env.TELEGRAM_CHAT_ID?.trim();
  if (token || chatId) {
    if (!token || !chatId) {
      throw new Error(
        "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set",
      );
    }
    return true;
  }

  const credentials = path.join(codexHome, "telegram-notify.json");
  try {
    const details = lstatSync(credentials);
    if (details.isSymbolicLink() || !details.isFile()) {
      throw new Error(
        `Telegram credentials must be a regular file: ${credentials}`,
      );
    }
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

function configureTelegram(python, argumentsList) {
  const codexHome = telegramCodexHome(argumentsList);
  if (telegramCredentialsExist(codexHome)) {
    console.log(`Telegram credentials already configured: ${codexHome}`);
    return;
  }
  runChild(
    python.command,
    [
      ...python.prefixArguments,
      "-X",
      "utf8",
      telegramNotifier,
      "--configure",
    ],
    "Telegram notifier setup",
    { ...process.env, CODEX_HOME: codexHome },
  );
}

function inspectArguments(argumentsList) {
  let singlePass = false;
  let verify = false;
  let dryRun = false;
  let force = false;
  let hasTarget = false;
  let hasAgentsFile = false;
  const normalizedArguments = [];

  for (let index = 0; index < argumentsList.length; index += 1) {
    const argument = argumentsList[index];
    if (argument === "--target" || argument === "--agents-file") {
      const value = argumentsList[index + 1];
      if (!value || value.startsWith("-")) {
        throw new Error(`${argument} requires a path`);
      }
      normalizedArguments.push(argument, resolveUserPath(value, argument));
      hasTarget ||= argument === "--target";
      hasAgentsFile ||= argument === "--agents-file";
      index += 1;
      continue;
    }
    normalizedArguments.push(argument);
    if (argument === "--verify") {
      verify = true;
      singlePass = true;
      continue;
    }
    if (argument === "--dry-run") {
      dryRun = true;
      singlePass = true;
      continue;
    }
    if (argument === "--force") {
      force = true;
      continue;
    }
    if (argument === "--with-hooks") {
      continue;
    }
    if (argument === "--with-telegram") {
      continue;
    }
    if (argument === "--configure-telegram") {
      continue;
    }
    if (argument === "--help" || argument === "-h") {
      singlePass = true;
      continue;
    }
    throw new Error(`Unknown option: ${argument}`);
  }

  if (verify && force) {
    throw new Error("--verify and --force cannot be used together");
  }
  if (verify && dryRun) {
    throw new Error("--verify and --dry-run cannot be used together");
  }
  if (!hasTarget) {
    normalizedArguments.push(
      "--target",
      path.join(os.homedir(), ".agents", "skills"),
    );
  }
  if (!hasAgentsFile) {
    const configuredHome = process.env.CODEX_HOME?.trim();
    const codexHome = configuredHome
      ? resolveUserPath(configuredHome, "CODEX_HOME")
      : path.join(os.homedir(), ".codex");
    normalizedArguments.push("--agents-file", path.join(codexHome, "AGENTS.md"));
  }
  return { singlePass, normalizedArguments };
}

function main() {
  assertSupportedNode();
  const originalArguments = process.argv.slice(2);
  const { singlePass, normalizedArguments } = inspectArguments(originalArguments);
  const python = findPython();
  const shouldConfigureTelegram = normalizedArguments.includes(
    "--configure-telegram",
  );

  if (singlePass) {
    runInstallers(python, normalizedArguments);
    return;
  }

  runInstallers(python, [...normalizedArguments, "--dry-run"]);
  runInstallers(python, normalizedArguments);
  if (shouldConfigureTelegram) {
    configureTelegram(python, normalizedArguments);
  }
  const verificationArguments = normalizedArguments.filter(
    (argument) => argument !== "--force",
  );
  runInstallers(python, [...verificationArguments, "--verify"]);
}

try {
  main();
} catch (error) {
  console.error(`AISUPPORT installer failed: ${error.message}`);
  process.exitCode = 1;
}
