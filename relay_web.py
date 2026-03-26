#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from relay_hub.web import serve


DEFAULT_ROOT = Path(__file__).resolve().parent / "runtime"


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay Hub local web entry")
    parser.add_argument("--root", help="Relay root directory. Defaults to relay-hub/runtime.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4317)
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve() if args.root else DEFAULT_ROOT
    serve(root=root, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
