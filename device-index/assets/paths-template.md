# Paths: repos in `<root>`

Back to [INDEX.md](INDEX.md).

<!-- Only when the user has many repos and a grouping that folder names don't show.
     Delete all comments. -->

~<count> git repos (<host>). <env var that points here, and whether agent shells get it>

## <Grouping>: the main grouping

<One paragraph: what a <group> is (team, product, capability, service family), and where the
authoritative list lives (a doc, a knowledge base file, the git host's group tree).>

One <group> spreads over several repos:

```
<group id>
├─ <host path>/<group>/<repo>      <what these repos are>
├─ <shared libraries path>          <what lives there>
└─ <monorepo>: <path>/              <the group's slice of it>
```

**The local layout is <flat | nested>.** <How to find the group of a repo, for example
`git -C <repo> remote get-url origin`.>

## <Group> → local repos

<Marks used in the table, for example *(archived)*: archived on the host, checked <date>.>

| <Group> | Host group | Local repos |
|---|---|---|
| `<id>` | `<host group>` | `<repo>`, `<repo>` |

## Other repos

| Repo | What |
|---|---|
| `<repo>` | <purpose> |
