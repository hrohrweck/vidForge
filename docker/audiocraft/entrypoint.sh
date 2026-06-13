#!/bin/sh
set -e

# The directories mounted as Docker volumes may be reused across image
# rebuilds. Their ownership can then differ from the non-root container user,
# which breaks:
#   - numba's JIT cache (NUMBA_CACHE_DIR must be writable)
#   - writing generated audio files to /app/output
# Fix ownership on startup before dropping privileges.
chown -R vidforge:vidforge /app/hf_cache /app/output /shared-storage 2>/dev/null || true

mkdir -p /app/hf_cache/numba
chown -R vidforge:vidforge /app/hf_cache/numba

exec setpriv --reuid=vidforge --regid=vidforge --init-groups -- python /app/server.py
