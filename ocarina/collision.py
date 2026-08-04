"""Parse a SoH O2R CollisionHeader resource into plain Python structures.

PORTED 2026-08-03 from `lab/navgraph/o2r_collision.py` (the fifth-flight
place-sense lab; dojo docs/24-25, RATIFIED by AJ 2026-08-03). Diff against
the lab original: this header and the removed CLI harness only. Layout is
transcribed from Shipwright source (the authority on this format):
  - soh/soh/resource/importer/CollisionHeaderFactory.cpp (binary V0 reader)
  - OTRExporter/OTRExporter/CollisionExporter.cpp (writer: surface words go
    data[1] first, then data[0])
  - ZAPDTR/ZAPD/ZSurfaceType.cpp (data[0] = first ROM word, the nav word)
  - soh/src/code/z_bgcheck.c (wall type -> wall flags table D_80119D90)

Stdlib only.
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field

RESOURCE_HEADER_SIZE = 0x40  # LUS binary resource header ('LOCO' fourcc at +4)

# z_bgcheck.c D_80119D90: wall *type* (data0 >> 21 & 0x1F) -> wall *flags*
WALL_FLAG_TABLE = [0, 1, 3, 5, 8, 16, 32, 64] + [0] * 24
WALL_FLAG_LADDER = 1 << 1
WALL_FLAG_LADDER_TOP = 1 << 2
WALL_FLAG_VINE = 1 << 3
WALL_FLAG_CRAWLSPACE = (1 << 4) | (1 << 5)


@dataclass
class Poly:
    index: int
    type: int          # index into surface_types
    va: int            # vertex indices, flag bits already masked off
    vb: int
    vc: int
    normal: tuple      # unit normal, floats
    dist: int          # plane d in s16 world units

    @property
    def ny(self):
        return self.normal[1]


@dataclass
class SurfaceType:
    data0: int  # nav word: bgCam/exit/floorType/wallType bits
    data1: int  # material word

    @property
    def wall_type(self):
        return (self.data0 >> 21) & 0x1F

    @property
    def wall_flags(self):
        return WALL_FLAG_TABLE[self.wall_type]

    @property
    def is_ladder(self):
        return bool(self.wall_flags & WALL_FLAG_LADDER)

    @property
    def is_vine(self):
        return bool(self.wall_flags & WALL_FLAG_VINE)

    @property
    def is_crawlspace(self):
        return bool(self.wall_flags & WALL_FLAG_CRAWLSPACE)

    @property
    def floor_type(self):
        return (self.data0 >> 13) & 0x1F

    @property
    def floor_property(self):
        return (self.data0 >> 26) & 0xF

    @property
    def exit_index(self):
        return (self.data0 >> 8) & 0x1F


@dataclass
class WaterBox:
    x_min: int
    y_surface: int
    z_min: int
    x_length: int
    z_length: int
    properties: int


@dataclass
class CollisionMesh:
    min_bounds: tuple
    max_bounds: tuple
    vertices: list = field(default_factory=list)      # [(x, y, z) s16]
    polys: list = field(default_factory=list)         # [Poly]
    surface_types: list = field(default_factory=list)  # [SurfaceType]
    water_boxes: list = field(default_factory=list)   # [WaterBox]

    def surface(self, poly: Poly) -> SurfaceType:
        return self.surface_types[poly.type]


class _Reader:
    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.off = offset

    def _take(self, fmt: str):
        vals = struct.unpack_from(fmt, self.data, self.off)
        self.off += struct.calcsize(fmt)
        return vals

    def s16(self):
        return self._take("<h")[0]

    def u16(self):
        return self._take("<H")[0]

    def s32(self):
        return self._take("<i")[0]

    def u32(self):
        return self._take("<I")[0]


def parse_collision(payload: bytes) -> CollisionMesh:
    """Parse the resource bytes (header included) per CollisionHeaderFactory."""
    magic = payload[4:8]
    if magic != b"LOCO":
        raise ValueError(f"not a CollisionHeader resource (fourcc {magic!r})")
    r = _Reader(payload, RESOURCE_HEADER_SIZE)

    min_bounds = (r.s16(), r.s16(), r.s16())
    max_bounds = (r.s16(), r.s16(), r.s16())

    mesh = CollisionMesh(min_bounds=min_bounds, max_bounds=max_bounds)

    for _ in range(r.s32()):
        mesh.vertices.append((r.s16(), r.s16(), r.s16()))

    num_polys = r.u32()
    for i in range(num_polys):
        ptype = r.u16()
        flags_via = r.u16()
        flags_vib = r.u16()
        vic = r.u16()
        # normals/dist are written as u16 but are semantically s16
        nx = struct.unpack("<h", struct.pack("<H", r.u16()))[0]
        ny = struct.unpack("<h", struct.pack("<H", r.u16()))[0]
        nz = struct.unpack("<h", struct.pack("<H", r.u16()))[0]
        dist = struct.unpack("<h", struct.pack("<H", r.u16()))[0]
        mesh.polys.append(Poly(
            index=i,
            type=ptype,
            va=flags_via & 0x1FFF,
            vb=flags_vib & 0x1FFF,
            vc=vic & 0x1FFF,
            normal=(nx / 32767.0, ny / 32767.0, nz / 32767.0),
            dist=dist,
        ))

    for _ in range(r.u32()):
        data1 = r.u32()  # exporter writes data[1] first
        data0 = r.u32()
        mesh.surface_types.append(SurfaceType(data0=data0, data1=data1))

    for _ in range(r.u32()):  # camData: stype, numCameras, posDataIdx
        r.u16(), r.s16(), r.s32()

    for _ in range(r.s32()):  # camPosData triplets
        r.s16(), r.s16(), r.s16()

    for _ in range(r.s32()):
        mesh.water_boxes.append(WaterBox(
            x_min=r.s16(), y_surface=r.s16(), z_min=r.s16(),
            x_length=r.s16(), z_length=r.s16(), properties=r.s32(),
        ))

    if r.off != len(payload):
        raise ValueError(f"trailing bytes: consumed {r.off} of {len(payload)}")
    return mesh


def load_from_o2r(o2r_path: str, entry: str) -> CollisionMesh:
    with zipfile.ZipFile(o2r_path) as z:
        return parse_collision(z.read(entry))
