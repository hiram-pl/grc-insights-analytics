#!/bin/zsh
# Install (or reinstall) the weekly refresh as a launchd job for the current user.
#
#   zsh ops/install_schedule.sh            # install / update, then load it
#   zsh ops/install_schedule.sh --remove   # unload and delete it
#
# Useful commands afterwards:
#   launchctl kickstart gui/$(id -u)/com.grc.insights.refresh   # run it now
#   launchctl print gui/$(id -u)/com.grc.insights.refresh       # status, last exit code
#   tail ~/Library/Logs/grc-insights-refresh.log                # launchd-level output
set -euo pipefail

LABEL=com.grc.insights.refresh
REPO=${0:A:h:h}                                  # this script's folder's parent = repo root
PYTHON=${PYTHON:-$(command -v python3)}          # override: PYTHON=/path/to/python3 zsh ops/...
DEST=~/Library/LaunchAgents/$LABEL.plist
DOMAIN=gui/$(id -u)

# Stop the old job if one is loaded (ignore "not loaded" errors).
launchctl bootout $DOMAIN/$LABEL 2>/dev/null || true

if [[ ${1:-} == --remove ]]; then
  rm -f $DEST
  echo "Removed $LABEL."
  exit 0
fi

mkdir -p ~/Library/LaunchAgents ~/Library/Logs
sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__PYDIR__|${PYTHON:h}|g" \
    -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" \
    $REPO/ops/$LABEL.plist > $DEST
plutil -lint $DEST >/dev/null                    # fail loudly on a malformed plist
launchctl bootstrap $DOMAIN $DEST

echo "Installed $LABEL: every Monday 08:00"
echo "  python: $PYTHON"
echo "  repo:   $REPO"
echo "Test it now: launchctl kickstart $DOMAIN/$LABEL"
