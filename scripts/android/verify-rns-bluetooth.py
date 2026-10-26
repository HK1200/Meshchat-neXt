#!/usr/bin/env python3

import sys
import zipfile
from pathlib import Path

if len(sys.argv) != 2:
    sys.exit("Usage: verify-rns-bluetooth.py <path-to-rns-wheel>")

wheel = Path(sys.argv[1])

target = "RNS/Interfaces/Android/RNodeInterface.py"

print("===== RNS BLUETOOTH VERIFICATION =====")
print("Wheel:", wheel)

if not wheel.is_file():
    sys.exit("FAIL: RNS wheel not found")

try:
    with zipfile.ZipFile(wheel) as archive:
        source = archive.read(target).decode("utf-8")
except (OSError, KeyError, zipfile.BadZipFile, UnicodeError) as error:
    sys.exit(f"FAIL: Cannot inspect RNodeInterface: {error}")

checks = {
    "Paired Bluetooth devices converted to Python list": "return list(devices.toArray())"
    in source,
    "Bluetooth enumeration exception handling": "Could not query paired Bluetooth devices:"
    in source,
    "Bluetooth adapter exception handling": "adapter = self.bt_adapter.getDefaultAdapter()"
    in source
    and "return adapter != None and adapter.isEnabled()" in source,
}

for description, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {description}")

if not all(checks.values()):
    sys.exit(1)

print()
print("SUCCESS: Expected Android Bluetooth fixes are present.")
