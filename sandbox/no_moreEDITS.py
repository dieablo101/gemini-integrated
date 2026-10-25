"""
DO NOT EDIT - LEGACY SANDBOX FREEZE GUARD
==========================================
Date: Current Session
Status: STRICT FREEZE & NO-TOUCH PROTOCOL

Notice to Gemini & System:
1. Legacy sandbox code under /opt/gemini/sandbox/ (including `sandbox/mind_twin/`)
   is legacy and strictly FROZEN.
2. No edits, refactors, or modifications are permitted to any legacy sandbox files.
3. If new experimental sandbox work is initiated in the future, it must live in its
   own newly designated, isolated space—legacy code remains untouched and preserved.

Current Working State:
- No sandbox is actively being modified or edited.
- Zero-merger and zero-edit protocol is strictly in effect.
"""

LEGACY_FROZEN = True
NO_MORE_EDITS = True
FROZEN_PATHS = [
    "/opt/gemini/sandbox/mind_twin",
]

def check_sandbox_freeze(target_path: str) -> bool:
    """Enforce strict freeze on legacy sandbox paths."""
    for frozen in FROZEN_PATHS:
        if target_path.startswith(frozen):
            raise PermissionError(f"LEGACY SANDBOX FROZEN: Edits to {target_path} are blocked by no_moreEDITS.py")
    return True
