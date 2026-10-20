"""Tests for kanvas.py. Run with: python -m unittest discover -s tests -v"""

import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import kanvas  # noqa: E402

SCRIPT = os.path.join(ROOT, "kanvas.py")


def write_board(path, board):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(kanvas.dumps(board))


def task(tid, state="todo", group=None, deps=(), **extra):
    t = {"id": tid, "title": f"Task {tid}", "state": state, "group": group, "deps": list(deps)}
    t.update(extra)
    return t


class TempBoard(unittest.TestCase):
    """A temporary directory with a kanvas.json, and a helper to run the CLI in it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kanvas-test-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = os.path.join(self.dir, "kanvas.json")
        write_board(self.path, self.initial_board())

    def initial_board(self):
        return {
            "kanvas": 1,
            "title": "Test",
            "groups": [{"id": "DV", "name": "Development"}],
            "tasks": [
                task("DV-01", "done", "DV"),
                task("DV-02", "todo", "DV", ["DV-01"]),
                task("DV-03", "todo", "DV", ["DV-02"]),
                task("DV-04", "proposed", "DV"),
            ],
        }

    def run_cli(self, *args, stdin=None, cwd=None, env=None, check=True):
        full_env = dict(os.environ, KANVAS_AGENT="")
        full_env.pop("KANVAS_BOARD", None)
        full_env.update(env or {})
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args],
            cwd=cwd or self.dir,
            input=stdin if stdin is not None else b"",
            capture_output=True,
            env=full_env,
        )
        out, err = proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")
        if check and proc.returncode != 0:
            self.fail(f"kanvas {' '.join(args)} failed ({proc.returncode}):\n{out}{err}")
        return proc.returncode, out, err

    def fails(self, *args, **kw):
        code, out, err = self.run_cli(*args, check=False, **kw)
        self.assertNotEqual(code, 0, f"expected kanvas {' '.join(args)} to fail:\n{out}")
        return err

    def board(self):
        return kanvas.load_board(self.path)

    def get(self, tid):
        return kanvas.find_task(self.board(), tid)

    def raw(self):
        with open(self.path, "rb") as f:
            return f.read()


class FormatTests(unittest.TestCase):
    def sample(self):
        with open(os.path.join(ROOT, "examples", "sample.json"), encoding="utf-8") as f:
            return f.read()

    def test_dumps_is_stable(self):
        text = self.sample()
        self.assertEqual(kanvas.dumps(kanvas.parse_board(text)), text)

    def test_short_string_arrays_stay_on_one_line(self):
        board = kanvas.new_board("t")
        board["tasks"] = [task("A-01"), task("A-02", deps=["A-01"]), task("A-03", deps=["A-01", "A-02"])]
        text = kanvas.dumps(board)
        self.assertIn('"deps": ["A-01", "A-02"]', text)
        self.assertEqual(json.loads(text)["tasks"][2]["deps"], ["A-01", "A-02"])

    def test_empty_optional_fields_are_omitted_and_unknown_keys_kept(self):
        board = kanvas.parse_board(json.dumps({
            "kanvas": 1, "groups": [], "custom": {"keep": True},
            "tasks": [{"id": "G-01", "title": "x", "state": "todo", "estimate": 3}],
        }))
        out = json.loads(kanvas.dumps(board))
        self.assertEqual(out["tasks"][0], {"id": "G-01", "title": "x", "state": "todo", "estimate": 3})
        self.assertEqual(out["custom"], {"keep": True})
        self.assertEqual(list(out)[:4], ["kanvas", "title", "groups", "tasks"])

    def test_newer_format_is_rejected(self):
        with self.assertRaises(kanvas.KanvasError):
            kanvas.parse_board('{"kanvas": 99, "groups": [], "tasks": []}')

    def test_html_serializer_matches_python(self):
        """kanvas.html must write byte-identical files, or every browser save would reformat the board."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        with open(os.path.join(ROOT, "kanvas.html"), encoding="utf-8") as f:
            html = f.read()
        start = html.index("const STATES =")
        end = html.index("// App state")
        board = kanvas.parse_board(self.sample())
        board["tasks"][0]["desc"] = 'Quotes " and \\ backslash, tab\t, unicode é 日本 ✓, </script>'
        board["tasks"][1]["deps"] = []
        board["tasks"][1]["extra"] = {"nested": [1, 2.5, None, True]}
        board["tasks"][2]["yolo"] = True
        board["tasks"][3]["yolo"] = False
        board["unknown"] = ["kept"]
        text = json.dumps(board, ensure_ascii=False)
        js = html[start:end] + "\nprocess.stdout.write(serialize(normalize(JSON.parse(require('fs').readFileSync(0, 'utf8')))));\n"
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(js)
        self.addCleanup(os.remove, f.name)
        proc = subprocess.run([node, f.name], input=text.encode("utf-8"), capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertEqual(proc.stdout.decode("utf-8"), kanvas.dumps(kanvas.parse_board(text)))


class ModelTests(unittest.TestCase):
    def test_suggest_prefix(self):
        self.assertEqual(kanvas.suggest_prefix("Research", []), "RS")
        self.assertEqual(kanvas.suggest_prefix("Development", []), "DV")
        self.assertEqual(kanvas.suggest_prefix("Delivery", ["DV"]), "DL")
        self.assertEqual(kanvas.suggest_prefix("Report Writing", []), "RW")
        self.assertEqual(kanvas.suggest_prefix("Level 0 Contract", []), "L0C")

    def test_next_id_goes_past_99(self):
        board = kanvas.new_board()
        board["tasks"] = [task("DV-99")]
        self.assertEqual(kanvas.next_id(board, "DV"), "DV-100")
        board["tasks"].append(task("DV-100"))
        self.assertEqual(kanvas.next_id(board, "dv"), "DV-101")

    def test_problems(self):
        board = kanvas.new_board()
        board["tasks"] = [
            task("A-01", deps=["A-02"]), task("A-02", deps=["A-01"]),
            task("A-03", deps=["A-09"]), task("A-04", "doing", deps=["A-03"]), task("bad id"),
        ]
        errors, warnings = kanvas.problems(board)
        self.assertTrue(any("Circular dependency" in e for e in errors), errors)
        self.assertTrue(any("missing task A-09" in e for e in errors), errors)
        self.assertTrue(any("Invalid task id" in e for e in errors), errors)
        self.assertTrue(any("A-04 is doing but depends on unfinished A-03" in w for w in warnings), warnings)


class WorkflowTests(TempBoard):
    def test_status_lists_what_matters(self):
        _, out, _ = self.run_cli("status")
        self.assertIn("Ready to start (1)", out)
        self.assertIn("DV-03  Task DV-03  (waiting on DV-02)", out)
        self.assertIn("Proposed, awaiting human approval (1)", out)
        _, out, _ = self.run_cli("ready")
        self.assertEqual(out.split(), ["DV-02", "Task", "DV-02"])

    def test_agents_cannot_start_blocked_proposed_or_running_tasks(self):
        self.assertIn("blocked by unfinished DV-02", self.fails("start", "DV-03"))
        self.assertIn("a human must approve it", self.fails("start", "DV-04"))
        self.run_cli("start", "DV-02")
        self.assertEqual(self.get("DV-02")["state"], "doing")
        self.assertIn("already in progress", self.fails("start", "DV-02"))

    def test_finish_requires_a_summary(self):
        self.run_cli("start", "DV-02")
        self.assertIn("needs a summary", self.fails("finish", "DV-02"))
        self.assertEqual(self.get("DV-02")["state"], "doing")
        self.run_cli("finish", "DV-02", "--as", "claude", "-m", "Parser done; 12 tests pass")
        t = self.get("DV-02")
        self.assertEqual(t["state"], "review")
        self.assertEqual((t["notes"][-1]["by"], t["notes"][-1]["text"]), ("claude", "Parser done; 12 tests pass"))
        self.assertIn("only tasks in progress", self.fails("finish", "DV-02", "-m", "again"))

    def test_pause_returns_the_task_with_a_note(self):
        self.run_cli("start", "DV-02", "-m", "Plan: write the parser first")
        self.run_cli("pause", "DV-02", "-m", "Waiting for an API key")
        t = self.get("DV-02")
        self.assertEqual(t["state"], "todo")
        self.assertEqual([n["text"] for n in t["notes"]], ["Plan: write the parser first", "Waiting for an API key"])

    def test_author_comes_from_as_or_environment(self):
        self.run_cli("note", "DV-02", "from env", env={"KANVAS_AGENT": "codex"})
        self.run_cli("note", "DV-02", "--as", "gemini", "after an option")
        self.run_cli("note", "DV-02", "plain")
        self.assertEqual([n["by"] for n in self.get("DV-02")["notes"]], ["codex", "gemini", "agent"])

    def test_utf8_from_stdin(self):
        text = "Café — naïve ✓ 日本語\nsecond line: ü"
        self.run_cli("note", "DV-02", "--stdin", stdin=text.encode("utf-8"))
        self.run_cli("propose", "Development", "Übersicht ✓", "--stdin", stdin=text.encode("utf-8"))
        self.assertEqual(self.get("DV-02")["notes"][0]["text"], text)
        self.assertEqual(self.get("DV-05")["title"], "Übersicht ✓")
        self.assertEqual(self.get("DV-05")["desc"], text)
        _, out, _ = self.run_cli("show", "DV-05")
        self.assertIn("Café — naïve ✓ 日本語", out)

    def test_multiline_text_from_a_file(self):
        notes = os.path.join(self.dir, "summary.md")
        with open(notes, "wb") as f:
            f.write("\ufeffDone:\r\n- parser\r\n- tests\r\n".encode("utf-8"))
        self.run_cli("start", "DV-02")
        self.run_cli("finish", "DV-02", "--file", notes)
        self.assertEqual(self.get("DV-02")["notes"][-1]["text"], "Done:\n- parser\n- tests")

    def test_text_may_be_given_only_once(self):
        self.assertIn("only once", self.fails("note", "DV-02", "inline", "--stdin", stdin=b"piped"))

    def test_done_tasks_are_frozen_for_agents(self):
        self.assertIn("propose a follow-up", self.fails("note", "DV-01", "late"))
        self.assertIn("dependencies can no longer change", self.fails("depend", "DV-01", "DV-04"))

    def test_depend_rejects_cycles_and_self(self):
        self.run_cli("depend", "DV-04", "DV-03")
        self.assertEqual(self.get("DV-04")["deps"], ["DV-03"])
        self.assertIn("circular", self.fails("depend", "DV-02", "DV-04"))
        self.assertIn("circular", self.fails("depend", "DV-04", "DV-04"))
        _, out, _ = self.run_cli("depend", "DV-04", "dv-03")
        self.assertIn("already depends", out)

    def test_failed_commands_leave_the_file_untouched(self):
        before = self.raw()
        self.fails("start", "DV-03")
        self.fails("propose", "Nope", "Title")
        self.fails("depend", "DV-02", "DV-03")
        self.assertEqual(self.raw(), before)

    def test_board_is_found_from_a_subdirectory(self):
        sub = os.path.join(self.dir, "src", "deep")
        os.makedirs(sub)
        _, out, _ = self.run_cli("ready", cwd=sub)
        self.assertIn("DV-02", out)

    def test_check_exit_code(self):
        _, out, _ = self.run_cli("check")
        self.assertTrue(out.startswith("OK: 4 tasks"))
        board = self.board()
        board["tasks"].append(task("DV-05", deps=["DV-77"]))
        write_board(self.path, board)
        self.assertNotEqual(self.run_cli("check", check=False)[0], 0)


class YoloTests(TempBoard):
    def initial_board(self):
        board = super().initial_board()
        board["tasks"][2]["yolo"] = True  # DV-03, which depends on DV-02
        board["tasks"].append(task("DV-05", "todo", "DV", ["DV-01"]))
        return board

    def test_yolo_is_stored_after_deps(self):
        t = json.loads(self.raw())["tasks"][2]
        self.assertEqual(list(t), ["id", "title", "state", "group", "deps", "yolo"])

    def test_covered_tasks_skip_review_and_others_do_not(self):
        _, out, _ = self.run_cli("ready")
        self.assertEqual(out.splitlines(), ["DV-02  Task DV-02  (YOLO)", "DV-05  Task DV-05"])
        self.run_cli("start", "DV-02")
        _, out, _ = self.run_cli("finish", "DV-02", "-m", "Parser done")
        self.assertIn("doing -> done", out)
        self.assertEqual(self.get("DV-02")["state"], "done")
        self.run_cli("start", "DV-03")
        _, out, _ = self.run_cli("finish", "DV-03", "-m", "Feature done")
        self.assertIn("YOLO is set on it", out)
        self.assertEqual(self.get("DV-03")["state"], "done")
        self.run_cli("start", "DV-05")
        self.run_cli("finish", "DV-05", "-m", "Outside the chain")
        self.assertEqual(self.get("DV-05")["state"], "review")

    def test_proposals_linked_into_the_chain_count_as_approved(self):
        self.assertIn("a human must approve it", self.fails("start", "DV-04"))
        self.run_cli("depend", "DV-02", "DV-04")
        _, out, _ = self.run_cli("status")
        self.assertIn("YOLO: DV-03", out)
        self.assertNotIn("Proposed, awaiting human approval", out)
        _, out, _ = self.run_cli("start", "DV-04")
        self.assertIn("proposed -> doing, approved by YOLO", out)
        self.assertIn("YOLO:   through DV-03", out)
        self.run_cli("finish", "DV-04", "-m", "Done")
        self.assertEqual(self.get("DV-04")["state"], "done")


class ProposalTests(TempBoard):
    def test_group_prefix_with_digits(self):
        self.run_cli("add-group", "Level 0 Contract")
        self.run_cli("propose", "Level 0 Contract", "Define the contract", "Scope and terms")
        t = self.get("L0C-01")
        self.assertEqual((t["state"], t["group"], t["desc"]), ("proposed", "L0C", "Scope and terms"))
        self.assertIn("approve", self.fails("start", "L0C-01"))
        self.run_cli("note", "L0C-01", "ids with digits in the prefix work")
        self.run_cli("depend", "L0C-01", "DV-02")
        self.assertEqual(self.get("l0c-01")["deps"], ["DV-02"])

    def test_propose_without_group_and_with_deps(self):
        self.run_cli("propose", "-", "Loose end", "--deps", "DV-02", "DV-03")
        t = self.get("G-01")
        self.assertEqual((t["group"], t["deps"]), (None, ["DV-02", "DV-03"]))
        self.assertIn("not found", self.fails("propose", "Development", "x", "--deps", "DV-99"))

    def test_batch_resolves_titles_and_creates_groups(self):
        spec = {
            "groups": ["Research", {"name": "Quality", "prefix": "QA"}],
            "tasks": [
                {"title": "Survey users", "group": "Research"},
                {"title": "Write test plan", "group": "QA", "deps": ["Survey users", "DV-02"]},
                {"title": "Automate tests", "group": "Quality", "depends_on": "Write test plan", "description": "CI"},
            ],
        }
        _, out, _ = self.run_cli("batch", stdin=json.dumps(spec).encode("utf-8"))
        self.assertIn("Proposed 3 tasks", out)
        self.assertEqual(self.get("QA-01")["deps"], ["RS-01", "DV-02"])
        self.assertEqual(self.get("QA-02")["deps"], ["QA-01"])
        self.assertEqual(self.get("QA-02")["desc"], "CI")
        self.assertTrue(all(self.get(i)["state"] == "proposed" for i in ("RS-01", "QA-01", "QA-02")))

    def test_batch_is_all_or_nothing(self):
        before = self.raw()
        spec = {"groups": ["Research"], "tasks": [{"title": "ok", "group": "Research"}, {"title": "bad", "deps": ["Nope"]}]}
        self.assertIn("Dependency 'Nope' not found", self.fails("batch", stdin=json.dumps(spec).encode("utf-8")))
        self.assertEqual(self.raw(), before)

    def test_more_than_99_tasks(self):
        spec = [{"title": f"Step {i}", "group": "Development"} for i in range(1, 101)]
        self.run_cli("batch", stdin=json.dumps(spec).encode("utf-8"))
        ids = [t["id"] for t in self.board()["tasks"]]
        self.assertIn("DV-99", ids)
        self.assertIn("DV-104", ids)
        self.assertEqual(len(set(ids)), len(ids))
        self.run_cli("check")


class InitTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kanvas-init-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def init(self):
        proc = subprocess.run([sys.executable, SCRIPT, "init", self.dir], capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        return proc.stdout.decode("utf-8")

    def test_init_installs_the_skill_and_never_overwrites(self):
        mine = "# My agent instructions\n"
        for name in ("AGENTS.md", "CLAUDE.md"):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
                f.write(mine)
        os.makedirs(os.path.join(self.dir, ".cursor"))
        out = self.init()
        self.assertIn("created   kanvas.json", out)
        for rel in (".agents/skills/kanvas/kanvas.py", ".agents/skills/kanvas/kanvas.html",
                    ".agents/skills/kanvas/SKILL.md", ".claude/skills/kanvas/SKILL.md", ".cursor/skills/kanvas/SKILL.md"):
            self.assertTrue(os.path.isfile(os.path.join(self.dir, rel)), rel)
        self.assertFalse(os.path.exists(os.path.join(self.dir, ".gemini")))
        for name in ("AGENTS.md", "CLAUDE.md"):
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                self.assertEqual(f.read(), mine)

        board = os.path.join(self.dir, "kanvas.json")
        data = kanvas.load_board(board)
        data["tasks"].append(task("G-01"))
        write_board(board, data)
        self.assertIn("kept      kanvas.json", self.init())
        self.assertEqual(len(kanvas.load_board(board)["tasks"]), 1)

        installed = os.path.join(self.dir, ".agents", "skills", "kanvas", "kanvas.py")
        proc = subprocess.run([sys.executable, installed, "status"], cwd=self.dir, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())

    def test_skill_has_frontmatter(self):
        with open(os.path.join(ROOT, "skill", "SKILL.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: kanvas\ndescription: "), text[:80])


LEGACY_CANVAS = {
    "nodes": [
        {"id": "g-res", "type": "group", "x": 0, "y": 0, "width": 400, "height": 600, "label": "Research"},
        {"id": "g-dev", "type": "group", "x": 500, "y": 0, "width": 400, "height": 600, "label": "Development"},
        {"id": "legend", "type": "text", "text": "## Legend\nRed = To Do", "x": -500, "y": 0, "width": 300, "height": 200, "color": "0"},
        {"id": "n1", "type": "text", "text": "## RS-01 Read papers\nFind prior work", "x": 20, "y": 20, "width": 300, "height": 120, "color": "4"},
        {"id": "n2", "type": "text", "text": "## RS-02 Summarise", "x": 20, "y": 200, "width": 300, "height": 120, "color": "0"},
        {"id": "n3", "type": "text", "text": "## DV-01 Build it\nLine one\nLine two", "x": 520, "y": 20, "width": 300, "height": 120, "color": "2"},
        {"id": "n4", "type": "text", "text": "## Untitled idea\nSomething new", "x": 520, "y": 200, "width": 300, "height": 120, "color": "6"},
        {"id": "n5", "type": "text", "text": "## DV-01 Duplicate id", "x": 520, "y": 400, "width": 300, "height": 120, "color": "5"},
        {"id": "note", "type": "text", "text": "free text without a heading", "x": 0, "y": 900, "width": 300, "height": 120},
    ],
    "edges": [
        {"id": "e1", "fromNode": "n1", "toNode": "n2"},
        {"id": "e2", "fromNode": "n2", "toNode": "n3"},
        {"id": "e3", "fromNode": "n3", "toNode": "n4"},
    ],
}


class ImportExportTests(TempBoard):
    def initial_board(self):
        return kanvas.new_board("empty")

    def test_import_legacy_canvas(self):
        src = os.path.join(self.dir, "Project.canvas")
        with open(src, "w", encoding="utf-8") as f:
            json.dump(LEGACY_CANVAS, f)
        self.run_cli("import", "Project.canvas")
        board = self.board()
        self.assertEqual(board["title"], "Project")
        self.assertEqual(board["groups"], [{"id": "RS", "name": "Research"}, {"id": "DV", "name": "Development"}])
        by_title = {t["title"]: t for t in board["tasks"]}
        self.assertEqual(set(by_title), {"Read papers", "Summarise", "Build it", "Untitled idea", "Duplicate id"})
        self.assertEqual(by_title["Read papers"]["state"], "done")
        self.assertEqual(by_title["Summarise"]["state"], "todo")
        self.assertEqual(by_title["Build it"]["state"], "doing")
        self.assertEqual(by_title["Build it"]["desc"], "Line one\nLine two")
        self.assertEqual(by_title["Untitled idea"]["state"], "proposed")
        self.assertEqual(by_title["Duplicate id"]["state"], "review")
        self.assertEqual(by_title["Summarise"]["deps"], ["RS-01"])
        self.assertEqual(by_title["Untitled idea"]["deps"], [by_title["Build it"]["id"]])
        ids = [t["id"] for t in board["tasks"]]
        self.assertEqual(len(set(ids)), 5)
        self.assertIn("DV-01", ids)
        self.run_cli("check")
        with open(src, encoding="utf-8") as f:
            self.assertEqual(json.load(f), LEGACY_CANVAS)
        self.assertIn("--force", self.fails("import", "Project.canvas"))
        self.run_cli("import", "Project.canvas", "--force")

    def test_export_snapshot(self):
        board = self.board()
        board["tasks"].append(task("G-01", desc="</script><script>alert(1)</script>"))
        write_board(self.path, board)
        self.run_cli("export", "snap.html")
        with open(os.path.join(self.dir, "snap.html"), encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'<script id="kanvas-snapshot" type="application/json" data-at="[^"]+">(.*?)</script>', html, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("<", m.group(1))
        self.assertEqual(json.loads(m.group(1))["tasks"][0]["desc"], "</script><script>alert(1)</script>")


class ConcurrencyTests(TempBoard):
    def test_parallel_agents_do_not_lose_writes(self):
        workers, per_worker = 6, 4
        script = (
            "import subprocess, sys\n"
            "for i in range(%d):\n"
            "    subprocess.run([sys.executable, %r, 'note', 'DV-02', '--as', sys.argv[1], str(i)], check=True, stdout=subprocess.DEVNULL)\n"
        ) % (per_worker, SCRIPT)
        procs = [subprocess.Popen([sys.executable, "-c", script, f"w{n}"], cwd=self.dir) for n in range(workers)]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        self.assertEqual(len(self.get("DV-02")["notes"]), workers * per_worker)
        leftovers = [f for f in os.listdir(self.dir) if f.endswith((".lock", ".tmp"))]
        self.assertEqual(leftovers, [])

    def test_stale_lock_is_cleared(self):
        lock = self.path + ".lock"
        open(lock, "w").close()
        old = time.time() - 60
        os.utime(lock, (old, old))
        self.run_cli("note", "DV-02", "after a crash")
        self.assertFalse(os.path.exists(lock))


class ServerTests(TempBoard):
    def setUp(self):
        super().setUp()
        self.server = kanvas.start_server(self.path, "127.0.0.1", 0, quiet=True)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conn.close()

    def put(self, board, etag=None, ctype="application/json"):
        headers = {"Content-Type": ctype}
        if etag:
            headers["If-Match"] = etag
        return self.request("PUT", "/api/board", json.dumps(board).encode("utf-8"), headers)

    def test_serves_the_page_and_the_board(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Kanvas</title>", body)
        status, headers, body = self.request("GET", "/api/board")
        self.assertEqual(status, 200)
        self.assertEqual(body, self.raw())
        status, _, body = self.request("GET", "/api/board", headers={"If-None-Match": headers["ETag"]})
        self.assertEqual((status, body), (304, b""))

    def test_compare_and_swap(self):
        _, headers, body = self.request("GET", "/api/board")
        etag = headers["ETag"]
        board = json.loads(body)
        self.run_cli("note", "DV-02", "agent wrote first")
        board["tasks"][3]["state"] = "todo"
        status, headers, body = self.put(board, etag)
        self.assertEqual(status, 409)
        current = json.loads(body)
        self.assertEqual(current["tasks"][1]["notes"][0]["text"], "agent wrote first")
        current["tasks"][3]["state"] = "todo"
        status, headers2, body = self.put(current, headers["ETag"])
        self.assertEqual(status, 200)
        self.assertEqual(body, self.raw())
        self.assertEqual(headers2["ETag"], kanvas.etag_of(self.raw()))
        self.assertEqual(self.get("DV-04")["state"], "todo")
        self.assertEqual(self.get("DV-02")["notes"][0]["text"], "agent wrote first")

    def test_rejects_unsafe_or_invalid_writes(self):
        before = self.raw()
        board = json.loads(before)
        self.assertEqual(self.put(board, ctype="text/plain")[0], 415)
        bad = json.loads(before)
        bad["tasks"][0]["state"] = "finished"
        self.assertEqual(self.put(bad)[0], 400)
        dup = json.loads(before)
        dup["tasks"].append(dict(dup["tasks"][0]))
        self.assertEqual(self.put(dup)[0], 400)
        status, _, _ = self.request("GET", "/api/board", headers={"Host": "evil.example:8765"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("PUT", "/api/board", b"{}", {"Host": "evil.example", "Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertEqual(self.raw(), before)

    def test_browser_writes_are_canonical(self):
        board = json.loads(self.raw())
        board["tasks"][3]["state"] = "todo"
        status, _, _ = self.request("PUT", "/api/board", json.dumps(board, indent=None).encode("utf-8"), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        text = self.raw().decode("utf-8")
        self.assertEqual(text, kanvas.dumps(kanvas.parse_board(text)))


if __name__ == "__main__":
    unittest.main()
