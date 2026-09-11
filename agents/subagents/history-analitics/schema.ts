import { z } from "zod";

export const HistoryAnalysisSchema = z.object({
  pattern: z
    .enum([
      "new_regression",
      "intermittent",
      "persistent",
      "default_branch_broken",
      "no_history",
    ])
    .describe("What the recent runs say about the failure."),
  changed_files: z
    .array(z.object({ path: z.string(), status: z.string() }))
    .describe(
      "Every file changed since the base; empty when no changes are available.",
    ),
  commits: z
    .array(z.object({ sha: z.string(), message: z.string() }))
    .describe(
      "Every commit since the base, with the first line of its message.",
    ),
  evidence: z
    .array(z.string())
    .describe("The run ids, conclusions and change base the pattern rests on."),
  gaps: z
    .array(z.string())
    .describe(
      "What is missing or truncated, such as an unavailable input or files_truncated.",
    ),
});
