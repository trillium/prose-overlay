#!/usr/bin/env bun
/**
 * sync-to-talon.ts
 *
 * Bidirectional watcher between ~/code/prose-overlay/ (git-tracked source)
 * and the live Talon plugin directory.
 *
 * SRC → DST: any edit in ~/code/prose-overlay/ is pushed to Talon immediately
 * DST → SRC: any edit in the Talon dir is pulled back to the git-tracked source
 *
 * Loop prevention: after syncing in one direction, a 1s cooldown suppresses
 * the echo change event from the destination write.
 *
 * Usage:
 *   bun scripts/sync-to-talon.ts
 */

import { watch } from "fs";
import { execSync } from "child_process";
import { resolve } from "path";

const SRC = resolve(import.meta.dir, "..");
const DST = `${process.env.HOME}/.talon/user/trillium_talon/trillium/plugin/prose_overlay`;

const EXCLUDE = [
  "--exclude=scripts/",
  "--exclude=README.md",
  "--exclude=CLAUDE.md",
  "--exclude=CURSORLESS_REIMPLEMENTATIONS.md",
  "--exclude=CURSORLESS_DEPENDENCIES.md",
  "--exclude=CURSORLESS_CAPABILITY_TRACKER.md",
  "--exclude=.git/",
  "--exclude=__pycache__/",
  "--exclude=*.pyc",
  "--exclude=.gitignore",
  "--exclude=prose_overlay_prefs.json",
];

function timestamp() {
  return new Date().toLocaleTimeString("en-US", { hour12: false });
}

function isExcluded(filename: string): boolean {
  return (
    filename.includes("__pycache__") ||
    filename.endsWith(".pyc") ||
    filename.startsWith("scripts/") ||
    filename === "prose_overlay_prefs.json" ||
    filename === "README.md" ||
    filename === "CLAUDE.md" ||
    filename === "CURSORLESS_REIMPLEMENTATIONS.md" ||
    filename === "CURSORLESS_DEPENDENCIES.md" ||
    filename === "CURSORLESS_CAPABILITY_TRACKER.md"
  );
}

// Cooldown map: direction → last sync timestamp (ms)
// Prevents echo: if we just pushed SRC→DST, ignore the DST change event for 1s
const lastSync: Record<"src-to-dst" | "dst-to-src", number> = {
  "src-to-dst": 0,
  "dst-to-src": 0,
};
const COOLDOWN_MS = 1000;

function syncSrcToDst(reason: string) {
  lastSync["src-to-dst"] = Date.now();
  try {
    execSync(`rsync -a --checksum ${EXCLUDE.join(" ")} "${SRC}/" "${DST}/"`, { stdio: "pipe" });
    console.log(`[→ talon  ${timestamp()}] ${reason}`);
  } catch (e: any) {
    console.error(`[→ talon  ${timestamp()}] FAILED (${reason}): ${e.message}`);
  }
}

function syncDstToSrc(reason: string) {
  lastSync["dst-to-src"] = Date.now();
  try {
    execSync(`rsync -a --checksum ${EXCLUDE.join(" ")} "${DST}/" "${SRC}/"`, { stdio: "pipe" });
    console.log(`[← source ${timestamp()}] ${reason}`);
  } catch (e: any) {
    console.error(`[← source ${timestamp()}] FAILED (${reason}): ${e.message}`);
  }
}

// Initial sync: SRC is canonical on start
syncSrcToDst("initial");

// Watch SRC → push to DST
let srcDebounce: Timer | null = null;
watch(SRC, { recursive: true }, (_, filename) => {
  if (!filename || isExcluded(filename)) return;
  if (Date.now() - lastSync["dst-to-src"] < COOLDOWN_MS) return; // echo from DST write
  if (srcDebounce) clearTimeout(srcDebounce);
  srcDebounce = setTimeout(() => syncSrcToDst(filename), 150);
});

// Watch DST → pull back to SRC
let dstDebounce: Timer | null = null;
watch(DST, { recursive: true }, (_, filename) => {
  if (!filename || isExcluded(filename)) return;
  if (Date.now() - lastSync["src-to-dst"] < COOLDOWN_MS) return; // echo from SRC write
  if (dstDebounce) clearTimeout(dstDebounce);
  dstDebounce = setTimeout(() => syncDstToSrc(filename), 150);
});

console.log(`[sync] source  ${SRC}`);
console.log(`[sync] talon   ${DST}`);
console.log(`[sync] bidirectional — cooldown ${COOLDOWN_MS}ms`);
