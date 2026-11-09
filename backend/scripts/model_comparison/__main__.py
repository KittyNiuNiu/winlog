"""`uv run --env-file ../.env python -m scripts.model_comparison ...` (run in `backend/`)."""

import sys

from scripts.model_comparison.comparison import main

sys.exit(main())
