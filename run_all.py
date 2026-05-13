import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from generate_data import main as phase1
from pipeline import run_pipeline as phase2
from alerts import run_alerts as phase3


def main():
    print("=" * 65)
    print("  PMO TRACKER: Burn-Rate & Risk Alert System")
    print("=" * 65)

    print("\n-- Phase 1: Data Simulation --")
    phase1()

    print("\n-- Phase 2: Processing Pipeline --")
    phase2()

    print("\n-- Phase 3: Burn-Rate Engine & Alerts --")
    phase3()

    print("\n" + "=" * 65)
    print("  All phases complete.")
    print("  Output files in /output/ -- import to Power BI")
    print("=" * 65)


if __name__ == "__main__":
    main()
