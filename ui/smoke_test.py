"""Headless render check for the dashboard — runs every page through Streamlit's
AppTest harness and fails (exit 1) if any page raises.

Usage:  python ui/smoke_test.py
Used by CI (.github/workflows/ui-check.yml) to catch UI regressions on push.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

PAGES = ["Takeaways", "Objections", "Scripts", "Action items", "Calls",
         "Call detail", "Run pipeline"]
APP = str(REPO_ROOT / "ui" / "app.py")


def main() -> int:
    failures = []
    for page in PAGES:
        at = AppTest.from_file(APP, default_timeout=90)
        at.session_state["_nav"] = page
        at.run()
        if at.exception:
            failures.append((page, str(at.exception[0])[:300]))
            print(f"FAIL  {page}: {failures[-1][1]}")
        else:
            print(f"OK    {page}")
    if failures:
        print(f"\n{len(failures)} page(s) failed.")
        return 1
    print(f"\nAll {len(PAGES)} pages rendered without exceptions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
