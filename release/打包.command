#!/bin/bash
cd "$(dirname "$0")/.."
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi
"$PY" release/pack.py
status=$?
echo
if [ $status -eq 0 ]; then
  echo "Done."
else
  echo "Failed ($status)."
fi
read -r -p "Press Enter to close..."
exit $status
