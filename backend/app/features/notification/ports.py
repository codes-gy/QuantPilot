from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, event_type: str, message: str) -> None: ...
