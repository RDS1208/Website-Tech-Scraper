from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
RULES_DIR = PROJECT_DIR / "rules"
RULES_PATH = RULES_DIR / "rules.json"
TECHNOLOGY_GROUPS_PATH = RULES_DIR / "technology_groups.json"
RESULTS_DIR = PROJECT_DIR / "results"
RESULTS_PATH = RESULTS_DIR / "results.json"
CHECKPOINT_PATH = RESULTS_DIR / "results.partial.tmp"
