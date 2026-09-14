"""The closed voice command grammar (spec R15 / M3 design §2's "In scope"
list). Matches only AsrStatus.TRANSCRIPT text -- EMPTY_OR_FAILURE and
LOCAL_ERROR both resolve to "no command", but as two distinct inputs, never
merged into a single "not a transcript" branch, so a later change to one
cannot silently change the other (spec R15's ambiguity-preservation rule).
"""

from __future__ import annotations

from pewpew.input.actions import Action
from pewpew.voice.asr import AsrResult, AsrStatus

# Only phrases whose Action is actually wired into the C patch (task 5) are
# listed here. An unreachable phrase would match and then silently do
# nothing, which is worse than not recognizing it yet.
_PHRASES: dict[str, Action] = {
    "use": Action.USE,
    "open": Action.USE,
    "weapon one": Action.WEAPON_1,
    "weapon two": Action.WEAPON_2,
    "weapon three": Action.WEAPON_3,
    "weapon four": Action.WEAPON_4,
    "weapon five": Action.WEAPON_5,
    "weapon six": Action.WEAPON_6,
    "weapon seven": Action.WEAPON_7,
    "pause": Action.PAUSE,
    "resume": Action.PAUSE,
    "menu up": Action.MENU_UP,
    "menu down": Action.MENU_DOWN,
    "confirm": Action.MENU_CONFIRM,
    "cancel": Action.MENU_CANCEL,
}


def match_command(result: AsrResult) -> Action | None:
    if result.status is not AsrStatus.TRANSCRIPT:
        return None
    return _PHRASES.get(result.text.strip().lower())
