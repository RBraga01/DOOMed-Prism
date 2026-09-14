from __future__ import annotations

from pewpew.input.actions import Action
from pewpew.voice.asr import AsrResult, AsrStatus
from pewpew.voice.grammar import match_command


def test_matches_each_wired_phrase_to_its_action() -> None:
    cases = {
        "use": Action.USE,
        "open": Action.USE,
        "weapon one": Action.WEAPON_1,
        "weapon seven": Action.WEAPON_7,
        "pause": Action.PAUSE,
        "resume": Action.PAUSE,
        "menu up": Action.MENU_UP,
        "menu down": Action.MENU_DOWN,
        "confirm": Action.MENU_CONFIRM,
        "cancel": Action.MENU_CANCEL,
    }
    for phrase, action in cases.items():
        result = AsrResult(AsrStatus.TRANSCRIPT, phrase)
        assert match_command(result) is action


def test_matching_is_case_and_whitespace_insensitive() -> None:
    result = AsrResult(AsrStatus.TRANSCRIPT, "  Weapon One  ")
    assert match_command(result) is Action.WEAPON_1


def test_unrecognized_transcript_matches_nothing() -> None:
    result = AsrResult(AsrStatus.TRANSCRIPT, "what time is it")
    assert match_command(result) is None


def test_empty_or_failure_and_local_error_both_match_nothing_but_are_not_the_same_input() -> None:
    empty_or_failure = AsrResult(AsrStatus.EMPTY_OR_FAILURE)
    local_error = AsrResult(AsrStatus.LOCAL_ERROR)
    # Two genuinely different inputs, asserted separately, so a future change
    # that special-cases one without the other is caught here -- not merged
    # into one assertion that would hide that distinction.
    assert match_command(empty_or_failure) is None
    assert match_command(local_error) is None
