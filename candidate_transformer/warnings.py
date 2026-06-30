class WarningCollector:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def add(self, message: str) -> None:
        self.messages.append(message)

    def as_records(self) -> list[dict]:
        return [{"level": "warning", "message": message} for message in self.messages]
