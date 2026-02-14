"""Tests for solver.py — response parsing and prompt building."""

import sys
import os

# Add parent directory to path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import QuestionData, Action
from solver import parse_gpt_response, _extract_answer_line, _build_prompt


class TestExtractAnswerLine:
    def test_simple_answer(self):
        text = "Some reasoning here.\nANSWER: B"
        assert _extract_answer_line(text) == "B"

    def test_answer_case_insensitive(self):
        text = "Thinking...\nanswer: C"
        assert _extract_answer_line(text) == "C"

    def test_answer_with_text(self):
        text = "Step 1: ...\nStep 2: ...\nANSWER: mitosis"
        assert _extract_answer_line(text) == "mitosis"

    def test_no_answer_line_returns_last(self):
        text = "First line\nSecond line\nThe answer is B"
        assert _extract_answer_line(text) == "The answer is B"

    def test_multi_answer_uses_first(self):
        text = "ANSWER: wrong\nMore thinking...\nANSWER: correct"
        assert _extract_answer_line(text) == "wrong"


class TestParseGptResponseMCSingle:
    def _make_qd(self, choices):
        return QuestionData(
            type="mc_single",
            question="Test question",
            choices=[{"label": c, "text": f"Choice {c}", "element": f"el_{c}"}
                     for c in choices],
        )

    def test_single_letter(self):
        qd = self._make_qd(["A", "B", "C"])
        action = parse_gpt_response("ANSWER: B", qd)
        assert action.type == "click"
        assert action.answer_text == "B"
        assert action.targets == ["el_B"]

    def test_letter_with_paren(self):
        qd = self._make_qd(["A", "B", "C"])
        action = parse_gpt_response("ANSWER: A)", qd)
        assert action.answer_text == "A"

    def test_chain_of_thought(self):
        qd = self._make_qd(["A", "B", "C", "D"])
        text = "The question asks about X.\nOption A is wrong because...\nOption C is correct.\nANSWER: C"
        action = parse_gpt_response(text, qd)
        assert action.answer_text == "C"
        assert action.targets == ["el_C"]

    def test_no_matching_choice(self):
        qd = self._make_qd(["A", "B"])
        action = parse_gpt_response("ANSWER: Z", qd)
        assert action.answer_text == "Z"
        assert action.targets == []


class TestParseGptResponseMCMulti:
    def test_multi_select(self):
        qd = QuestionData(
            type="mc_multi",
            question="Test",
            choices=[{"label": c, "text": f"Choice {c}", "element": f"el_{c}"}
                     for c in ["A", "B", "C", "D"]],
        )
        action = parse_gpt_response("ANSWER: A, C", qd)
        assert action.type == "multi_click"
        assert action.answer_text == "A, C"
        assert action.targets == ["el_A", "el_C"]


class TestParseGptResponseFill:
    def test_single_blank(self):
        qd = QuestionData(type="fill", question="Test ___", blank_count=1,
                          input_elements=["input1"])
        action = parse_gpt_response("ANSWER: mitosis", qd)
        assert action.type == "multi_type"
        assert action.values == ["mitosis"]

    def test_multi_blank_semicolons(self):
        qd = QuestionData(type="fill", question="Test ___ and ___", blank_count=2,
                          input_elements=["input1", "input2"])
        action = parse_gpt_response("ANSWER: cell; membrane", qd)
        assert action.values == ["cell", "membrane"]

    def test_multi_blank_pads_missing(self):
        qd = QuestionData(type="fill", question="Test", blank_count=3,
                          input_elements=["i1", "i2", "i3"])
        action = parse_gpt_response("ANSWER: only one", qd)
        assert len(action.values) == 3
        assert action.values[0] == "only one"
        assert action.values[1] == ""
        assert action.values[2] == ""


class TestParseGptResponseOrdering:
    def test_numbered_list(self):
        qd = QuestionData(type="ordering", question="Order these",
                          items=["Alpha", "Beta", "Gamma"])
        text = "1. Gamma\n2. Alpha\n3. Beta"
        action = parse_gpt_response(text, qd)
        assert action.type == "ordering"
        assert action.ordered_items == ["Gamma", "Alpha", "Beta"]

    def test_with_answer_prefix(self):
        qd = QuestionData(type="ordering", question="Order these",
                          items=["A", "B", "C"])
        text = "Thinking...\nANSWER:\n1. B\n2. C\n3. A"
        action = parse_gpt_response(text, qd)
        assert action.ordered_items == ["B", "C", "A"]


class TestParseGptResponseMatching:
    def test_arrow_format(self):
        qd = QuestionData(type="matching", question="Match",
                          sources=["Left1", "Left2"],
                          targets=["Right1", "Right2"])
        text = "Left1 -> Right2\nLeft2 -> Right1"
        action = parse_gpt_response(text, qd)
        assert action.type == "matching"
        assert len(action.matches) == 2
        assert action.matches[0] == {"source": "Left1", "target": "Right2"}
        assert action.matches[1] == {"source": "Left2", "target": "Right1"}


class TestParseGptResponseDropdown:
    def test_dropdown_parsing(self):
        qd = QuestionData(type="dropdown", question="Fill ___",
                          input_elements=["sel1", "sel2"],
                          choices=[{"options": ["a", "b"]}, {"options": ["c", "d"]}])
        action = parse_gpt_response("ANSWER: 1: b; 2: c", qd)
        assert action.type == "dropdown"
        assert action.values == ["b", "c"]


class TestBuildPrompt:
    def test_mc_single_has_choices(self):
        qd = QuestionData(type="mc_single", question="What is 2+2?",
                          choices=[{"label": "A", "text": "3"},
                                   {"label": "B", "text": "4"}])
        prompt = _build_prompt(qd)
        assert "A) 3" in prompt
        assert "B) 4" in prompt
        assert "ANSWER:" in prompt

    def test_context_appears_first(self):
        qd = QuestionData(type="mc_single", question="Test?",
                          context="Important passage here.",
                          choices=[{"label": "A", "text": "Yes"}])
        prompt = _build_prompt(qd)
        ctx_pos = prompt.find("Important passage here")
        q_pos = prompt.find("Question: Test?")
        assert ctx_pos < q_pos

    def test_fill_multi_blank(self):
        qd = QuestionData(type="fill", question="Fill ___ and ___", blank_count=2)
        prompt = _build_prompt(qd)
        assert "2 blanks" in prompt
        assert "semicolon" in prompt

    def test_ordering(self):
        qd = QuestionData(type="ordering", question="Order these",
                          items=["Alpha", "Beta"])
        prompt = _build_prompt(qd)
        assert "- Alpha" in prompt
        assert "- Beta" in prompt
        assert "correct order" in prompt.lower()
