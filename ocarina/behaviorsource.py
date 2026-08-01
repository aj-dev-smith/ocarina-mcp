"""Load behaviors from the save-file repo's machine/behaviors/ directory.

skillsource.py's contract, renamed (MACHINE.md): behavior modules are any
`*.py` in the directory that defines a module-level `BEHAVIORS` mapping of
`full_name -> Behavior`. Modules are loaded BY PATH — never imported as
save-file packages — and import `ocarina.*` absolutely for the Game API.

One difference from the workshop loader: import errors are COLLECTED, not
raised. reload_machine() returns diagnostics, and a behavior module with a
syntax error must come back as a diagnostic that names the file, not a
stack trace that kills the reload (MACHINE.md validation step 4).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .behavior import Behavior


def load_module(path: Path):
    """Import a single .py file as a module, by path rather than by package."""
    path = Path(path).resolve()
    name = f"_ocarina_behaviors_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load behavior module: {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so dataclasses/pickle can resolve the module.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_behaviors(behaviors_dir: Path | str) -> tuple[dict[str, Behavior], list[str]]:
    """Collect `full_name -> Behavior` from every module in a directory.

    Returns (behaviors, errors). A missing directory yields ({}, []) — the
    machine validator will flag every behavior reference as unresolved,
    which is the diagnostic that actually helps. Modules without a
    BEHAVIORS mapping are skipped (helpers may live alongside behaviors);
    modules that fail to import or that collide on a full_name land in
    `errors` with the file named.
    """
    behaviors_dir = Path(behaviors_dir)
    if not behaviors_dir.is_dir():
        return {}, []

    collected: dict[str, Behavior] = {}
    errors: list[str] = []
    for py in sorted(behaviors_dir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        try:
            found = getattr(load_module(py), "BEHAVIORS", None)
        except Exception as e:
            errors.append(f"{py.name}: import failed: {type(e).__name__}: {e}")
            continue
        if not isinstance(found, dict):
            continue
        for full_name, behavior in found.items():
            if full_name in collected:
                errors.append(
                    f"{py.name}: duplicate behavior {full_name!r}; behavior "
                    f"names must be unique across the behaviors directory")
                continue
            collected[full_name] = behavior
    return collected, errors
