#!/bin/bash

# Detect if any commands failed.
# https://stackoverflow.com/a/42219754
err=0
trap 'err=1' ERR

python3 ../hammer-vlsi/test.py
python3 ../hammer-vlsi/tech_test.py
python3 ../hammer-vlsi/constraints_test.py
python3 ../hammer-vlsi/cli_driver_test.py
python3 ../hammer-vlsi/utils_test.py
python3 ../hammer-vlsi/units_test.py
python3 ../hammer-vlsi/verilog_utils_test.py
python3 ../hammer-vlsi/spice_utils_test.py
python3 ../hammer-vlsi/lef_utils_test.py
python3 ../hammer_config_test/test.py

test $err = 0 # Return non-zero if any command failed
