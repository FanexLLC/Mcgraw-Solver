"""Tests for models.py — dataclass construction and defaults."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import QuestionData, Action


class TestQuestionData:
    def test_defaults(self):
        qd = QuestionData()
        assert qd.type == "unknown"
        assert qd.question == ""
        assert qd.choices == []
        assert qd.blank_count == 1

    def test_from_kwargs(self):
        qd = QuestionData(type="mc_single", question="What?",
                          choices=[{"label": "A", "text": "Yes"}])
        assert qd.type == "mc_single"
        assert len(qd.choices) == 1

    def test_lists_independent(self):
        """Ensure mutable defaults don't share state between instances."""
        qd1 = QuestionData()
        qd2 = QuestionData()
        qd1.choices.append({"label": "A"})
        assert len(qd2.choices) == 0


class TestAction:
    def test_defaults(self):
        a = Action(type="click")
        assert a.answer_text == ""
        assert a.targets == []
        assert a.values == []

    def test_ordering_fields(self):
        a = Action(type="ordering", ordered_items=["A", "B"], original_items=["B", "A"])
        assert a.ordered_items == ["A", "B"]
        assert a.original_items == ["B", "A"]

    def test_matching_fields(self):
        a = Action(type="matching", matches=[{"source": "L", "target": "R"}])
        assert len(a.matches) == 1

    def test_lists_independent(self):
        a1 = Action(type="click")
        a2 = Action(type="click")
        a1.targets.append("x")
        assert len(a2.targets) == 0
