# Decision Gate is downgrade-only code

The model proposes a Triage Decision, but AUTO_FIX is a safety boundary, not a suggestion. A deterministic Decision Gate applies after assess and may only downgrade (AUTO_FIX → HUMAN_REVIEW or UNRESOLVED). It never upgrades toward AUTO_FIX. GitHub Actions then branches on the gated decision, not on the raw model field.
