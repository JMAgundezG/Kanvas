# Changelog
## v0.4.0 — 2026-10-19
Kanvas runs without Obsidian. The board is a JSON file, agents use a new CLI, and you plan and review in an interactive HTML page.

- Add `kanvas.html`: a single-file board with a dependency graph (swimlanes per group, left-to-right or top-to-bottom, adjustable spacing, lineage highlighting, drag to connect) and a kanban view, right-click menus for cards, dependencies and empty space, undo and redo that keep agents' changes, a task panel with Markdown, notes and review actions, filters, search, dark mode and keyboard shortcuts
- Add `kanvas.py serve`: live two-way sync between the browser, the file and your agents, with compare-and-swap saves
- Open `kanvas.html` directly in Chrome or Edge to edit `kanvas.json` in place, or export a read-only snapshot with `kanvas.py export`
- Replace `canvas-tool.py` with `kanvas.py`; boards live in `kanvas.json` with stable formatting for clean diffs
- `finish` requires a summary, stored as a note, so task descriptions stay as written (#10)
- YOLO: mark a task in the board and agents may start and finish it and everything it depends on without approval or review
- Agents add notes with `note`; notes record the author (`--as`, `KANVAS_AGENT`)
- Group prefixes may contain digits, such as `L0C-01` (#12), and IDs continue past 99
- `init` installs an agent skill in `.agents/skills/kanvas/` and never modifies existing files (#8)
- Text options read UTF-8 from `--stdin` or `--file` on every platform, fixing multi-line and non-ASCII text on Windows (#20, #23)
- Text arguments may follow options, as in `note DV-01 --as claude "..."`
- Add `check`, `depend`, `add-group`, `import` (migrates Obsidian `.canvas` boards) and `export`
- Writes are locked and atomic, so several agents and the browser can work at once
- Remove the Obsidian plugin, `canvas-watcher.js`, `RULES.md` and the `.canvas` examples
- Add a test suite and CI on Linux, macOS and Windows

## v0.3.1 — 2026-03-19
- Fix `add-dep` incorrectly rejecting valid edges when a pre-existing unrelated cycle existed elsewhere in the graph
## v0.3.0 — 2026-03-19
- Add DAG auto-layout engine to the Canvas Watcher plugin
- Add vertical and horizontal layout buttons to the Obsidian canvas toolbar
- Add layer-gap slider to control spacing between dependency levels, persisted across sessions
- Layout respects group membership, resolves depth conflicts via graph coloring, and applies transitive reduction
- Add `.gitattributes` to normalize line endings

## v0.2.0 — 2026-03-16
- Add `init` command to set up Kanvas in a project directory
- Add `--no-plugin` flag to skip Obsidian plugin install during init
- Improve README setup instructions

## v0.1.0 — 2026-03-13
- Initial release
- CLI tool (`canvas-tool.py`) with workflow enforcement
- Workflow rules (`RULES.md`) and agent instructions (`CLAUDE.md`, `AGENTS.md`)
- Canvas Watcher Obsidian plugin
- Standalone canvas watcher (`canvas-watcher.js`)
- Example boards (blank template, sample project)
