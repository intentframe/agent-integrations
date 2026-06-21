#!/usr/bin/env node
/** Example using @if-integration/bridge-client (same client external agents should use). */
import { BridgeClient } from "@if-integration/bridge-client";

async function main() {
  const client = BridgeClient.fromEnv();

  const pre = await client.validateExpectStatus(
    {
      action: "RUN_COMMAND",
      command: "echo bridge-ts-pre-handshake",
      target: "echo bridge-ts-pre-handshake",
      reason: "Should require handshake first",
    },
    412,
  );
  if (!String(pre.error || "").toLowerCase().includes("handshake")) {
    console.error("FAIL ts pre-handshake:", pre);
    process.exit(1);
  }
  console.log("PASS ts pre-handshake: HTTP 412");

  const ctx = await client.handshake();
  console.log(`PASS ts handshake: session_id=${JSON.stringify(ctx.session_id)}`);

  const ok = await client.validateRunCommand({
    command: "echo bridge-ts-ok",
    reason: "TypeScript bridge client example",
  });
  if (!ok.allowed) {
    console.error("FAIL ts benign:", ok);
    process.exit(1);
  }
  console.log("PASS ts benign: allowed=true");

  const blocked = await client.validateRunCommand({
    command: "sudo rm -rf /",
    reason: "Should block",
  });
  if (blocked.allowed) {
    console.error("FAIL ts blocked:", blocked);
    process.exit(1);
  }
  console.log(`PASS ts blocked: error=${JSON.stringify(blocked.error)}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
