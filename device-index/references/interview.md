# Interview

The pairing step: confirm what the probe found, then ask what only the user knows. Walk the
sections in this order; skip a section the user marks N/A.

## How each round works

0. With a companion profile: read the store's page for this machine first. A question it already
   answers is not asked; show the answer with its fact ID instead, and link that ID in the draft
   (never copy the claim). Ask only when the probe contradicts the store, and note the conflict as
   a durable candidate for the store.
1. Show the draft facts for the section in a short list, with evidence for anything surprising.
2. Ask up to 4 questions. Put your recommended answer first and say why. Prefer a confirm/correct
   question built from evidence ("Colima is your only container runtime. Right?") over an open one.
3. Write answers into the draft facts at once. Rules go to the **proposed rules** list.
4. Questions the user defers go to an **open items** list, shown again at the end.

Batch small sections together (machine + where things go) and keep large ones alone (toolchains).

Question tools: Claude Code `AskUserQuestion` (1–4 questions, 2–4 options each, the user can
always type "Other"); OpenCode `question`; pi and others: numbered questions in chat, one line each,
with the recommended answer in brackets.

## Fact or rule?

The user often answers with a rule. Split it:

| User says | Index (fact) | Proposed rule |
|---|---|---|
| "Never touch the prod clusters" | "Prod contexts: A, B. Local: colima." | "No side effects on prod contexts without approval." |
| "Always use the project's JDK" | "Projects pin the JDK in `.sdkmanrc`." | "Honour `.sdkmanrc`." |
| "Use glab, not curl" | "GitLab CLI: `glab`, authenticated." | "GitLab work goes through `glab`." |

## Sections

Each section lists what the probe usually settles and what to ask.

### Machine
- Found: model, OS, MDM, VPN app. The companion store often owns the machine's role and identity.
- Ask: work, personal or both? Which resources need the VPN (databases, internal UIs, cluster APIs)?

### Where things go
- Found: repo roots with counts and git hosts; symlinked config.
- Ask: purpose of each root; what each origin group is for (unless the companion store says it);
  where new work, personal and throwaway projects go; legacy or
  tool-generated dirs agents should ignore; whether a grouping exists that folder names don't show
  (→ `paths.md`); other knowledge stores agents should read (team knowledge base, work log).

### Shells and terminal
- Found: login shell, installed shells, terminal app, rc files and their link targets.
- Ask: which shell the terminal starts; helpers or aliases agents should know; anything in the rc
  files that agents keep tripping over.

### Toolchains
- Found: managers, locations, installed vs ambient versions, envgap names, pin files in repos.
- Ask per stack: canonical manager when two are installed; the version most repos use; the build
  tool (wrapper scripts, task runners); traps already hit ("sourcing init before exporting X falls
  back to ~/.x"). Confirm each activation snippet you tested.

### Containers
- Found: runtime, Docker context, daemon state, Testcontainers config.
- Ask: start command and default resources; which runtime never to suggest (for example a desktop
  app the company doesn't license).

### Clusters and clouds
- Found: context names, names with `prod`, current context, cloud accounts and projects.
- Ask: every prod context, including those without `prod` in the name; the safe local context;
  main vs occasional clusters; GitOps or console URLs; re-login steps that only the user can do.

### Services and accounts
- Found: git CLIs and auth, password manager, SSH agent.
- Ask: git host URLs and team helper scripts; issue tracker and wiki access path (CLI, MCP, web);
  where secrets live; local URLs that hit shared backends (a local UI talking to staging).

### Applications
- Found: dev-relevant apps.
- Ask: which app the user uses per purpose, and which tool agents use instead (agents: `git` CLI;
  user: a GUI client).

### Agents
- Found: installed agents, versions, instruction files, skill dirs, MCP server names.
- Ask: connectors or MCP servers the probe can't see; how skills are shared between agents;
  multi-agent tooling; which agents to wire in step 5 (multi-select, detected agents only); the
  shell each agent uses on Windows.

## Done

Every section of the templates is filled from evidence or an answer, or marked N/A. Show the open
items and the proposed rules lists before moving to the draft.
