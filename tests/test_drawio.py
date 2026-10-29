"""``to_drawio``: mxGraph XML parsed back with xml.etree, positions equal to the layout."""
import xml.etree.ElementTree as ET

import pytest

from asi_escher import Diagram, layout, to_drawio
from asi_escher.examples import activity_swimlanes_estop, bdd_wheel_loader, control_structure_demo


def _cells(xml: str):
    root = ET.fromstring(xml)
    assert root.tag == "mxfile" and root.get("compressed") == "false"
    model = root.find("diagram/mxGraphModel")
    cells = model.findall("root/mxCell")
    by_id = {c.get("id"): c for c in cells}
    assert by_id["0"].get("parent") is None and by_id["1"].get("parent") == "0"
    return root, by_id


def _geometry(cell):
    g = cell.find("mxGeometry")
    return tuple(float(g.get(k)) for k in ("x", "y", "width", "height"))


def test_vertices_and_edges_match_the_layout(example):
    layout(example)
    _, cells = _cells(to_drawio(example))
    for n in example.real_nodes():
        cell = cells[n.id]
        assert cell.get("vertex") == "1" and cell.get("parent") == "1"
        x, y, w, h = _geometry(cell)
        assert (x, y, w, h) == pytest.approx((n.left, n.top, n.w, n.h), abs=0.01), n.id
    edge_cells = [c for c in cells.values() if c.get("edge") == "1"]
    assert len(edge_cells) == len(example.edges)
    for cell, e in zip(edge_cells, example.edges, strict=True):
        assert cell.get("source") == e.src and cell.get("target") == e.dst
        geo = cell.find("mxGeometry")
        assert geo.get("relative") == "1"
        src_pt = geo.find("mxPoint[@as='sourcePoint']")
        dst_pt = geo.find("mxPoint[@as='targetPoint']")
        assert (float(src_pt.get("x")), float(src_pt.get("y"))) == pytest.approx(e.points[0], abs=0.01)
        assert (float(dst_pt.get("x")), float(dst_pt.get("y"))) == pytest.approx(e.points[-1], abs=0.01)
        waypoints = geo.findall("Array[@as='points']/mxPoint")
        assert len(waypoints) == len(e.points) - 2
        for wp, (x, y) in zip(waypoints, e.points[1:-1], strict=True):
            assert (float(wp.get("x")), float(wp.get("y"))) == pytest.approx((x, y), abs=0.01)
        if e.label:
            assert geo.find("mxPoint[@as='offset']") is not None


def test_labels_carry_the_signals_and_styles_the_colours():
    d = control_structure_demo()
    _, cells = _cells(to_drawio(d))
    edges = [c for c in cells.values() if c.get("edge") == "1"]
    ca = next(c for c in edges if c.get("source") == "operator" and c.get("target") == "supervisor")
    fb = next(c for c in edges if c.get("source") == "supervisor" and c.get("target") == "operator")
    assert ca.get("value") == "CA-01 Mission Start<br>CA-02 Mission Stop"
    assert fb.get("value") == "FB-01 Mission State<br>FB-02 Machine Health"
    assert "strokeColor=#C62828" in ca.get("style") and "endArrow=block" in ca.get("style")
    assert "strokeColor=#1565C0" in fb.get("style") and "endArrow=block" in fb.get("style")
    assert "exitX=" in ca.get("style") and "entryY=" in ca.get("style")
    assert "html=1" in ca.get("style")


def test_box_styles_and_html_sections():
    d = control_structure_demo()
    _, cells = _cells(to_drawio(d))
    assert "shape=ext;double=1" in cells["machine"].get("style")           # controlled process
    assert "dashed=1" in cells["environment"].get("style")
    assert "rounded=1" in cells["operator"].get("style")                    # human controller
    assert "shape=note" in cells["note_vehicle"].get("style")
    assert "html=1" in cells["vehicle"].get("style")
    value = cells["vehicle"].get("value")
    assert value.startswith("<b>Vehicle Controller</b>")
    assert "background:#FFF3E0" in value and "V1 Trajectory planning" in value
    assert "background:#E3F2FD" in value and "<b>Vehicle process model</b>" in value
    assert "&lt;" not in value                                               # value is HTML after parsing


def test_flowchart_with_lanes_and_a_bdd_export_too():
    d = activity_swimlanes_estop()
    _, cells = _cells(to_drawio(d))
    assert all(f"lane_{ln.id}" in cells for ln in d.lanes)
    assert "rhombus" in cells["agree"].get("style")
    assert "ellipse" in cells["start"].get("style")
    b = bdd_wheel_loader()
    _, bcells = _cells(to_drawio(b))
    assert "frame" in bcells and bcells["frame"].get("value") == b.frame
    assert "startArrow=diamondThin" in next(c for c in bcells.values() if c.get("edge") == "1").get("style")
    assert "<b>Autonomous Wheel Loader</b>" in bcells["loader"].get("value")


def test_to_drawio_lays_out_an_unlaid_diagram():
    d = Diagram("Fresh", "flowchart")
    d.start()
    d.action("a", "Do")
    d.end()
    d.chain("start", "a", "end")
    xml = to_drawio(d)
    assert d.width > 0
    _, cells = _cells(xml)
    assert _geometry(cells["a"])[2] == pytest.approx(d.nodes["a"].w, abs=0.01)


def test_ids_stay_unique_when_nodes_use_reserved_ones():
    d = Diagram("Ids")
    d.action("0", "zero")
    d.action("1", "one")
    d.action("e1", "edge-like")
    d.edge("0", "1")
    _, cells = _cells(to_drawio(d, provenance=False))
    ids = list(cells)
    assert len(ids) == len(set(ids))
    vertices = [c for c in cells.values() if c.get("vertex") == "1"]
    assert {c.get("value") for c in vertices} == {"zero", "one", "edge-like"}


def test_provenance_comment_and_note_are_there_by_default_and_gone_when_off():
    d = layout(control_structure_demo())
    xml = to_drawio(d)
    head, _, rest = xml.partition("\n  <!--")
    assert head.endswith('compressed="false">')                      # the comment follows the mxfile opening
    comment = rest.partition("-->")[0]
    assert "Generated by asi_escher" in comment and "escher's renderings" in comment
    assert "demo_loader_control_structure.png and demo_loader_control_structure.svg" in comment
    _, cells = _cells(xml)
    note = cells["provenance"]
    assert "fontColor=#9E9E9E" in note.get("style") and "fontStyle=2" in note.get("style")
    assert "asi_escher" in note.get("value") and "not draw.io exports" in note.get("value")
    assert _geometry(note)[1] >= d.height                             # outside the drawing's bounding box
    bare = to_drawio(d, provenance=False)
    assert "<!--" not in bare
    assert "provenance" not in _cells(bare)[1]
    named = to_drawio(d, name="wl_master")
    assert "wl_master.png and wl_master.svg" in named
