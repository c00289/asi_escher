# asi_escher

One of the [ASI FuSa tools](https://github.com/c00289/c00289/blob/main/README.md) by Roy Mendoza; the master README there lists every sibling.

Pure-Python diagram generator for engineering documentation. Describe a
diagram in a few lines of Python (or a JSON file), and asi_escher lays it out,
writes it as an editable **draw.io** file and renders it to **PNG** and
**SVG**, plus **Graphviz DOT** and **Mermaid** source, with no draw.io,
Graphviz, Node or browser needed. Version **0.2.1**, alpha.

Supported diagram families:

| Family | Node kinds | Typical use |
|---|---|---|
| Activity | start, end, flowfinal, action, decision, merge, fork, join, note, object, swimlanes | processes, safety reactions, handovers between actors |
| Flowchart | io, process, document, database + the activity kinds | procedures, test routines |
| State machine | state, start, end | modes and transitions |
| SysML BDD / IBD / REQ | block, part, requirement + composition, aggregation, generalization, connector, itemflow, satisfy, derive, verify, refine, allocate | structure, interfaces, traceability |
| STPA control structure | controller, human_controller, controlled_process, environment, sensor, actuator, external_system, note + control_action, feedback | hazard analysis: who controls what, through which signals |

![Swimlane activity diagram](docs/img/activity_swimlanes_estop.png)

## Install

Requires Python 3.13 or newer. The only runtime dependencies are matplotlib
and Pillow.

```bash
# for development inside this folder
uv sync

# as a dependency of another project, from a checkout
uv add --editable ../asi_escher      # or: pip install ../asi_escher
```

### From a sibling project

This repository sits next to its siblings and the `Roy's Brain` folder:

```
OneDrive - Capgemini/
├── asi_dewey/             <- primary tool: working-knowledge store
├── asi_kletz/             <- primary tool: safety plan
├── asi_escher/            <- this repo
├── asi_gutenberg/         <- document generator (depends on this repo)
├── asi_hopper/            <- gateway: read-only Jira door
└── Roy's Brain/           <- notes, corpus, datasets
```

Each consumer declares the dependency once with a uv path source. From the
asi_gutenberg folder (or any other sibling):

```bash
uv add --editable ../asi_escher
```

The command writes the two lines below into the consumer's pyproject
(with its own relative path), locks it, installs it into the consumer's
`.venv`, and from then on `from asi_escher import Diagram, build` works
there. Because the install is editable, pulling a newer asi_escher is picked
up without reinstalling; only a changed dependency list needs a `uv sync`.

```toml
[project]
dependencies = ["asi-escher"]

[tool.uv.sources]
asi-escher = { path = "../asi_escher", editable = true }
```

A pinned git source works the same way:
`asi-escher = { git = "https://github.com/c00289/asi_escher", tag = "v0.2.1" }`.

This folder lives in OneDrive, which rejects the hardlinks uv normally makes
from its cache; `pyproject.toml` therefore sets `tool.uv.link-mode = "copy"`
so plain `uv sync` works. Consumers in OneDrive need the same setting, or
`--link-mode=copy` on the command line.

## Quick start

```python
from asi_escher import Diagram, build

d = Diagram("Emergency Stop", "activity")
d.start()
d.action("press", "Press E-stop")
d.decision("agree", "Channels agree?")
d.action("inhibit", "Open drive inhibit relay")
d.action("flag", "Flag channel discrepancy")
d.end()
d.chain("start", "press", "agree")
d.edge("agree", "inhibit", "yes")
d.edge("agree", "flag", "no")
d.edge("flag", "inhibit")
d.edge("inhibit", "end")

paths = build(d, "out")        # out/emergency_stop.drawio and out/emergency_stop.png
print(paths["png"], paths["size"], paths["issues"])
```

`build()` is the one-call pipeline. The individual steps are also public when
you need control over them:

```python
from asi_escher import layout, render, to_drawio, to_dot, to_mermaid, LayoutOptions

layout(d, LayoutOptions(ranksep=70, nodesep=40))   # positions, edge routes, canvas size
fig = render(d, png="e.png", svg="e.svg", dpi=200)  # matplotlib Figure is returned too
xml = to_drawio(d)                                  # str, the draw.io file with the layout's positions
dot = to_dot(d)                                     # str, paste into Graphviz
mmd = to_mermaid(d)                                 # str, paste into Markdown
```

### Formats

| Key | Produces | Made by |
|---|---|---|
| `drawio` | `<slug>.drawio` | `to_drawio`, the positions of the layout |
| `png` | `<slug>.png` | the renderer, the same layout |
| `svg` | `<slug>.svg` | the renderer, the same layout |

`asi_escher.FORMATS` is this set, the one the sibling tools offer in their
export dialogs; `DEFAULT_FORMATS` is `("drawio", "png")`, the file to edit
and the picture to look at, and what `build()` writes when `formats` is not
given. `build()` also accepts `dot` and `mmd` (`ALL_FORMATS` lists all five).
The `.drawio` file is the real draw.io artefact: uncompressed mxGraph XML
(`compressed="false"`) with one vertex cell per box whose geometry is the
layout's x, y, width and height, one edge cell per arrow with the routed
points as waypoints and the label as its value, so draw.io or the VS Code
draw.io extension opens it with every box exactly where asi_escher put it
and a person can refine it by hand from there. The PNG and SVG are
asi_escher's renderings of that same layout, not draw.io exports.

Every output says so: the `.drawio` carries an XML comment after the
`<mxfile>` opening and a small grey note under the drawing, and the PNG and
SVG a grey footer line in the bottom-left corner ("asi_escher 0.2.1,
2026-10-29; layout shared with `<slug>.drawio`"). `provenance=False` on
`build()`, `render()` or `to_drawio()` (`--no-provenance` on the command
line) switches the marks off; `name=` sets the stem they name.

### Control structures

The `control_structure` kind draws an STPA control structure: boxes with a
title, a responsibility, an orange algorithms section and a blue process
model, joined by red control actions pointing down the hierarchy and blue
feedback pointing up, each carrying numbered signals drawn one per line.

```python
d = Diagram("Demo Loader Control Structure", "control_structure")
d.controller("operator", "Remote Operator", kind="human_controller",
             responsibility="Starts and stops the mission.",
             algorithms=[("O1", "Mission start / stop decision")],
             process_model=("Operator process model", ["Mission state (updated by FB-01)"]))
d.controller("vehicle", "Vehicle Controller", responsibility="Turns a mission into drive commands.")
d.controller("machine", "Loader Machine", kind="controlled_process")
d.controller("site", "Work Site", kind="environment")
d.control_action("operator", "vehicle", ["CA-01 Mission Start", "CA-02 Mission Stop"])
d.feedback("vehicle", "operator", ["FB-01 Mission State"])
d.control_action("vehicle", "machine", ["CA-20 Drive Command"])
d.feedback("machine", "vehicle", ["FB-10 Machine State"])
d.control_action("machine", "site", ["CA-40 Material Moved"])
d.note("n1", "Stops within 2 s of any fault", attached_to="vehicle")
```

`kind` sets the box: plain for a `controller` and an `external_system`, a
rounded box for a `human_controller`, a double border for the
`controlled_process`, a dashed border for the `environment`, small shapes for
a `sensor` and an `actuator`. A note attached to a box floats beside it. DOT
and Mermaid export the sections as label lines, the draw.io file as an HTML
label with the same colours. `docs/control_structure_spec.json` is the
bundled example as a JSON spec.

The layout follows the control hierarchy, in tiers. A box sits one tier
below the deepest box that sends it a control action; boxes that nobody
commands are peers and share the top tier side by side; a box commanded
from two tiers sits below both. Feedback never moves a box of the
hierarchy: a box that only reports (a sensor, the environment) sits below
the boxes it reports to, one that only listens (an external system taking
reports) just above the nearest box it hears from, and the environment at
the bottom beside the controlled process. A control action between two
peers is a request, not a step down: when the sender's every other control
action reaches past the receiver's own subordinates into the receiver's
domain (a field operator asking the control-room operator for a stop while
commanding the vehicle controller and the machine directly), the two stay
on one tier and the arrow runs horizontally between them, its answer
beneath it. Between two tiers the control action keeps to the left of a
pair of arrows and the feedback to the right; each arrow jogs just under
its tier and runs straight into its target with its signal stack hanging
beside it in the channel, and a channel grows until the stacks in it fit,
so the labels never overlap. `LayoutOptions.for_kind("control_structure")`
gives the kind its wider gaps, and a box with many algorithms is drawn
wider so the arrows on its edge keep apart.

![STPA control structure](docs/img/control_structure_demo.png)

### Legibility: the OCR quality gate

A diagram is only competent when a reader can read it, so a rendered PNG can
be read back with the built-in Windows OCR engine (`Windows.Media.Ocr`
through PowerShell 5.1, no Tesseract) and compared with what it was meant to
say: every node title, every signal id (`CA-01`, `FB-12`) and, in a control
structure, every algorithm code and process-model title. `build(d, out,
ocr=True)` (`--ocr` on the command line) adds the report under `"ocr"` (an
`OcrReport`: `verdict`, `lines`, `found`, `missing`, `competent`) and one
`LayoutIssue` of kind `ocr` per unreadable label; `ocr_check(png_path,
expected)` runs it on any picture and `asi-escher verify <png> --expect
LABEL...` from the shell (exit 0 competent, 1 unreadable labels, 3 engine
unavailable). The match is tolerant: case, punctuation and accents ignored,
words found in order on one OCR line or across adjacent ones, hyphenation
and the engine's usual confusions (`O`/`0`, `I`/`l`/`1`, `rn`/`tn` for an
italic `m`) folded. The PowerShell side writes UTF-8 and the Python side
reads UTF-8, so a label with a bullet, a dash or an accent (`•`, `–`, `é`)
comes back intact instead of as a control byte of the console code page,
which used to break the JSON report and make the gate say `unavailable`.
When the engine is not there (no Windows, no language pack, as on CI) the
report says `ocr unavailable` as one issue and never fails a build. The gallery runs the
gate on every control structure; the test suite asserts the bundled
`control_structure_demo` is competent whenever the engine is available.

## Command line

The package installs an `asi-escher` command (also `python -m asi_escher`).

```bash
asi-escher export diagram.json --out out                     # <slug>.drawio and <slug>.png
asi-escher export diagram.json --out out --format svg        # one format, repeatable
asi-escher export diagram.json --out out --all               # drawio, png and svg
asi-escher build diagram.json -o out            # render one or more JSON specs, all five formats
asi-escher build a.json b.json --formats svg,mmd
asi-escher gallery -o out                       # all bundled examples + index.html
asi-escher example state_autonomy_modes -o out  # one bundled example
asi-escher verify out/diagram.png --expect "Vehicle Controller" CA-01 V1   # the OCR gate
asi-escher list                                 # names of bundled examples
```

`export` writes the format set (`--format drawio|png|svg`, repeatable;
`--all` for the three; default `drawio` and `png`), with `--name STEM`,
`--dpi N`, `--no-provenance` and `--ocr`. `build`, `gallery` and `example`
share the options `-o/--out DIR` (default `out`), `--dpi N` (PNG resolution,
default 160), `--formats drawio,png,svg,dot,mmd` (any subset, default all),
`--ranksep PX` and `--nodesep PX` (layout spacing), `--no-provenance` and
`--ocr`. `build` also takes `--name STEM` for a single spec and reads one
spec from stdin when the file argument is `-`. `asi-escher --version` prints
the installed version.

Run `asi-escher gallery` and open `out/index.html` to see every diagram
family rendered, with its DOT and Mermaid source alongside. Layout issues
(see below) are printed to stderr per diagram.

The seventeen bundled examples (`src/asi_escher/examples.py`), all themed
around an autonomous wheel loader and its safety system:

| Family | Examples |
|---|---|
| Activity | `activity_load_cycle`, `activity_swimlanes_estop`, `activity_fork_join_post`, `activity_object_flow`, `swimlanes_lr_dispatch` |
| Flowchart | `flowchart_fault_response`, `flowchart_pipeline_lr`, `flowchart_calibration_loops`, `flowchart_fusa_lifecycle`, `stress_random_dag` |
| State machine | `state_autonomy_modes`, `state_estop_channel` |
| SysML | `bdd_wheel_loader`, `bdd_safety_system`, `ibd_safety_controller`, `req_safety_requirements` |
| Control structure | `control_structure_demo` |

### JSON spec

A spec is the JSON form of `Diagram.to_dict()`. Everything except `title`,
node `id` and edge `src`/`dst` is optional.

```json
{
  "title": "Login",
  "kind": "flowchart",
  "direction": "TB",
  "lanes": [{"id": "user", "title": "User"}, {"id": "sys", "title": "System"}],
  "nodes": [
    {"id": "start", "kind": "start", "lane": "user"},
    {"id": "enter", "label": "Enter credentials", "lane": "user"},
    {"id": "check", "label": "Valid?", "kind": "decision", "lane": "sys"},
    {"id": "end", "kind": "end", "lane": "sys"}
  ],
  "edges": [
    {"src": "start", "dst": "enter"},
    {"src": "enter", "dst": "check"},
    {"src": "check", "dst": "end", "label": "yes"},
    {"src": "check", "dst": "enter", "label": "no", "style": "dashed"}
  ]
}
```

See [docs/example_spec.json](docs/example_spec.json) for a complete example
and [docs/control_structure_spec.json](docs/control_structure_spec.json) for
a control structure. Node fields: `id`, `label`, `kind`, `lane`,
`stereotype`, `compartments` (list of `[title, [lines]]`), `fill`, `stroke`,
and for a control structure `responsibility`, `algorithms` (list of
`[code, name]`), `process_model` (`[title, [entries]]`) and, on a note,
`attached_to`. Edge fields: `src`, `dst`, `label`, `kind`, `style` (`solid`,
`dashed`, `dotted`), `src_port`, `dst_port`, and `signals` (a list of lines;
the label is their join when no label is given).

## Building diagrams in Python

`Diagram(title, kind="activity", direction="TB", frame=None)`

* `kind` is one of `activity`, `flowchart`, `state`, `bdd`, `ibd`, `req`,
  `control_structure`. It selects the Mermaid diagram type and, for a control
  structure, the layout rules above; the renderer draws any node kind in any
  diagram.
* `direction` is `TB` or `LR`.
* `frame` draws a SysML diagram frame with the given header, e.g.
  `"bdd [Package] WheelLoader"`.

Shorthand constructors: `start()`, `end()`, `action()`, `decision()`,
`merge()`, `fork()`, `join()`, `note(id, label, lane=None, attached_to=None)`,
`state()`, `block()`, `requirement()`, `controller(id, title, kind=...,
responsibility=..., algorithms=[(code, name)], process_model=(title,
[entries]))`, plus the general `node(id, label, kind, **fields)`. Edges come
from `edge(src, dst, label="", kind="flow", style="solid", src_port=None,
dst_port=None)`, `chain(*ids, labels=[...])`, `control_action(src, dst,
[signals])` and `feedback(src, dst, [signals])`. Swimlanes come from
`lane(id, title)`; when a diagram has lanes, every node must name one.

Invalid input raises early: unknown kinds, duplicate ids, edges to missing
nodes and nodes outside any lane are all `ValueError`/`KeyError` at build
time, not at render time.

![SysML block definition diagram](docs/img/bdd_wheel_loader.png)

## Layout engine

The layout is a deterministic layered (Sugiyama-style) algorithm:

1. cycle removal by DFS back edges (back edges are routed in a channel on
   the right, or at the bottom for left-to-right diagrams);
2. longest-path layering, with side inputs such as notes pulled next to
   their consumer (a control structure layers by its control hierarchy, in
   the tiers described above);
3. dummy nodes for edges that span several layers;
4. barycenter ordering, lane-aware when swimlanes are present;
5. per-component coordinate balancing and chain straightening, with
   components packed side by side;
6. orthogonal edge routing that only jogs in the gaps between layers;
7. edge-label placement that avoids nodes and other labels, with layer gaps
   widened to fit labels in left-to-right diagrams.

`LayoutOptions` exposes `ranksep`, `nodesep`, `margin`, `lane_pad`,
`lane_header`, `iterations` and `back_channel`; `LayoutOptions.for_kind(kind)`
gives the defaults `layout()` uses when none are passed (wider gaps for a
control structure). Text is measured with the DejaVu Sans font bundled with
matplotlib, so output is identical on every machine.

### Layout issues

When the engine cannot find a clean result it still produces a drawing, but
it says so. After `layout()` (or `build()`), `diagram.issues` holds one
`LayoutIssue` per problem:

| kind | meaning |
|---|---|
| `label_overlap` | an edge label had to be placed touching a node or another label |
| `edge_through_node` | a routed edge segment passes through a node it does not connect |
| `ocr` | the OCR gate could not read a label in the PNG, or the engine was unavailable (only with `ocr=True`) |

Each issue carries a `message`, the `edge` `(src, dst)` and, where relevant,
the `node` id. A single `LayoutWarning` (a `UserWarning` subclass) is also
emitted per diagram so that hosts which do nothing special still see it;
silence it with `warnings.filterwarnings("ignore", category=LayoutWarning)`
or turn it into an error in tests. None of the bundled examples produce
issues, and the test suite enforces that.

![State machine](docs/img/state_autonomy_modes.png)

## Using it inside a larger tool

* No global state. The renderer uses the object-oriented matplotlib API,
  never calls `pyplot`, selects no backend and restores rcParams after each
  call. It is safe inside applications that use matplotlib themselves.
* `render()` accepts file paths or file-like objects and returns the
  `Figure`, so you can write to memory, embed in a GUI or save as PDF.
* The model is plain data. `Diagram.to_dict()` / `Diagram.from_dict()` give
  a JSON-serialisable interchange format; the author's labels are never
  modified by layout (wrapped text lives in `Node.lines`).
* `layout()` can be re-run on the same diagram after edits; stale layout
  state is discarded.
* Degraded results are reported, never hidden (see Layout issues).
* The package ships `py.typed`; everything is typed, deterministic and
  covered by the test suite.

## Theming

`render(d, theme={...})` overrides any entry of `asi_escher.THEME`, a dict of
colours keyed by node kind (`(fill, stroke)` pairs) and by role (`bg`,
`edge`, `label_bg`, `lane_a`, `lane_b`, `frame`, `bar`). Individual nodes
take `fill=` and `stroke=` too.

## Development

```bash
uv sync                      # create .venv with dev tools
uv run pytest                # tests, including geometric invariants on every example
uv run ruff check src tests  # lint
uv run asi-escher gallery    # regenerate out/ for a visual check
uv build                     # wheel + sdist in dist/
```

The suite lives in `tests/`: `test_model.py` (validation and JSON round
trips), `test_layout.py` (geometric invariants), `test_issues.py` (layout
issue reporting), `test_export.py` (DOT and Mermaid), `test_drawio.py` (the
draw.io file parsed back, positions equal to the layout, provenance marks),
`test_control_structure.py` (the kind: builder, layout rules, renderer,
exports), `test_ocr.py` (the matcher, the unavailable path, the CLI and the
demo's legibility under the real engine), `test_render_pipeline.py`
(renderer isolation, `build()`, formats and the CLI) and
`test_private_smoke.py` (skipped unless a private sibling dataset is beside
the repo; asserts counts, the tier shape and the OCR verdict only);
`conftest.py` provides every bundled example
as a fixture. The geometry tests assert, for every bundled example, that
nodes never overlap, edges are orthogonal, edges never pass through
unrelated nodes, all geometry and labels fit the canvas, layout is repeatable
and no layout issues are reported.

## Limitations

* Layout quality on dense, highly cyclic graphs (see the bundled stress
  example) is readable but not pretty; Graphviz will do better on those, and
  the DOT export is there for that reason.
* Mermaid and DOT output follow the published grammars but have not been
  run through Mermaid or Graphviz on this machine, since neither is
  installed here.
* Port symbols on IBD connectors are drawn at the edge endpoints and can be
  crowded on blocks with many connectors.
* The draw.io file has been checked as XML and against the mxGraph format
  (uncompressed, exit/entry constraints, waypoints) by the test suite;
  draw.io itself is not installed on this machine, so the file has not been
  opened in the desktop application.
* The OCR gate needs Windows with an English OCR language pack; elsewhere it
  reports `ocr unavailable` and checks nothing.

## Versioning

See [CHANGELOG.md](CHANGELOG.md). Versions follow semantic versioning; while
the major version is 0 the Python API may change between minor versions.
