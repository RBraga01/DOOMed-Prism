"""The closed voice command grammar (spec R15; the subset wired as of M3b
task 6 -- not the full M3 design §2 "In scope" list, which also names "next
weapon", "map", "save game"/"load game" and "exit Doom", deliberately
deferred per the plan). Matches only AsrStatus.TRANSCRIPT text --
EMPTY_OR_FAILURE and LOCAL_ERROR are preserved as two distinct AsrStatus
values for any future consumer that wants to branch on them, but
match_command itself currently treats both identically: either one returns
None, the same as an unmatched transcript. Don't read more into this
function than that -- if a caller needs to react differently to a
persistently broken backend (a stuck LOCAL_ERROR run), it must inspect
AsrResult.status directly rather than relying on match_command to surface it
(see VoiceWorker's consecutive-LOCAL_ERROR handling).
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

# Actions whose C-side key is state-polled (read from DOOM's gamekeydown[]
# inside G_BuildTiccmd) rather than edge-consumed. These need to be held
# across at least one built tic to be observed, so ActionRouter.pulse() (the
# existing PULSE_HOLD_TICS mechanism, patches/crispy-doom-ipc-input.diff's
# MT_PULSE case) must be used instead of .discrete()'s instantaneous
# keydown+keyup pair -- see the final-review fix brief's Critical 1/2 for the
# full root cause. USE and all seven weapon slots share this trap; PAUSE and
# the four MENU_* actions are edge-consumed and are fine with .discrete().
_PULSE_ACTIONS: frozenset[Action] = frozenset(
    {
        Action.USE,
        Action.WEAPON_1,
        Action.WEAPON_2,
        Action.WEAPON_3,
        Action.WEAPON_4,
        Action.WEAPON_5,
        Action.WEAPON_6,
        Action.WEAPON_7,
    }
)


def match_command(result: AsrResult) -> Action | None:
    if result.status is not AsrStatus.TRANSCRIPT:
        return None
    return _PHRASES.get(result.text.strip().lower())
