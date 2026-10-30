# Changelog

All notable changes to asi_escher are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-10-29

The owner's ask: "a new project for escher that will eventually be used elsewhere; for now just an
escher demo: a diagram that shows how all the events are chained, basically showing what is a blocker
for what, and this framework can tie in predecessors and successors." The later consumer is asi_kletz
(its Safety Plan deliverables and the Jira "blocks" links), so the model is plain data a plan can feed.

### Added

- Diagram kind `chain`, a precedence network. Builder: `event(id, title, *, status, kind, owner, due,
  note, effort)` with `status` in `done | active | blocked | pending | late` (the box colour: done
  green-grey, active blue, blocked `#F4C2C2`, pending white, late amber) and `kind` in `event |
  milestone | gate | external` (the shape: rounded, pointed ends, double border, dashed), the owner and
  due date as small lines under the title, the note as a small italic one; `blocks(predecessor,
  successor, *, kind, label)` with `kind` in `blocks | enables | informs` (solid with an arrowhead,
  solid thin, dashed with an open arrowhead). `blocked` is derived when not given: a pending event whose
  direct predecessor on a `blocks` edge is late, or marked blocked, is blocked (a pending or active
  predecessor is the normal course of a plan; the literal "any predecessor not done" rule paints every
  future event of a plan pink and says nothing).
- The queries: `predecessors`, `successors` (direct), `upstream`, `downstream` (transitive, in
  dependency order), `blockers` (the not-done events on the `blocks` chains above an event, up to the
  first done one, nearest first), `critical_path` (the longest chain by count, or by `effort` where
  given), `critical_edges`, `cycles` and `back_edges` (every cycle as its ids; a cycle is a
  `LayoutIssue` of kind `cycle`, the layout completes by drawing the closing edge backwards),
  `status` / `statuses` (effective), `columns`.
- Layout rules of the kind: left to right, an event's column one past the deepest of its `blocks` /
  `enables` predecessors, events with no predecessor in column 0, `informs` edges rank nothing (a
  backward one goes through the channel), the critical path pinned on one straight row with its
  arrows thicker and leaving on the centre line, the other rows relaxing around it, a long edge
  following its source and jogging once near its target; `LayoutOptions.for_kind("chain")`.
- Rendering: status colours and kind shapes, the critical path's arrows thicker, `render(d,
  focus=<id>)` (`build(..., focus=)`, `asi-escher export --focus ID`) dims everything but the event,
  its blockers and the `blocks` edges between them.
- Exports for the kind: DOT (status colours, hexagon / double border / dashed box, thicker critical
  edges, `informs` dashed without rank), Mermaid (`flowchart LR`, one `classDef` per status and every
  event in the class of its effective status), draw.io (the same shapes, colours and widths).
- The chain spec form: `to_dict()` writes a chain as `events` and `edges` plain lists (`id`, `title`,
  `kind`, `status`, `owner`, `due`, `note`, `effort`; `src`, `dst`, `kind`, `label`) and `from_dict()`
  reads a spec with `events` as a chain; `docs/chain_spec.json`. `asi-escher chain SPEC [--blockers
  ID...]` prints the critical path, the cycles, the effective statuses and the blockers as JSON.
- Bundled example `chain_demo` (synthetic: a safety programme from scope definition to release for
  operation along one spine, a supplier's failure data and a verification plan on branches, a gate
  before the milestone; fourteen events, two done, one active, two blocked, one late, one external,
  one `informs` edge, one labelled edge; the owners are roles, no person) and the README picture
  `docs/img/chain_demo.png`; the gallery builds it and runs the OCR gate on it (`gallery.OCR_KINDS`).
- Tests: `test_chain.py`; the session OCR probe moved to `conftest.py` so both kinds share it.

### Changed

- `Diagram(title, kind)` defaults `direction` to `LR` for a chain and `TB` for every other kind (the
  parameter default is now `None`; passing `"TB"` or `"LR"` works as before). `from_dict` passes the
  spec's `direction` through unchanged, so a spec without one gets the kind's default.
- `metrics.DASHED_EDGE_KINDS` includes `informs`; the renderer's `_draw_edge` takes `thick` and
  `alpha`, `_draw_node` a `status` and `alpha`, all defaulted so an undimmed drawing is the same bytes.
- `build_gallery(ocr=)` accepts a tuple of kinds; the default is `("control_structure", "chain")`.
- Every other diagram kind lays out and exports as before, byte for byte (checked against 0.2.2 for all
  seventeen examples: layout, draw.io, DOT, Mermaid and the SVG drawing).

## [0.2.2] - 2026-10-29

Broken-windows sweep at the end of the day that shipped 0.1.2 to 0.2.1: nothing new, everything
tidied. The Python API, the formats and every output are unchanged.

### Changed

- `__version__` comes from `asi_escher.provenance.package_version()`, the one lookup, instead of a
  second copy of the same try / except in `__init__`.
- `provenance.today()` says in its docstring that the date in the marks is the local calendar date on
  purpose: the file says when it was drawn on the machine that drew it.
- The renderer's private helpers `_draw_node`, `_draw_edge` and `_draw_block` no longer take the
  parameters they never read.
- The docstring of the lateral-arrow rule illustrates it with a generic pair of operators, not with the
  owner's structure.
- `docs/img/control_structure_demo.png` regenerated without the provenance footer, like the other three
  README pictures (dpi 110, the layout of 0.2.1 unchanged), so a version bump no longer dates it; the
  README says how the pictures are made.
- README: `verify` documents `--json`, `export` reads a spec from stdin like `build`, the test list
  names `test_version.py`.

### Fixed

- Tests: the session-wide OCR probe wrote a PNG with `NamedTemporaryFile(delete=False)` and never
  removed it (one file per run in `%TEMP%`); it now lives in pytest's `tmp_path_factory` directory.
  The private smoke test's comments no longer describe the private structure's tiers, and it no longer
  asks for a fixture it did not use.

## [0.2.1] - 2026-10-29

The owner, looking at the rendering of his own control structure (two operators stacked one above the
other, a drawing almost three times as tall as wide, two signal stacks overlapping): "have escher put
peers at the same level and widen the canvas."

### Changed

- Control-structure layout in tiers by the control hierarchy: a box sits one tier below the deepest box
  that sends it a control action, boxes that nobody commands are peers and share the top tier side by
  side, a box commanded from two tiers sits below both. Feedback never moves a box of the hierarchy; a
  box that only reports (a sensor, the environment) sits below the boxes it reports to, one that only
  listens (an external system taking reports) just above the nearest box it hears from (it sat at the
  top), the environment at the bottom beside the controlled process. A control action between two
  peers (a field operator's stop request to the control-room operator, while the field operator also
  commands the vehicle controller and the machine directly) is lateral: the two stay on one tier, the
  arrow runs horizontally between them, its answer beneath it, the label above / below the line. The
  owner's eight boxes come out in four tiers instead of five.
- Wider canvas: `LayoutOptions.for_kind("control_structure")` gives `ranksep=110, nodesep=160` (was 96,
  120); a control-structure box spreads its arrows over 70 % of its width (was 50 %) and is drawn at
  least 12 px wider per algorithm line; every arrow jogs just under its tier and runs straight into its
  target with the signal stack hanging beside that run in the channel between the two tiers (it jogged
  mid-channel, splitting the run in two short halves the stacks did not fit beside); the tallest stacks
  are placed first and slide along their arrow in finer steps; a channel grows by the height of a stack
  that still overlapped and the layout is redone, up to three times. The bundled demo lays out
  1133 x 1369 (was 837 x 1313, now wider than 0.8 of its height); the owner's structure 1724 x 2220
  (was 1249 x 2570) with no layout issue (it had two `label_overlap`), both competent under OCR.
- A note attached to a box gets 8 px more under its text: the OCR engine dropped the last italic line
  when it sat tight on the border.
- `LayoutIssue.edge` of a feedback edge names the author's `(src, dst)` (it named the reversed pair the
  engine works with).
- Every other diagram kind lays out as before, byte for byte.

### Fixed

- OCR gate and UTF-8 (found by asi_dewey): a non-ASCII label (a `•` bullet, an en dash, an `é`) came
  back through PowerShell in the console code page as a control byte that broke the JSON report, so the
  gate said `ocr unavailable`. The script now sets `[Console]::OutputEncoding` and `$OutputEncoding` to
  UTF-8 and the subprocess output is decoded as UTF-8; the match strips accents and folds `rn`/`tn` to
  an italic `m` on both sides.
- Tests: the tier rule (peers share a tier, a box reached from two tiers sits below both, feedback
  moves no box, a lateral arrow is horizontal with room for its label), the demo's width (at least 0.8
  of its height) and zero label overlaps, the UTF-8 path with a faked payload and with the real engine
  on a diagram carrying `•`, `–` and `é`; the private smoke test asserts the four tiers, zero label
  overlaps and the OCR verdict, counts only.

## [0.2.0] - 2026-10-29

Phase 1 of the control-structure plan (asi_dewey `docs/control-structure-plan.md`). The owner's ask: "we
need to make control structures like the one in Roy's Brain [...] the user can export them to their folder
of preference, selecting the format [...] drawio makes drawings by getting the positioning from the
automatically positioned pydraw; the user can pick which of the formats they want; [...] the default must be
drawio png"; "no drawio; generate the drawio file and we can use the VS Code preview to see it"; "when you
make the diagrams please use OCR on the PNG so that the final diagrams are competent"; and, on the PNG and
SVG being escher's pictures of the draw.io layout, "include a comment in the drawing".

### Added

- Diagram kind `control_structure` (STPA): a box has a title, a responsibility, an algorithms section
  (orange) and a process model (blue); node kinds `controller`, `human_controller` (rounded),
  `controlled_process` (double border), `environment` (dashed), `sensor` and `actuator` (small shapes),
  `external_system`; edge kinds `control_action` (red, arrowhead down the hierarchy) and `feedback` (blue,
  arrowhead up), each carrying numbered signals drawn one per label line; a note attached to a box floats
  beside it. Builder: `controller()`, `control_action()`, `feedback()`, `note(..., attached_to=)`; the JSON
  spec carries `responsibility`, `algorithms`, `process_model`, `attached_to` and `signals`.
- Layout rules of the kind: top-down by hierarchy (feedback is laid out reversed beside the control action
  it answers, then turned round), control actions keep the left of a pair of boxes and feedback the right,
  their labels hang outward, so the two arrows between two boxes never overlap; `LayoutOptions.for_kind()`
  gives a control structure wider gaps by default.
- `to_drawio(diagram, provenance=True, name=None)`: the diagram as uncompressed mxGraph XML
  (`compressed="false"`, cells 0 and 1), one vertex per box with the layout's x, y, width and height, the
  sections as an HTML label in the renderer's colours, one edge per arrow with exit/entry constraints, the
  routed points as `mxPoint` waypoints and the signal lines as its label placed where the layout put it;
  swimlanes and the SysML frame as background rectangles; every diagram kind exports. It is the editable
  master: draw.io or the VS Code draw.io extension opens it with every box where escher put it.
- The format set `FORMATS = ("drawio", "png", "svg")` with `DEFAULT_FORMATS = ("drawio", "png")`, shared
  with the sibling tools; `ALL_FORMATS` adds `dot` and `mmd`. `asi-escher export <spec.json> --out <dir>
  [--format drawio|png|svg]... [--all]` writes `<slug>.drawio` / `.png` / `.svg`.
- Provenance marks: the `.drawio` carries an XML comment after `<mxfile>` and a grey note cell under the
  drawing, the PNG and SVG a grey footer line ("asi_escher 0.2.0, <date>; layout shared with
  <slug>.drawio"), all saying the pictures are escher's renderings of the draw.io layout, not draw.io
  exports; `provenance=False` (`--no-provenance`) switches them off.
- The OCR quality gate (`asi_escher.ocr`): `ocr_check(png_path, expected) -> OcrReport` reads a PNG back
  with the built-in Windows OCR engine (PowerShell 5.1 WinRT, no Tesseract) and checks every node title,
  signal id and algorithm code with a tolerant match; `build(..., ocr=True)` and `--ocr` add the misses as
  `LayoutIssue` entries of kind `ocr` and the report with its verdict ("competent" or the unreadable
  labels) and OCR line count; `asi-escher verify <png> --expect LABEL...`; `expected_labels(diagram)`.
  When the engine is unavailable the gate reports `ocr unavailable` and never fails a build. The gallery
  runs it on every control structure; the suite asserts the demo is competent when the engine is there.
- Bundled example `control_structure_demo` (synthetic: an operator, a site supervisor, a vehicle
  controller, a safety supervisor on the stop path, the machine, a perception unit, the work site, a fleet
  service; invented signals), `docs/control_structure_spec.json` and the README picture.
- Tests: `test_control_structure.py`, `test_drawio.py`, `test_ocr.py` and `test_private_smoke.py` (runs
  only when the owner's private datasets sit beside the repo; asserts counts and well-formed output,
  nothing from the data).

### Changed

- `build()` writes `drawio` and `png` when `formats` is not given (it wrote png, svg, dot and mmd); callers
  that name their formats, as asi_dewey and asi_kletz do, are unaffected. `asi-escher build` still writes
  every format by default, now five.
- `build_gallery()` takes `formats`, `provenance` and `ocr`; the index links the draw.io file and shows the
  legibility verdict.
- `pipeline.slug` lives in `asi_escher.provenance` (still importable from `pipeline`).
- Algorithm lines in a control-structure box are set as `code name` with one space: a wider gap made the
  OCR engine read the codes as a separate column and drop some of them.

## [0.1.3] - 2026-10-29

### Fixed
- README: the folder tree of the siblings named asi_dewey and asi_gutenberg only; asi_kletz (the other
  primary tool) and asi_hopper (the Jira gateway) sit beside this repo too and are listed now, as the
  sibling READMEs list them. Found by the family's integration review of 2026-10-29; no code changed.

## [0.1.2] - 2026-10-29

### Changed

- `examples.flowchart_lifecycle` is now `flowchart_fusa_lifecycle`, the name
  it is registered under in `EXAMPLES` and listed under in the README. No
  sibling imported the function; the example name is unchanged.

### Fixed

- CHANGELOG compare links pointed at an `example.invalid` placeholder; they
  now point at the GitHub repository. Versions 0.1.0 and 0.0.0 predate this
  repository (its history starts at the `v0.1.1` tag) and have no tag here,
  so their headings are unlinked.
- README: the git-source example no longer says "once the repo has a remote";
  it names the remote and pins `v0.1.2`.
- The CI workflow comment said windows-latest was chosen so the GUI tests
  could run under Tk; asi_escher has no GUI. The comment now gives the real
  reason (the platform the sibling tools and Roy's machine use).
- `tests/test_version.py` checks that `pyproject.toml`, the README version
  line and git-source pin, the top CHANGELOG entry and
  `asi_escher.__version__` agree, so a half-done bump fails the suite.
- `test_cli_example` no longer takes a `capsys` fixture it never used.

## [0.1.1] - 2026-10-28

### Fixed

- Back-edge labels in left-to-right diagrams (for example `replan` in
  `flowchart_pipeline_lr` and `re-check` in `swimlanes_lr_dispatch`) were
  drawn centred on the dashed line instead of just below it: the renderer
  ignored the `label_ha` / `label_va` anchors the layout chose when it
  transposed the diagram, so the drawn box differed from the one the layout
  had kept clear of nodes and other labels. The renderer now honours them.
- The renderer rebuilt the edge-label text (stereotype plus label) with its
  own copy of the `deriveReqt` mapping; it now uses `metrics.edge_label`,
  the same function the layout measures with.
- The list of edge kinds drawn dashed lived once in the renderer and once in
  the exporters; it is now the single `metrics.DASHED_EDGE_KINDS`.
- README: a version line, the shared command-line options (`--dpi`,
  `--formats`, `--ranksep`, `--nodesep`, `--name`, stdin via `-`,
  `--version`), the table of the sixteen bundled examples and the names of
  the test files, so the README matches `--help`, `examples.py` and `tests/`.
- README's git-source example now pins `v0.1.1`.
- CHANGELOG: compare links at the foot for every released version.

## [0.1.0] - 2026-10-27

Renamed from `asi_pydraw` to `asi_escher` and moved into its own repository
next to the Roy's Brain folder. Import name, package directory, command name
(`asi-escher`) and release tags all change; the Python API is otherwise the
0.0.0 API.

### Added

- `py.typed` marker so host type-checkers see the package as typed.
- Layout quality reporting: `layout()` records every degraded result in
  `Diagram.issues` as `LayoutIssue` objects (`label_overlap` when a label had
  to touch a node or another label, `edge_through_node` when a routed edge
  crosses an unrelated node) and emits one `LayoutWarning` per diagram.
  `build()` returns the issues under `"issues"`; the CLI prints them to
  stderr; the gallery log counts them. Previously these fallbacks were silent.
- README section on installing from Roy's Brain and asi_gutenberg via a uv
  path source, verified against a scratch consumer.

### Changed

- Project metadata for the new name; `Typing :: Typed` classifier.

## [0.0.0] - 2026-10-27 (released as `asi_pydraw`)

First release, under the name `asi_pydraw` inside the Roy's Brain
repository (tag `asi_pydraw-v0.0.0` there). Superseded the earlier
unversioned `pydraw` prototype.

### Added

- `Diagram` model with activity, flowchart, state-machine and SysML
  block / internal-block / requirement node and edge kinds, swimlanes and
  diagram frames.
- Deterministic layered layout engine (`layout`, `LayoutOptions`) with cycle
  removal, dummy nodes, lane-aware ordering, per-component balancing,
  orthogonal routing and collision-avoiding edge-label placement.
- matplotlib renderer (`render`, `THEME`) producing PNG and SVG with text
  kept as text; accepts paths or file objects and returns the `Figure`.
- Graphviz DOT and Mermaid exporters (`to_dot`, `to_mermaid`).
- One-call pipeline `build()` with selectable output formats.
- JSON interchange via `Diagram.to_dict()` / `Diagram.from_dict()`.
- Command line (`build`, `gallery`, `example`, `list`) and `python -m`.
- Sixteen bundled example diagrams and a gallery builder.
- Test suite covering model validation, geometric layout invariants on every
  example, exporters, renderer isolation, pipeline and CLI.

### Changed (relative to the `pydraw` prototype)

- Layout no longer rewrites node labels; wrapped text is stored separately
  in `Node.lines` and exporters emit the author's original labels.
- The renderer no longer imports `pyplot`, forces the Agg backend or mutates
  global rcParams.
- Disconnected components are laid out independently and packed side by
  side instead of drifting apart during balancing.
- Edges through dummy nodes stay vertical across a layer band and only jog in
  the gaps between layers, so long edges no longer clip neighbouring nodes.
- Decisions exit sideways only when no node in the same row is in the way.
- Canvas size accounts for edge labels, so labels on back edges are no longer
  clipped at the right edge.
- Layer gaps widen to fit edge labels in left-to-right diagrams.
- Input validation: unknown diagram/node/edge kinds, edge styles, duplicate
  node or lane ids, and nodes without a lane in a swimlane diagram raise
  immediately.
- Empty diagrams and very long chains (thousands of nodes) lay out without
  errors.
- `networkx` removed from the dependencies (it was never used).
- Demo catalog moved into the package as `examples`; `demos/build_all.py`
  is a thin wrapper around `gallery`.

[Unreleased]: https://github.com/c00289/asi_escher/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/c00289/asi_escher/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/c00289/asi_escher/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/c00289/asi_escher/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/c00289/asi_escher/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/c00289/asi_escher/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/c00289/asi_escher/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/c00289/asi_escher/releases/tag/v0.1.1
