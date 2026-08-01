"""The machine: parse and validate machine.yaml per MACHINE.md.

The machine is source in the save-file repo (`machine/machine.yaml` +
`machine/behaviors/`); this module turns that source into a validated
in-memory Machine or a list of diagnostics — it is the load half of
`reload_machine()`. The transition grammar and its validation are ported
from the workshop's rules.py, arranged into a hierarchy; the guard
whitelist lives in guards.py; behavior loading in behaviorsource.py.

Validation runs MACHINE.md's five steps in order, collecting ALL
diagnostics rather than stopping at the first (errors fail the load;
warnings don't):

1. strict parse (miniyaml; unknown keys rejected at every level)
2. structure (unique names, initial chains, goto targets, leaf/interior)
3. guards (whitelist, state paths vs schema, cooldowns, wake defaults)
4. leaves (behaviors exist and import, unguarded behavior_done in scope)
5. reachability from `initial` (warnings)

One reading of MACHINE.md made explicit here: `do` may be a list, but at
most one of its actions may move or suspend the machine (`goto`, `wake`,
`hold`), and that action must come last — `journal` entries execute
first. Two gotos in one transition would be ambiguous brain surgery.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Optional

from . import MACHINE_FORMAT_VERSION, miniyaml, senses
from .behavior import Behavior
from .behaviorsource import load_behaviors
from .guards import CompiledGuard, GuardError, compile_guard

ROOT = "<root>"

_VERBS = ("goto", "wake", "journal", "hold")
#: Verbs that end an action list: they move the machine, freeze it, or
#: explicitly do nothing. At most one per `do`, last.
_TERMINAL_VERBS = ("goto", "wake", "hold")

_TOP_KEYS = {"version", "initial", "nodes", "transitions"}
_NODE_KEYS = {"initial", "children", "behavior", "transitions"}
_TRANSITION_KEYS = {"name", "on", "where", "when", "do", "default", "cooldown_s"}


@dataclass
class Diagnostic:
    level: str          # "error" | "warning"
    where: str          # node/transition the problem is in
    msg: str

    def as_dict(self) -> dict:
        return {"level": self.level, "where": self.where, "msg": self.msg}

    def __str__(self) -> str:
        return f"{self.level.upper()} [{self.where}] {self.msg}"


@dataclass
class Action:
    verb: str
    arg: str


@dataclass
class Transition:
    name: str
    owner: str                       # node name, or ROOT
    kind: str                        # "event" (on/where) | "state" (when)
    on: Optional[str] = None
    guard: Optional[CompiledGuard] = None
    do: list = dc_field(default_factory=list)
    default: Optional[Action] = None
    cooldown_s: float = 0.0

    @property
    def wakes(self) -> bool:
        return any(a.verb == "wake" for a in self.do)


@dataclass
class Node:
    name: str
    parent: Optional[str]            # node name, or None for top level
    initial: Optional[str] = None    # interior nodes
    behavior: Optional[str] = None   # leaf nodes (full behavior name)
    children: list = dc_field(default_factory=list)
    transitions: list = dc_field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.behavior is not None


@dataclass
class Machine:
    initial: str
    nodes: dict                      # name -> Node
    root_transitions: list
    behaviors: dict                  # full_name -> Behavior
    source_hash: str

    def ancestors(self, name: str) -> list:
        """Ancestor node names, innermost first (excludes `name` itself)."""
        out = []
        node = self.nodes.get(name)
        while node is not None and node.parent is not None:
            out.append(node.parent)
            node = self.nodes.get(node.parent)
        return out

    def scope(self, name: str) -> list:
        """Transitions in dispatch order for a current node: its own first,
        then each ancestor's, root last — innermost-out, file order within
        a node (MACHINE.md dispatch semantics)."""
        out = list(self.nodes[name].transitions)
        for anc in self.ancestors(name):
            out.extend(self.nodes[anc].transitions)
        out.extend(self.root_transitions)
        return out

    def descend(self, name: str) -> list:
        """Nodes entered by `goto name`, outermost first, ending at a leaf:
        `name`'s un-entered ancestors are the caller's business; this is
        the initial chain downward."""
        chain = [name]
        node = self.nodes[name]
        while not node.is_leaf:
            node = self.nodes[node.initial]
            chain.append(node.name)
        return chain


# -- loading -----------------------------------------------------------------

def load_machine(repo: Path | str):
    """(Machine | None, diagnostics). Machine is None iff any errors."""
    repo = Path(repo)
    yaml_path = repo / "machine" / "machine.yaml"
    behaviors_dir = repo / "machine" / "behaviors"
    diags: list[Diagnostic] = []

    # Step 1: strict parse.
    try:
        doc = miniyaml.load_path(yaml_path)
    except miniyaml.MiniYamlError as e:
        return None, [Diagnostic("error", str(yaml_path), str(e))]
    if not isinstance(doc, dict):
        return None, [Diagnostic("error", str(yaml_path), "top level must be a map")]

    unknown = set(doc) - _TOP_KEYS
    if unknown:
        diags.append(Diagnostic("error", "machine.yaml",
                                f"unknown top-level keys {sorted(unknown)}"))
    if doc.get("version") != MACHINE_FORMAT_VERSION:
        diags.append(Diagnostic(
            "error", "machine.yaml",
            f"version must be {MACHINE_FORMAT_VERSION}, got {doc.get('version')!r}"))

    nodes: dict[str, Node] = {}
    _parse_nodes(doc.get("nodes"), None, nodes, diags)
    root_transitions = _parse_transitions(
        doc.get("transitions"), ROOT, diags, seen_names={
            t.name for n in nodes.values() for t in n.transitions})

    initial = doc.get("initial")
    if not isinstance(initial, str) or not initial:
        diags.append(Diagnostic("error", "machine.yaml", "missing 'initial' node"))
        initial = ""
    elif nodes and initial not in nodes:
        diags.append(Diagnostic("error", "machine.yaml",
                                f"initial node {initial!r} does not exist"))

    # Step 2 (continued): structure checks over the parsed tree.
    _check_structure(nodes, root_transitions, diags)

    # Step 3 (continued): the transition-level guard rules are enforced at
    # parse time; state paths were collected per-guard and checked there.

    # Step 4: leaves and behaviors.
    behaviors, behavior_errors = load_behaviors(behaviors_dir)
    for err in behavior_errors:
        diags.append(Diagnostic("error", "behaviors", err))
    _check_leaves(nodes, root_transitions, behaviors, diags)

    # Step 5: reachability (warnings).
    if initial in nodes:
        _check_reachability(nodes, root_transitions, initial, diags)

    if any(d.level == "error" for d in diags):
        return None, diags

    return Machine(initial=initial, nodes=nodes,
                   root_transitions=root_transitions, behaviors=behaviors,
                   source_hash=_source_hash(yaml_path, behaviors_dir)), diags


def _source_hash(yaml_path: Path, behaviors_dir: Path) -> str:
    h = hashlib.sha256()
    h.update(yaml_path.read_bytes())
    if behaviors_dir.is_dir():
        for py in sorted(behaviors_dir.glob("*.py")):
            h.update(py.name.encode())
            h.update(py.read_bytes())
    return h.hexdigest()[:16]


# -- parsing -----------------------------------------------------------------

def _parse_nodes(raw, parent: Optional[str], nodes: dict, diags: list) -> None:
    if raw is None:
        if parent is None:
            diags.append(Diagnostic("error", "machine.yaml", "no 'nodes' declared"))
        return
    if not isinstance(raw, dict):
        diags.append(Diagnostic("error", parent or "machine.yaml",
                                "'nodes'/'children' must be a map of node name -> node"))
        return
    for name, body in raw.items():
        if name in nodes:
            # Node names are unique MACHINE-WIDE (nesting is scope, not
            # namespace): goto and force_state take the bare name.
            diags.append(Diagnostic("error", name, "duplicate node name"))
            continue
        if not isinstance(body, dict):
            diags.append(Diagnostic("error", name, "node must be a map"))
            continue
        unknown = set(body) - _NODE_KEYS
        if unknown:
            diags.append(Diagnostic("error", name, f"unknown keys {sorted(unknown)}"))
        node = Node(name=name, parent=parent,
                    initial=body.get("initial"),
                    behavior=body.get("behavior"))
        node.transitions = _parse_transitions(
            body.get("transitions"), name, diags,
            seen_names={t.name for n in nodes.values() for t in n.transitions})
        nodes[name] = node
        children = body.get("children")
        if children is not None:
            before = set(nodes)
            _parse_nodes(children, name, nodes, diags)
            node.children = [n for n in nodes if n not in before
                             and nodes[n].parent == name]


def _parse_transitions(raw, owner: str, diags: list, seen_names: set) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list):
        diags.append(Diagnostic("error", owner, "'transitions' must be a list"))
        return []
    out = []
    for item in raw:
        t = _parse_transition(item, owner, diags, seen_names)
        if t is not None:
            out.append(t)
    return out


def _parse_transition(raw, owner: str, diags: list, seen_names: set):
    if not isinstance(raw, dict):
        diags.append(Diagnostic("error", owner, f"transition must be a map, got {raw!r}"))
        return None
    name = raw.get("name")
    if not name or not isinstance(name, str):
        diags.append(Diagnostic("error", owner, f"transition missing 'name': {raw!r}"))
        return None
    where_id = f"{owner}/{name}"

    def err(msg):
        diags.append(Diagnostic("error", where_id, msg))

    unknown = set(raw) - _TRANSITION_KEYS
    if unknown:
        err(f"unknown keys {sorted(unknown)}")
    if name in seen_names:
        err("duplicate transition name (names are unique machine-wide)")
    seen_names.add(name)

    # Two kinds, one shape: `on` + optional `where`, XOR `when`.
    on, where_src, when_src = raw.get("on"), raw.get("where"), raw.get("when")
    if when_src is not None and (on is not None or where_src is not None):
        err("a transition has 'on' (+ optional 'where') OR 'when' — never both")
        return None
    if when_src is None and on is None:
        err("a transition needs 'on' or 'when'")
        return None

    kind = "state" if when_src is not None else "event"
    guard = None
    guard_src = when_src if kind == "state" else where_src
    if guard_src is not None:
        try:
            guard = compile_guard(guard_src, where_id)
        except GuardError as e:
            err(str(e))
            guard = None
        else:
            if kind == "state" and guard.event_names:
                err(f"'when' guards read only state.* paths; bare names "
                    f"{sorted(guard.event_names)} have no event to resolve against")
            for path in guard.state_paths:
                problem = senses.check_path(path)
                if problem:
                    err(f"guard {guard.src!r}: {problem}")
    if kind == "event" and (not isinstance(on, str) or not on):
        err("'on' must be an event name")
        on = None

    do_raw = raw.get("do")
    if isinstance(do_raw, str):
        do_raw = [do_raw]
    actions = []
    if not isinstance(do_raw, list) or not do_raw:
        err("'do' must be an action or a non-empty list of actions")
    else:
        for a in do_raw:
            action = _parse_action(a, where_id, diags)
            if action is not None:
                actions.append(action)
        terminals = [a for a in actions if a.verb in _TERMINAL_VERBS]
        if len(terminals) > 1:
            err(f"at most one of {_TERMINAL_VERBS} per 'do', got "
                f"{[a.verb for a in terminals]}")
        elif terminals and actions and actions[-1].verb not in _TERMINAL_VERBS:
            err(f"the {terminals[0].verb!r} action must come last in 'do'")

    if kind == "state" and any(a.verb == "journal" for a in actions):
        err("'journal' templates fields from the event; it is event-triggered "
            "only (MACHINE.md action verbs)")

    cooldown = raw.get("cooldown_s", 0.0)
    if not isinstance(cooldown, (int, float)) or cooldown < 0:
        err("cooldown_s must be a non-negative number")
        cooldown = 0.0

    default_raw = raw.get("default")
    default = None
    if default_raw is not None:
        default = _parse_action(default_raw, where_id, diags)
        if default is not None and default.verb == "wake":
            err("'default' cannot be another wake")
    wakes = any(a.verb == "wake" for a in actions)
    if wakes and default is None:
        err("every transition that wakes must declare a non-wake 'default' — "
            "what to do when no usable answer arrives (MACHINE.md; a frozen "
            "game waiting on a mind that never answers is the failure this kills)")
    if not wakes and default is not None:
        err("'default' only means something on a transition that wakes")

    return Transition(name=name, owner=owner, kind=kind, on=on, guard=guard,
                      do=actions, default=default, cooldown_s=float(cooldown))


def _parse_action(raw, where_id: str, diags: list):
    if not isinstance(raw, str) or not raw.strip():
        diags.append(Diagnostic("error", where_id,
                                f"actions are strings like 'goto kill_baba', got {raw!r}"))
        return None
    verb, _, arg = raw.strip().partition(" ")
    if verb not in _VERBS:
        diags.append(Diagnostic("error", where_id,
                                f"unknown action verb {verb!r} (known: {', '.join(_VERBS)})"))
        return None
    if not arg.strip():
        diags.append(Diagnostic("error", where_id, f"action {verb!r} needs an argument"))
        return None
    return Action(verb=verb, arg=arg.strip())


# -- structure ---------------------------------------------------------------

def _check_structure(nodes: dict, root_transitions: list, diags: list) -> None:
    for node in nodes.values():
        if node.children and node.behavior:
            diags.append(Diagnostic("error", node.name,
                                    "a node has 'children' or 'behavior', never both"))
        elif not node.children and not node.behavior:
            diags.append(Diagnostic("error", node.name,
                                    "a node needs 'children' (interior) or 'behavior' (leaf)"))
        if node.children:
            if not node.initial:
                diags.append(Diagnostic("error", node.name,
                                        "interior node needs 'initial'"))
            elif node.initial not in node.children:
                diags.append(Diagnostic(
                    "error", node.name,
                    f"'initial' {node.initial!r} is not one of its children "
                    f"{node.children}"))
        elif node.initial:
            diags.append(Diagnostic("error", node.name,
                                    "leaf node cannot have 'initial'"))

    for t in _all_transitions(nodes, root_transitions):
        for action in list(t.do) + ([t.default] if t.default else []):
            if action.verb == "goto" and action.arg not in nodes:
                diags.append(Diagnostic(
                    "error", f"{t.owner}/{t.name}",
                    f"goto target {action.arg!r} does not exist"))


def _all_transitions(nodes: dict, root_transitions: list):
    for node in nodes.values():
        yield from node.transitions
    yield from root_transitions


# -- leaves ------------------------------------------------------------------

def _check_leaves(nodes: dict, root_transitions: list,
                  behaviors: dict, diags: list) -> None:
    for node in nodes.values():
        if not node.is_leaf:
            continue
        if node.behavior not in behaviors:
            known = ", ".join(sorted(behaviors)) or "(none)"
            diags.append(Diagnostic(
                "error", node.name,
                f"behavior {node.behavior!r} not in the loaded corpus "
                f"(known: {known}) — a missing behavior is a load error, "
                f"not a runtime surprise"))
        # Every leaf's scope chain must contain an unguarded behavior_done
        # transition: a machine with nothing to do after a body returns is
        # a load error, never a silent stall (MACHINE.md, leaf completion).
        scope: list = list(node.transitions)
        parent = node.parent
        while parent is not None:
            scope.extend(nodes[parent].transitions)
            parent = nodes[parent].parent
        scope.extend(root_transitions)
        if not any(t.kind == "event" and t.on == "behavior_done"
                   and t.guard is None for t in scope):
            diags.append(Diagnostic(
                "error", node.name,
                "no unguarded 'on: behavior_done' transition in this leaf's "
                "scope chain — the machine must always know what to do when "
                "the body returns (guarded ones may precede it)"))


# -- reachability ------------------------------------------------------------

def _check_reachability(nodes: dict, root_transitions: list,
                        initial: str, diags: list) -> None:
    machine = Machine(initial=initial, nodes=nodes,
                      root_transitions=root_transitions, behaviors={},
                      source_hash="")

    def entered_by_goto(target: str) -> set:
        # Entering a node activates its ancestors' scopes and descends to
        # a leaf via initial chains.
        out = set(machine.ancestors(target))
        try:
            out.update(machine.descend(target))
        except KeyError:
            out.add(target)   # structurally broken; already an error
        return out

    reachable = entered_by_goto(initial)
    frontier = set(reachable)
    while frontier:
        current = frontier.pop()
        for t in machine.scope(current) if current in nodes else []:
            for action in list(t.do) + ([t.default] if t.default else []):
                if action.verb == "goto" and action.arg in nodes:
                    newly = entered_by_goto(action.arg) - reachable
                    reachable.update(newly)
                    frontier.update(newly)

    for name in nodes:
        if name not in reachable:
            diags.append(Diagnostic(
                "warning", name,
                "unreachable from 'initial' via transitions (dead code, not "
                "necessarily wrong — force_state can still reach it)"))
