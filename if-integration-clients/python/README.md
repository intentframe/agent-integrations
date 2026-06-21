# if-integration-bridge-client (Python)

Talk to the IntentFrame validate bridge over Unix socket HTTP.

```python
from if_integration_bridge import BridgeClient

client = BridgeClient.from_env()  # IF_SECURITY_BRIDGE_SOCKET, IF_AGENT_BRIDGE_SECRET
with client:
    ctx = client.handshake()
    result = client.validate_run_command(
        command="echo hello",
        reason="User requested greeting",
    )
    if result["allowed"]:
        ...  # run locally
```
