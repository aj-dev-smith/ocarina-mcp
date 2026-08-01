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
OCARINA_VERSION = "0.1.0"

#: The machine's on-disk format version (machine.yaml `version:` key).
MACHINE_FORMAT_VERSION = 1
