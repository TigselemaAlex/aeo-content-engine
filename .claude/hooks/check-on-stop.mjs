#!/usr/bin/env node
// Stop hook: Claude cannot finish while the worker checks are red.

/**
 * Run the worker checks of the CI every time Claude tries to finish its turn.
 *
 * Claude Code calls this script on the `Stop` event, when Claude is about to end its answer.
 * It is registered in `.claude/settings.json` under `hooks.Stop` as
 * `node ${CLAUDE_PROJECT_DIR}/.claude/hooks/check-on-stop.mjs` with a `timeout` of 600 s:
 * 5 checks x `CHECK_TIMEOUT_MS` (120 s) = 600 s, so the slowest possible run still fits.
 * Claude Code passes the hook input as JSON on stdin; this script reads `stop_hook_active`
 * (true when Claude is already continuing because a Stop hook blocked it) and `cwd`.
 *
 * How it works:
 *
 * 1. If nothing changed under `worker/` (no uncommitted or untracked files, and no commits
 *    on this branch that touch it compared with `origin/main`), it exits 0 right away.
 *    If the clone has no `origin/main`, `worker/` counts as changed.
 * 2. Otherwise it computes a fingerprint of the current state of `worker/`. If it matches
 *    the last fingerprint that passed every check, it exits 0 without running anything.
 *    That fingerprint and the block counter live in a JSON file in the system temp folder
 *    (`os.tmpdir()`), one file per project folder.
 * 3. Otherwise it runs the same checks as the `worker` job of `.github/workflows/ci.yml`,
 *    in the same order, and stops at the first one that fails.
 *
 * Exit codes and output, as Claude Code reads them:
 *
 * - **Exit 0, no output:** Claude may stop. Used when `worker/` did not change, when the
 *   fingerprint is already known to be green, and when every check passes.
 * - **Exit 2, message on stderr:** Claude Code does not let Claude stop and gives it the
 *   stderr text (the failing check and the last `MAX_LINES` lines of its output), so
 *   Claude keeps working to fix it.
 * - **Exit 0 with `{"systemMessage": "..."}` on stdout:** after `MAX_BLOCKS` blocks in a
 *   row the checks are still red. Claude may stop, and Claude Code shows the message to
 *   the user so they know the worker is still red.
 *
 * Measured on 26 Nov 2026: 0.15 s when `worker/` has no changes; with changes, about 7 s
 * the first time and 0.24 s afterwards, because the green fingerprint is remembered.
 *
 * @example
 * Manual run from the repository root, with `CLAUDE_PROJECT_DIR` pointing to it:
 * `echo '{"stop_hook_active":false}' | node .claude/hooks/check-on-stop.mjs; echo $?`
 * prints `0` when the worker checks are green.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/**
 * Most times in a row the hook blocks Claude from stopping while the checks stay red.
 *
 * On the next red stop after this many blocks, the hook lets Claude stop and warns the user
 * with a `systemMessage` instead. It keeps Claude from looping forever on something it
 * cannot fix. Decided on 26 Nov 2026.
 */
const MAX_BLOCKS = 3;

/**
 * Lines kept from the end of a failing check's output, the part Claude receives on stderr.
 *
 * Only the tail of the error is sent, so each block costs Claude few tokens.
 */
const MAX_LINES = 40;

/**
 * Longest time one check may run before it is killed and counted as failed, in milliseconds.
 *
 * 120 000 ms = 120 s per check. With the 5 checks of `CHECKS`, 5 x 120 s = 600 s, the
 * `timeout` of the hook in `.claude/settings.json`.
 */
const CHECK_TIMEOUT_MS = 120_000;

/**
 * Worker checks as `[name, arguments for uv]` pairs, run in this order from `worker/`.
 *
 * Same checks and order as the `worker` job of `.github/workflows/ci.yml`: Ruff lint and
 * docstrings, Ruff format, Pyright, import-linter and pytest (unit tests and doctests).
 * Differences from the CI, all about how the output looks or how it starts: Ruff prints
 * `concise` instead of `github`, Pyright and pytest start with `python -m` because Windows
 * may block uv's `.exe` launchers (`worker/README.md`), and pytest runs with `-q -x
 * --no-header` to stop at the first failing test and keep the output short.
 */
const CHECKS = [
  ['Ruff', ['run', 'ruff', 'check', '--output-format=concise']],
  ['Ruff format', ['run', 'ruff', 'format', '--check']],
  ['Pyright', ['run', 'python', '-m', 'pyright']],
  ['import-linter', ['run', 'lint-imports']],
  ['pytest', ['run', 'python', '-m', 'pytest', '-q', '-x', '--no-header']],
];

/**
 * Return the SHA-256 hash of a text as 64 lowercase hexadecimal characters.
 *
 * @param {string} text - Text to hash, read as UTF-8.
 * @returns {string} The hash in hexadecimal.
 */
const sha256 = (text) => createHash('sha256').update(text).digest('hex');

/**
 * Read the JSON that Claude Code sends to the hook on stdin.
 *
 * @returns {{ stop_hook_active?: boolean, cwd?: string }} The parsed input, or an empty
 *   object if stdin is empty or is not valid JSON, so a manual run without input still works.
 */
function readHookInput() {
  try {
    return JSON.parse(readFileSync(0, 'utf8'));
  } catch {
    return {};
  }
}

/**
 * Run a git command in the project folder and wait for it to finish.
 *
 * @param {string} projectDir - Repository root, used as the working directory.
 * @param {string[]} args - Arguments for git, for example `['rev-parse', 'HEAD']`.
 * @returns {import('node:child_process').SpawnSyncReturns<string>} The result, with `stdout`
 *   as UTF-8 text and the exit code in `status`. It does not throw when git fails: the
 *   caller reads `status`.
 */
function git(projectDir, args) {
  return spawnSync('git', args, { cwd: projectDir, encoding: 'utf8' });
}

/**
 * Tell whether `worker/` has anything the CI would check differently from `origin/main`.
 *
 * It is true in three cases, checked in this order: `worker/` has uncommitted or untracked
 * files (`git status --porcelain`); the clone has no `origin/main` to compare with, so the
 * hook cannot rule out a change; or a commit of this branch since it split from `origin/main`
 * touches `worker/` (`git diff origin/main...HEAD`). It compares with the local copy of
 * `origin/main` and does not fetch.
 *
 * @param {string} projectDir - Repository root.
 * @returns {boolean} `true` if the checks have to run, `false` if `worker/` is as on `main`.
 */
function workerChanged(projectDir) {
  const dirty = git(projectDir, ['status', '--porcelain', '--', 'worker']).stdout.trim() !== '';
  if (dirty) return true;
  if (git(projectDir, ['rev-parse', '--verify', '--quiet', 'origin/main']).status !== 0) return true;
  return git(projectDir, ['diff', '--quiet', 'origin/main...HEAD', '--', 'worker']).status !== 0;
}

/**
 * Return a hash that changes whenever the content of `worker/` changes.
 *
 * It hashes three parts joined by line breaks: the commit `HEAD` points to, the diff of the
 * tracked files of `worker/` against `HEAD` (staged and unstaged), and one
 * `path:size:mtimeMs` line per untracked file of `worker/` (git ignore rules apply). Untracked
 * files are described by size and modification time, in milliseconds, instead of by content,
 * so they are not read.
 *
 * @param {string} projectDir - Repository root.
 * @returns {string} A SHA-256 hash in hexadecimal; equal hashes mean the same `worker/`.
 */
function fingerprint(projectDir) {
  const head = git(projectDir, ['rev-parse', 'HEAD']).stdout;
  const diff = git(projectDir, ['diff', 'HEAD', '--', 'worker']).stdout;
  const untracked = git(projectDir, ['ls-files', '-o', '--exclude-standard', '--', 'worker'])
    .stdout.split('\n')
    .filter(Boolean)
    .map((file) => {
      const stats = statSync(join(projectDir, file), { throwIfNoEntry: false });
      return `${file}:${stats?.size}:${stats?.mtimeMs}`;
    })
    .join('\n');
  return sha256(`${head}\n${diff}\n${untracked}`);
}

/**
 * Read the state the hook keeps between runs.
 *
 * @param {string} path - JSON file in the system temp folder (see `statePath`).
 * @returns {{ green: string, blocks: number }} `green` is the last fingerprint that passed
 *   every check (empty if none) and `blocks` how many times in a row Claude was blocked.
 *   If the file is missing or is not valid JSON, it returns `{ green: '', blocks: 0 }`.
 */
function loadState(path) {
  if (!existsSync(path)) return { green: '', blocks: 0 };
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return { green: '', blocks: 0 };
  }
}

/**
 * Run the `CHECKS` in order with `uv` and stop at the first one that fails.
 *
 * Each check runs in `workerDir` with `PYTHONUTF8=1`, so Python writes UTF-8 also on the
 * Windows console, and with `NO_COLOR=1` and `FORCE_COLOR=0`, so the output has no color
 * codes. A check fails if it exits with a code other than 0, if it runs longer than
 * `CHECK_TIMEOUT_MS` (it is killed), or if `uv` cannot be started.
 *
 * @param {string} workerDir - The `worker/` folder of the project.
 * @returns {{ name: string, tail: string } | null} `null` if every check passed. Otherwise
 *   the name of the failing check and the last `MAX_LINES` lines of its stdout, stderr and
 *   start-up error, joined in that order.
 */
function runChecks(workerDir) {
  const env = { ...process.env, PYTHONUTF8: '1', NO_COLOR: '1', FORCE_COLOR: '0' };
  for (const [name, args] of CHECKS) {
    const result = spawnSync('uv', args, {
      cwd: workerDir,
      encoding: 'utf8',
      env,
      timeout: CHECK_TIMEOUT_MS,
    });
    if (result.status !== 0) {
      const output = `${result.stdout ?? ''}${result.stderr ?? ''}${result.error?.message ?? ''}`;
      const tail = output.trimEnd().split('\n').slice(-MAX_LINES).join('\n');
      return { name, tail };
    }
  }
  return null;
}

/** Hook input sent by Claude Code on stdin (see `readHookInput`). */
const input = readHookInput();

/**
 * Repository root: `CLAUDE_PROJECT_DIR` set by Claude Code, else the `cwd` of the hook input,
 * else the folder the script runs from.
 */
const projectDir = process.env.CLAUDE_PROJECT_DIR ?? input.cwd ?? process.cwd();

/**
 * State file of this project: `claude-stop-check-<id>.json` in the system temp folder.
 *
 * `<id>` is the first 12 hexadecimal characters of the SHA-256 of `projectDir`, so two
 * clones of the repository in different folders do not share their state.
 */
const statePath = join(tmpdir(), `claude-stop-check-${sha256(projectDir).slice(0, 12)}.json`);

if (!workerChanged(projectDir)) process.exit(0);

/** Fingerprint of `worker/` right now (see `fingerprint`). */
const current = fingerprint(projectDir);

/** State saved by the previous run (see `loadState`). */
const state = loadState(statePath);
if (state.green === current) process.exit(0);

/** First failing check, or `null` if all passed (see `runChecks`). */
const failure = runChecks(join(projectDir, 'worker'));
if (!failure) {
  writeFileSync(statePath, JSON.stringify({ green: current, blocks: 0 }));
  process.exit(0);
}

/**
 * Number of this block in the current streak, from 1.
 *
 * It continues the saved count only while `stop_hook_active` is true, that is, while Claude
 * is still working because of an earlier block; a fresh stop starts again at 1. When it goes
 * above `MAX_BLOCKS` the hook lets Claude stop and resets the state.
 */
const blocks = (input.stop_hook_active ? state.blocks : 0) + 1;
if (blocks > MAX_BLOCKS) {
  writeFileSync(statePath, JSON.stringify({ green: '', blocks: 0 }));
  process.stdout.write(
    JSON.stringify({
      systemMessage: `Worker checks are still red after ${MAX_BLOCKS} attempts (${failure.name}). Claude stopped anyway; run pnpm lint and pnpm test to see the errors.`,
    }),
  );
  process.exit(0);
}

writeFileSync(statePath, JSON.stringify({ green: '', blocks }));
process.stderr.write(
  `Worker checks failed (${failure.name}, attempt ${blocks} of ${MAX_BLOCKS}). ` +
    'Fix them before finishing, or explain to Alex why they cannot be fixed.\n\n' +
    `${failure.tail}\n`,
);
process.exit(2);
