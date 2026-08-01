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

    def test_underscore_names_reserved(self):
        # The membership rewrite injects _cmp_chain; guard source must not
        # be able to name (and thus shadow) anything in that namespace.
        for bad in ("_cmp_chain == 1", "_x == 1"):
            with self.assertRaises(GuardError, msg=bad):
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
                    "state.nearest_enemy.dist + 100 <= 900",
                    "100 <= state.nearest_enemy.dist <= 800",
                    "state.nearest_enemy.kind in ('deku_baba', 'skulltula')",
                    # `not in` is the trap: the container's reflected ==
                    # yields False, which native `not in` negates to True —
                    # the rewrite keeps the contract's "never match".
                    "state.nearest_enemy.kind not in ('deku_baba', 'skulltula')"):
            g = compile_guard(src, "t")
            ok, warn = eval_guard(g, {}, state)
            self.assertFalse(ok, src)
            self.assertIsNone(warn, src)

    def test_membership_still_works_when_present(self):
        state = {"nearest_enemy": {"kind": "skulltula", "dist": 300.0}}
        g_in = compile_guard("state.nearest_enemy.kind in ('deku_baba', 'skulltula')", "t")
        g_notin = compile_guard("state.nearest_enemy.kind not in ('deku_baba',)", "t")
        self.assertEqual(eval_guard(g_in, {}, state), (True, None))
        self.assertEqual(eval_guard(g_notin, {}, state), (True, None))
        state["nearest_enemy"]["kind"] = "deku_baba"
        self.assertEqual(eval_guard(g_notin, {}, state), (False, None))

    def test_runtime_error_warns_no_fire(self):
        # A guard must never be able to kill the 20 Hz loop: whatever it
        # raises, it did not fire and the caller journals why.
        g = compile_guard("state.rupees % state.sticks == 0", "t")
        ok, warn = eval_guard(g, {}, {"rupees": 10, "sticks": 0})
        self.assertFalse(ok)
        self.assertIn("ZeroDivisionError", warn)

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
