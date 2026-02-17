"""CSS selectors for SmartBook DOM elements.

Extracted from parser.py so selectors can be updated independently
from parsing logic. All values are CSS selector strings.
"""

SELECTORS: dict[str, str] = {
    # Question elements
    "question_prompt": ".prompt",
    "responses_container": ".responses-container",
    "question_fieldset": ".multiple-choice-fieldset, .true-false-fieldset",
    "choice_row": ".choice-row",
    "choice_radio": "input.form-check-input[type='radio']",
    "choice_checkbox": "input.form-check-input[type='checkbox']",
    "choice_text": ".choiceText",
    "choice_clickable": ".choice",

    # Fill-in-the-blank
    "text_input": "input[type='text'], textarea, input.form-control, input.fitb-input",
    "dropdown_select": "select, select.form-select",
    "blank_indicator": "span._visuallyHidden",

    # Ordering (sortable) questions — uses react-beautiful-dnd
    "sortable_component": ".sortable-component, [class*='probe-type-sortable']",
    "sortable_item": ".sortable-component .responses-container "
                     ".choice-item[data-react-beautiful-dnd-draggable]",
    "sortable_item_text": ".content p",

    # Matching (drag-to-match) questions
    "matching_component": ".matching-component, [class*='probe-type-matching'], "
                          "[class*='probe-type-categorize']",
    "matching_label": ".matching-component .match-row .match-prompt-label .content p",
    "matching_drop_zone": ".matching-component .match-row .match-single-response-wrapper",
    "matching_choice": ".matching-component .choices-container .choice-item-wrapper",
    "matching_choice_text": ".content p",

    # Confidence buttons (these act as submit + next)
    "confidence_container": "awd-confidence-buttons, .confidence-buttons-container",
    "confidence_high": "button.btn-confidence:nth-child(1)",
    "confidence_medium": "button.btn-confidence:nth-child(2)",
    "confidence_low": "button.btn-confidence:nth-child(3)",
    "confidence_any": "button.btn-confidence",

    # Reading button
    "reading_button": "button.reading-button",

    # Concept resource / recharge page
    "recharge_tray_button": "button[data-automation-id='lr-tray_button'], "
                            "button.lr-tray-expand-button",
    "read_about_concept": ".lr__action-label",
    "to_questions_button": "button[data-automation-id='reading-questions-button']",

    # Page type indicators
    "complete_indicator": "[class*='score-summary'], [class*='assignment-complete'], "
                          "[class*='completion'], [class*='results-container']",
    "loading_spinner": "[class*='spinner'], .loader, [class*='loading-indicator']",

    # Navigation bar (always present during questions)
    "nav_bar": "awd-navigation-bar, .main-container__navigation-bar",

    # Next Question button (appears after answering)
    "next_question": "button.next-button, button.btn-primary.next-button",

    # Continue button (intermediate content pages)
    "continue_button": "button:contains('Continue'), button.btn-primary:contains('Continue')",
}
