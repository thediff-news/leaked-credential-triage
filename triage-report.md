## Credential triage report

- **Alert hint:** `paydemo_live_f4k3`
- **Variable:** `PAYDEMO_API_KEY`
- **Value:** `paydemo_live_f4k...h9i0`
- **Production exposure:** YES

### Where it lives (literal occurrences)
- `demo-app/src/payments.py:10` - PAYDEMO_API_KEY = "paydemo_live_f4k3d3m0_1a2b3c4d5e6f7g8h9i0"

### Every reference (literal + variable)
- `demo-app/src/payments.py:10` (literal) - PAYDEMO_API_KEY = "paydemo_live_f4k3d3m0_1a2b3c4d5e6f7g8h9i0"
- `README.md:46` (reference) - the variable name (`PAYDEMO_API_KEY`).
- `demo-app/config/production.yaml:5` (reference) - api_key: ${PAYDEMO_API_KEY}
- `demo-app/config/staging.yaml:5` (reference) - api_key: ${PAYDEMO_API_KEY}
- `demo-app/src/payments.py:19` (reference) - "auth_header": f"Bearer {PAYDEMO_API_KEY}",
- `demo-app/src/refunds.py:5` (reference) - PAYDEMO_API_KEY = os.environ.get("PAYDEMO_API_KEY", "")
- `demo-app/src/refunds.py:9` (reference) - if not PAYDEMO_API_KEY:
- `demo-app/src/refunds.py:10` (reference) - raise RuntimeError("PAYDEMO_API_KEY is not configured")

### Ownership
- `README.md` - owner (no CODEOWNERS entry); last touched by thediff-news
- `demo-app/config/production.yaml` - owner @thediff-news; last touched by thediff-news
- `demo-app/config/staging.yaml` - owner @thediff-news; last touched by thediff-news
- `demo-app/src/payments.py` - owner @thediff-news; last touched by thediff-news
- `demo-app/src/refunds.py` - owner @thediff-news; last touched by thediff-news

### Blast radius
- **production**: `demo-app/config/production.yaml`
- **staging**: `demo-app/config/staging.yaml`
- **source**: `README.md`, `demo-app/src/payments.py`, `demo-app/src/refunds.py`

### Recommended rotation steps
1. Revoke the leaked key at the provider (it is public; assume it is used).
2. Issue a replacement key and store it in the secret manager.
3. Merge the draft rotation PR to remove the literal from source.
4. Deploy, verify the service works with the new key, then close this alert.

_Posted by the credential-triage agent. The draft rotation PR waits for human approval; the agent never merges._
