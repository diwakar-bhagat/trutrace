"""Workbench tests: prompt store, runner, and the seed equivalence.

The load-bearing test is the first one: the file-based seed prompts
must assemble to byte-identical text to the legacy in-code versions,
so the Prompt Lab versions ARE the benchmark prompts, not copies.
"""

import json
import os
import shutil
import tempfile
import unittest

from app.config import get_config
from app.prompts import build_prompt
from workbench import prompt_store, runner

QUESTION = "Red roses, a dozen, delivery today"
TRANSCRIPT = "[00:00] Agent: Hi\n[00:05] Seller: Yes, $30, today."


class TestSeedEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()

    def test_seed_prompts_match_legacy_output(self):
        for file_key, legacy_key in (
            ("baseline-naive@1.0.0", "baseline-naive"),
            ("trutrace@1.0.0", "trutrace-1.0.0"),
        ):
            self.assertEqual(
                build_prompt(QUESTION, TRANSCRIPT, file_key),
                build_prompt(QUESTION, TRANSCRIPT, legacy_key),
                f"{file_key} drifted from legacy {legacy_key}",
            )

    def test_seed_configs_match_legacy_labels(self):
        self.assertEqual(get_config("baseline-naive@1.0.0").label, "baseline")
        self.assertEqual(get_config("trutrace@1.0.0").label, "current")


class TestPromptStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old_dir = prompt_store.PROMPTS_DIR
        prompt_store.PROMPTS_DIR = self.tmp

    def tearDown(self):
        prompt_store.PROMPTS_DIR = self._old_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_reload(self):
        rec = prompt_store.save_new_version(
            name="demo", version="0.1.0",
            system="You extract.", user="Q: {question}\nT: {transcript}",
            temperature=0, verification="full", notes="",
        )
        self.assertEqual(rec["key"], "demo@0.1.0")
        loaded = prompt_store.get_prompt("demo@0.1.0")
        self.assertEqual(loaded["system"], "You extract.")
        keys = [p["key"] for p in prompt_store.list_prompts()
                if p["name"] == "demo"]
        self.assertEqual(keys, ["demo@0.1.0"])

    def test_versions_are_immutable(self):
        kwargs = dict(name="demo", version="0.1.0", system="s", user="u")
        prompt_store.save_new_version(**kwargs)
        with self.assertRaises(FileExistsError):
            prompt_store.save_new_version(**kwargs)

    def test_diff_reports_text_and_param_changes(self):
        prompt_store.save_new_version(
            name="demo", version="0.1.0", system="alpha", user="u",
            temperature=0)
        prompt_store.save_new_version(
            name="demo", version="0.2.0", system="beta", user="u",
            temperature=1, parent="demo@0.1.0")
        d = prompt_store.diff_prompts("demo@0.1.0", "demo@0.2.0")
        self.assertIn("temperature", d["param_changes"])
        self.assertNotEqual(d["fingerprint_a"], d["fingerprint_b"])
        self.assertIn("beta", d["system_diff"])


class TestRunnerOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()

    def test_offline_campaign_run_reproduces_recorded_numbers(self):
        # The recorded benchmark (reports/benchmark_results.md):
        # offline baseline on campaign = 52/70 fields, 9 unsupported.
        run = runner.run_experiment(
            "baseline-naive@1.0.0", "offline", None, "campaign")
        m = run["metrics"]
        self.assertEqual(
            (m["extraction_accuracy"]["correct"],
             m["extraction_accuracy"]["total"]), (52, 70))
        self.assertEqual(m["unsupported_claim_rate"]["unsupported"], 9)
        self.assertEqual(run["langfuse"]["connected"], False)
        self.assertIn("pending human review", run["labels_status"])
        # The run persisted where the workbench reads it back.
        loaded = runner.get_run(run["run_id"])
        self.assertEqual(loaded["run_id"], run["run_id"])
        trace = runner.get_case_trace(
            run["run_id"], "campaign_01_showcase_hedged")
        self.assertEqual(trace["evaluations"]["correct_fields"], 3)
        self.assertIn("price", trace["evaluations"]["failed_fields"])
        # Clean up the smoke run so the repo keeps only deliberate runs.
        shutil.rmtree(
            os.path.join(runner.RUNS_DIR, run["run_id"]), ignore_errors=True)


class TestCompare(unittest.TestCase):
    def test_compare_flags_identical_inputs(self):
        runs = runner.list_runs()
        campaign = [r for r in runs
                    if r["dataset"]["split"] == "campaign"
                    and r["cases_run"] == r["dataset"]["cases_total"]]
        if len(campaign) < 2:
            self.skipTest("needs two completed campaign runs")
        c = runner.compare_runs(campaign[0]["run_id"], campaign[1]["run_id"])
        self.assertTrue(c["identical_inputs"])
        self.assertEqual(len(c["per_case"]), 10)


if __name__ == "__main__":
    unittest.main()
