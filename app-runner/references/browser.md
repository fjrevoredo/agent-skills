# Browser-driven web app

A dev server serves HTML, but nobody is sitting at a browser to look at it. "Run the app" means:
launch the dev server, drive a headless browser against it, and produce a screenshot that proves
the page actually rendered and did the thing.

## Dev server

Same lifecycle as any server: background launch, poll for readiness, port-based stop. See
`server.md` for the full pattern — don't repeat it here, just apply it to whatever serves the
frontend (`npm run dev`, `yarn dev`, `pnpm dev`, `make serve`, `./dev.sh`, ...).

```bash
npm run dev > /tmp/web.log 2>&1 &
timeout 30 bash -c 'until curl -sf http://localhost:3000 > /dev/null; do sleep 1; done'
```

Stop by killing the port's listener before relaunching, or the next attempt hits "address in use":

```bash
lsof -ti:3000 -sTCP:LISTEN | xargs -r kill
```

## Drive

Use whatever headless-browser automation is available in the current environment — a bundled
browser-automation tool or skill, an MCP browser server, or a library called directly from a
script. Whichever mechanism is available, the loop is the same:

**navigate → wait for the element that matters → act (click / fill / type) → screenshot → check for
console/network errors.**

If nothing else is available, a plain script using a Playwright-style API is a reasonable default:

```javascript
const { chromium } = require('playwright');

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('console', msg => msg.type() === 'error' && errors.push(msg.text()));
page.on('pageerror', err => errors.push(String(err)));

await page.goto('http://localhost:3000');
await page.waitForSelector('text=Dashboard');
await page.screenshot({ path: '/tmp/before.png' });

await page.click('button:has-text("New item")');
await page.fill('input[name="title"]', 'Smoke test');
await page.keyboard.press('Enter');
await page.waitForSelector('text=Smoke test');
await page.screenshot({ path: '/tmp/after.png' });

console.log(errors.length ? `Console errors: ${errors.join('; ')}` : 'No console errors');
await browser.close();
```

That's the whole loop: `goto` → `waitForSelector` the element you need → act → `screenshot` →
check collected console/page errors before declaring success.

## What to put in a project skill

If this app's launch-and-drive steps turn out non-obvious enough to write up (Step 4 of the main
skill), keep it to the project-specific bits — the driving mechanics above are reusable as-is.

- **Dev command + port + stop.** The exact start line, any env vars it needs, the kill command.
- **Auth.** Whatever produces a logged-in session — a cookie to set directly, a login
  fill/click sequence, or a helper that does the login and hands back a session token/cookie.
- **One representative interaction.** Not the whole app — one path that proves the change works,
  ending in a screenshot.
- **App-specific gotchas.** Only the ones actually hit while running it.

## Gotchas that recur

- **Framework-controlled inputs need a real input-pipeline interaction, not raw DOM assignment.**
  Setting an input's value directly (e.g. via a raw `eval`) doesn't fire the framework's change
  handlers in React/Vue/etc. Use the automation tool's `fill`/`type` action — it goes through the
  same input pipeline a real keystroke would.
- **Websocket / long-poll pages never reach network-idle.** A "wait until network is idle" check
  can hang forever on these. Wait for the specific element that shows the state you need instead.
- **Slow first paint isn't a sign to add a fixed delay.** Dev servers often compile routes on
  demand, so the first navigation can take several seconds. Wait for the element that matters
  rather than a fixed `sleep` — a `sleep` long enough for the slow case wastes time on the fast
  case, and one short enough for the fast case races the slow one.
- **Check for console and network errors before declaring success.** A page can render its shell
  correctly while every data fetch underneath it fails — a screenshot alone won't show that.
