import { execFile } from "node:child_process";
import { access } from "node:fs/promises";
import type { Shell, ShellOutputResult } from "@openai/agents";

// Upper bounds; the model may ask for less, never more.
const MAX_TIMEOUT_MS = 30_000;
const MAX_OUTPUT_LENGTH = 20_000;
// Above the output limit, so a large file is cut by truncate() instead of killing the command.
const MAX_BUFFER_BYTES = 10 * 1024 * 1024;

const truncate = (text: string, maxLength: number) =>
  text.length > maxLength
    ? `${text.slice(0, maxLength)}\n[output truncated to ${maxLength} characters]`
    : text;

function runCommand(
  command: string,
  cwd: string,
  timeoutMs: number,
  maxOutputLength: number,
): Promise<ShellOutputResult> {
  return new Promise((resolve) => {
    execFile(
      "bash",
      ["-c", command],
      {
        cwd,
        timeout: timeoutMs,
        maxBuffer: MAX_BUFFER_BYTES,
        // Keeps OPENAI_API_KEY and the runner's variables out of the command's environment.
        env: {
          PATH: process.env.PATH,
          HOME: process.env.HOME,
          LANG: process.env.LANG,
        },
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
          // A numeric code is the exit code; otherwise bash did not start and the message says why.
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
  return {
    async run(action) {
      const unavailable = {
        output: action.commands.map(() => ({
          stdout: "",
          stderr: "The repository checkout is not available.",
          outcome: { type: "exit" as const, exitCode: null },
        })),
      };
      if (!sourcePath) return unavailable;
      try {
        await access(sourcePath);
      } catch {
        return unavailable;
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
