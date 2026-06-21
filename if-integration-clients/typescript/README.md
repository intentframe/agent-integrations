# @if-integration/bridge-client (TypeScript)

Talk to the IntentFrame validate bridge over Unix socket HTTP.

```bash
npm install @if-integration/bridge-client
npm run build   # when installing from source
```

```typescript
import { BridgeClient } from "@if-integration/bridge-client";

const client = BridgeClient.fromEnv();
await client.handshake();
const result = await client.validateRunCommand({
  command: "echo hello",
  reason: "User requested greeting",
});
if (result.allowed) {
  // run locally
}
```
