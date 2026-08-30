"""
Spashta-CKG — Project Context Loader

PURPOSE
-------
Provides a standard entry point for Agents and tools to discover
the active project configuration.

This module reads project/profile.json to determine:
- Which languages (builders) are active
- Which frameworks (adapters) are active

It performs no validation and applies no interpretation.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_PATH = BASE_DIR / "project" / "profile.json"

def load_project_profile() -> Optional[Dict[str, Any]]:
    """
    Loads the project profile configuration.
    Returns None if profile.json is missing or invalid.
    """
    if not PROFILE_PATH.exists():
        return None
        
    try:
        with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        # Silently fail for library usage; validation is separate.
        return None

if __name__ == "__main__":
    profile = load_project_profile()
    if profile:
        print("Active Project Profile:")
        print(json.dumps(profile, indent=2))
    else:
        print("No active project profile found.")
