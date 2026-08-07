"""Wire protocol constants for talking to Ship of Harkinian's Sail + DojoLink.

Ported verbatim from the workshop (oot-dojo ootdojo/protocol.py, validated
against the real game 2026-07-29/31).

Transport: the game is the TCP *client*; it connects out to us (default
127.0.0.1:43384). Messages both ways are JSON documents delimited by a
null byte (\\0). Requests carry an "id" and a "type"; responses echo the id
with type == "result". DojoLink events arrive unsolicited with
type == "agent_event".
"""

DEFAULT_PORT = 43384

# N64 controller button masks (libultraship/include/libultraship/libultra/controller.h)
BTN_CRIGHT = 0x0001
BTN_CLEFT = 0x0002
BTN_CDOWN = 0x0004
BTN_CUP = 0x0008
BTN_R = 0x0010
BTN_L = 0x0020
BTN_DRIGHT = 0x0100
BTN_DLEFT = 0x0200
BTN_DDOWN = 0x0400
BTN_DUP = 0x0800
BTN_START = 0x1000
BTN_Z = 0x2000
BTN_B = 0x4000
BTN_A = 0x8000

BUTTON_NAMES = {
    "A": BTN_A, "B": BTN_B, "Z": BTN_Z, "START": BTN_START,
    "R": BTN_R, "L": BTN_L,
    "C_UP": BTN_CUP, "C_DOWN": BTN_CDOWN, "C_LEFT": BTN_CLEFT, "C_RIGHT": BTN_CRIGHT,
    "D_UP": BTN_DUP, "D_DOWN": BTN_DDOWN, "D_LEFT": BTN_DLEFT, "D_RIGHT": BTN_DRIGHT,
}

# Actor IDs (soh/include/tables/actor_table.h)
ACTOR_EN_DEKUBABA = 0x0055   # Deku Baba
ACTOR_EN_KAREBABA = 0x00C7   # Withered Deku Baba
# EN_FIREFLY is every Keese: params select fly/perch x normal/fire, plus ice
# (KeeseType in z_en_firefly.h). One actor id, five behaviours — so a skill
# that targets "a Keese" must read params, not just the id.
ACTOR_EN_FIREFLY = 0x0013    # Keese (all variants)
# EN_ST is the ceiling Skulltula; params 0=normal, 1=big (x1.4), 2=invisible.
# NOT to be confused with EN_SW (Skullwalltula), a different actor that crawls
# on walls and shares the room. fixtures/dev-run/docs/14-skulltula.md
ACTOR_EN_ST = 0x0037         # Skulltula
ACTOR_EN_SW = 0x0095         # Skullwalltula (wall crawler — different enemy)
# Two actors whose PARAMS carry the identity a player reads off the sprite,
# so naming them needs the census's params field, not the id alone (0.9.0):
# En_Item00's params are the Item00Type (masked to 0xFF in its own Init,
# z_en_item00.c:362), and a shop item's params are its shop row (SI_*).
ACTOR_EN_GIRLA = 0x0004      # the item standing on a shop shelf
ACTOR_EN_ITEM00 = 0x0015     # the collectible drops (rupees, hearts, ...)

# Actor categories (soh/include/z64actor.h)
ACTORCAT_SWITCH = 0
ACTORCAT_BG = 1
ACTORCAT_PLAYER = 2
ACTORCAT_EXPLOSIVE = 3
ACTORCAT_NPC = 4
ACTORCAT_ENEMY = 5
ACTORCAT_PROP = 6
ACTORCAT_ITEMACTION = 7
ACTORCAT_MISC = 8
ACTORCAT_BOSS = 9
ACTORCAT_DOOR = 10
ACTORCAT_CHEST = 11

# Player state flags (soh/include/z64player.h, stateFlags1)
PLAYER_STATE1_INPUT_DISABLED = 1 << 5
PLAYER_STATE1_TALKING = 1 << 6
PLAYER_STATE1_DEAD = 1 << 7
PLAYER_STATE1_GETTING_ITEM = 1 << 10
PLAYER_STATE1_HOSTILE_LOCK_ON = 1 << 4
PLAYER_STATE1_IN_CUTSCENE = 1 << 29

# Climbing. These three are the whole observable vocabulary of a vertical
# route, and they are EXACT rather than inferred (CLAUDE.md "Some actor states
# can be detected EXACTLY"): the game sets CLIMBING_LADDER the same frame it
# accepts the wall grab (z_player.c:7563) and clears it the frame it hands off
# to the ledge mount, which sets CLIMBING_LEDGE (z_player.c:4972). So "did the
# grab take" and "did we top out" are equality tests on a bitmask, not
# thresholds on a position.
PLAYER_STATE1_HANGING_OFF_LEDGE = 1 << 13
PLAYER_STATE1_CLIMBING_LEDGE = 1 << 14
PLAYER_STATE1_CLIMBING_LADDER = 1 << 21   # vines AND ladders, both
PLAYER_STATE1_ON_A_WALL = (PLAYER_STATE1_CLIMBING_LADDER | PLAYER_STATE1_CLIMBING_LEDGE
                           | PLAYER_STATE1_HANGING_OFF_LEDGE)

# stateFlags2. DO_ACTION_CLIMB is the game offering the climb — it is set when
# Link is against a climbable surface and is what the HUD "Climb" prompt reads.
PLAYER_STATE2_DO_ACTION_GRAB = 1 << 0
PLAYER_STATE2_DO_ACTION_CLIMB = 1 << 2

# Any of these means Link will ignore the pad. A savestate captured while one
# is set replays the whole lock on every load — entering the Deku Tree holds
# IN_CUTSCENE for ~5.5s, which would be dead time at the head of every trial.
PLAYER_UNCONTROLLABLE = (PLAYER_STATE1_IN_CUTSCENE | PLAYER_STATE1_INPUT_DISABLED
                         | PLAYER_STATE1_TALKING | PLAYER_STATE1_GETTING_ITEM)

# One game logic tick, in seconds (R_UPDATE_RATE = 3 -> 20 Hz)
TICK = 1.0 / 20.0


def buttons_mask(*names: str) -> int:
    mask = 0
    for name in names:
        mask |= BUTTON_NAMES[name.upper()]
    return mask
