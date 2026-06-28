# IntentFrame Control Plane

Operator admin UI for IntentFrame agent integrations. Runs separately from Hermes on port **9720**.

```bash
intentframe-integrations control-plane start
# http://127.0.0.1:9720
```

Build the React frontend before packaging:

```bash
cd web && npm ci && npm run build
```
