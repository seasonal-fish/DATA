"""
scheduler.py 유닛 테스트
외부 의존성(APScheduler, subprocess) 없이 실행 가능한 동작만 대상으로 함
"""
from unittest.mock import MagicMock, call, patch

import pytest

import scheduler


# ---------------------------------------------------------------------------
# main — PIPELINE_ENABLED 플래그 동작
# ---------------------------------------------------------------------------

class TestMain:
    def test_disabled_by_default_does_not_start_scheduler(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("scheduler.BlockingScheduler") as mock_sched:
            scheduler.main()
        mock_sched.return_value.start.assert_not_called()

    def test_pipeline_enabled_false_does_not_start_scheduler(self):
        with patch.dict("os.environ", {"PIPELINE_ENABLED": "false"}, clear=True), \
             patch("scheduler.BlockingScheduler") as mock_sched:
            scheduler.main()
        mock_sched.return_value.start.assert_not_called()

    def test_pipeline_enabled_true_starts_scheduler(self):
        mock_sched_instance = MagicMock()
        mock_sched_instance.start.side_effect = KeyboardInterrupt
        with patch.dict("os.environ", {"PIPELINE_ENABLED": "true"}, clear=True), \
             patch("scheduler.BlockingScheduler", return_value=mock_sched_instance), \
             patch("scheduler.CronTrigger"):
            scheduler.main()
        mock_sched_instance.add_job.assert_called_once()
        mock_sched_instance.start.assert_called_once()

    def test_cron_and_timezone_passed_to_trigger(self):
        mock_sched_instance = MagicMock()
        mock_sched_instance.start.side_effect = KeyboardInterrupt
        env = {
            "PIPELINE_ENABLED": "true",
            "PIPELINE_SCHEDULE_CRON": "0 6 * * *",
            "PIPELINE_TIMEZONE": "UTC",
        }
        with patch.dict("os.environ", env, clear=True), \
             patch("scheduler.BlockingScheduler", return_value=mock_sched_instance), \
             patch("scheduler.CronTrigger") as mock_trigger:
            scheduler.main()
        mock_trigger.from_crontab.assert_called_once_with("0 6 * * *", timezone="UTC")


# ---------------------------------------------------------------------------
# run_pipeline — 스텝 실행 순서 및 실패 처리
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def _mock_run(self, returncode=0):
        result = MagicMock()
        result.returncode = returncode
        return MagicMock(return_value=result)

    def test_all_steps_executed_in_order(self):
        with patch("scheduler.subprocess.run", self._mock_run()) as mock_run:
            scheduler.run_pipeline()
        cmds = [call_args[0][0] for call_args in mock_run.call_args_list]
        scripts = [cmd[1] for cmd in cmds]
        assert scripts == [
            "step1_get_word_list.py",
            "step2_crawl_descriptions.py",
            "step3_save_final.py",
            "step4_enrich_with_openai.py",
            "step5_load_enriched_to_db.py",
        ]

    def test_run_id_passed_to_steps_3_4_5(self):
        with patch("scheduler.subprocess.run", self._mock_run()) as mock_run:
            scheduler.run_pipeline()
        calls = mock_run.call_args_list
        for idx in [2, 3, 4]:
            cmd = calls[idx][0][0]
            assert "--run-id" in cmd

    def test_pipeline_stops_on_step_failure(self):
        fail_result = MagicMock()
        fail_result.returncode = 1
        ok_result = MagicMock()
        ok_result.returncode = 0

        side_effects = [ok_result, fail_result]
        with patch("scheduler.subprocess.run", side_effect=side_effects) as mock_run:
            scheduler.run_pipeline()
        assert mock_run.call_count == 2

    def test_run_id_consistent_across_steps(self):
        with patch("scheduler.subprocess.run", self._mock_run()) as mock_run:
            scheduler.run_pipeline()
        calls = mock_run.call_args_list
        run_ids = []
        for c in calls:
            cmd = c[0][0]
            if "--run-id" in cmd:
                idx = cmd.index("--run-id")
                run_ids.append(cmd[idx + 1])
        assert len(set(run_ids)) == 1
