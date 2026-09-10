import { readFile } from "node:fs/promises";
import { z } from "zod";
import { setDefaultOpenAIKey } from "@openai/agents";
import { Agent, run } from "@openai/agents";

setDefaultOpenAIKey(process.env.OPENAI_API_KEY!);

const FailedJobs = z.array(
  z.object({
    id: z.number(),
    name: z.string(),
    failed_steps: z.array(z.string()),
    log_path: z.string(),
  }),
);
const manifestPath = process.env.FAILED_JOBS_PATH;
if (!manifestPath) throw new Error("FAILED_JOBS_PATH is not set");
const failedJobs = FailedJobs.parse(
  JSON.parse(await readFile(manifestPath, "utf8")),
);

const agent = new Agent({
  name: "History Tutor",
  instructions:
    "You provide assistance with historical queries. Explain important events and context clearly.",
});

const result = await run(
  agent,
  `Can you see the logs? can you see the error?\n\n <logs>${JSON.stringify(failedJobs, null, 2)}</logs>`,
);

console.log(result.finalOutput);
