#!/usr/bin/env bun
/**
 * gen-command-table.ts
 * Prints a markdown command-reference table for prose overlay.
 *
 * Usage:
 *   bun scripts/gen-command-table.ts
 *   bun scripts/gen-command-table.ts >> README.md
 */

type Row = { genre: string; command: string; hint: string };

const COMMANDS: Row[] = [
  // ── Global (always available) ────────────────────────────────────────────
  { genre: "Global",   command: "`prose overlay`",       hint: "Open the overlay" },
  { genre: "Global",   command: "`overlay auto`",         hint: "Toggle auto-dictation mode" },
  { genre: "Global",   command: "`prose history`",        hint: "Toggle history panel" },
  { genre: "Global",   command: "`overlay top`",          hint: "Attach panel to top of window" },
  { genre: "Global",   command: "`overlay bottom`",       hint: "Attach panel to bottom of window" },

  // ── Confirm / dismiss ────────────────────────────────────────────────────
  { genre: "Confirm",  command: "`bravely`",              hint: "Confirm and paste to target window" },
  { genre: "Confirm",  command: "`<prose> bravely`",      hint: "Append prose then confirm" },
  { genre: "Confirm",  command: "`<window> bravely`",     hint: "Retarget window then confirm" },
  { genre: "Confirm",  command: "`overlay dismiss`",      hint: "Dismiss without pasting" },

  // ── Dictation ────────────────────────────────────────────────────────────
  { genre: "Dictation", command: "`<prose>`",             hint: "Append spoken text to buffer" },
  { genre: "Dictation", command: "`<window> <prose>`",    hint: "Focus window then append prose" },
  { genre: "Dictation", command: "`{symbol}`",            hint: "Route symbol key into buffer" },

  // ── Delete ───────────────────────────────────────────────────────────────
  { genre: "Delete",   command: "`chuck <hat>`",          hint: "Delete word at hat" },
  { genre: "Delete",   command: "`chuck past <hat>`",     hint: "Delete hat through end of buffer" },
  { genre: "Delete",   command: "`chuck head <hat>`",     hint: "Delete start of buffer through hat" },
  { genre: "Delete",   command: "`chuck tail <hat>`",     hint: "Delete hat through end of buffer" },

  // ── Cursor ───────────────────────────────────────────────────────────────
  { genre: "Cursor",   command: "`pre <hat>`",            hint: "Move insertion cursor before hat" },
  { genre: "Cursor",   command: "`post <hat>`",           hint: "Move insertion cursor after hat" },
  { genre: "Cursor",   command: "`pre file`",             hint: "Move cursor to start of buffer" },
  { genre: "Cursor",   command: "`post file`",            hint: "Move cursor to end of buffer" },

  // ── Edit ─────────────────────────────────────────────────────────────────
  { genre: "Edit",     command: "`change <hat>`",         hint: "Delete word at hat, enter insert mode" },
  { genre: "Edit",     command: "`change head <hat>`",    hint: "Delete start→hat, enter insert mode" },
  { genre: "Edit",     command: "`change tail <hat>`",    hint: "Delete hat→end, enter insert mode" },
  { genre: "Edit",     command: "`change <hat> <prose>`", hint: "Delete word, insert replacement prose" },
  { genre: "Edit",     command: "`pre <hat> <prose>`",    hint: "Set cursor before hat, insert prose" },
  { genre: "Edit",     command: "`post <hat> <prose>`",   hint: "Set cursor after hat, insert prose" },
  { genre: "Edit",     command: "`overlay undo`",         hint: "Undo last buffer edit" },

  // ── Move / copy ──────────────────────────────────────────────────────────
  { genre: "Move",     command: "`bring <hat> to <hat>`", hint: "Copy word at src to dst position" },
  { genre: "Move",     command: "`move <hat> to <hat>`",  hint: "Cut word at src, replace dst" },

  // ── Hat colors ───────────────────────────────────────────────────────────
  { genre: "Colors",   command: "`chuck <color> <hat>`",  hint: "Target a colored hat (collision avoidance)" },
  { genre: "Colors",   command: "`pre <color> <hat>`",    hint: "Cursor before colored hat" },
  { genre: "Colors",   command: "`change <color> <hat>`", hint: "Edit at colored hat" },

  // ── Overlay controls ─────────────────────────────────────────────────────
  { genre: "Controls", command: "`overlay speak`",        hint: "Read buffer aloud via TTS" },
  { genre: "Controls", command: "`overlay help`",         hint: "Toggle paginated help panel" },
  { genre: "Controls", command: "`overlay anchor`",       hint: "Scope panel to current window width" },
  { genre: "Controls", command: "`overlay anchor clear`", hint: "Full-screen panel (no window scope)" },

  // ── History ──────────────────────────────────────────────────────────────
  { genre: "History",  command: "`prose history`",        hint: "Show/hide history panel (last 50 phrases)" },
  { genre: "History",  command: "`history next`",         hint: "Next history page" },
  { genre: "History",  command: "`history back`",         hint: "Previous history page" },
  { genre: "History",  command: "`history pick <N>`",     hint: "Load history entry N into buffer" },
];

function pad(s: string, n: number): string {
  return s + " ".repeat(Math.max(0, n - s.length));
}

function renderTable(rows: Row[]): string {
  const genres   = rows.map(r => r.genre);
  const commands = rows.map(r => r.command);
  const hints    = rows.map(r => r.hint);

  const gw = Math.max(5,  ...genres.map(s => s.length));
  const cw = Math.max(7,  ...commands.map(s => s.length));
  const hw = Math.max(4,  ...hints.map(s => s.length));

  const sep = `| ${"-".repeat(gw)} | ${"-".repeat(cw)} | ${"-".repeat(hw)} |`;
  const header = `| ${pad("Genre", gw)} | ${pad("Command", cw)} | ${pad("Hint", hw)} |`;

  const lines = [header, sep];
  let lastGenre = "";
  for (const row of rows) {
    const genre = row.genre === lastGenre ? "" : row.genre;
    lastGenre = row.genre;
    lines.push(`| ${pad(genre, gw)} | ${pad(row.command, cw)} | ${pad(row.hint, hw)} |`);
  }
  return lines.join("\n");
}

console.log(renderTable(COMMANDS));
