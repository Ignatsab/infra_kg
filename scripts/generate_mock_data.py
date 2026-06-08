#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.mock_data import write_mock_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate connected mock APM CSV tables.")
    parser.add_argument("--output-dir", default="data/mock", help="Directory for generated CSV files.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    write_mock_data(output_dir)
    print(f"Wrote mock APM tables to {output_dir}")


if __name__ == "__main__":
    main()
