#!/bin/bash
# Precompile the board's code into CIRCUITPY_MPY/ (the board then skips compiling,
# which is what uses the most memory at startup).
#   bash scripts/build_mpy.sh path/to/mpy-cross
# mpy-cross must match the board's CircuitPython (10.x): Adafruit publishes it at
# https://adafruit-circuit-python.s3.amazonaws.com/index.html?prefix=bin/mpy-cross/
# Run it again after every change to a CIRCUITPY/chatty_*.py file (the tests check).
set -e
MPY_CROSS="${1:-mpy-cross}"
cd "$(dirname "$0")/.."
rm -rf CIRCUITPY_MPY
mkdir CIRCUITPY_MPY
cp CIRCUITPY/code.py CIRCUITPY_MPY/
for f in CIRCUITPY/chatty_*.py; do
    "$MPY_CROSS" -O1 -o "CIRCUITPY_MPY/$(basename "${f%.py}").mpy" "$f"
done
python3 scripts/mpy_sources.py > CIRCUITPY_MPY/sources.txt
"$MPY_CROSS" --version | head -1
ls CIRCUITPY_MPY
