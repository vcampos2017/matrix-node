"""Fingerprints of the .py files CIRCUITPY_MPY/ was built from (tests compare them)."""
import glob
import hashlib
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def fingerprints():
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "CIRCUITPY", "chatty_*.py"))):
        with open(path, "rb") as f:
            out.append(os.path.basename(path) + " " + hashlib.sha256(f.read()).hexdigest()[:16])
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    print(fingerprints(), end="")
