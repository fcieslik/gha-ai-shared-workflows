import { readFile } from "node:fs/promises";
import { stripVTControlCharacters } from "node:util";
import type OpenAI from "openai";
import { z } from "zod";

const FailedJob = z.object({
  id: z.number(),
  name: z.string(),
  failed_steps: z.array(z.string()),
  log_path: z.string(),
});
export type FailedJob = z.infer<typeof FailedJob>;

const ErrorExcerpt = z.object({
  job_id: z.number(),
  job_name: z.string(),
  excerpt: z.string(),
});
export type ErrorExcerpt = z.infer<typeof ErrorExcerpt>;

async function readContextFile<T>(
  envName: string,
  schema: z.ZodType<T>,
): Promise<T> {
  const path = process.env[envName];
  if (!path) throw new Error(`${envName} is not set`);
  return schema.parse(JSON.parse(await readFile(path, "utf8")));
}

export const loadFailedJobs = () =>
  readContextFile("FAILED_JOBS_PATH", z.array(FailedJob));
export const loadErrorExcerpts = () =>
  readContextFile("ERROR_EXCERPTS_PATH", z.array(ErrorExcerpt));

export const jobLogFilename = (jobId: number) => `failed-job-${jobId}.log`;

// Raw job logs keep ANSI colour codes, which only cost tokens.
async function readStrippedJobLog(job: FailedJob) {
  return stripVTControlCharacters(await readFile(job.log_path, "utf8"));
}

export async function readJobLogLines(
  job: FailedJob,
  fromLine: number,
  toLine: number,
) {
  const allLines = (await readStrippedJobLog(job)).split("\n");
  const start = Math.max(1, fromLine);
  const end = Math.min(toLine, allLines.length);
  const lines = allLines
    .slice(start - 1, end)
    .map((line, index) => `${start + index}: ${line}`);
  return { lines, totalLines: allLines.length };
}

// The code interpreter container runs at OpenAI and cannot see the runner's files, so the
// logs are uploaded only for the duration of `analyze` and deleted afterwards.
export async function withUploadedJobLogs<T>(
  client: OpenAI,
  failedJobs: FailedJob[],
  analyze: (logFileIds: string[]) => Promise<T>,
): Promise<T> {
  const logFileIds: string[] = [];
  try {
    // One at a time, so a failed upload still leaves the earlier ids for cleanup.
    for (const job of failedJobs) {
      const file = new File(
        [await readStrippedJobLog(job)],
        jobLogFilename(job.id),
        { type: "text/plain" },
      );
      const uploaded = await client.files.create({
        file,
        purpose: "user_data",
      });
      logFileIds.push(uploaded.id);
    }
    return await analyze(logFileIds);
  } finally {
    await Promise.allSettled(
      logFileIds.map((fileId) => client.files.delete(fileId)),
    );
  }
}
