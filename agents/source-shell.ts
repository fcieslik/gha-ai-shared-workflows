import { execFile } from "node:child_process";
import { access } from "node:fs/promises";
import type { Shell, ShellOutputResult } from "@openai/agents";

// Upper bounds; the model may ask for less, never more.
const MAX_TIMEOUT_MS = 30_000;
const MAX_OUTPUT_LENGTH = 20_000;
// Above the output limit, so a large file is cut by truncate() instead of killing the command.
const MAX_BUFFER_BYTES = 10 * 1024 * 1024;
const ISOLATION_CHECK_TIMEOUT_MS = 5_000;

// Commands run as nobody: as the runner user they could read OPENAI_API_KEY from
// /proc/<parent pid>/environ, which only its owner can read (ADR 0005). -n fails instead of
// asking for a password.
const RUN_AS_NOBODY = ["-n", "-u", "nobody", "--"];
// env -i sets the whole environment instead of relying on sudo's env_reset. The checkout
// belongs to another user, so git needs safe.directory to work in it.
const ISOLATED_ENV = [
  "env",
  "-i",
  "PATH=/usr/local/bin:/usr/bin:/bin",
  "HOME=/tmp",
  "LANG=C.UTF-8",
  "GIT_CONFIG_COUNT=1",
  "GIT_CONFIG_KEY_0=safe.directory",
  "GIT_CONFIG_VALUE_0=*",
];
// sudo itself only needs to be found; the key stays out of its environment too.
const SUDO_ENV = { PATH: process.env.PATH, LANG: process.env.LANG };

const truncate = (text: string, maxLength: number) =>
  text.length > maxLength
    ? `${text.slice(0, maxLength)}\n[output truncated to ${maxLength} characters]`
    : text;

// Resolves to null when nobody can run commands in cwd, otherwise to the reason it cannot,
// such as sudo asking for a password.
function checkIsolation(cwd: string): Promise<string | null> {
  return new Promise((resolve) => {
    execFile(
      "sudo",
      [...RUN_AS_NOBODY, "test", "-r", ".", "-a", "-x", "."],
      { cwd, timeout: ISOLATION_CHECK_TIMEOUT_MS, env: SUDO_ENV },
      (error, _stdout, stderr) => {
        resolve(error ? stderr.trim() || error.message : null);
      },
    );
  });
}

function runCommand(
  command: string,
  cwd: string,
  timeoutMs: number,
  maxOutputLength: number,
): Promise<ShellOutputResult> {
  return new Promise((resolve) => {
    execFile(
      "sudo",
      [...RUN_AS_NOBODY, ...ISOLATED_ENV, "bash", "-c", command],
      {
        cwd,
        timeout: timeoutMs,
        maxBuffer: MAX_BUFFER_BYTES,
        env: SUDO_ENV,
      },
      (error, stdout, stderr) => {
        const output = {
          stdout: truncate(stdout, maxOutputLength),
          stderr: truncate(stderr, maxOutputLength),
        };
        if (!error) {
          resolve({ ...output, outcome: { type: "exit", exitCode: 0 } });
        } else if (error.code === "ERR_CHILD_PROCESS_STDIO_MAXBUFFER") {
          resolve({
            ...output,
            stderr: `${output.stderr}\nOutput exceeded ${MAX_BUFFER_BYTES} bytes; the command was stopped.`,
            outcome: { type: "exit", exitCode: null },
          });
        } else if (error.killed) {
          resolve({ ...output, outcome: { type: "timeout" } });
        } else {
          // A numeric code is the exit code; otherwise sudo did not start and the message says why.
          const exitCode = typeof error.code === "number" ? error.code : null;
          resolve({
            ...output,
            stderr: exitCode === null ? error.message : output.stderr,
            outcome: { type: "exit", exitCode },
          });
        }
      },
    );
  });
}

// Runs the triage lead's commands in the caller's repository at the failed commit (ADR 0005).
// It never rejects: a rejected tool call would stop the whole triage run.
export function createSourceShell(sourcePath: string | undefined): Shell {
  // Checked once, on the first call that has a checkout.
  let isolationCheck: Promise<string | null> | undefined;

  return {
    async run(action) {
      const notRun = (reason: string) => ({
        output: action.commands.map(() => ({
          stdout: "",
          stderr: reason,
          outcome: { type: "exit" as const, exitCode: null },
        })),
      });
      const checkoutUnavailable = "The repository checkout is not available.";
      if (!sourcePath) return notRun(checkoutUnavailable);
      try {
        await access(sourcePath);
      } catch {
        return notRun(checkoutUnavailable);
      }
      // Without isolation the commands are not run at all, rather than as the runner user.
      isolationCheck ??= checkIsolation(sourcePath);
      const isolationError = await isolationCheck;
      if (isolationError !== null) {
        return notRun(
          `Shell isolation (sudo -n -u nobody) is unavailable, so commands were not run: ${isolationError}`,
        );
      }

      const timeoutMs = Math.min(
        action.timeoutMs ?? MAX_TIMEOUT_MS,
        MAX_TIMEOUT_MS,
      );
      const maxOutputLength = Math.min(
        action.maxOutputLength ?? MAX_OUTPUT_LENGTH,
        MAX_OUTPUT_LENGTH,
      );
      const output: ShellOutputResult[] = [];
      for (const command of action.commands) {
        output.push(
          await runCommand(command, sourcePath, timeoutMs, maxOutputLength),
        );
      }
      return { output, maxOutputLength };
    },
  };
}
