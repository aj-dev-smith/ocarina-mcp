"""ocarina — the instrument you play Hyrule through.

A stdio MCP server exposing Ocarina of Time (via Ship of Harkinian) as a
fair, bounded tool surface. The contract is SURFACE.md + MACHINE.md
(BLESSED, AJ 2026-08-01); this package implements them exactly.

Internals are ported from the OoT Bench workshop (../oot-dojo), where they
were validated against the real game — see MACHINE.md "Provenance".
"""

#: Server version. Semver with benchmark meaning (SURFACE.md, Versioning):
#: a diff touching SURFACE.md or MACHINE.md is a major bump, full stop.
#: 0.x = building toward the first complete implementation of the blessed
#: contract; 1.0.0 is "the surface is fully implemented as blessed".
#: 0.2.0: the MACHINE.md clarification pass (2026-08-01) — the six
#: post-first-light rulings ratified into the contract, and `on:` event
#: names now validated at load. In 0.x, the minor digit carries the
#: major-bump meaning.
#: 0.2.1: two guard-layer bugfixes toward the ratified absence contract —
#: `not in` no longer fires on an absent entity, and a guard that raises
#: (e.g. ZeroDivisionError) warns instead of killing the 20 Hz loop.
OCARINA_VERSION = "0.2.1"

#: The machine's on-disk format version (machine.yaml `version:` key).
MACHINE_FORMAT_VERSION = 1
