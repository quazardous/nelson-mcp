#!/bin/bash
# Clear all Nelson log files in every known location.
# Filenames: nelson_debug.log, nelson_agent.log (see core/logging.py).

LO="${HOME}/.config/libreoffice"
rm -f \
  "${HOME}/nelson_debug.log" \
  "${HOME}/nelson_agent.log" \
  "${LO}/4/user/nelson_debug.log" \
  "${LO}/4/user/nelson_agent.log" \
  "${LO}/4/user/config/nelson_debug.log" \
  "${LO}/4/user/config/nelson_agent.log" \
  "${LO}/24/user/nelson_debug.log" \
  "${LO}/24/user/nelson_agent.log" \
  "${LO}/24/user/config/nelson_debug.log" \
  "${LO}/24/user/config/nelson_agent.log"
echo "Logs deleted."
