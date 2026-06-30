#!/usr/bin/env bash
# Pipe a command to the prose-overlay test queue.
#
# Requires the plugin to be loaded with PROSE_OVERLAY_TEST=1 set in the
# Talon process environment. See prose_overlay_test_driver.py for details.
#
# Usage:
#   scripts/test-overlay.sh show
#   scripts/test-overlay.sh add "hello world there"
#   scripts/test-overlay.sh dump
#   scripts/test-overlay.sh hide
#   scripts/test-overlay.sh undo
#   scripts/test-overlay.sh delete a            # delete gray-a
#   scripts/test-overlay.sh delete a blue       # delete blue-a
#   scripts/test-overlay.sh pre a               # cursor before gray-a
#   scripts/test-overlay.sh post a              # cursor after gray-a
#   scripts/test-overlay.sh change a            # change gray-a
#   scripts/test-overlay.sh confirm
#   scripts/test-overlay.sh homo on             # homophone hint on
#   scripts/test-overlay.sh homo off
#   scripts/test-overlay.sh clear-queue         # truncate queue file
#
# Convenience flags:
#   --tail N    after enqueueing, sleep 0.3 then tail N lines of the debug log
#   --json      print the JSON we wrote instead of dispatching
#
# Sequencing tip: each line in the queue is processed in order on the 200 ms
# cron tick, so pipelines work — just chain calls back-to-back. There's no
# acknowledgement signal; rely on the debug log to confirm state.

set -euo pipefail

QUEUE="$HOME/.talon/prose_overlay_test_queue.jsonl"
DEBUG_LOG="$HOME/.talon/prose_overlay_debug.jsonl"

usage() {
    sed -n '2,30p' "$0" | sed 's/^# \?//'
    exit "${1:-2}"
}

[[ $# -eq 0 ]] && usage

# Strip and capture optional flags
TAIL_LINES=""
JSON_ONLY=""
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tail) TAIL_LINES="$2"; shift 2 ;;
        --json) JSON_ONLY=1; shift ;;
        -h|--help) usage 0 ;;
        *) ARGS+=("$1"); shift ;;
    esac
done

set -- "${ARGS[@]}"
verb="${1:-}"
shift || true

case "$verb" in
    show)      json='{"cmd":"show"}' ;;
    hide)      json='{"cmd":"hide"}' ;;
    dump)      json='{"cmd":"dump"}' ;;
    undo)      json='{"cmd":"undo"}' ;;
    confirm)   json='{"cmd":"confirm"}' ;;
    clear-queue) json='{"cmd":"clear_queue"}' ;;
    add)
        [[ $# -ge 1 ]] || { echo "add requires text" >&2; exit 2; }
        text="$*"
        json=$(python3 -c 'import json,sys; print(json.dumps({"cmd":"add","text":sys.argv[1]}))' "$text")
        ;;
    delete|pre|post|change)
        case "$verb" in
            delete) cmd_name="delete_hat" ;;
            pre)    cmd_name="set_cursor_before_hat" ;;
            post)   cmd_name="set_cursor_after_hat" ;;
            change) cmd_name="change_hat" ;;
        esac
        [[ $# -ge 1 ]] || { echo "$verb requires letter [color]" >&2; exit 2; }
        letter="$1"; color="${2:-gray}"
        json=$(python3 -c 'import json,sys; print(json.dumps({"cmd":sys.argv[1],"letter":sys.argv[2],"color":sys.argv[3]}))' "$cmd_name" "$letter" "$color")
        ;;
    homo)
        [[ $# -ge 1 ]] || { echo "homo requires on|off" >&2; exit 2; }
        case "$1" in
            on)  json='{"cmd":"homophone_hint","enabled":true}' ;;
            off) json='{"cmd":"homophone_hint","enabled":false}' ;;
            *)   echo "homo: expected on|off" >&2; exit 2 ;;
        esac
        ;;
    *)
        echo "unknown verb: $verb" >&2
        usage 2
        ;;
esac

if [[ -n "$JSON_ONLY" ]]; then
    echo "$json"
    exit 0
fi

mkdir -p "$(dirname "$QUEUE")"
printf '%s\n' "$json" >> "$QUEUE"
echo "queued: $json"

if [[ -n "$TAIL_LINES" ]]; then
    sleep 0.3
    if [[ -f "$DEBUG_LOG" ]]; then
        tail -n "$TAIL_LINES" "$DEBUG_LOG" | python3 -m json.tool --json-lines
    else
        echo "(no debug log at $DEBUG_LOG yet)" >&2
    fi
fi
