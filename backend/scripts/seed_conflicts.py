from __future__ import annotations

from backend.app.conflicts import seed_demo_conflicts
from backend.app.database import initialize_database


def main() -> None:
    initialize_database()
    records = seed_demo_conflicts()
    print(f"Conflict log contains {len(records)} seeded demo records.")


if __name__ == "__main__":
    main()
