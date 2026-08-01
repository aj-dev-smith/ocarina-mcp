import unittest

from ocarina import miniyaml
from ocarina.miniyaml import MiniYamlError


class TestMiniYaml(unittest.TestCase):
    def test_nested(self):
        doc = miniyaml.load(
            "version: 1\n"
            "nodes:\n"
            "  explore:\n"
            "    initial: walk\n"
            "    transitions:\n"
            "      - name: t1\n"
            "        on: spawn\n"
            "        cooldown_s: 1.5\n"
            "      - name: t2\n"
            "        on: despawn\n")
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["nodes"]["explore"]["initial"], "walk")
        ts = doc["nodes"]["explore"]["transitions"]
        self.assertEqual([t["name"] for t in ts], ["t1", "t2"])
        self.assertEqual(ts[0]["cooldown_s"], 1.5)

    def test_scalars(self):
        doc = miniyaml.load("a: 0x0055\nb: true\nc: null\nd: 'q s'\ne: bare words\n")
        self.assertEqual(doc, {"a": 0x55, "b": True, "c": None,
                               "d": "q s", "e": "bare words"})

    def test_rejects(self):
        for bad in ("a: 1\na: 2\n",          # duplicate key
                    "\ta: 1\n",              # tab
                    "a: [1, 2]\n",           # flow
                    "a: &anchor\n"):         # anchor
            with self.assertRaises(MiniYamlError):
                miniyaml.load(bad)

    def test_continuation_folds_scalar(self):
        # MACHINE.md's own example wraps a `when:` guard across lines.
        doc = miniyaml.load(
            "t:\n"
            "  when: state.nearest_enemy.kind == 'deku_baba'\n"
            "        and state.nearest_enemy.dist <= 800\n"
            "  do: goto kill_baba\n")
        self.assertEqual(doc["t"]["when"],
                         "state.nearest_enemy.kind == 'deku_baba' "
                         "and state.nearest_enemy.dist <= 800")
        self.assertEqual(doc["t"]["do"], "goto kill_baba")

    def test_continuation_after_non_string_rejected(self):
        # Folding only extends STRING scalars; a stray deeper line after an
        # int must error with a line number, never guess (docs/08).
        with self.assertRaises(MiniYamlError) as ctx:
            miniyaml.load("a:\n  key: 30\n    stray continuation\n")
        self.assertEqual(ctx.exception.lineno, 3)

    def test_continuation_does_not_eat_nested_blocks(self):
        doc = miniyaml.load(
            "a: scalar\n"
            "b:\n"
            "  c: 1\n")
        self.assertEqual(doc, {"a": "scalar", "b": {"c": 1}})


if __name__ == "__main__":
    unittest.main()
