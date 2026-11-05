#!/bin/sh
# Writes the runtime config so one image works in every environment.
set -e
printf 'window.SLIPCAST_CONFIG = { apiUrl: "%s" };\n' "${API_URL:-http://localhost:8000}" \
  > /usr/share/nginx/html/config.js
