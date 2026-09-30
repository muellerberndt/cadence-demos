"""Task outcome, denominator and native initialization checks; no trained claim."""
import unittest
from unittest.mock import patch

from .tasks import TaskSpec, classify_outcome, get_task, MAP_SPLITS
from .evaluate import summarize
from .teacher import GeometryTeacher
from .interface import ACTION_NAMES


class TaskOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.spec = get_task("doom1:E1M1")

    def outcome(self, **changes):
        fields = dict(terminal=True, dead=False, timeout=False, kills=3, elapsed_tics=400)
        return classify_outcome(self.spec, **(fields | changes))

    def test_exit_requires_alive_native_terminal_before_timeout(self):
        self.assertTrue(self.outcome()["native_exit"])
        self.assertTrue(self.outcome()["success"])
        for change in (dict(dead=True), dict(timeout=True), dict(terminal=False), dict(external_cutoff="wall_cap")):
            result = self.outcome(**change)
            self.assertFalse(result["success"])
            self.assertFalse(result["native_exit"])

    def test_task_success_is_not_reward_or_kill_proxy(self):
        self.assertFalse(self.outcome(terminal=False, kills=999)["success"])
        # Exiting alive without killing is an exit, unless the named curriculum
        # task separately declares a combined combat requirement.
        self.assertTrue(self.outcome(kills=0)["success"])
        combined = get_task("combined")
        self.assertFalse(classify_outcome(combined, terminal=True, dead=False,
                                         timeout=False, kills=0, elapsed_tics=300)["success"])

    def test_survival_native_timeout_is_success_only_while_alive(self):
        spec = get_task("survival")
        for dead in (False, True):
            result = classify_outcome(spec, terminal=True, dead=dead, timeout=True,
                                      kills=0, elapsed_tics=spec.timeout_tics-1)
            self.assertEqual(result["success"], not dead)
            self.assertFalse(result["native_exit"])

    def test_scenario_completion_does_not_claim_full_level(self):
        spec = get_task("navigation")
        result = classify_outcome(spec, terminal=True, dead=False, timeout=False, kills=0, elapsed_tics=100)
        self.assertTrue(result["success"])
        self.assertFalse(result["native_exit"])
        with self.assertRaises(ValueError):
            TaskSpec("bad", "freedoom2", scenario="basic", objective="native_exit")

    def test_map_partitions_are_disjoint_and_explicit(self):
        all_maps = [m for maps in MAP_SPLITS.values() for m in maps]
        self.assertEqual(len(all_maps), len(set(all_maps)))
        self.assertEqual(get_task("doom1:E1M5").split, "heldout")
        self.assertEqual(get_task("doom1:E1M8").split, "reserved_extension")


class EvaluationAccountingTests(unittest.TestCase):
    def row(self, seed=1, **changes):
        return dict(task_id="doom1:E1M1", seed=seed, success=True, native_exit=True,
                    queries=10, qualified_queries=10, status="complete", tics=40, **changes)

    def test_missing_and_cutoff_jobs_stay_in_denominator(self):
        rows = [self.row(), self.row(seed=2)]
        rows[1]["status"] = "evaluation_wall_cap"
        report = summarize(rows, [("doom1:E1M1", i) for i in (1, 2, 3)])
        group = report["tasks"]["doom1:E1M1"]
        self.assertEqual(group["successes"], 1)
        self.assertEqual(group["success_rate"], 1/3)
        self.assertEqual(group["missing"], 1)

    def test_unqualified_native_finish_cannot_count_as_student_success(self):
        row = self.row()
        row["qualified_queries"] = 9
        result = summarize([row], [("doom1:E1M1", 1)])
        self.assertEqual(result["successes"], 0)
        self.assertEqual(result["tasks"]["doom1:E1M1"]["native_exits"], 0)

    def test_duplicates_and_unscheduled_rows_fail(self):
        with self.assertRaises(ValueError):
            summarize([self.row(), self.row()], [("doom1:E1M1", 1)])
        with self.assertRaises(ValueError):
            summarize([self.row(2)], [("doom1:E1M1", 1)])


class TeacherMotorFeedbackTests(unittest.TestCase):
    def teacher(self):
        teacher = object.__new__(GeometryTeacher)
        teacher.steps = 12
        teacher.door_used_step = 12
        teacher.last_use_step = 12
        teacher.door_target = {"index": 1}
        teacher.last_action = "use"
        return teacher

    def test_unexecuted_teacher_use_does_not_open_internal_door_phase(self):
        teacher = self.teacher()
        teacher.acknowledge(ACTION_NAMES.index("fire"), 4)
        self.assertIsNone(teacher.door_used_step)
        self.assertEqual(teacher.last_action, "fire")
        self.assertNotEqual(teacher.last_use_step, 12)

    def test_executed_intervention_controls_stuck_tracking(self):
        teacher = self.teacher()
        teacher.acknowledge(ACTION_NAMES.index("forward"), 4)
        self.assertEqual(teacher.last_action, "forward")
        with self.assertRaises(ValueError):
            teacher.acknowledge(ACTION_NAMES.index("use"), 5)


class NativeScenarioStartTests(unittest.TestCase):
    def test_native_scenario_warmup_is_preserved(self):
        from .tasks import DoomEnv, configured_start_time, task_identity
        for task, start in [('basic', 14), ('navigation', 10)]:
            self.assertEqual(configured_start_time(task), start)
            self.assertEqual(task_identity(task)['episode_start_time'], start)
            with DoomEnv(task, 1100300000, teacher=False) as env:
                facts = env.facts()
                self.assertEqual(facts['episode_start_time'], start)
                self.assertGreaterEqual(facts['initial_episode_tic'], start)
                self.assertEqual(facts['elapsed_tics'], 0)
                self.assertEqual(env.observe().shape, (240, 320))
        self.assertEqual(configured_start_time('doom1:E1M1'), 1)

    def test_initialization_failure_cleans_temporary_config(self):
        from pathlib import Path
        from .tasks import DoomEnv
        paths = []
        def fail(env, visible):
            paths.append(Path(env.tmp.name))
            raise RuntimeError('deliberate initialization failure')
        with patch.object(DoomEnv, '_initialize', fail):
            with self.assertRaisesRegex(RuntimeError, 'deliberate'):
                DoomEnv('basic', 1100300000)
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())


if __name__ == "__main__":
    unittest.main()
