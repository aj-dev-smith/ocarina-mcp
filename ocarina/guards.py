"""The guard language: `where` and `when` expressions.

Ported from the workshop's rules.py `compile_where` (the validated AST
whitelist: comparisons, boolean ops, arithmetic, literals, tuples/lists,
names — no calls, no subscripts) with the ONE extension MACHINE.md
blesses: **attribute chains rooted at `state`**
(`state.nearest_enemy.dist`). Attribute access anywhere else remains
rejected.

The guard vocabulary IS the sense vocabulary: `state.*` paths resolve
into the curated digest (senses.py), never raw values — "presented, not
computed" enforced at the machine layer. Every `state.*` path is checked
against the state schema at load time (machine.py validation step 3);
bare names resolve to the triggering event's fields and can only be
checked at fire time (a `where` naming a field its event doesn't carry
does not fire, and the miss is journaled once per (transition, field) —
ported behavior).

Absence semantics (this module's one design decision, documented because
MACHINE.md doesn't spec it): a `state.*` path whose entity is legitimately
absent at runtime — `state.nearest_enemy.dist` with no enemy in view —
resolves to the ABSENT sentinel, which is falsy and compares False in
EVERY comparison including `!=`. A guard over an absent entity therefore
never fires, rather than erroring or accidentally matching. Write
`state.nearest_enemy and state.nearest_enemy.kind != 'deku_baba'` to mean
"there is an enemy and it isn't a baba".
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


class GuardError(ValueError):
    pass


_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
    ast.GtE, ast.In, ast.NotIn, ast.BinOp, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.FloorDiv, ast.Mod, ast.Name, ast.Load, ast.Constant,
    ast.Tuple, ast.List, ast.Attribute,
)


@dataclass
class CompiledGuard:
    src: str
    code: object = field(repr=False)
    #: Dotted paths under `state` used by the expression, as tuples of
    #: parts ('nearest_enemy', 'dist'). Checked against the schema at load.
    state_paths: set = field(default_factory=set)
    #: Bare names — event fields for `where`; a load error for `when`.
    event_names: set = field(default_factory=set)


def _attr_chain(node: ast.Attribute):
    """('nearest_enemy', 'dist') if the chain roots at Name('state'), else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name) and node.id == "state":
        return tuple(reversed(parts))
    return None


def compile_guard(src: str, owner: str) -> CompiledGuard:
    """Compile a guard expression through the whitelist. Raises GuardError."""
    if not isinstance(src, str) or not src.strip():
        raise GuardError(f"{owner}: guard must be a non-empty string expression")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise GuardError(f"{owner}: bad guard expression {src!r}: {e}") from e

    # Attribute nodes that are the .value of another Attribute are interior
    # to a chain; only the outermost node names a full path.
    inner = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}

    state_paths: set = set()
    event_names: set = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise GuardError(
                f"{owner}: {type(node).__name__} not allowed in guard {src!r} "
                f"(comparisons/bool/arith/literals/names/state.* only)")
        if isinstance(node, ast.Attribute):
            chain = _attr_chain(node)
            if chain is None:
                raise GuardError(
                    f"{owner}: attribute access in guard {src!r} must be a "
                    f"chain rooted at 'state' (e.g. state.nearest_enemy.dist)")
            if id(node) not in inner:
                state_paths.add(chain)
        elif isinstance(node, ast.Name) and node.id != "state":
            event_names.add(node.id)

    code = compile(tree, f"<guard:{owner}>", "eval")
    return CompiledGuard(src=src, code=code, state_paths=state_paths,
                         event_names=event_names)


# -- runtime resolution ------------------------------------------------------

class _Absent:
    """Falsy, compares False in every comparison, absorbs arithmetic and
    attribute access. See the module docstring for why."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "<absent>"

    def __bool__(self):
        return False

    def __getattr__(self, name):
        return self

    def __hash__(self):
        return 0

    def __eq__(self, other): return False          # noqa: E704
    def __ne__(self, other): return False          # noqa: E704
    def __lt__(self, other): return False          # noqa: E704
    def __le__(self, other): return False          # noqa: E704
    def __gt__(self, other): return False          # noqa: E704
    def __ge__(self, other): return False          # noqa: E704
    def __contains__(self, item): return False     # noqa: E704

    def _absorb(self, *_):
        return self
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _absorb
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = _absorb
    __mod__ = __rmod__ = __neg__ = _absorb


ABSENT = _Absent()


class StateView:
    """Attribute-chain access over the curated digest dict.

    Missing keys and None values resolve to ABSENT so that guards over
    legitimately-absent entities evaluate False instead of raising. Paths
    are schema-checked at load time, so a missing key here means "absent
    now", never "typo".
    """

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data if isinstance(data, dict) else {})

    def __getattr__(self, name):
        value = self._data.get(name)
        if value is None:
            return ABSENT
        if isinstance(value, dict):
            return StateView(value)
        return value

    def __bool__(self):
        return bool(self._data)

    def __repr__(self):
        return f"StateView({self._data!r})"


def eval_guard(guard: CompiledGuard, event: dict = None, state: dict = None):
    """-> (fired: bool, warning: str | None).

    A warning means the guard could not be evaluated as written — a field
    the event doesn't carry, or a type mismatch — and the guard did NOT
    fire. The caller journals it once per (transition, warning) so a typo
    is visible instead of producing a transition that looks armed and
    never triggers (ported rules.py behavior).
    """
    env = dict(event or {})
    env["state"] = StateView(state or {})
    try:
        return bool(eval(guard.code, {"__builtins__": {}}, env)), None
    except NameError as e:
        missing = getattr(e, "name", str(e))
        return False, f"references {missing!r} which this event does not carry"
    except TypeError as e:
        return False, f"type error evaluating {guard.src!r}: {e}"
