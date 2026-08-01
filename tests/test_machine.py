import tempfile
import textwrap
import unittest
from pathlib import Path

from ocarina.machine import load_machine

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "save-file"

NOOP_BEHAVIOR = textwrap.dedent("""\
    from ocarina.behavior import Behavior
    BEHAVIORS = {
        "noop_v1": Behavior(name="noop", version=1, description="nothing",
                            body=lambda game, ctx: None,
                            success=lambda game, initial, events: True),
    }
    """)


def leaf_machine(extra_transitions: str = "", version: int = 1,
                 behavior: str = "noop_v1", top_extra: str = "") -> str:
    """A one-leaf machine with a valid behavior_done loop, plus optional
    extra transition lines (already indented for the leaf's list)."""
    return textwrap.dedent(f"""\
        version: {version}
        initial: leaf{top_extra}
        nodes:
          leaf:
            behavior: {behavior}
            transitions:
              - name: done
                on: behavior_done
                do: goto leaf
        """) + extra_transitions


def write_repo(tmp: str, yaml_text: str, behaviors: str = NOOP_BEHAVIOR) -> Path:
    repo = Path(tmp)
    (repo / "machine" / "behaviors").mkdir(parents=True, exist_ok=True)
    (repo / "machine" / "machine.yaml").write_text(yaml_text)
    (repo / "machine" / "behaviors" / "b.py").write_text(behaviors)
    return repo


def errors(diags):
    return [d.msg for d in diags if d.level == "error"]


def warnings(diags):
    return [d.msg for d in diags if d.level == "warning"]


def load_text(yaml_text, behaviors=NOOP_BEHAVIOR):
    with tempfile.TemporaryDirectory() as tmp:
        return load_machine(write_repo(tmp, yaml_text, behaviors))


class TestMachineLoads(unittest.TestCase):
    def test_fixture_machine_loads_clean(self):
        machine, diags = load_machine(FIXTURE_REPO)
        self.assertEqual(errors(diags), [])
        self.assertIsNotNone(machine)
        self.assertEqual(machine.initial, "explore")
        self.assertEqual(machine.descend("explore"),
                         ["explore", "navigate_field"])
        # The multiline `when` folded and compiled.
        nf = machine.nodes["navigate_field"]
        baba = next(t for t in nf.transitions if t.name == "baba-in-reach")
        self.assertEqual(baba.kind, "state")
        self.assertEqual(baba.guard.state_paths,
                         {("nearest_enemy", "kind"), ("nearest_enemy", "dist")})

    def test_scope_order_is_innermost_out(self):
        machine, _ = load_machine(FIXTURE_REPO)
        names = [t.name for t in machine.scope("kill_baba")]
        self.assertEqual(names, ["baba-done", "novel-actor", "keep-going",
                                 "health-drop"])

    def test_minimal(self):
        machine, diags = load_text(leaf_machine())
        self.assertEqual(errors(diags), [])
        self.assertIsNotNone(machine)


class TestValidation(unittest.TestCase):
    def check(self, yaml_text, expect_error, behaviors=NOOP_BEHAVIOR):
        machine, diags = load_text(yaml_text, behaviors)
        self.assertIsNone(machine)
        joined = "\n".join(errors(diags))
        self.assertIn(expect_error, joined, f"diagnostics: {joined!r}")

    def extra(self, lines: str) -> str:
        """Append a transition to the minimal leaf's list."""
        return leaf_machine(textwrap.indent(textwrap.dedent(lines), " " * 6))

    def test_version_mismatch(self):
        self.check(leaf_machine(version=2), "version must be 1")

    def test_unknown_top_key(self):
        self.check(leaf_machine() + "mystery: 1\n", "unknown top-level keys")

    def test_unknown_transition_key(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: goto leaf
              extra: 1
            """), "unknown keys")

    def test_children_and_behavior(self):
        self.check(textwrap.dedent("""\
            version: 1
            initial: a
            nodes:
              a:
                behavior: noop_v1
                initial: b
                children:
                  b:
                    behavior: noop_v1
                    transitions:
                      - name: done
                        on: behavior_done
                        do: goto b
            """), "'children' or 'behavior', never both")

    def test_on_and_when_both(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              when: state.hearts <= 1
              do: goto leaf
            """), "never both")

    def test_missing_behavior_done(self):
        self.check(textwrap.dedent("""\
            version: 1
            initial: leaf
            nodes:
              leaf:
                behavior: noop_v1
                transitions:
                  - name: hurt
                    on: damage_taken
                    do: goto leaf
            """), "behavior_done")

    def test_guarded_behavior_done_is_not_enough(self):
        self.check(textwrap.dedent("""\
            version: 1
            initial: leaf
            nodes:
              leaf:
                behavior: noop_v1
                transitions:
                  - name: done
                    on: behavior_done
                    where: outcome == 'success'
                    do: goto leaf
            """), "behavior_done")

    def test_on_record_only_machine_event(self):
        # `entered` is recorded but never dispatched — a transition on it
        # can never fire, so it must not load silently.
        self.check(self.extra("""\
            - name: bad
              on: entered
              do: goto leaf
            """), "recorded but never dispatched")

    def test_on_unknown_event(self):
        self.check(self.extra("""\
            - name: bad
              on: spwan
              do: goto leaf
            """), "not in the event grammar")

    def test_wake_needs_default(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: wake help
            """), "must declare a non-wake 'default'")

    def test_default_cannot_wake(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: wake help
              default: wake again
            """), "'default' cannot be another wake")

    def test_default_only_on_waking(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: goto leaf
              default: hold x
            """), "only means something")

    def test_bad_state_path(self):
        self.check(self.extra("""\
            - name: bad
              when: state.nope == 1
              do: goto leaf
            """), "state has no field 'nope'")

    def test_deep_state_path_past_leaf(self):
        self.check(self.extra("""\
            - name: bad
              when: state.hearts.deep == 1
              do: goto leaf
            """), "leaf field")

    def test_bare_name_in_when(self):
        self.check(self.extra("""\
            - name: bad
              when: novel == 1
              do: goto leaf
            """), "no event to resolve against")

    def test_templated_arg_on_when_transition(self):
        # `{field}` templates resolve from the event; a `when` transition
        # has none — for every templating verb, not just journal.
        for action in ("journal down to {hearts_after} hearts",
                       "hold waiting on {cue}"):
            self.check(self.extra(f"""\
                - name: bad
                  when: state.hearts <= 1
                  do:
                    - {action}
                    - goto leaf
                """), "no event to resolve against")

    def test_plain_journal_on_when_transition_is_fine(self):
        # The 0.2.2 ruling: MACHINE.md restricts the TEMPLATING to events,
        # not the verb — a state reflex may journal plain text (the stage-2
        # vigilance rung of the compile-downward ladder).
        machine, diags = load_text(self.extra("""\
            - name: fine
              when: state.hearts <= 1
              do:
                - journal hearts critical, watching
            """))
        self.assertEqual([d.msg for d in diags if d.level == "error"], [])
        self.assertIsNotNone(machine)

    def test_goto_target_missing(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: goto nowhere
            """), "goto target 'nowhere' does not exist")

    def test_unknown_verb(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: pad A
            """), "unknown action verb")

    def test_missing_behavior(self):
        self.check(leaf_machine(behavior="ghost_v9"), "not in the loaded corpus")

    def test_behavior_import_error(self):
        self.check(leaf_machine(), "import failed",
                   behaviors="this is not python\n")

    def test_negative_cooldown(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do: goto leaf
              cooldown_s: -1
            """), "non-negative")

    def test_two_terminal_actions(self):
        self.check(self.extra("""\
            - name: bad
              on: spawn
              do:
                - goto leaf
                - hold what
            """), "at most one of")

    def test_duplicate_node_name(self):
        self.check(textwrap.dedent("""\
            version: 1
            initial: a
            nodes:
              a:
                initial: leaf
                children:
                  leaf:
                    behavior: noop_v1
                    transitions:
                      - name: done
                        on: behavior_done
                        do: goto leaf
                  a:
                    behavior: noop_v1
            """), "duplicate")


class TestReachability(unittest.TestCase):
    def test_unreachable_is_warning_not_error(self):
        yaml_text = textwrap.dedent("""\
            version: 1
            initial: a
            nodes:
              a:
                behavior: noop_v1
              island:
                behavior: noop_v1

            transitions:
              - name: any-done
                on: behavior_done
                do: goto a
            """)
        machine, diags = load_text(yaml_text)
        self.assertEqual(errors(diags), [])
        self.assertIsNotNone(machine)
        self.assertTrue(any(d.level == "warning" and d.where == "island"
                            for d in diags))


if __name__ == "__main__":
    unittest.main()
