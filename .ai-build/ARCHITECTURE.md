# ARCHITECTURE

Single deployable Python service.

- FastAPI: API + static UI
- SQLite: local run/packs persistence
- `providers.py`: heuristic, OpenAI-compatible, webhook adapters
- `graders.py`: deterministic JSON field graders + critical mismatch rules
- `runner.py`: bounded concurrent execution + business metrics
- `compare.py`: paired baseline/candidate analysis, Wilson intervals, exact McNemar test and release recommendation
- `builtin_packs.py`: bundled deterministic 100-case fraud arena
- `web/`: zero-build frontend

This intentionally avoids a JavaScript build chain for the MVP. One command should boot the product.
