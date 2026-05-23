# prose-overlay — Project Rules

## Source of Truth

All edits happen in `~/code/prose-overlay/`. The live Talon plugin lives at:

```
~/.talon/user/trillium_talon/trillium/plugin/prose_overlay/
```

Do NOT edit the Talon path directly. Do NOT symlink it.

## Sync Workflow

Run this before editing (keep alive in a terminal):

```bash
bun ~/code/prose-overlay/scripts/sync-to-talon.ts
```

The watcher rsyncs any changed file into the Talon plugin directory within 150ms. Talon hot-reloads from there.

## Verify Load

```bash
bun ~/.talon/tools/talon-check-reload.ts \
  ~/.talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_draw.py \
  ~/.talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay.py
```

Expected: `LOADED` for both files.
