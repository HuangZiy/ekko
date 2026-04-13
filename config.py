from pathlib import Path

# Model
MODEL = "claude-opus-4-6"

# Paths
ARTIFACTS_DIR = Path(__file__).resolve().parent / ".harness"
SCREENSHOTS_DIR = ARTIFACTS_DIR / "screenshots"
SPECS_DIR = ARTIFACTS_DIR / "specs"
TASKS_DIR = ARTIFACTS_DIR / "tasks"

# Ralph Loop
MAX_RALPH_LOOPS = 30
MAX_TURNS_PER_LOOP = 150
MAX_BUDGET_PER_LOOP = 5.0  # USD per loop

# Ports — 3000 is reserved by system
EVAL_PORT = 3001       # Evaluator dev server
RALPH_PORT = 3002      # Generator (Ralph) dev server

# Evaluator
MAX_EVAL_ROUNDS = 3
EVAL_PASS_THRESHOLD = 7  # each dimension >= 7/10

# Planner
MAX_PLANNER_TURNS = 50

# Planning Agent (per-issue planning before generator)
MAX_PLANNING_TURNS = 30
MAX_PLANNING_BUDGET = 1.0  # USD per planning run
