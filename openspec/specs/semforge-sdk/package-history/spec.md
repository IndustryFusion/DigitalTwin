# semforge-sdk/package-history Specification

## Purpose
Defines how the SemForge editor keeps a KMS package's own git history, so that
every change can be taken back: when it starts one, what it commits, where it
keeps out, how publishing tags a version, and how Undo, Redo and History… step
along it.

## Requirements

### Requirement: The editor starts a package's own history
When the editor opens a package that is not the top of a git repository of its own, it SHALL start one in the package folder, with a `.gitignore` for `.semforge/` and release archives, and commit every file of the package as the starting point. A package inside another repository SHALL get its own as well, and the editor SHALL NOT commit into the enclosing one.

#### Scenario: No repository
- **WHEN** the editor opens a package folder that no repository holds
- **THEN** the folder has a repository whose one commit holds every file of the package, and `.semforge/` is not in it

#### Scenario: Inside another repository
- **WHEN** the editor opens a package folder inside a repository that tracks its files
- **THEN** the folder has a repository of its own, the enclosing repository has no new commit, and it still sees the package's changes

### Requirement: Every change is committed
Every change the editor writes into a package SHALL be committed after it, named by what it changed. A change made outside the editor SHALL be committed, as a change made outside, before the editor reads the package again or takes a step of its history.

#### Scenario: An edit of the editor
- **WHEN** the editor writes a change into a file of the package
- **THEN** the history has a new commit that names the file and what happened to it

#### Scenario: A change made by hand
- **WHEN** a file of the package is changed outside the editor and the editor reads the package again
- **THEN** the history has a commit for that change, made before anything else

### Requirement: Commits never make an edit fail
Commits SHALL be made as SemForge, unsigned and without hooks. When git is not available, or a commit fails, the edit SHALL stand and no history is kept.

#### Scenario: A signing setup
- **WHEN** the user's git configuration signs every commit and no key is at hand
- **THEN** the editor's commits are made all the same, unsigned, by SemForge

#### Scenario: No git
- **WHEN** git cannot be run
- **THEN** the package is edited as before, with no history

### Requirement: A package can keep no history of its own
A package folder holding a `.semforge-no-history` file SHALL get no history: no repository is started, no commit made, and Undo, Redo and History… are refused with a message saying why. The file is no package member, so it is not exported. `SEMFORGE_HISTORY=off` SHALL turn the history off for every package.

#### Scenario: Marked
- **WHEN** the editor opens a package folder with a `.semforge-no-history` file
- **THEN** no repository is started there, and Undo says the package keeps no history of its own

#### Scenario: Extracted from a marked package
- **WHEN** a package with the marker is exported and the export is opened in the editor
- **THEN** the export has no marker, and its history is started

#### Scenario: Turned off
- **WHEN** `SEMFORGE_HISTORY` is `off`
- **THEN** no package gets a history

### Requirement: A history is the editor's only when it started it
A history SHALL be SemForge's only when SemForge started it: a mark it leaves in the repository's git folder, or a single root commit by SemForge in a repository without a remote. A package folder that is the top of any other repository (a clone, a checkout) SHALL be read only: no commit, also none of outside changes, no tag, and Undo, Redo and History… refused with a short message why.

#### Scenario: A history SemForge started
- **WHEN** the editor opens a package it started a history for, also one inside a source checkout
- **THEN** every change is committed, and Undo and Redo work

#### Scenario: A clone of a package repository
- **WHEN** the editor opens a package folder that is the top of a repository SemForge did not start, with work in progress
- **THEN** nothing is committed, the work in progress stays, and Undo says the history belongs to that repository

#### Scenario: A clone of a history SemForge started
- **WHEN** a repository SemForge started is cloned and the clone is opened in the editor
- **THEN** the clone is treated as a repository SemForge did not start

### Requirement: The editor's git stays in the package
A package that links files or folders from elsewhere SHALL get no history, since git would not see changes behind a link. git SHALL act on the package's folder only, whatever repository or index the environment names.

#### Scenario: Linked files
- **WHEN** the editor opens a package that links a file from elsewhere
- **THEN** no repository is started, and Undo names the link

#### Scenario: A repository named by the environment
- **WHEN** the editor runs with `GIT_DIR` or `GIT_INDEX_FILE` naming another repository
- **THEN** the package's history is kept in the package, and the other repository is untouched

### Requirement: Publishing tags a version and starts no history
`semforge publish` SHALL tag the commit of a published version `v<version>` in the package's own history, and SHALL NOT move an existing tag. It SHALL NOT start a history: in a package without one, it tags nothing.

#### Scenario: Tagged
- **WHEN** version 1.2.3 is published from a package with a history
- **THEN** its commit is tagged `v1.2.3`, and a later publication of 1.2.3 leaves the tag where it is

#### Scenario: A checkout
- **WHEN** a package inside a repository checkout, with no history of its own, is published
- **THEN** no repository is started in the package folder

### Requirement: Undo and Redo step along the history
Undo SHALL take the package back one commit, and Redo SHALL take it forward onto what the last Undo took back, until a new change is committed. Nothing SHALL be asked: every step can be redone. Undo SHALL be refused at the starting point.

#### Scenario: Undone and redone
- **WHEN** an entity is removed, then Undo, then Redo
- **THEN** the entity is back after Undo, and gone again after Redo

#### Scenario: A new change
- **WHEN** a change is made after an Undo
- **THEN** Redo is refused, as there is nothing to redo

#### Scenario: The starting point
- **WHEN** the history has only its first commit
- **THEN** Undo is refused with a message saying the history starts there

### Requirement: History goes back to a step
History… SHALL list the last steps of the package, newest first, with their age and version tags, and SHALL go back to the package as it was right after the step chosen; Redo SHALL then bring the later steps back one by one, the oldest first.

#### Scenario: Back three steps
- **WHEN** three changes were made and History… goes back to the starting point
- **THEN** the package is as it started, and Redo brings back the first of the three

### Requirement: Unsaved edits are refused
Undo, Redo and History… SHALL be refused, with a message naming the files, while a file of the package has unsaved edits in an editor.

#### Scenario: Unsaved
- **WHEN** a file of the package has unsaved edits and Undo is run
- **THEN** nothing changes, and the message names the file

### Requirement: Undo is reachable where the work is
Undo and Redo SHALL be bound to Ctrl+Z and Ctrl+Shift+Z (and Ctrl+Y) while one of SemForge's views has focus, not in a text editor, SHALL be buttons on Entities & Test Cases while they can be taken, and SHALL be in the command palette with History…. A status bar item SHALL show Undo while a package with a history is open, saying what it takes back and what Redo would bring back.

#### Scenario: The status bar
- **WHEN** a change was just made in a package with a history
- **THEN** the status bar's Undo says that change, and clicking it takes it back

#### Scenario: In a view
- **WHEN** Entities & Test Cases has focus and Ctrl+Z is pressed
- **THEN** the last change is undone
