"""
Spashta-CKG — Project Profile Validator

PURPOSE
-------
Validates that `project/profile.json` defines a valid configuration.

It ensures:
1. All referenced "languages" exist in `builders/`
2. All referenced "frameworks" exist in `adapters/`
3. The profile structure is parseable.

This script prevents "broken configuration" states where agents might try
to load non-existent tools.

USAGE
-----
python project/validation/validate_project_profile.py
"""


import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BUILDERS_DIR = BASE_DIR / "builders"
ADAPTERS_DIR = BASE_DIR / "adapters"
PROFILE_PATH = BASE_DIR / "project" / "profile.json"

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_profile():
    if not PROFILE_PATH.exists():
        print(f"Error: Profile not found at {PROFILE_PATH}")
        sys.exit(1)
        
    try:
        profile = load_json(PROFILE_PATH)
    except Exception as e:
        print(f"Error parsing profile: {e}")
        sys.exit(1)
        
    violations = []
    
    # Check Languages
    languages = profile.get("languages", [])
    for lang in languages:
        # Ignore empty
        if not lang: continue
        lang_path = BUILDERS_DIR / lang
        if not lang_path.is_dir():
            violations.append(f"Invalid Language: '{lang}' (No builder found at builders/{lang})")
            
    # Check Frameworks
    frameworks = profile.get("frameworks", [])
    for fw in frameworks:
        if not fw: continue
        fw_path = ADAPTERS_DIR / fw
        if not fw_path.is_dir():
            violations.append(f"Invalid Framework: '{fw}' (No adapter found at adapters/{fw})")
            
    if violations:
        print("Project Profile Validation FAILED:")
        for v in violations:
            print(f"- {v}")
        sys.exit(1)
    else:
        print("Project Profile Validation PASSED.")

if __name__ == "__main__":
    validate_profile()
