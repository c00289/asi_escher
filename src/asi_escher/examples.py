"""Example diagrams shipped with asi_escher.

Each builder returns a Diagram.  Content is themed around an autonomous wheel
loader and its functional-safety system so the pictures look like real
engineering artefacts rather than lorem ipsum.
"""
from __future__ import annotations

import random
from collections.abc import Callable

from .model import Diagram


# --------------------------------------------------------------- activity --
def activity_load_cycle() -> Diagram:
    d = Diagram("Autonomous Load Cycle", "activity")
    d.start()
    d.action("rx", "Receive mission from fleet server")
    d.action("plan", "Plan path to stockpile")
    d.action("approach", "Approach pile at crawl speed")
    d.action("dig", "Execute dig trajectory")
    d.decision("full", "Bucket fill > 85%?")
    d.action("lift", "Lift and tilt bucket")
    d.action("travel", "Travel to dump target")
    d.action("dump", "Dump load into truck")
    d.decision("done", "Mission complete?")
    d.action("report", "Report cycle metrics")
    d.end()
    d.chain("start", "rx", "plan", "approach", "dig", "full")
    d.edge("full", "lift", "yes")
    d.edge("full", "dig", "no, re-dig")
    d.chain("lift", "travel", "dump", "done")
    d.edge("done", "plan", "no")
    d.edge("done", "report", "yes")
    d.edge("report", "end")
    return d


def activity_swimlanes_estop() -> Diagram:
    d = Diagram("Emergency Stop Handling", "activity")
    d.lane("op", "Operator")
    d.lane("auto", "Autonomy Controller")
    d.lane("safe", "Safety Controller")
    d.lane("mach", "Machine Platform")
    d.start(lane="op")
    d.action("press", "Press E-stop", lane="op")
    d.action("detect", "Read dual-channel E-stop input", lane="safe")
    d.decision("agree", "Channels agree?", lane="safe")
    d.action("disc", "Flag channel discrepancy", lane="safe")
    d.action("inhibit", "Open drive inhibit relay", lane="safe")
    d.fork("f1", lane="safe")
    d.action("pilot", "Cut hydraulic pilot pressure", lane="mach")
    d.action("brake", "Apply park brake", lane="mach")
    d.action("safestop", "Transition to SAFE_STOP state", lane="auto")
    d.join("j1", lane="safe")
    d.action("ack", "Acknowledge and reset E-stop", lane="op")
    d.action("verify", "Verify reset conditions", lane="safe")
    d.decision("ok", "Safe to resume?", lane="safe")
    d.action("standby", "Resume STANDBY mode", lane="auto")
    d.end(lane="auto")
    d.chain("start", "press", "detect", "agree")
    d.edge("agree", "inhibit", "yes")
    d.edge("agree", "disc", "no")
    d.edge("disc", "inhibit")
    d.edge("inhibit", "f1")
    d.edge("f1", "pilot")
    d.edge("f1", "brake")
    d.edge("f1", "safestop")
    d.edge("pilot", "j1")
    d.edge("brake", "j1")
    d.edge("safestop", "j1")
    d.chain("j1", "ack", "verify", "ok")
    d.edge("ok", "standby", "yes")
    d.edge("ok", "verify", "no")
    d.edge("standby", "end")
    return d


def activity_fork_join_post() -> Diagram:
    d = Diagram("Power-On Self Test", "activity")
    d.start()
    d.action("boot", "Boot safety controller")
    d.fork("f")
    d.action("t1", "Test lidar heartbeat")
    d.action("t2", "Test radar heartbeat")
    d.action("t3", "Test E-stop loop continuity")
    d.action("t4", "Test brake pressure sensor")
    d.action("t5", "Test steering feedback")
    d.join("j")
    d.decision("all", "All tests passed?")
    d.action("standby", "Enter STANDBY")
    d.action("degraded", "Enter DEGRADED mode")
    d.action("notify", "Notify operator with fault list")
    d.end()
    d.chain("start", "boot", "f")
    for t in ("t1", "t2", "t3", "t4", "t5"):
        d.edge("f", t)
        d.edge(t, "j")
    d.edge("j", "all")
    d.edge("all", "standby", "yes")
    d.edge("all", "degraded", "no")
    d.edge("degraded", "notify")
    d.edge("standby", "end")
    d.edge("notify", "end")
    return d


def activity_object_flow() -> Diagram:
    d = Diagram("Bucket Fill Estimation", "activity")
    d.start()
    d.action("cap", "Capture bucket point cloud")
    d.node("pc", "pointCloud : PointCloud", "object")
    d.action("seg", "Segment material surface")
    d.node("mesh", "surface : Mesh", "object")
    d.action("vol", "Integrate volume above bucket floor")
    d.node("est", "fill : FillEstimate", "object")
    d.decision("conf", "Confidence > 0.8?")
    d.action("pub", "Publish fill estimate")
    d.action("fallback", "Use hydraulic pressure model")
    d.note("n1", "Pressure model calibrated per material density")
    d.end()
    d.chain("start", "cap", "pc", "seg", "mesh", "vol", "est", "conf")
    d.edge("conf", "pub", "yes")
    d.edge("conf", "fallback", "no")
    d.edge("n1", "fallback", kind="dependency")
    d.edge("fallback", "pub")
    d.edge("pub", "end")
    return d


# -------------------------------------------------------------- flowchart --
def flowchart_fault_response() -> Diagram:
    d = Diagram("Fault Response Selection", "flowchart")
    d.start()
    d.node("dtc", "Read diagnostic trouble code", "io")
    d.decision("sr", "Safety relevant?")
    d.decision("latch", "Latching fault?")
    d.decision("moving", "Machine moving?")
    d.node("db", "Fault log database", "database")
    d.node("rep", "Incident report", "document")
    d.action("cont", "Continue operation, raise warning")
    d.action("cstop", "Controlled stop\n(ramp down 2 m/s²)")
    d.action("istop", "Immediate stop\n(open inhibit relay)")
    d.action("lock", "Lock out autonomy until service")
    d.end()
    d.chain("start", "dtc", "sr")
    d.edge("sr", "cont", "no")
    d.edge("sr", "latch", "yes")
    d.edge("latch", "moving", "no")
    d.edge("latch", "istop", "yes")
    d.edge("moving", "cstop", "yes")
    d.edge("moving", "cont", "no")
    d.edge("istop", "lock")
    d.edge("lock", "rep")
    d.edge("cstop", "db")
    d.edge("cont", "db")
    d.edge("rep", "db")
    d.edge("db", "end")
    return d


def flowchart_pipeline_lr() -> Diagram:
    d = Diagram("Perception to Actuation Pipeline", "flowchart", direction="LR")
    d.node("lidar", "Lidar frames", "io")
    d.node("radar", "Radar tracks", "io")
    d.node("cam", "Camera images", "io")
    d.node("gnss", "GNSS / IMU pose", "io")
    d.action("fuse", "Sensor fusion")
    d.action("track", "Object tracking")
    d.action("free", "Free-space estimation")
    d.action("plan", "Path planner")
    d.action("ctrl", "Motion controller")
    d.node("valves", "Hydraulic valves", "io")
    d.node("drive", "Drive train", "io")
    d.action("mon", "Safety monitor")
    d.action("wd", "Watchdog")
    for s in ("lidar", "radar", "cam", "gnss"):
        d.edge(s, "fuse")
    d.edge("fuse", "track")
    d.edge("fuse", "free")
    d.edge("track", "plan")
    d.edge("free", "plan")
    d.edge("plan", "ctrl", "trajectory")
    d.edge("ctrl", "valves", "bucket / boom")
    d.edge("ctrl", "drive", "speed / steer")
    d.edge("lidar", "mon")
    d.edge("mon", "ctrl", "speed limit", kind="dependency")
    d.edge("ctrl", "wd", "heartbeat")
    d.edge("wd", "plan", "replan", style="dashed")
    return d


def flowchart_calibration_loops() -> Diagram:
    d = Diagram("Sensor Calibration Routine", "flowchart")
    d.start()
    d.action("init", "Initialise calibration targets")
    d.action("wait", "Wait for stable platform")
    d.action("cap", "Capture frame set")
    d.action("ext", "Solve extrinsics (ICP)")
    d.decision("res", "Residual < 2 cm?")
    d.decision("att", "Attempts < 10?")
    d.action("save", "Save calibration to NVM")
    d.action("abort", "Abort and flag sensor")
    d.action("nudge", "Adjust target pose")
    d.end()
    d.chain("start", "init", "wait", "cap", "ext", "res")
    d.edge("wait", "wait", "unstable")
    d.edge("res", "save", "yes")
    d.edge("res", "att", "no")
    d.edge("att", "nudge", "yes")
    d.edge("att", "abort", "no")
    d.edge("nudge", "cap", "retry")
    d.edge("abort", "init", "restart", style="dashed")
    d.edge("save", "end")
    return d


def flowchart_fusa_lifecycle() -> Diagram:
    d = Diagram("Functional Safety Lifecycle (ISO 25119 / ISO 13849)", "flowchart")
    d.start()
    d.node("concept", "Item definition and operating concept", "process")
    d.node("hara", "Hazard analysis and risk assessment", "process")
    d.node("pl", "Determine required PLr / AgPLr per hazard", "process")
    d.node("sg", "Safety goals", "document")
    d.node("fsc", "Functional safety concept", "process")
    d.node("tsc", "Technical safety concept", "process")
    d.node("hw", "Hardware design and PL evaluation", "process")
    d.node("sw", "Software design and verification", "process")
    d.node("int", "Integration testing", "process")
    d.decision("ok", "PL achieved and validated?")
    d.node("case", "Safety case", "document")
    d.action("rework", "Rework design and re-assess")
    d.node("rel", "Release for operation", "process")
    d.end()
    d.chain("start", "concept", "hara", "pl", "sg", "fsc", "tsc")
    d.edge("tsc", "hw")
    d.edge("tsc", "sw")
    d.edge("hw", "int")
    d.edge("sw", "int")
    d.edge("int", "ok")
    d.edge("ok", "case", "yes")
    d.edge("ok", "rework", "no")
    d.edge("rework", "tsc")
    d.chain("case", "rel", "end")
    return d


def swimlanes_lr_dispatch() -> Diagram:
    d = Diagram("Mission Dispatch", "activity", direction="LR")
    d.lane("fleet", "Fleet Server")
    d.lane("loader", "Loader Autonomy")
    d.lane("site", "Site Safety System")
    d.start(lane="fleet")
    d.action("create", "Create mission", lane="fleet")
    d.action("geo", "Check geofence and exclusion zones", lane="site")
    d.decision("clear", "Zone clear?", lane="site")
    d.action("send", "Send mission to loader", lane="fleet")
    d.action("accept", "Validate and accept mission", lane="loader")
    d.action("exec", "Execute load cycles", lane="loader")
    d.action("hold", "Hold mission", lane="fleet")
    d.action("done", "Report completion", lane="loader")
    d.end(lane="fleet")
    d.chain("start", "create", "geo", "clear")
    d.edge("clear", "send", "yes")
    d.edge("clear", "hold", "no")
    d.edge("hold", "geo", "re-check", style="dashed")
    d.chain("send", "accept", "exec", "done", "end")
    return d


# ------------------------------------------------------------------ state --
def state_autonomy_modes() -> Diagram:
    d = Diagram("Autonomy Mode State Machine", "state")
    d.start()
    d.state("manual", "MANUAL\nentry / disable autonomy outputs")
    d.state("standby", "STANDBY\nentry / run self-tests")
    d.state("auto", "AUTONOMOUS\ndo / execute mission")
    d.state("degraded", "DEGRADED\nentry / limit speed to 2 km/h")
    d.state("safestop", "SAFE_STOP\nentry / open inhibit relay")
    d.end()
    d.edge("start", "manual")
    d.edge("manual", "standby", "operator arms autonomy")
    d.edge("standby", "auto", "mission received\n[self-tests OK]")
    d.edge("auto", "standby", "mission complete")
    d.edge("auto", "degraded", "sensor fault")
    d.edge("degraded", "auto", "fault cleared")
    d.edge("degraded", "safestop", "second fault")
    d.edge("auto", "safestop", "E-stop / zone breach")
    d.edge("standby", "safestop", "E-stop")
    d.edge("safestop", "manual", "operator reset")
    d.edge("standby", "manual", "operator disarms")
    d.edge("manual", "end", "power off")
    return d


def state_estop_channel() -> Diagram:
    d = Diagram("E-Stop Dual Channel Monitor", "state", direction="LR")
    d.start()
    d.state("idle", "Idle")
    d.state("armed", "Armed")
    d.state("tripped", "Tripped")
    d.state("disc", "Discrepancy")
    d.state("reset", "Reset Pending")
    d.edge("start", "idle")
    d.edge("idle", "armed", "both channels closed")
    d.edge("armed", "tripped", "both channels open")
    d.edge("armed", "disc", "one channel open > 500 ms")
    d.edge("disc", "tripped", "second channel opens")
    d.edge("tripped", "reset", "channels closed")
    d.edge("reset", "armed", "reset button pressed")
    d.edge("disc", "reset", "service reset")
    return d


# ------------------------------------------------------------------ SysML --
def bdd_wheel_loader() -> Diagram:
    d = Diagram("Wheel Loader Structure", "bdd", frame="bdd [Package] WheelLoader [Structure]")
    d.block("loader", "Autonomous Wheel Loader",
            values=["mass : kg = 24000", "ratedPayload : kg = 5500", "maxSpeed : km/h = 35"],
            parts=["powertrain", "hydraulics", "autonomyKit", "safetySystem", "cab"])
    d.block("pt", "Powertrain", values=["enginePower : kW = 200"])
    d.block("hyd", "Hydraulic System", values=["pumpFlow : L/min = 320", "pilotPressure : bar"])
    d.block("kit", "Autonomy Kit", parts=["perception", "planner", "vehicleInterface"])
    d.block("safety", "Safety System", values=["PL = d", "category = 3"])
    d.block("cab", "Operator Cab", values=["eStopCount : int = 2"])
    d.block("perc", "Perception Suite", parts=["sensors[3..6]"])
    d.block("plan", "Planning Computer", operations=["planPath()", "replan()"])
    d.block("vif", "Vehicle Interface", operations=["sendCanCmd()"])
    d.block("sensor", "Sensor", values=["fov : deg", "rate : Hz"], operations=["publish()"])
    d.block("lidar", "Lidar", values=["range : m = 120"])
    d.block("radar", "Radar", values=["range : m = 200"])
    d.block("camera", "Camera", values=["resolution : px"])
    for p in ("pt", "hyd", "kit", "safety", "cab"):
        d.edge("loader", p, kind="composition")
    for p in ("perc", "plan", "vif"):
        d.edge("kit", p, kind="composition")
    d.edge("perc", "sensor", "3..6", kind="aggregation")
    for s in ("lidar", "radar", "camera"):
        d.edge("sensor", s, kind="generalization")
    return d


def bdd_safety_system() -> Diagram:
    d = Diagram("Safety System Definition", "bdd", frame="bdd [Package] SafetySystem")
    d.block("sys", "Safety System", values=["PLr = d", "MTTFd : years", "DCavg : %"],
            operations=["monitor()", "safeStop()"])
    d.block("plc", "Safety PLC", values=["SIL = 2", "cycleTime : ms = 10"],
            operations=["readInputs()", "evaluateLogic()", "driveOutputs()"])
    d.block("estop", "E-Stop Circuit", values=["channels : int = 2", "category = 3"])
    d.block("relay", "Drive Inhibit Relay", values=["forceGuided : bool = true"])
    d.block("brake", "Brake Actuator", values=["responseTime : ms < 150"])
    d.block("slidar", "Safety Lidar", values=["zones : int = 3", "type = 3 (IEC 61496)"])
    d.block("wd", "Watchdog", values=["timeout : ms = 100"])
    d.block("hmi", "Safety HMI", operations=["showFault()", "requestReset()"])
    for p in ("plc", "estop", "relay", "brake", "slidar", "hmi"):
        d.edge("sys", p, kind="composition")
    d.edge("plc", "wd", kind="composition")
    d.edge("hmi", "plc", "status", kind="association")
    return d


def ibd_safety_controller() -> Diagram:
    d = Diagram("Safety System Internal Structure", "ibd", direction="LR",
                frame="ibd [Block] SafetySystem")
    d.node("estop", "estop : E-Stop Circuit", "part")
    d.node("slidar", "slidar : Safety Lidar", "part")
    d.node("auto", "autonomy : Autonomy Computer", "part")
    d.node("plc", "plc : Safety PLC", "part")
    d.node("relay", "relay : Drive Inhibit Relay", "part")
    d.node("brake", "brake : Brake Actuator", "part")
    d.node("hmi", "hmi : Safety HMI", "part")
    d.edge("estop", "plc", "24 V dual channel", kind="connector", src_port="ch1/ch2", dst_port="di0:1")
    d.edge("slidar", "plc", "OSSD pairs", kind="connector", src_port="ossd", dst_port="di2:5")
    d.edge("auto", "plc", "heartbeat 10 Hz", kind="itemflow", src_port="can1", dst_port="can_s")
    d.edge("plc", "auto", "safe speed limit", kind="itemflow", src_port="can_s", dst_port="can1")
    d.edge("plc", "relay", "inhibit", kind="connector", src_port="do0", dst_port="coil")
    d.edge("plc", "brake", "brake_cmd", kind="connector", src_port="do1", dst_port="sol")
    d.edge("plc", "hmi", "fault codes", kind="itemflow", src_port="eth0", dst_port="eth")
    return d


def req_safety_requirements() -> Diagram:
    d = Diagram("Safety Requirements", "req", frame="req [Package] SafetyRequirements")
    d.requirement("sg1", "Prevent Unintended Motion", "SG-01",
                  "The loader shall not move while in STANDBY or SAFE_STOP.")
    d.requirement("sg2", "Stop Within Zone", "SG-02",
                  "The loader shall stop before entering an occupied exclusion zone.")
    d.requirement("fsr1", "Drive Inhibit", "FSR-01",
                  "A drive inhibit relay shall remove pilot pressure on safe stop.")
    d.requirement("fsr2", "Zone Monitoring", "FSR-02",
                  "Protective fields shall be monitored at >= 10 Hz.")
    d.requirement("tsr1", "Relay Diagnostics", "TSR-01",
                  "The inhibit relay shall be force-guided and read back each cycle.")
    d.requirement("tsr2", "Stopping Distance", "TSR-02",
                  "Stop within 2.0 m from 5 km/h on 10% grade.")
    d.block("plc", "Safety PLC")
    d.block("relay", "Drive Inhibit Relay")
    d.block("slidar", "Safety Lidar")
    d.block("tc1", "Brake Test on Grade", stereotype="testCase")
    d.edge("sg1", "fsr1", kind="derive")
    d.edge("sg2", "fsr2", kind="derive")
    d.edge("sg2", "tsr2", kind="derive")
    d.edge("fsr1", "tsr1", kind="derive")
    d.edge("tsr1", "relay", kind="satisfy")
    d.edge("tsr1", "plc", kind="satisfy")
    d.edge("fsr2", "slidar", kind="satisfy")
    d.edge("tsr2", "tc1", kind="verify")
    return d


# ----------------------------------------------------------------- stress --
def stress_random_dag(n: int = 44, seed: int = 7) -> Diagram:
    rng = random.Random(seed)
    d = Diagram(f"Stress Test: {n}-node Random DAG", "flowchart")
    d.start()
    verbs = ["Validate", "Fuse", "Filter", "Estimate", "Check", "Plan", "Log", "Encode",
             "Arbitrate", "Schedule", "Sample", "Compare"]
    objs = ["pose", "zones", "payload", "tyres", "CAN bus", "lidar", "radar", "brakes",
            "steering", "map", "mission", "watchdog"]
    for i in range(n):
        kind = "decision" if i % 7 == 3 else "action"
        d.node(f"t{i}", f"{rng.choice(verbs)} {rng.choice(objs)}" + ("?" if kind == "decision" else ""), kind)
    d.end()
    ids = [f"t{i}" for i in range(n)]
    d.edge("start", ids[0])
    d.edge("start", ids[1])
    for i in range(2, n):
        for _ in range(1 if rng.random() < 0.6 else 2):
            j = rng.randrange(max(0, i - 6), i)
            lab = rng.choice(["", "", "", "ok", "fail", "yes", "no"])
            d.edge(ids[j], ids[i], lab)
    sinks = [i for i in ids if not any(e.src == i for e in d.edges)]
    for s in sinks:
        d.edge(s, "end")
    # a few loops
    d.edge(ids[20], ids[5], "retry")
    d.edge(ids[n - 3], ids[12], "replan")
    return d


# ------------------------------------------------------ control structure --
def control_structure_demo() -> Diagram:
    """An STPA control structure of a demonstration loader: an operator and a
    site supervisor above a vehicle controller, the machine below it, the
    environment at the bottom and a stop path from the operator straight to
    the machine.  Every name and signal is invented."""
    d = Diagram("Demo Loader Control Structure", "control_structure")
    d.controller("operator", "Remote Operator", kind="human_controller",
                 responsibility="Starts and stops the mission; takes over when the machine asks.",
                 algorithms=[("O1", "Mission start / stop decision"), ("O2", "Takeover on request")],
                 process_model=("Operator process model",
                                ["Mission state (updated by FB-01)", "Machine health (updated by FB-02)"]))
    d.controller("supervisor", "Site Supervisor",
                 responsibility="Plans missions, assigns zones and keeps the site map current.",
                 algorithms=[("S1", "Mission planning"), ("S2", "Zone assignment"), ("S3", "Map update")],
                 process_model=("Supervisor process model",
                                ["Vehicle position (updated by FB-03)", "Zone occupancy (updated by FB-03)"]))
    d.controller("vehicle", "Vehicle Controller",
                 responsibility="Turns a mission into trajectories and drive commands; "
                                "stops within the zone on any fault.",
                 algorithms=[("V1", "Trajectory planning"), ("V2", "Speed control"),
                             ("V3", "Obstacle response"), ("V4", "Fault reaction")],
                 process_model=("Vehicle process model",
                                ["Machine speed and heading (updated by FB-10)",
                                 "Obstacle list (updated by FB-11)",
                                 "Drive inhibit state (updated by FB-12)"]))
    d.controller("safety", "Safety Supervisor",
                 responsibility="Monitors the stop paths and inhibits the drive on a stop request.",
                 algorithms=[("K1", "Stop path monitoring"), ("K2", "Drive inhibit")],
                 process_model=("Safety process model", ["Stop request state (updated by FB-20)"]))
    d.controller("machine", "Loader Machine", kind="controlled_process",
                 responsibility="Drives, steers and lifts as commanded.",
                 algorithms=[("M1", "Drive actuation"), ("M2", "Steering actuation"), ("M3", "Boom actuation")])
    d.controller("perception", "Perception Unit", kind="sensor")
    d.controller("environment", "Work Site", kind="environment",
                 responsibility="Stockpiles, haul roads, people and other machines.")
    d.controller("fleet", "Fleet Service", kind="external_system",
                 responsibility="Receives mission reports.")
    d.note("note_vehicle", "V4 stops the machine within 2 s of any fault", attached_to="vehicle")

    d.control_action("operator", "supervisor", ["CA-01 Mission Start", "CA-02 Mission Stop"])
    d.feedback("supervisor", "operator", ["FB-01 Mission State", "FB-02 Machine Health"])
    d.control_action("supervisor", "vehicle", ["CA-10 Mission Data", "CA-11 Zone Limits", "CA-12 Site Map"])
    d.feedback("vehicle", "supervisor", ["FB-03 Vehicle Position", "FB-04 Mission Progress"])
    d.control_action("vehicle", "machine", ["CA-20 Drive Command", "CA-21 Steer Command", "CA-22 Boom Command"])
    d.feedback("machine", "vehicle", ["FB-10 Machine State", "FB-12 Drive Inhibit State"])
    d.control_action("operator", "safety", ["CA-30 Emergency Stop"])
    d.feedback("safety", "operator", ["FB-20 Stop Request State"])
    d.control_action("safety", "machine", ["CA-31 Drive Inhibit"])
    d.feedback("perception", "vehicle", ["FB-11 Obstacle List"])
    d.feedback("environment", "perception", ["FB-30 Scene"])
    d.control_action("machine", "environment", ["CA-40 Material Moved"])
    d.feedback("vehicle", "fleet", ["FB-05 Mission Report"])
    return d


# ------------------------------------------------------------------ chain --
def chain_demo() -> Diagram:
    """A chain of a demonstration safety programme: scope to release along
    one spine, a supplier's data and a verification plan on branches, a
    gate before the milestone.  Every name, owner and date is invented;
    the owners are roles, not people."""
    d = Diagram("Demo Safety Programme Chain", "chain")
    d.event("scope", "Scope definition", status="done", owner="Programme lead", due="2026-09-04")
    d.event("standards", "Standards review", status="done", owner="Safety engineer", due="2026-09-11")
    d.event("supplier", "Supplier failure data", kind="external", status="late", owner="Supplier",
            due="2026-10-16", note="second reminder sent")
    d.event("hazards", "Hazard list", status="active", owner="Safety engineer", due="2026-11-06")
    d.event("risk", "Risk assessment", owner="Safety engineer", due="2026-11-20")
    d.event("metrics", "Hardware metrics", owner="Hardware engineer", due="2026-11-27")
    d.event("concept", "Safety concept", owner="Systems engineer", due="2026-12-11")
    d.event("reqs", "Safety requirements", owner="Systems engineer", due="2027-01-08")
    d.event("design", "Safety design", owner="Hardware engineer", due="2027-02-05")
    d.event("testplan", "Verification plan", owner="Test lead", due="2027-01-22")
    d.event("verification", "Verification", owner="Test lead", due="2027-03-05")
    d.event("validation", "Validation", owner="Test lead", due="2027-03-26")
    d.event("assessment", "Safety assessment", kind="gate", owner="Assessor", due="2027-04-09")
    d.event("release", "Release for operation", kind="milestone", owner="Programme lead", due="2027-04-23")
    d.blocks("scope", "hazards")
    d.blocks("hazards", "risk")
    d.blocks("supplier", "risk")
    d.blocks("supplier", "metrics", label="failure rates")
    d.blocks("risk", "concept")
    d.blocks("concept", "reqs")
    d.blocks("standards", "reqs", kind="enables")
    d.blocks("reqs", "design")
    d.blocks("metrics", "design")
    d.blocks("reqs", "testplan")
    d.blocks("risk", "testplan", kind="informs")
    d.blocks("design", "verification")
    d.blocks("testplan", "verification", kind="enables")
    d.blocks("verification", "validation")
    d.blocks("validation", "assessment")
    d.blocks("assessment", "release")
    return d


EXAMPLES: list[tuple[str, Callable[[], Diagram]]] = [
    ("activity_load_cycle", activity_load_cycle),
    ("activity_swimlanes_estop", activity_swimlanes_estop),
    ("activity_fork_join_post", activity_fork_join_post),
    ("activity_object_flow", activity_object_flow),
    ("flowchart_fault_response", flowchart_fault_response),
    ("flowchart_pipeline_lr", flowchart_pipeline_lr),
    ("flowchart_calibration_loops", flowchart_calibration_loops),
    ("flowchart_fusa_lifecycle", flowchart_fusa_lifecycle),
    ("swimlanes_lr_dispatch", swimlanes_lr_dispatch),
    ("state_autonomy_modes", state_autonomy_modes),
    ("state_estop_channel", state_estop_channel),
    ("bdd_wheel_loader", bdd_wheel_loader),
    ("bdd_safety_system", bdd_safety_system),
    ("ibd_safety_controller", ibd_safety_controller),
    ("req_safety_requirements", req_safety_requirements),
    ("stress_random_dag", stress_random_dag),
    ("control_structure_demo", control_structure_demo),
    ("chain_demo", chain_demo),
]
