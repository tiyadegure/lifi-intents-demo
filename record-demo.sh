#!/bin/bash
# Record the LI.FI Intents demo with asciinema
# Usage: bash record-demo.sh
# Output: recordings/demo.cast

set -e
cd "$(dirname "$0")"

CAST_FILE="recordings/demo.cast"
DEMO_SCRIPT="demo/record_demo.py"

echo "🎬 Recording LI.FI Intents Demo..."
echo "   Output: $CAST_FILE"
echo ""

# Remove old recording
rm -f "$CAST_FILE"

# Record with asciinema
# --cols/--rows match the terminal size for consistent rendering
# -c runs the demo command directly
asciinema rec "$CAST_FILE" \
  --command "python3 $DEMO_SCRIPT" \
  --cols 120 \
  --rows 40 \
  --title "LI.FI Intents × AI Agent Demo" \
  --idle-time-limit 2

echo ""
echo "✅ Recording saved to $CAST_FILE"
echo ""
echo "Next steps:"
echo "  1. Preview:  asciinema play $CAST_FILE"
echo "  2. Convert:  asciinema-agg $CAST_FILE recordings/demo.svg"
echo "  3. Embed:    Copy .cast to remotion/public/recordings/"
