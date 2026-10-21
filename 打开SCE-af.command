#!/bin/bash
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  echo "Packed .venv is missing or not for this Mac. Running setup_env.py ..."
  python3 setup_env.py || {
    echo "Failed to create .venv. Install Python 3.10+."
    read -r -p "Press Enter to close..."
    exit 1
  }
  PY=".venv/bin/python"
else
  echo "No usable Python. Install Python 3.10+."
  read -r -p "Press Enter to close..."
  exit 1
fi
"$PY" run.py
status=$?
echo
if [ $status -eq 0 ]; then
  echo "Done."
else
  echo "Failed ($status). If .venv came from another OS, run setup.command."
fi
read -r -p "Press Enter to close..."
exit $status
