# Docker test: Hermes web chat user journey

Production-like install: the container runs the same GitHub install script as a real user (`curl …/install-hermes-plugin.sh | bash`). Only `entrypoint.sh` is mounted — it seeds test config and starts services.

Hermes is installed with `--skip-setup --skip-browser` (headless). OpenAI model/provider are seeded like `tests/hermes_gateway/isolation.py`. Dashboard basic auth is seeded so Hermes can bind `0.0.0.0` for Docker port publishing (required since Hermes 0.17+).

```bash
export OPENAI_API_KEY=sk-...
docker compose -f tests/docker/docker-compose.test.yml up
```

Open **http://localhost:9119/chat** — sign in with default credentials `hermes` / `docker-test` (override via `HERMES_DASHBOARD_USER` / `HERMES_DASHBOARD_PASSWORD`).

Pin a GitHub branch or tag for the install script and integration pack:

```bash
export VERSION=my-branch
```

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
