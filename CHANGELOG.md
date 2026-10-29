# Changelog

All notable changes to asi_escher are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/c00289/asi_escher/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/c00289/asi_escher/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/c00289/asi_escher/releases/tag/v0.1.1
