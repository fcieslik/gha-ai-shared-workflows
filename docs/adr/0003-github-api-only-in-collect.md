# GitHub API stays in collect

LLM nodes must not call the GitHub API. Deterministic collect resolves the Failed Job, reads logs, and writes metadata into state. Specialists then read log files, the checkout, and git. That keeps `GITHUB_TOKEN` off the tool surface and makes collect the only choke point toward GitHub.

Superseded in mechanism, not in intent: the reusable workflow now runs `gh api .../jobs` and `gh run view --log-failed` before Python starts and hands collect two files. The Python package makes no network calls at all, which `test_the_package_never_reaches_the_network` enforces.
