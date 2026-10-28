"""Command-line interface.

    asi-escher build SPEC.json [SPEC2.json ...] [-o OUT] [--formats png,svg,dot,mmd]
    asi-escher gallery [-o OUT]
    asi-escher example NAME [-o OUT]
    asi-escher list

A spec file is the JSON form of :meth:`asi_escher.Diagram.to_dict`; see
README.md for the schema.
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
from .pipeline import FORMATS, build


def _formats(s: str) -> tuple[str, ...]:
    fmts = tuple(f.strip() for f in s.split(",") if f.strip())
    bad = [f for f in fmts if f not in FORMATS]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown format(s) {bad}; choose from {', '.join(FORMATS)}")
    return fmts


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="asi-escher", description="Render diagrams from JSON specs.")
    p.add_argument("--version", action="version", version=f"asi-escher {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("-o", "--out", default="out", help="output directory (default: out)")
        sp.add_argument("--dpi", type=int, default=160, help="PNG resolution (default: 160)")
        sp.add_argument("--formats", type=_formats, default=FORMATS,
                        help="comma-separated subset of png,svg,dot,mmd (default: all)")
        sp.add_argument("--ranksep", type=float, help="gap between layers in px")
        sp.add_argument("--nodesep", type=float, help="gap between nodes in a layer in px")

    b = sub.add_parser("build", help="render one or more JSON diagram specs")
    b.add_argument("spec", nargs="+", help="JSON spec file(s); '-' reads one spec from stdin")
    b.add_argument("--name", help="output file stem (single spec only; default: slug of title)")
    common(b)

    g = sub.add_parser("gallery", help="render all bundled examples plus index.html")
    common(g)

    e = sub.add_parser("example", help="render one bundled example")
    e.add_argument("name", help="example name (see 'list')")
    common(e)

    sub.add_parser("list", help="list bundled example names")
    return p


def _opts(args) -> LayoutOptions | None:
    kw = {k: v for k, v in (("ranksep", args.ranksep), ("nodesep", args.nodesep)) if v is not None}
    return LayoutOptions(**kw) if kw else None


def _load_spec(path: str) -> Diagram:
    if path == "-":
        data = json.load(sys.stdin)
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    return Diagram.from_dict(data)


def _report(res: dict) -> None:
    written = ", ".join(res[f] for f in FORMATS if f in res)
    print(f"{res['nodes']} nodes, {res['edges']} edges, {res['size'][0]}x{res['size'][1]} px -> {written}")
    for issue in res["issues"]:
        print(f"  warning: {issue.message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    warnings.simplefilter("ignore", LayoutWarning)      # issues are printed per diagram instead
    try:
        if args.cmd == "list":
            for name, _ in EXAMPLES:
                print(name)
            return 0
        if args.cmd == "gallery":
            build_gallery(args.out, dpi=args.dpi)
            return 0
        if args.cmd == "example":
            table = dict(EXAMPLES)
            if args.name not in table:
                print(f"unknown example {args.name!r}; run 'asi-escher list'", file=sys.stderr)
                return 2
            _report(build(table[args.name](), args.out, args.name, opts=_opts(args),
                          dpi=args.dpi, formats=args.formats))
            return 0
        if args.name and len(args.spec) > 1:
            print("--name applies to a single spec only", file=sys.stderr)
            return 2
        for path in args.spec:
            d = _load_spec(path)
            _report(build(d, args.out, args.name, opts=_opts(args), dpi=args.dpi, formats=args.formats))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
