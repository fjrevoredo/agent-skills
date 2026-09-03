# Server / API

The distinguishing concern for servers is **lifecycle**: launch in the background, verify it's
actually up, interact with it, then cleanly stop it. A blocking foreground command is useless —
it never returns control.

## Structure to follow

1. **Prerequisites & setup** — same as any project (dependencies, env vars, dependent services).
2. **Run** — the background-launch pattern below, never a blocking foreground command.
3. **Verify** — poll for readiness, then hit the specific route the change touches.
4. **Stop** — cleanly terminate the background process.

## Background-launch pattern

Don't run a blocking command directly:

```bash
npm start          # blocks — never returns, agent is now stuck
```

Launch it in the background, capture how to find it again, and poll for readiness instead of
guessing a fixed delay:

```bash
npm run dev > /tmp/api.log 2>&1 &
SERVER_PID=$!

# Poll for readiness — don't sleep a fixed guess
for i in $(seq 1 30); do
  curl -sf http://localhost:3000/health > /dev/null && break
  sleep 1
done
```

Then verify against the route the change actually touches, not just a generic health check:

```bash
curl -s http://localhost:3000/api/the-endpoint-that-changed
# -> read the actual response body
```

And stop it. Prefer the captured PID or the port's listener over a broad `pkill -f` pattern — a
broad pattern can match the agent's own process and kill its own session. Also note that `$!`
after a wrapper command (`npm run dev &`, `yarn dev &`) is the wrapper's PID, and many wrappers
don't forward `SIGTERM` to the process they spawned — killing the port's listener is what reliably
frees it:

```bash
lsof -ti:3000 -sTCP:LISTEN | xargs -r kill
```

## Details worth documenting

- **Which port**, and how to override it (e.g. a `PORT` env var).
- **What "ready" looks like** — a specific log line or a health endpoint to poll.
- **Required env vars** — database URL, API keys, etc.
- **Dependent services** — if the server needs a database, cache, or queue, either point at a
  compose file that brings them up or give the exact command to start them.

## Environment table example

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | Connection string |
| `PORT` | No | `3000` | |
| `LOG_LEVEL` | No | `info` | `debug` / `info` / `warn` / `error` |

## Example Run section

```markdown
## Run

Start the dev server in the background:

    npm run dev > /tmp/api.log 2>&1 &

The server listens on port 3000. Wait for it to be ready, then verify against the changed route:

    for i in $(seq 1 20); do curl -sf http://localhost:3000/health && break; sleep 0.5; done
    curl -s http://localhost:3000/api/orders/123
    # -> {"id":123,"status":"shipped"}

Logs are at /tmp/api.log. Stop by killing the port's listener:

    lsof -ti:3000 -sTCP:LISTEN | xargs -r kill
```
