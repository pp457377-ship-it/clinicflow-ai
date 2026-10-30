"""Rule-based safety layer.

These checks run on every intake BEFORE and AFTER the AI. If a red flag is
found the case is always marked as an emergency, whatever the AI says.
AI is helpful, but life-threatening symptoms must never depend on a model.
"""

import re
from typing import Dict, List

RED_FLAG_PATTERNS: Dict[str, List[str]] = {
    "Chest pain / possible heart attack": [
        r"chest (pain|tightness|pressure)", r"heart attack", r"pain (spreading|radiating) to (my )?(left )?arm",
    ],
    "Breathing difficulty": [
        r"can'?t breathe", r"cannot breathe", r"unable to breathe", r"difficulty breathing",
        r"struggling to breathe", r"gasping",
    ],
    "Possible stroke": [
        r"stroke", r"face (is )?droop", r"slurred speech", r"sudden (weakness|numbness)",
    ],
    "Loss of consciousness / seizure": [
        r"unconscious", r"passed out", r"fainted", r"seizure", r"fitting", r"convulsion",
    ],
    "Severe bleeding": [
        r"severe bleeding", r"won'?t stop bleeding", r"bleeding heavily", r"coughing (up )?blood", r"vomiting blood",
    ],
    "Severe allergic reaction": [
        r"anaphyla", r"throat (is )?(swelling|closing)", r"swollen (tongue|throat)",
    ],
    "Mental health crisis": [
        r"suicid", r"kill myself", r"end my life", r"self[- ]harm", r"overdose",
    ],
}

_COMPILED = {
    label: [re.compile(p, re.IGNORECASE) for p in patterns]
    for label, patterns in RED_FLAG_PATTERNS.items()
}

EMERGENCY_MESSAGE = (
    "Your symptoms may need emergency care. Please call 000 now or go to your nearest "
    "Emergency Department. Do not wait for a GP appointment."
)
CRISIS_MESSAGE = (
    "If you are thinking about harming yourself, please call 000 now, or Lifeline on 13 11 14 (24/7)."
)


def detect_red_flags(text: str) -> List[str]:
    """Return the list of red-flag categories found in the text."""
    return [label for label, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)]
