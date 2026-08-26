from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Session:
    session_id: str
    history: List[dict] = field(default_factory=list)
    last_order_id: Optional[str] = None
    last_topic: Optional[str] = None

    def add_user_message(self, text: str):
        self.history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str):
        self.history.append({"role": "assistant", "content": text})

    def summarize(self):
        return self.history[-6:]
