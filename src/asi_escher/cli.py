"""Command-line interface.

    asi-escher export SPEC.json [--out DIR] [--format drawio|png|svg]... [--all]
    asi-escher build SPEC.json [SPEC2.json ...] [-o OUT] [--formats drawio,png,svg,dot,mmd]
    asi-escher gallery [-o OUT]
    asi-escher example NAME [-o OUT]
    asi-escher verify PICTURE.png --expect LABEL [LABEL ...]
    asi-escher list

A spec file is the JSON form of :meth:`asi_escher.Diagram.to_dict`; see
README.md for the schema.  ``export`` writes the format set shared with the
sibling tools (``drawio`` and ``png`` by default); ``build`` writes any of
the five formats, all of them by default.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings

from . import __version__
from .examples import EXAMPLES
from .gallery import build_gallery
from .layout import LayoutOptions, LayoutWarning
from .model import Diagram
from .pipeline import ALL_FORMATS, DEFAULT_FORMATS, FORMATS, build


def _formats(s: str) -> tuple[str, ...]:
    fmts = tuple(f.strip() for f in s.split(",") if f.strip())
    bad = [f for f in fmts if f not in ALL_FORMATS]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown format(s) {bad}; choose from {', '.join(ALL_FORMATS)}")
    return fmts


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="asi-escher", description="Render diagrams from JSON specs.")
    p.add_argument("--version", action="version", version=f"asi-escher {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("-o", "--out", default="out", help="output directory (default: out)")
        sp.add_argument("--dpi", type=int, default=160, help="PNG resolution (default: 160)")
        sp.add_argument("--formats", type=_formats, default=ALL_FORMATS,
                        help=f"comma-separated subset of {','.join(ALL_FORMATS)} (default: all)")
        sp.add_argument("--ranksep", type=float, help="gap between layers in px")
        sp.add_argument("--nodesep", type=float, help="gap between nodes in a layer in px")
        sp.add_argument("--no-provenance", action="store_true",
                        help="no footer on the renderings, no comment and note in the draw.io file")
        sp.add_argument("--ocr", action="store_true",
                        help="read the PNG back with the Windows OCR engine and report unreadable labels")

    b = sub.add_parser("build", help="render one or more JSON diagram specs in any of the five formats")
    b.add_argument("spec", nargs="+", help="JSON spec file(s); '-' reads one spec from stdin")
    b.add_argument("--name", help="output file stem (single spec only; default: slug of title)")
    common(b)

    x = sub.add_parser("export", help="write a JSON diagram spec as <slug>.drawio / .png / .svg")
    x.add_argument("spec", help="JSON spec file; '-' reads it from stdin")
    x.add_argument("--out", default="out", help="output directory (default: out)")
    x.add_argument("--format", action="append", choices=FORMATS, dest="format",
                   help=f"a format to write, repeatable (default: {' and '.join(DEFAULT_FORMATS)})")
    x.add_argument("--all", action="store_true", help=f"write every format ({', '.join(FORMATS)})")
    x.add_argument("--name", help="output file stem (default: slug of title)")
    x.add_argument("--dpi", type=int, default=160, help="PNG resolution (default: 160)")
    x.add_argument("--no-provenance", action="store_true",
                   help="no footer on the renderings, no comment and note in the draw.io file")
    x.add_argument("--ocr", action="store_true",
                   help="read the PNG back with the Windows OCR engine and report unreadable labels")

    g = sub.add_parser("gallery", help="render all bundled examples plus index.html")
    common(g)

    e = sub.add_parser("example", help="render one bundled example")
    e.add_argument("name", help="example name (see 'list')")
    common(e)

    v = sub.add_parser("verify", help="read a PNG back with the Windows OCR engine and check its labels")
    v.add_argument("png", help="the picture to read")
    v.add_argument("--expect", nargs="+", default=[], metavar="LABEL", help="labels that must be legible")
    v.add_argument("--json", action="store_true", help="print the report as JSON")

    sub.add_parser("list", help="list bundled example names")
    return p


def _opts(args) -> LayoutOptions | None:
    kw = {k: v for k, v in (("ranksep", getattr(args, "ranksep", None)), ("nodesep", getattr(args, "nodesep", None)))
          if v is not None}
    return LayoutOptions(**kw) if kw else None


def _load_spec(path: str) -> Diagram:
    if path == "-":
        data = json.load(sys.stdin)
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    return Diagram.from_dict(data)


def _report(res: dict) -> None:
    written = ", ".join(res[f] for f in ALL_FORMATS if f in res)
    print(f"{res['nodes']} nodes, {res['edges']} edges, {res['size'][0]}x{res['size'][1]} px -> {written}")
    if "ocr" in res:
        print(f"  legibility: {res['ocr'].verdict} ({len(res['ocr'].lines)} OCR lines)")
    for issue in res["issues"]:
        print(f"  warning: {issue.message}", file=sys.stderr)


def _verify(args) -> int:
    from .ocr import ocr_check

    report = ocr_check(args.png, list(args.expect))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"{report.verdict} ({len(report.lines)} OCR lines)")
        for label in report.missing:
            print(f"  unreadable: {label}")
    if not report.available:
        return 3
    return 0 if report.competent else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    warnings.simplefilter("ignore", LayoutWarning)      # issues are printed per diagram instead
    try:
        if args.cmd == "list":
            for name, _ in EXAMPLES:
                print(name)
            return 0
        if args.cmd == "verify":
            return _verify(args)
        if args.cmd == "gallery":
            build_gallery(args.out, dpi=args.dpi, formats=args.formats, provenance=not args.no_provenance,
                          ocr=True if args.ocr else "control_structure")
            return 0
        if args.cmd == "export":
            formats = tuple(FORMATS) if args.all else tuple(dict.fromkeys(args.format or DEFAULT_FORMATS))
            d = _load_spec(args.spec)
            _report(build(d, args.out, args.name, dpi=args.dpi, formats=formats,
                          provenance=not args.no_provenance, ocr=args.ocr))
            return 0
        if args.cmd == "example":
            table = dict(EXAMPLES)
            if args.name not in table:
                print(f"unknown example {args.name!r}; run 'asi-escher list'", file=sys.stderr)
                return 2
            _report(build(table[args.name](), args.out, args.name, opts=_opts(args), dpi=args.dpi,
                          formats=args.formats, provenance=not args.no_provenance, ocr=args.ocr))
            return 0
        if args.name and len(args.spec) > 1:
            print("--name applies to a single spec only", file=sys.stderr)
            return 2
        for path in args.spec:
            d = _load_spec(path)
            _report(build(d, args.out, args.name, opts=_opts(args), dpi=args.dpi, formats=args.formats,
                          provenance=not args.no_provenance, ocr=args.ocr))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
