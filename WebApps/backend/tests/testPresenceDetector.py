import unittest

import numpy as np

from detection.presenceDetector import PersonPresenceDetector


def blankFrame(height=120, width=160):
    return np.zeros((height, width, 3), dtype=np.uint8)


def trainBackground(detector, frames=40):
    ratio = 0.0

    for _ in range(frames):
        ratio = detector.foregroundRatio(blankFrame())

    return ratio


class PersonPresenceDetectorTest(unittest.TestCase):
    def testStaticBackgroundConvergesToLowRatio(self):
        detector = PersonPresenceDetector()

        finalRatio = trainBackground(detector)

        self.assertLess(finalRatio, 0.05)

    def testInsertedForegroundRaisesRatioAboveBackground(self):
        detector = PersonPresenceDetector()
        backgroundRatio = trainBackground(detector)

        personFrame = blankFrame()
        personFrame[40:80, 60:100] = 255
        personRatio = detector.foregroundRatio(personFrame)

        self.assertGreater(personRatio, backgroundRatio)
        self.assertGreater(personRatio, 0.05)


if __name__ == "__main__":
    unittest.main()
