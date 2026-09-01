class CameraUnavailableError(RuntimeError):
    """Configured camera cannot be opened for an event recording."""


class RecordingNotFoundError(KeyError):
    """The requested recording is neither active nor retryable."""


class RecordingCameraMismatchError(ValueError):
    """The stop camera differs from the camera used at start."""


class EmptyRecordingError(ValueError):
    """A recording ended without a frame that can be encoded."""


class RecordingConflictError(ValueError):
    """A recordingId was reused for a different detection result."""


class ReportEmailSettingsError(RuntimeError):
    """The automatic-report recipient settings could not be read or saved."""
