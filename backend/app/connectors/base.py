from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.models import CanonicalObservation, FetchResult


class DatasetConnector(ABC):
    dataset_code: str

    @abstractmethod
    def fetch(self) -> FetchResult:
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw: FetchResult) -> list[CanonicalObservation]:
        raise NotImplementedError
