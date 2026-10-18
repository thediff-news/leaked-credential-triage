# demo-app

A deliberately tiny fictional payments service. It exists so the triage
agent has a realistic target: one hardcoded key in `src/payments.py` (the
"leak"), one proper env-var consumer in `src/refunds.py`, and prod/staging
configs that reference the same variable.

Everything here is fake. PayDemo is not a real provider and the key is not
a real credential.
