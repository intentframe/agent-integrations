# Docker test: Hermes web chat user journey

Non-interactive: skips Hermes setup wizard and Playwright/Chromium install (`--skip-setup --skip-browser`), then seeds OpenAI config (same as `tests/hermes_gateway/isolation.py`). Compose project name is `hermes-intentframe-test` (not `docker`).

```bash
export OPENAI_API_KEY=sk-...
docker compose -f tests/docker/docker-compose.test.yml up
```

Open **http://localhost:9119/chat**.

Optional model override:

```bash
export INTENTFRAME_HERMES_E2E_MODEL=gpt-4o-mini
```

Verify IntentFrame gating:

```bash
docker compose -f tests/docker/docker-compose.test.yml exec hermes-intentframe \
  tail -f /root/.intentframe/integrations/hermes/adapter.log
```

Reset (fresh install):

```bash
docker compose -f tests/docker/docker-compose.test.yml down -v
```
