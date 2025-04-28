import json
from dataclasses import dataclass
from typing import Any


@dataclass
class BaseMessage:
    action: str

    def to_json(self) -> str:
        """Serialize the message to JSON."""
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, data: str) -> "BaseMessage":
        """Deserialize JSON to a message object."""
        parsed = json.loads(data)
        action = parsed.get("action")
        if action == "join":
            return JoinMessage(**parsed)
        elif action == "move":
            return MoveMessage(**parsed)
        elif action == "leave":
            return LeaveMessage(**parsed)
        else:
            return UnknownMessage(**parsed)


@dataclass
class JoinMessage(BaseMessage):
    player_name: str


@dataclass
class MoveMessage(BaseMessage):
    position: dict[str, Any]


@dataclass
class LeaveMessage(BaseMessage):
    pass


@dataclass
class UnknownMessage(BaseMessage):
    details: str | None = None
