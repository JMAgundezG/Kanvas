"""Measure the clutter of kanvas.html's graph layout for one or more boards.

    python tests/layout_stats.py [BOARD.json ...] [-v] [--manual] [--unfolded]

Runs the layout code from kanvas.html under Node.js and prints, per board and
orientation, the cards and stubs of folded finished tasks the graph shows, the
number of drawn arrows, pairs of arrows that cross, arrows that run under other
cards or stubs, arrows drawn as one straight line, bends (runs of curve that
shift across the flow), the total arrow length in pixels, the space the drawing
takes as a multiple of the area of its cards and stubs (1 would be cards edge to
edge, with no lanes, gaps or arrows), and its size in pixels. -v lists which
arrows cross and which cards hide which arrows. --manual measures the manual
layout, where cards keep their order in the file. --unfolded shows every
finished task, as when the human opens every lane's stub. Without board
arguments it measures the example and the test fixtures.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BOARDS = [
    os.path.join(ROOT, "examples", "sample.json"),
    os.path.join(ROOT, "tests", "fixtures", "tetris.json"),
    os.path.join(ROOT, "tests", "fixtures", "phases.json"),
]

# `misordered` counts pairs of cards in one lane and depth that appear in the
# opposite order of the file.
RUNNER = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = [];
for (const { text, vertical, levelGap, manual, unfolded } of input) {
  const b = normalize(JSON.parse(text));
  const { tasks, stubs } = foldDone(b.tasks, b, new Set(unfolded ? [...b.groups.map((g) => g.id), ""] : []));
  const L = layout(tasks, b, { vertical, levelGap, manual, stubs });
  const m = layoutMetrics(L);
  Object.assign(m, { cards: tasks.length, stubs: stubs.length, size: `${Math.round(L.width)}x${Math.round(L.height)}` });
  const along = (p) => (vertical ? p.y : p.x), across = (p) => (vertical ? p.x : p.y);
  const cards = tasks.map((t) => ({ group: t.group, p: L.pos.get(key(t.id)) }));
  m.misordered = 0;
  cards.forEach((a, i) => cards.slice(i + 1).forEach((c) => {
    if (a.group === c.group && along(a.p) === along(c.p) && across(a.p) > across(c.p)) m.misordered++;
  }));
  out.push(m);
}
process.stdout.write(JSON.stringify(out));
"""


def layout_js():
    with open(os.path.join(ROOT, "kanvas.html"), encoding="utf-8") as f:
        html = f.read()
    return html[html.index("const STATES ="):html.index("// App state")]


def measure(paths, orientations=(False, True), level_gap=70, manual=False, unfolded=False):
    """Return {(path, vertical): metrics} for every board and orientation."""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node is not installed")
    jobs = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        jobs += [(path, v, text) for v in orientations]
    payload = [{"text": text, "vertical": v, "levelGap": level_gap, "manual": manual, "unfolded": unfolded} for _, v, text in jobs]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(layout_js() + RUNNER)
    try:
        proc = subprocess.run([node, f.name], input=json.dumps(payload).encode("utf-8"), capture_output=True)
    finally:
        os.remove(f.name)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode())
    return {(path, v): m for (path, v, _), m in zip(jobs, json.loads(proc.stdout))}


def main(argv):
    verbose, manual, unfolded = "-v" in argv, "--manual" in argv, "--unfolded" in argv
    paths = [a for a in argv if a not in ("-v", "--manual", "--unfolded")] or DEFAULT_BOARDS
    print(f"{'board':<20} {'flow':<6} {'cards':>5} {'stubs':>5} {'arrows':>6} {'cross':>6} {'behind':>6} {'straight':>8} {'bends':>6} {'length':>8} {'space':>6} {'size':>10}")
    for (path, vertical), m in measure(paths, manual=manual, unfolded=unfolded).items():
        flow = "down" if vertical else "right"
        print(f"{os.path.basename(path):<20} {flow:<6} {m['cards']:>5} {m['stubs']:>5} {m['arrows']:>6} {m['crossings']:>6} {m['behind']:>6} {m['straight']:>8} {m['bends']:>6} {m['length']:>8} {m['space']:>6} {m['size']:>10}")
        if verbose:
            for b in m["detail"]["behind"]:
                print(f"    {b['from']} -> {b['to']} runs under {', '.join(b['cards'])}")
            for a, b in m["detail"]["crossings"]:
                print(f"    {a.replace('>', ' -> ')} crosses {b.replace('>', ' -> ')}")


if __name__ == "__main__":
    main(sys.argv[1:])
