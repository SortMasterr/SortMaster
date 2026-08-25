import os
import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from RPAs.reportAutomation.reportAutomation import ConfigurationError
from RPAs.reportAutomation.reportScheduler import (
    SchedulerConfig,
    dueReportTypes,
    initializeAttemptState,
    loadSchedulerConfig,
)


class ReportSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.config = SchedulerConfig(
            dailySendTime=time(9, 0),
            weeklySendDay=0,
            weeklySendTime=time(9, 10),
            pollSeconds=30,
        )

    def testMondayRunsDailyThenWeeklyAtConfiguredTimes(self):
        timezone = ZoneInfo("Asia/Seoul")

        dailyDue = dueReportTypes(
            datetime(2026, 8, 24, 9, 0, tzinfo=timezone),
            {},
            self.config,
        )
        bothDue = dueReportTypes(
            datetime(2026, 8, 24, 9, 10, tzinfo=timezone),
            {},
            self.config,
        )

        self.assertEqual(("daily",), dailyDue)
        self.assertEqual(("daily", "weekly"), bothDue)

    def testAttemptedReportDoesNotRunAgainThatDay(self):
        now = datetime(
            2026,
            8,
            24,
            9,
            30,
            tzinfo=ZoneInfo("Asia/Seoul"),
        )

        due = dueReportTypes(
            now,
            {"daily": date(2026, 8, 24)},
            self.config,
        )

        self.assertEqual(("weekly",), due)

    def testStartupAfterScheduleDoesNotBackfillReport(self):
        now = datetime(
            2026,
            8,
            25,
            15,
            0,
            tzinfo=ZoneInfo("Asia/Seoul"),
        )

        attempts = initializeAttemptState(now, self.config)

        self.assertEqual({"daily": date(2026, 8, 25)}, attempts)
        self.assertEqual(
            (),
            dueReportTypes(now, attempts, self.config),
        )

    def testInvalidScheduleConfigurationIsRejected(self):
        with patch.dict(
            os.environ,
            {"RPA_WEEKLY_SEND_DAY": "INVALID"},
            clear=True,
        ):
            with self.assertRaises(ConfigurationError):
                loadSchedulerConfig()


if __name__ == "__main__":
    unittest.main()
