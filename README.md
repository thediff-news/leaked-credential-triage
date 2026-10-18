# leaked-credential-triage

A minimal, working demo of a **leaked-credential triage agent**: when a
secret-scanning alert fires, an agent investigates the leak and prepares
the fix, but a human stays on the merge button.

Built as a demo. The target app is fictional (PayDemo does not exist), the
leaked key is fake, and no real credentials or customer data are involved.

## The loop

```
alert (GitHub issue, label "secret-alert", or manual dispatch)
   |
   v
[agent] locate the credential in the repo
[agent] map every usage (literal + variable references)
[agent] name an owner per path (CODEOWNERS + last committer)
[agent] compute blast radius (production / staging / config / source)
   |
   v
triage report posted as a comment on the alert issue
   |
   v
[agent] DRAFT rotation PR: literal removed from source, ROTATION.md checklist
   |
   v
HUMAN reviews and merges. The agent never merges.
```

The approval gate is the point: the agent holds no standing permission to
change production code. It produces evidence and a prepared change, then
stops.

## What triggers it

Two equivalent entry points, mirroring how real alerts arrive:

1. **Issue trigger** - open an issue with the `secret-alert` label (template
   included) and a `key_hint:` line. This stands in for a scanner alert or a
   Slack/message ping.
2. **Manual dispatch** - Actions -> credential-triage -> Run workflow, pass a
   `key_hint`.

`key_hint` is a substring of the leaked value (e.g. `paydemo_live_f4k3`) or
the variable name (`PAYDEMO_API_KEY`).

## What the agent does

`agent/triage.py` (stdlib-only Python, no model key needed):

- **Locate** - `git grep` for the hint, parse the assignment to recover the
  variable name and literal value.
- **Usage map** - `git grep` for both the literal and the variable across
  the repo.
- **Owner** - reads `.github/CODEOWNERS` (last match wins) and `git log` for
  the last committer per affected file.
- **Blast radius** - classifies every affected path as production / staging /
  config / source and flags production exposure.
- **Report** - posts the triage report on the alert issue and uploads it as
  a workflow artifact.
- **Draft rotation PR** - replaces the hardcoded literal with
  `os.environ[...]`, adds `ROTATION.md` (revoke at provider, issue new key,
  deploy, verify, close), opens the PR as a **draft**, and stops.

If the literal is gone but references remain, the agent reports "already
rotated" instead of opening a PR, so the demo is re-runnable: close the
draft PR without merging and run it again.

## Where an LLM plugs in

Each investigation step is mechanical by design. The evidence collection
(grep, blame, CODEOWNERS) should stay deterministic; the LLM slot is the
narrative: turn the same evidence into the report, judge whether a
reference is a real use or a test fixture, and rank the blast radius. In a
production deployment the durable-execution layer (e.g. Pi Durable) is what
makes the approval gate replay-safe: if the agent crashes while holding the
prepared rotation, it resumes instead of re-acting.

## Files

- `demo-app/` - fictional payments service with the planted fake key
- `agent/triage.py` - the triage agent
- `.github/workflows/triage.yml` - trigger + runner
- `.github/ISSUE_TEMPLATE/secret-alert.md` - alert issue template
- `.github/CODEOWNERS` - ownership map the agent reads

## Not included (deliberately)

- No real secrets, no real provider, no LLM API key, no third-party services.
- No auto-merge, no revocation calls to a provider API. The human does those.
