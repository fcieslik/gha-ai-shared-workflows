# Investigation graph without LangGraph

Triage runs in one ephemeral GitHub Actions job, so LangGraph’s durable checkpoints and mid-graph interrupts buy nothing here. We implement the investigation as an explicit Python graph (collect → logs → localize → hypothesis → evidence loop → assess → gate) and use the OpenAI Agents SDK only inside LLM nodes. GitHub Environments remain the human-in-the-loop boundary between jobs, not inside Triage.
