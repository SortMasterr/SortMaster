import json
import tempfile
import unittest
from unittest.mock import patch
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from RPAs.reportAutomation.reportAutomation import (
    ConfigurationError,
    DataMismatchError,
    DuplicateReportError,
    RecipientSettingsStore,
    ReportSnapshotStore,
    Settings,
    SnapshotUnavailableError,
    aggregateData,
    buildCsv,
    buildExecutionKey,
    buildHtml,
    calculatePeriod,
    runReport,
    validateData,
)


def makeEvent(
    eventId="event-1",
    timestamp="2026-08-24T01:00:00Z",
    eventCategory="misclassification",
    detectedClass="recyclables",
    binType="paper",
    confidenceScore=0.84,
):
    if eventCategory == "overflow":
        detectedClass = None
        confidenceScore = None
    return {
        "eventId": eventId,
        "timestamp": timestamp,
        "cameraId": "ELEV-TOP" if eventCategory == "misclassification" else "ELEV-SIDE",
        "eventCategory": eventCategory,
        "detectionId": f"detection-{eventId}",
        "trackingId": 1 if eventCategory == "misclassification" else None,
        "detectedClass": detectedClass,
        "binId": f"BIN-{binType.upper()}",
        "binType": binType,
        "isMisclassified": True if eventCategory == "misclassification" else None,
        "confidenceScore": confidenceScore,
        "actionTaken": "lightAndSound",
        "imageFileId": None,
        "overflowDuration": None,
        "overflowThreshold": None,
        "modelVersion": "test-model",
        "notes": None,
    }


def makeStatistics(events):
    labels = ["normal", "paper", "recyclables", "coffeeCup"]
    counts = [
        sum(event["eventCategory"] == "misclassification" and event["detectedClass"] == label for event in events)
        for label in labels
    ]
    return {
        "labels": labels,
        "counts": counts,
        "totalEventCount": len(events),
        "misclassificationCount": sum(event["eventCategory"] == "misclassification" for event in events),
        "overflowCount": sum(event["eventCategory"] == "overflow" for event in events),
    }


class FakeApiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.periods = []

    def getReportData(self, period):
        self.periods.append(period)
        return self.responses.pop(0)


class ReportAutomationTests(unittest.TestCase):
    def testSavedRecipientOverridesEnvironmentRecipient(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            stateDirectory = Path(temporaryDirectory)
            RecipientSettingsStore(stateDirectory).saveRecipient(
                "saved@example.com"
            )
            with patch.dict(
                "os.environ",
                {
                    "RPA_STATE_DIRECTORY": temporaryDirectory,
                    "RPA_REPORT_RECIPIENTS": "old@example.com",
                    "RPA_REPORT_FROM": "sender@example.com",
                    "SMTP_HOST": "smtp.example.com",
                    "SMTP_USER": "sender@example.com",
                    "SMTP_PASSWORD": "app-password",
                },
                clear=True,
            ):
                settings = Settings.fromEnvironment()

        self.assertEqual(("saved@example.com",), settings.recipients)

    def testRecipientSettingsStoreNormalizesAddress(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            store = RecipientSettingsStore(Path(temporaryDirectory))

            saved = store.saveRecipient(" Manager@Example.com ")

            self.assertEqual("manager@example.com", saved)
            self.assertEqual(saved, store.loadRecipient())

    def testGmailSenderAndSmtpUserMustMatch(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            with patch.dict(
                "os.environ",
                {
                    "RPA_STATE_DIRECTORY": temporaryDirectory,
                    "RPA_REPORT_RECIPIENTS": "manager@example.com",
                    "RPA_REPORT_FROM": "sender@gmail.com",
                    "SMTP_HOST": "smtp.gmail.com",
                    "SMTP_USER": "different@gmail.com",
                    "SMTP_PASSWORD": "app-password",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    ConfigurationError,
                    "SMTP_USER",
                ):
                    Settings.fromEnvironment()

    def testDailyPeriodUsesPreviousKstCalendarDayAndUtcBoundary(self):
        now = datetime(2026, 8, 25, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        period = calculatePeriod("daily", now)

        self.assertEqual(date(2026, 8, 24), period.startKst.date())
        self.assertEqual(datetime(2026, 8, 23, 15, 0, tzinfo=timezone.utc), period.startUtc)
        self.assertEqual(datetime(2026, 8, 24, 14, 59, 59, 999999, tzinfo=timezone.utc), period.endUtc)

    def testWeeklyPeriodUsesPreviousMondayThroughSunday(self):
        now = datetime(2026, 8, 24, 9, 10, tzinfo=ZoneInfo("Asia/Seoul"))

        period = calculatePeriod("weekly", now)

        self.assertEqual(date(2026, 8, 17), period.startKst.date())
        self.assertEqual(date(2026, 8, 23), period.endKst.date())

    def testValidationAcceptsValidEventsAndRejectsStatisticsMismatch(self):
        period = calculatePeriod("daily", targetDate=date(2026, 8, 24))
        events = [
            makeEvent(),
            makeEvent("event-2", "2026-08-24T02:00:00Z", "overflow", binType="paper"),
        ]
        statistics = makeStatistics(events)

        validateData(statistics, events, period)
        statistics["totalEventCount"] = 3

        with self.assertRaises(DataMismatchError):
            validateData(statistics, events, period)

    def testAggregationUsesKstHourAndBuildsKoreanUtf8Csv(self):
        period = calculatePeriod("daily", targetDate=date(2026, 8, 24))
        events = [makeEvent()]
        statistics = makeStatistics(events)

        data = aggregateData(statistics, events, period)
        csvBytes = buildCsv(events, "Asia/Seoul")

        self.assertEqual(1, data["timeline"][10]["misclassification"])
        self.assertAlmostEqual(0.84, data["averageConfidence"])
        self.assertTrue(csvBytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn("recyclables", csvBytes.decode("utf-8-sig"))

    def testZeroEventHtmlIsAValidReport(self):
        period = calculatePeriod("daily", targetDate=date(2026, 8, 24))
        statistics = makeStatistics([])
        validateData(statistics, [], period)

        htmlBody = buildHtml(aggregateData(statistics, [], period), period, "http://localhost:8047")

        self.assertIn("해당 기간의 집계 결과는 0건입니다", htmlBody)
        self.assertIn("http://localhost:8047/statistics", htmlBody)

    def testDryRunCreatesArtifactsWithoutSendingOrRecordingDelivery(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            root = Path(temporaryDirectory)
            settings = self.makeSettings(root)
            events = [makeEvent()]
            client = FakeApiClient([(makeStatistics(events), events)])
            sendCalls = []

            result = runReport(
                "daily",
                settings,
                dryRun=True,
                targetDate=date(2026, 8, 24),
                apiClient=client,
                emailSender=lambda *args: sendCalls.append(args),
            )

            self.assertEqual("dryRun", result["status"])
            self.assertTrue(Path(result["htmlPath"]).exists())
            self.assertTrue(Path(result["csvPath"]).exists())
            self.assertEqual([], sendCalls)
            self.assertFalse((settings.stateDirectory / "sentReports.json").exists())

    def testSuccessfulRunPreventsDuplicateSend(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            root = Path(temporaryDirectory)
            settings = self.makeSettings(root)
            events = [makeEvent()]
            response = (makeStatistics(events), events)

            result = runReport(
                "daily",
                settings,
                targetDate=date(2026, 8, 24),
                apiClient=FakeApiClient([response]),
                emailSender=lambda unusedSettings, unusedMessage, recipients: set(recipients),
            )

            self.assertEqual("sent", result["status"])
            snapshotPath = (
                settings.stateDirectory
                / "dailyReportSnapshots"
                / "2026-08-24.json"
            )
            self.assertTrue(snapshotPath.exists())
            self.assertNotIn(
                "imageFileId",
                json.loads(
                    snapshotPath.read_text(encoding="utf-8")
                )["events"][0],
            )
            period = calculatePeriod("daily", targetDate=date(2026, 8, 24))
            self.assertEqual("daily:2026-08-24:operations", buildExecutionKey(period, "operations"))
            with self.assertRaises(DuplicateReportError):
                runReport(
                    "daily",
                    settings,
                    targetDate=date(2026, 8, 24),
                    apiClient=FakeApiClient([response]),
                    emailSender=lambda unusedSettings, unusedMessage, recipients: set(recipients),
                )

    def testWeeklyUsesSevenSnapshotsAndSavedAggregateForComparison(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            settings = self.makeSettings(Path(temporaryDirectory))
            currentEvents = [makeEvent("current", "2026-08-17T01:00:00Z")]
            previousEvents = [makeEvent("previous", "2026-08-10T01:00:00Z", "overflow", binType="normal")]
            snapshotStore = ReportSnapshotStore(settings.stateDirectory)
            for offset in range(7):
                targetDate = date(2026, 8, 17 + offset)
                dailyEvents = currentEvents if offset == 0 else []
                snapshotStore.saveDaily(
                    makeStatistics(dailyEvents),
                    dailyEvents,
                    calculatePeriod("daily", targetDate=targetDate),
                )
            previousPeriod = calculatePeriod(
                "weekly",
                targetDate=date(2026, 8, 10),
            )
            snapshotStore.saveWeeklyAggregate(
                aggregateData(
                    makeStatistics(previousEvents),
                    previousEvents,
                    previousPeriod,
                ),
                previousPeriod,
            )
            client = FakeApiClient([])

            result = runReport(
                "weekly",
                settings,
                dryRun=True,
                targetDate=date(2026, 8, 17),
                apiClient=client,
            )

            self.assertEqual("dryRun", result["status"])
            self.assertEqual([], client.periods)
            self.assertIn("전주 대비 증감", Path(result["htmlPath"]).read_text(encoding="utf-8"))

    def testWeeklyRejectsMissingDailySnapshot(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            settings = self.makeSettings(Path(temporaryDirectory))

            with self.assertRaisesRegex(
                SnapshotUnavailableError,
                "2026-08-17",
            ):
                runReport(
                    "weekly",
                    settings,
                    dryRun=True,
                    targetDate=date(2026, 8, 17),
                    apiClient=FakeApiClient([]),
                )

    def testDailySnapshotStoreKeepsOnlyLatestSevenDates(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            store = ReportSnapshotStore(Path(temporaryDirectory))
            for offset in range(8):
                targetDate = date(2026, 8, 1 + offset)
                period = calculatePeriod("daily", targetDate=targetDate)
                store.saveDaily(makeStatistics([]), [], period)

            snapshotNames = sorted(
                path.name
                for path in store.dailyDirectory.glob("*.json")
            )

            self.assertEqual(7, len(snapshotNames))
            self.assertEqual("2026-08-02.json", snapshotNames[0])

    def testPartialRecipientSuccessRetriesOnlyPendingRecipient(self):
        with tempfile.TemporaryDirectory() as temporaryDirectory:
            settings = replace(
                self.makeSettings(Path(temporaryDirectory)),
                retryDelays=(0,),
            )
            events = [makeEvent()]
            recipientCalls = []

            def partialSender(unusedSettings, unusedMessage, recipients):
                recipientCalls.append(set(recipients))
                if len(recipientCalls) == 1:
                    return {"one@example.com"}
                return set(recipients)

            result = runReport(
                "daily",
                settings,
                targetDate=date(2026, 8, 24),
                apiClient=FakeApiClient([(makeStatistics(events), events)]),
                emailSender=partialSender,
            )

            self.assertEqual("sent", result["status"])
            self.assertEqual(
                [
                    {"one@example.com", "two@example.com"},
                    {"two@example.com"},
                ],
                recipientCalls,
            )

    @staticmethod
    def makeSettings(root):
        return Settings(
            enabled=True,
            timezoneName="Asia/Seoul",
            recipients=("one@example.com", "two@example.com"),
            recipientGroup="operations",
            sender="sortmaster@example.com",
            smtpHost="smtp.example.com",
            smtpPort=587,
            smtpUser="user",
            smtpPassword="secret",
            smtpUseTls=True,
            apiBaseUrl="http://localhost:8047",
            webBaseUrl="http://localhost:8047",
            retryDelays=(),
            requestTimeoutSeconds=1,
            stateDirectory=root / "state",
            outputDirectory=root / "output",
        )


if __name__ == "__main__":
    unittest.main()
