# Paths: repos in `<root>`

Back to [INDEX.md](INDEX.md).

<!-- Only when the user has many repos and a grouping that folder names don't show.
     Pick ONE of the two layouts below and delete the other. Delete all comments. -->

~<count> git repos. <env var that points here, and whether agent shells get it>

<!-- ============ Layout A: a grouping the user defines (team, product, capability) ============ -->

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

<!-- ============ Layout B: grouped by origin host and group ============ -->

## Grouped by origin

**The local layout is <flat | nested>.** The group of a folder is the first path part of its
origin URL: `git -C <repo> remote get-url origin`. What each group is for: <where that is
recorded, for example a knowledge-store page `<page id>`; do not repeat it here>.

| Host / group | Repos | Local repos (or "see `git remote`") |
|---|---|---|
| `<host>/<group>` | <count> | `<repo>`, `<repo>` |
| `<host>/<owner>` (public, own) | <count> | … |
| other owners (forks, clones) | <count> | … |
| no `origin` (local only) | <count> | `<folder>`, … |

New projects: <which group, which local folder>.

## Other repos

| Repo | What |
|---|---|
| `<repo>` | <purpose> |
