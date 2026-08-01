import unittest

from ocarina.guards import (ABSENT, GuardError, StateView, compile_guard,
                            eval_guard)


class TestCompile(unittest.TestCase):
    def test_collects_state_paths_and_event_names(self):
        g = compile_guard("state.nearest_enemy.kind == 'deku_baba' "
                          "and state.nearest_enemy.dist <= 800 and novel == 1", "t")
        self.assertEqual(g.state_paths, {("nearest_enemy", "kind"),
                                         ("nearest_enemy", "dist")})
        self.assertEqual(g.event_names, {"novel"})

    def test_whitelist_rejections(self):
        for bad in ("open('/etc/passwd')",       # call
                    "state.actors[0]",           # subscript
                    "event.field",               # attribute not rooted at state
                    "x.y == 1",                  # ditto
                    "__import__",                # fine name-wise but... call-less name is allowed
                    ):
            if bad == "__import__":
                continue    # names alone are allowed; nothing to call them with
            with self.assertRaises(GuardError, msg=bad):
                compile_guard(bad, "t")

    def test_lambda_and_comprehension_rejected(self):
        for bad in ("(lambda: 1)()", "[x for x in (1,2)]"):
            with self.assertRaises(GuardError):
                compile_guard(bad, "t")


class TestEval(unittest.TestCase):
    def test_event_fields(self):
        g = compile_guard("hearts_after <= 3 and hearts_after > 0", "t")
        ok, warn = eval_guard(g, {"hearts_after": 2.5}, {})
        self.assertTrue(ok)
        self.assertIsNone(warn)

    def test_missing_event_field_warns_no_fire(self):
        g = compile_guard("nope == 1", "t")
        ok, warn = eval_guard(g, {"other": 1}, {})
        self.assertFalse(ok)
        self.assertIn("nope", warn)

    def test_state_paths(self):
        g = compile_guard("state.nearest_enemy.dist <= 800", "t")
        state = {"nearest_enemy": {"kind": "deku_baba", "dist": 300.0}}
        self.assertEqual(eval_guard(g, {}, state), (True, None))
        state["nearest_enemy"]["dist"] = 900.0
        self.assertEqual(eval_guard(g, {}, state), (False, None))

    def test_absent_entity_never_fires(self):
        state = {"hearts": 3.0}    # no nearest_enemy
        for src in ("state.nearest_enemy.dist <= 800",
                    "state.nearest_enemy.kind == 'deku_baba'",
                    "state.nearest_enemy.kind != 'deku_baba'",
                    "state.nearest_enemy.dist + 100 <= 900"):
            g = compile_guard(src, "t")
            ok, warn = eval_guard(g, {}, state)
            self.assertFalse(ok, src)
            self.assertIsNone(warn, src)

    def test_absent_truthiness_composes(self):
        g = compile_guard("not state.nearest_enemy and state.hearts >= 1", "t")
        self.assertEqual(eval_guard(g, {}, {"hearts": 3.0}), (True, None))

    def test_stateview(self):
        view = StateView({"a": {"b": 1}, "c": None})
        self.assertEqual(view.a.b, 1)
        self.assertIs(view.c, ABSENT)
        self.assertIs(view.missing, ABSENT)
        self.assertIs(view.a.missing, ABSENT)


if __name__ == "__main__":
    unittest.main()
