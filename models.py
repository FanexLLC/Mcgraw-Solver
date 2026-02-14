from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuestionData:
    type: str = "unknown"
    question: str = ""
    context: str = ""
    choices: list[dict[str, Any]] = field(default_factory=list)
    input_elements: list[Any] = field(default_factory=list)
    blank_count: int = 1
    items: list[str] = field(default_factory=list)
    item_elements: list[Any] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    source_elements: list[Any] = field(default_factory=list)
    target_elements: list[Any] = field(default_factory=list)


@dataclass
class Action:
    type: str
    answer_text: str = ""
    targets: list[Any] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    # Ordering-specific
    ordered_items: list[str] = field(default_factory=list)
    item_elements: list[Any] = field(default_factory=list)
    original_items: list[str] = field(default_factory=list)
    # Matching-specific
    matches: list[dict[str, str]] = field(default_factory=list)
    source_elements: list[Any] = field(default_factory=list)
    target_elements: list[Any] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    targets_list: list[str] = field(default_factory=list)
