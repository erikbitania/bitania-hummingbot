# Publishing this connector to a public repo

This directory lives **inside the Bitania monorepo** (so it's versioned with
everything else and visible to Gitea CI), but it is published to a **separate,
public repository** that contains *only* this connector — never any private
backend/engine/frontend sources.

That separation is done with **`git subtree`**: only the `hummingbot/`
prefix is ever pushed to the public remote, so there is no way for private code
to leak into the public repo.

## Where to host the public repo

| Goal | Host |
|---|---|
| Let market makers install the connector today | **Anywhere public** — our own Gitea public repo, GitLab, or GitHub. Hummingbot just needs the files; it doesn't care where they're hosted. |
| Get *officially merged* into Hummingbot releases (the NCP governance path) | **GitHub** — `hummingbot/hummingbot` lives on GitHub, so the official merge requires a fork + PR there. The canonical copy can still live on Gitea; GitHub is only needed for that PR. |

So our public Gitea instance is fine for distribution. A GitHub fork is only
needed later, if/when we pursue the official in-release listing.

## One-time setup

Add the public remote (pick one — Gitea or GitHub):

```bash
# our own public Gitea
git remote add hb-public https://gitea.example.org/bitania/bitania-hummingbot.git
# …or GitHub
git remote add hb-public git@github.com:<org>/bitania-hummingbot.git
```

## Publish (run from the monorepo root)

```bash
git subtree push --prefix=hummingbot hb-public main
```

Only this subdirectory's content/history is sent. Repeat after each change you
want to publish.

If `subtree push` is ever slow or rejected on a diverged public history, split
then force the export branch explicitly:

```bash
git subtree split --prefix=hummingbot -b hb-export
git push hb-public hb-export:main      # add --force only if you intend to overwrite
git branch -D hb-export
```

## Pulling public-side changes back (rare)

If a contributor opens a PR against the public repo and it's merged there:

```bash
git subtree pull --prefix=hummingbot hb-public main --squash
```
