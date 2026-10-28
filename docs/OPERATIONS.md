# AI_BUDDY: verification and operations

Reviewed against [default-branch commit 0e6dbd406da0](https://github.com/noel-ult/AI_BUDDY/commit/0e6dbd406da0f30b7b80822de8c529ddda64df3a) on 2026-10-28. Start with the [developer guide](../README.md) for installation and architecture, and the [source reference](REFERENCE.md) for exact scripts, configuration readers, routes, and source locations.

## Local model and state

Verify Ollama is running with the selected model, then test chat, model switching, a disposable memory and a short reminder. Inspect registered action handlers before exercising system actions.

These are acceptance scenarios for a maintainer to run in the documented environment. Their inclusion is not a claim that live integrations or production credentials were tested during this documentation update.

## Deployment and failure diagnosis

Back up SQLite chat/memory files before experiments. Desktop notifications need an active supported desktop environment; web research still requires network access.

## Maintaining the contract

When behavior changes, update the guide and examples in the same PR. Check the entry point and working directory before copying commands. Use the linked source readers to distinguish build-time configuration from process environment. For failures, capture the first application error, runtime version, selected mode, and redacted configuration names before later proxy or port errors.

Keep changes tied to evidence: a declared command is not proof it passes, a process health response is not a successful end-to-end workflow, and a historical report describes its own revision. Record actual check results and any unavailable external services in the PR.
