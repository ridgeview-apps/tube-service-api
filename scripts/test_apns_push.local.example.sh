#!/usr/bin/env bash
# Copy this file to test_apns_push.local.sh, replace the placeholders, and run
# it. The .local.sh copy is ignored by Git.

export TUBE_API_URL="https://YOUR_API_DOMAIN"
export TUBE_API_KEY="ios.REPLACE_WITH_FULL_API_KEY"
export TUBE_DEVICE_ID="REPLACE_WITH_REGISTERED_IOS_DEVICE_ID"

exec "$(dirname "$0")/test_apns_push.sh"
