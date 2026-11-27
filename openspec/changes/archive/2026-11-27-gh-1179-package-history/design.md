# Design

## Context

The editor writes a package's files in many places (cooked/*, expect/*); after
each write it calls `session.forget(root)`, and `session.package_for(root)`
reloads a package whose files changed. `semforge publish` records a version in
`.kms/releases.yaml`. Dot-files are no package members (`package/conformance.py`),
so they change no digest and are not exported.

## Conflicts

None with approved specifications.

## Decisions

### git in the package folder

`semforge/package/history.py` runs git in the package folder: `git init` and a
first commit when it is no repository's top, `git add -A` and a commit after
each write. Hooked into the session: on the first read of a package and when its
files changed while it was loaded (outside changes), and in `forget` (the
editor's own). A commit names what changed from `git status`.

Alternatives:
- **A history of our own** (copies under `.semforge/`): no diff, no tooling, and
  a second store to keep consistent.
- **The enclosing repository's history.** It would commit into a source
  checkout on every edit; a package of its own is what an extracted package
  needs anyway.

### Committed as SemForge, unsigned, without hooks

`-c user.name=SemForge -c commit.gpgsign=false -c core.hooksPath=` on every
call: a user's signing setup or a hook must never make an edit fail. A failing
git keeps the edit and the history goes without it.

### An opt-out that is not exported

A `.semforge-no-history` file, not a key in `kms.yaml`: `kms.yaml` is exported,
and a package extracted from a marked one would then never get a history. A
dot-file is no member and is not exported.

### Publish never starts a history

`semforge publish` runs in CI on checkouts; a repository started in the package
folder would hide its files from that checkout. It tags only a history the
editor started.

### Undo as a step back, Redo by a stack

Undo is `git reset --hard HEAD~1` after committing what is outside; the commit it
left goes on a redo stack in the repository's git folder. Redo resets onto the
top of the stack while it is the child of HEAD; any new commit empties it.
History… resets to a chosen commit and stacks the later ones, oldest on top.
Nothing is ever lost: outside changes are committed first, and every state stays
in git.

Alternatives:
- **`git revert`** for Undo: an undo becomes a new commit, and undoing it again
  redoes the change, so Undo twice does not go back two steps.

### Whose history it is

A history is SemForge's only when SemForge started it: starting one leaves a
mark (`semforge-started`) in the repository's git folder, which a clone does
not copy. A history started before the mark existed counts when its single
root commit is SemForge's "Start tracking …" and the repository has no remote.
A repository someone else made there (a clone of a package repository on a
feature branch, a CI checkout) is that repository's and read only to the
editor: it commits nothing, not even outside changes, tags nothing and steps
nowhere in it; Undo, Redo and History… say why. A package with symbolic links
gets no history, because git stores the link and never sees a change behind it.
git runs in English (its messages are read), without the inherited `GIT_DIR`,
`GIT_WORK_TREE`, `GIT_INDEX_FILE` and the like, and waits briefly for an `index.lock` another git holds (VS
Code's git extension refreshes on every file change). Outside changes are
recognised by the files' fingerprint at the last commit -- dot-folders such
as `.kms/` included, which git takes in -- whether the package is loaded or not, and committed before every `semforge/…` request -- also one
that writes without reading -- and only on the thread that handles requests:
the warm-up and the verdict worker, looking in the middle of an edit, would
commit half of it. What is derived is excluded in the repository's own
`info/exclude`, whatever a package's `.gitignore` says. A step whose reload
fails still answers as done.

### Where it is reached

Ctrl+Z / Ctrl+Shift+Z (Ctrl+Y) bound to SemForge's views only, so text editors
keep their own; Undo and Redo buttons on Entities & Test Cases while they can be
taken (context keys); a status bar item whose tooltip says what Undo takes back
and Redo brings back; the command palette, with History….

## Risks

- A package inside a source checkout without the marker gets a nested
  repository; the checkout then sees its `.gitignore` as an untracked file, and a
  `git add -A` there would add the nested repository as an embedded one. The
  packages this repository keeps carry the marker; any other package a checkout
  keeps should carry it too.
