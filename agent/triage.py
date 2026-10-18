#!/usr/bin/env python3
"""Leaked-credential triage agent (deterministic demo, stdlib only).

Given a hint about a leaked credential (a substring of the key or its
variable name), the agent:

  1. locates the credential in the repo,
  2. maps every usage (literal occurrences + variable references),
  3. names an owner for each affected path (CODEOWNERS + last committer),
  4. computes a blast radius (production / staging / config / source),
  5. writes a triage report and comments it on the alert issue,
  6. opens a DRAFT rotation PR and stops. A human approves; the agent
     never merges.

The investigation steps (1-4) are deliberately mechanical here. Each one is
a clean insertion point for an LLM: feed it the same evidence and let it
write the narrative, but keep the evidence collection deterministic.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

ASSIGNMENT_RE = re.compile(
    r"(?P<name>[A-Z][A-Z0-9_]{2,}(?:KEY|TOKEN|SECRET))\s*[:=]\s*"
    r"[\"'](?P<value>[A-Za-z0-9_\-]{12,})[\"']"
)
CODEOWNERS_CANDIDATES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


def sh(*args: str, check: bool = True) -> str:
    res = subprocess.run(args, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{res.stderr.strip()}")
    return res.stdout


def git_grep_fixed(needle: str) -> list[tuple[str, int, str]]:
    out = sh("git", "grep", "-n", "-I", "-F", "-e", needle, check=False)
    hits = []
    for line in out.splitlines():
        try:
            path, lineno, text = line.split(":", 2)
            hits.append((path, int(lineno), text.strip()))
        except ValueError:
            continue
    return hits


def mask(value: str) -> str:
    return value if len(value) <= 20 else f"{value[:16]}...{value[-4:]}"


class Credential:
    def __init__(self, name: str | None, value: str | None):
        self.name = name
        self.value = value
        self.literal_hits: list[tuple[str, int, str]] = []
        self.var_hits: list[tuple[str, int, str]] = []


def discover(hint: str) -> Credential:
    """Find the credential's variable name and literal value from a hint."""
    hint_hits = git_grep_fixed(hint)
    name = value = None
    for _path, _lineno, text in hint_hits:
        m = ASSIGNMENT_RE.search(text)
        if m:
            name, value = m["name"], m["value"]
            break
    if name is None and re.fullmatch(r"[A-Z][A-Z0-9_]+", hint):
        name = hint  # the hint itself is the variable name
    cred = Credential(name, value)
    if value:
        cred.literal_hits = git_grep_fixed(value)
    if name:
        cred.var_hits = [h for h in git_grep_fixed(name) if h not in cred.literal_hits]
    return cred


def load_codeowners() -> list[tuple[str, list[str]]]:
    rules: list[tuple[str, list[str]]] = []
    for candidate in CODEOWNERS_CANDIDATES:
        if os.path.exists(candidate):
            for line in open(candidate):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                rules.append((parts[0].lstrip("/"), parts[1:] or ["(unowned)"]))
    return rules


def owner_for(path: str, rules: list[tuple[str, list[str]]]) -> list[str]:
    for pattern, owners in reversed(rules):  # last match wins, per CODEOWNERS
        pat = pattern.rstrip("/")
        if path == pat or path.startswith(pat + "/"):
            return owners
    return ["(no CODEOWNERS entry)"]


def last_committer(path: str) -> str:
    return sh("git", "log", "-1", "--format=%an", "--", path, check=False).strip() or "unknown"


def classify(path: str) -> str:
    p = path.lower()
    if "prod" in p:
        return "production"
    if "stag" in p:
        return "staging"
    if p.endswith((".yaml", ".yml", ".env", ".tf", ".ini", ".cfg", ".json")):
        return "config"
    return "source"


def build_report(cred: Credential, hint: str, rules) -> str:
    affected = sorted({p for p, _, _ in cred.literal_hits + cred.var_hits})
    by_class: dict[str, list[str]] = {}
    for path in affected:
        by_class.setdefault(classify(path), []).append(path)
    prod_exposed = "production" in by_class or (
        cred.literal_hits and "source" in by_class
    )

    lines = [
        "## Credential triage report",
        "",
        f"- **Alert hint:** `{hint}`",
        f"- **Variable:** `{cred.name or 'not identified'}`",
        f"- **Value:** `{mask(cred.value) if cred.value else 'not found in source (may already be rotated)'}`",
        f"- **Production exposure:** {'YES' if prod_exposed else 'no'}",
        "",
        "### Where it lives (literal occurrences)",
    ]
    lines += [f"- `{p}:{n}` - {t}" for p, n, t in cred.literal_hits] or ["- none found"]
    lines += ["", "### Every reference (literal + variable)"]
    for p, n, t in cred.literal_hits:
        lines.append(f"- `{p}:{n}` (literal) - {t}")
    for p, n, t in cred.var_hits:
        lines.append(f"- `{p}:{n}` (reference) - {t}")
    lines += ["", "### Ownership"]
    for path in affected:
        lines.append(
            f"- `{path}` - owner {', '.join(owner_for(path, rules))};"
            f" last touched by {last_committer(path)}"
        )
    lines += ["", "### Blast radius"]
    for cls in ("production", "staging", "config", "source"):
        if cls in by_class:
            lines.append(f"- **{cls}**: " + ", ".join(f"`{p}`" for p in by_class[cls]))
    lines += [
        "",
        "### Recommended rotation steps",
        "1. Revoke the leaked key at the provider (it is public; assume it is used).",
        "2. Issue a replacement key and store it in the secret manager.",
        "3. Merge the draft rotation PR to remove the literal from source.",
        "4. Deploy, verify the service works with the new key, then close this alert.",
        "",
        "_Posted by the credential-triage agent. The draft rotation PR waits for human approval; the agent never merges._",
    ]
    return "\n".join(lines) + "\n"


def rotate(cred: Credential, report: str) -> str | None:
    """Remove the literal from source on a branch and open a draft PR."""
    if not cred.value or not cred.literal_hits:
        return None
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch = f"rotation/{cred.name}-{stamp}"
    sh("git", "checkout", "-b", branch)

    touched = sorted({p for p, _, _ in cred.literal_hits})
    for path in touched:
        src = open(path).read()
        if path.endswith(".py"):
            src = src.replace(f'"{cred.value}"', f'os.environ["{cred.name}"]')
            src = src.replace(f"'{cred.value}'", f'os.environ["{cred.name}"]')
            if "import os" not in src:
                src = "import os\n\n" + src
        else:
            src = src.replace(cred.value, f"${{{cred.name}}}")
        open(path, "w").write(src)

    with open("ROTATION.md", "w") as f:
        f.write(f"# Rotation checklist: `{cred.name}`\n\n")
        f.write(f"Leaked value: `{mask(cred.value)}` (revoked at provider before merge).\n\n")
        f.write("- [ ] Old key revoked at the provider\n")
        f.write("- [ ] New key issued and stored in the secret manager\n")
        f.write("- [ ] Literal removed from source (this PR)\n")
        f.write("- [ ] Deployed and verified\n")
        f.write("- [ ] Alert closed\n")

    sh("git", "add", "-A")
    sh("git", "commit", "-m", f"Rotate {cred.name}: remove hardcoded literal from source")
    sh("git", "push", "-u", "origin", branch)

    with open("/tmp/pr-body.md", "w") as f:
        f.write("Draft rotation prepared by the credential-triage agent.\n\n")
        f.write("**This PR waits for human approval. The agent does not merge.**\n\n")
        f.write(report)
    out = sh(
        "gh", "pr", "create", "--draft",
        "--title", f"[draft] Rotate {cred.name} ({mask(cred.value)})",
        "--body-file", "/tmp/pr-body.md",
        "--base", "main", "--head", branch,
    )
    return out.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-hint", required=True)
    ap.add_argument("--issue-number", type=int, default=None)
    args = ap.parse_args()

    rules = load_codeowners()
    cred = discover(args.key_hint)

    if not cred.literal_hits and not cred.var_hits:
        report = (
            f"## Credential triage report\n\nNo occurrence of `{args.key_hint}` found in the repo. "
            "The key may already be rotated, or the hint is wrong.\n"
        )
    else:
        report = build_report(cred, args.key_hint, rules)

    with open("triage-report.md", "w") as f:
        f.write(report)
    print(report)

    if args.issue_number and os.environ.get("GH_TOKEN"):
        sh("gh", "issue", "comment", str(args.issue_number), "--body-file", "triage-report.md")

    pr_url = rotate(cred, report) if cred.value else None
    if pr_url:
        print(f"Draft rotation PR: {pr_url}")
        if args.issue_number and os.environ.get("GH_TOKEN"):
            sh("gh", "issue", "comment", str(args.issue_number),
               "--body", f"Draft rotation PR opened for review: {pr_url}")
    elif cred.value is None and (cred.var_hits or cred.literal_hits):
        print("No literal in source: credential appears already rotated. No PR opened.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
