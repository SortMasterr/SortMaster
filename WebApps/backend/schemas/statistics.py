from pydantic import BaseModel

from schemas.event import DetectedClass


class Statistics(BaseModel):
    labels: list[DetectedClass]
    counts: list[int]