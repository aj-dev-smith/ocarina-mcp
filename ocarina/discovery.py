"""The discovery store: which places THIS SAVE LINE has earned (dojo
docs/34, RATIFIED by AJ 2026-08-07 — the discovery grain, ratified
together with docs/30 as one story).

The line, now doctrine: **knowledge in the head is fair; geometry in
the hand must be earned.** The mind may remember from training data
that the sword is behind a crawlspace; the binding between remembered
places and the map's geometric names is a hypothesis until PRESENCE
confirms it. This module is the presence ledger.

Scoping and shape follow SeenKinds exactly: save-line state, persisted
in the save-file repo (`.ocarina/place_discovered.json`), never only in
server memory — the game keeps minimap knowledge in its save file, and
the repo is our save-adjacent state. A fresh line starts dark; a line
that has bled for its map keeps it across sessions and re-entries
(re-presenting on re-entry, never re-fogging — docs/34's grotto note).

Seeding (docs/34 open call 5, ratified as recommended): a repo with no
discovery file but a journal full of `region_entered` fossils gets its
state seeded FROM the journal — the fossil already proves the presence,
and starting dark would fog regions the line has bled for. Runs once,
on first load; the seeded file is then the record.

Grain honesty (the retargeted docs/25 flag): the game's own predicate
reveals a whole ROOM on entry, but scene collision carries no room
table, so v1 discovers at REGION grain by presence — the wire's `room`
field is recorded as an observed region→room binding for the day the
game's own room tables are read. Under-revealing, never over.

Stdlib only.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path


class Discovery:
    """Per-save-line presence ledger: {scene id -> discovered region
    names} plus observed region→room bindings. Mutated only via
    discover(); reads are set membership. Thread-shared between the
    20 Hz fold and resource reads, hence the lock."""

    def __init__(self, path: Path | str, journal: Path | str | None = None,
                 scene_dirs: dict | None = None):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._regions: dict = {}     # scene id (int) -> set of region names
        self._rooms: dict = {}       # region full name -> room (int)
        self.seeded_from_journal = 0
        loaded = self._load()
        if not loaded and journal is not None:
            self.seeded_from_journal = self._seed(Path(journal),
                                                  scene_dirs or {})
            if self.seeded_from_journal:
                self._save()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> bool:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        self._regions = {int(k): set(v)
                         for k, v in (raw.get("regions") or {}).items()}
        self._rooms = {str(k): int(v)
                       for k, v in (raw.get("rooms") or {}).items()}
        return True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"regions": {str(k): sorted(v)
                            for k, v in self._regions.items()},
                "rooms": dict(sorted(self._rooms.items()))}
        self.path.write_text(json.dumps(body, indent=1), encoding="utf-8")

    def _seed(self, journal: Path, scene_dirs: dict) -> int:
        """Mine `region_entered`/`region_discovered` fossils out of the
        mechanical journal. Region names carry their scene DIR as a
        prefix ("ydan:r@30,0,70"); `scene_dirs` (place.SCENE_DIRS) maps
        ids to dirs, so the reverse map recovers the scene id."""
        dir_to_scene = {v: k for k, v in scene_dirs.items()}
        count = 0
        try:
            lines = journal.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
        for line in lines:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") != "place" or ev.get("cue") not in (
                    "region_entered", "region_discovered", "fell"):
                continue
            name = ev.get("region") or ""
            scene = dir_to_scene.get(name.split(":", 1)[0])
            if scene is None:
                continue
            if name not in self._regions.setdefault(scene, set()):
                self._regions[scene].add(name)
                count += 1
        return count

    # -- queries -------------------------------------------------------------

    def known(self, scene: int, region_name: str) -> bool:
        with self._lock:
            return region_name in self._regions.get(scene, ())

    def room_of(self, region_name: str):
        with self._lock:
            return self._rooms.get(region_name)

    # -- mutation ------------------------------------------------------------

    def discover(self, scene: int, region_name: str, room=None) -> bool:
        """Record presence. True exactly when this is the line's FIRST
        time in the region (the region_discovered narration consumes
        it). The room binding is observational plumbing for the future
        room-grain reveal, never presented."""
        with self._lock:
            fresh = region_name not in self._regions.setdefault(scene, set())
            if fresh:
                self._regions[scene].add(region_name)
            if room is not None and room >= 0 and \
                    self._rooms.get(region_name) != room:
                self._rooms[region_name] = int(room)
                fresh_binding = True
            else:
                fresh_binding = False
            if fresh or fresh_binding:
                self._save()
            return fresh
