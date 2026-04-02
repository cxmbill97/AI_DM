"""Shim so `python -m eval.run` works in addition to `python -m eval`."""

from eval.__main__ import main

if __name__ == "__main__":
    main()
