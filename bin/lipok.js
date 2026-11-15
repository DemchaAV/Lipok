#!/usr/bin/env node
// lipok — install the Lipok skills into Claude Code and check what they need.
//   npx github:DemchaAV/Lipok install      copy the skills into ~/.claude/skills (after a check)
//   npx github:DemchaAV/Lipok doctor       only the check
//   npx github:DemchaAV/Lipok uninstall    remove the two skill folders
// No dependencies; works the same on Windows, macOS and Linux.
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const SKILLS = ["lipok", "lipok-task"];
const VERSION = require(path.join(ROOT, "package.json")).version;

const ok = (m) => console.log(`  ok    ${m}`);
const bad = (m) => console.log(`  MISS  ${m}`);
const warn = (m) => console.log(`  warn  ${m}`);

function run(cmd, args) {
  const r = spawnSync(cmd, args, { encoding: "utf8", windowsHide: true, timeout: 20000 });
  if (r.error || r.status !== 0) return null;
  return `${r.stdout || ""}${r.stderr || ""}`.trim();
}

function skillsDir(args) {
  const i = args.indexOf("--dir");
  if (i >= 0) {
    if (!args[i + 1]) throw new Error("--dir needs a folder");
    return path.resolve(args[i + 1]);
  }
  return process.env.CLAUDE_SKILLS_DIR || path.join(os.homedir(), ".claude", "skills");
}

// Every check returns true when the skills can work. Optional ones only warn.
function doctor() {
  console.log(`Lipok ${VERSION} — checking what the skills need`);
  let good = true;

  const git = run("git", ["--version"]);
  if (git) ok(git); else { bad("git — install Git"); good = false; }

  const gh = run("gh", ["--version"]);
  if (!gh) { bad("gh — install the GitHub CLI (https://cli.github.com)"); good = false; }
  else if (!run("gh", ["auth", "status"])) { bad("gh is not signed in — run: gh auth login"); good = false; }
  else ok(`${gh.split("\n")[0]}, signed in`);

  // The skills call `python -I …`, so `python` itself must be Python 3.10+.
  const py = run("python", ["-c", "import sys;print('%d.%d' % sys.version_info[:2])"]);
  if (!py) {
    bad("python — install Python 3.10+ so that `python` runs it" +
        (run("python3", ["--version"]) ? " (python3 exists, but the skills call `python`)" : ""));
    good = false;
  } else {
    const [maj, min] = py.split(".").map(Number);
    if (maj > 3 || (maj === 3 && min >= 10)) ok(`python ${py}`);
    else { bad(`python ${py} — need 3.10+`); good = false; }
  }

  // The scripts are bash. On Windows Claude Code runs them in Git Bash, not WSL.
  if (process.platform === "win32") {
    const candidates = [process.env.CLAUDE_CODE_GIT_BASH_PATH,
      "C:\\Program Files\\Git\\bin\\bash.exe", "C:\\Program Files (x86)\\Git\\bin\\bash.exe"];
    const where = run("where", ["git"]);
    if (where) {
      for (const g of where.split(/\r?\n/)) candidates.push(path.join(path.dirname(path.dirname(g)), "bin", "bash.exe"));
    }
    const found = candidates.find((c) => c && fs.existsSync(c));
    if (found) ok(`Git Bash ${found}`); else { bad("Git Bash — install Git for Windows"); good = false; }
  } else if (run("bash", ["--version"])) ok("bash");
  else { bad("bash"); good = false; }

  const claude = path.join(os.homedir(), ".claude");
  if (fs.existsSync(claude)) ok(`Claude Code folder ${claude}`);
  else warn(`no ${claude} yet — open the Claude Code app once`);

  const planStatus = path.join(skillsDir([]), "plan-status", "plan_status.py");
  if (fs.existsSync(planStatus)) ok('plan-status skill (plan position in "status")');
  else warn("optional plan-status skill not found: the status answer will not show the plan's position");

  console.log(good ? "Ready." : "Fix the MISS lines, then run the command again.");
  return good;
}

function install(args) {
  const dest = skillsDir(args);
  const ready = doctor();
  fs.mkdirSync(dest, { recursive: true });
  for (const s of SKILLS) {
    const src = path.join(ROOT, "skills", s);
    if (!fs.existsSync(path.join(src, "SKILL.md"))) throw new Error(`package is missing ${src}`);
    const to = path.join(dest, s);
    fs.rmSync(to, { recursive: true, force: true });  // only the folder we install
    fs.cpSync(src, to, { recursive: true });
    console.log(`installed ${to}`);
  }
  console.log("\nNext: open a project in the Claude Code app and type  /lipok-task <plan or task>");
  if (!ready) console.log("The skills are in place, but fix the MISS lines above before the first task.");
}

function uninstall(args) {
  const dest = skillsDir(args);
  for (const s of SKILLS) {
    const to = path.join(dest, s);
    if (fs.existsSync(to)) { fs.rmSync(to, { recursive: true, force: true }); console.log(`removed ${to}`); }
    else console.log(`not installed ${to}`);
  }
  console.log("Task state in ~/.lipok is kept; delete it by hand if you no longer need it.");
}

const HELP = `lipok ${VERSION}
  lipok install [--dir <skills folder>]    check, then copy the skills (default ~/.claude/skills)
  lipok doctor                             check git, gh, python, bash
  lipok uninstall [--dir <skills folder>]  remove the lipok and lipok-task skills
  lipok version`;

function main(argv) {
  const [cmd, ...args] = argv;
  try {
    switch (cmd) {
      case "install": install(args); return 0;
      case "doctor": return doctor() ? 0 : 1;
      case "uninstall": uninstall(args); return 0;
      case "version": case "--version": case "-v": console.log(VERSION); return 0;
      case undefined: case "help": case "--help": case "-h": console.log(HELP); return 0;
      default: console.log(`unknown command: ${cmd}\n\n${HELP}`); return 2;
    }
  } catch (e) {
    console.error(`error: ${e.message}`);
    return 1;
  }
}

process.exitCode = main(process.argv.slice(2));
