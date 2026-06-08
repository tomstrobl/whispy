"""Example runner for the NAFC scaffold.

Run this from the repo root to open a single N-AFC trial window.
This is a minimal demo to exercise the scaffold; use a proper ExperimentScheduler
screen for real experiments.
"""

from whispy.ui import NAFC

if __name__ == '__main__':
    screen = {
        "block": 0,
        "section": 0,
        "test": [1, 2, 3, 4],
        "correct": 2,
        "trial_id": 1,
        "block_changed": True,
        "section_changed": True,
        "block_name": "Demo",
        "section_name": "Demo Section",
    }

    naf = NAFC(screen=screen, blocking=True, debug=True)
    results = naf.get_results()
    print(results)

