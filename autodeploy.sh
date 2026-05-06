#!/bin/bash
REPO=/root/mytestbot

cd "$REPO" || exit 1
BEFORE=$(git rev-parse HEAD)
git pull --quiet
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" != "$AFTER" ]; then
    "$REPO/venv/bin/pip" install -q -r requirements.txt
    if [ -f "$REPO/mybot.service" ]; then
        cp "$REPO/mybot.service" /etc/systemd/system/mybot.service
        systemctl daemon-reload
    fi
    systemctl restart mybot.service
fi
