#!/usr/bin/env bun
/**
 * build-js.ts
 *
 * Builds the prose-overlay QuickJS bundles from cursorless source.
 *
 *   bun scripts/build-js.ts targets    # prose_resolve_targets.js  (target/scope resolver)
 *   bun scripts/build-js.ts hats       # prose_allocate_hats.js    (hat allocator)
 *   bun scripts/build-js.ts actions    # prose_actions.js          (action geometries)
 *   bun scripts/build-js.ts all        # all three
 *
 * Resolves the cursorless source dir from CURSORLESS_DIR (env), defaulting to
 * ~/code/cursorless. Writes bundles into ~/code/prose-overlay/js/; the
 * sync-to-talon watcher then propagates them to the live Talon dir.
 *
 * After each build, prints raw + gzip sizes and the ratio of the targets
 * bundle to the hat bundle. The migration ISA (brain-z6m4) constrains the
 * targets bundle to ≤ 1.5× the hat bundle on both metrics.
 */

import { execSync } from "child_process";
import { resolve, dirname } from "path";
import { existsSync, readFileSync } from "fs";
import { gzipSync } from "zlib";

const PROSE_OVERLAY_DIR = resolve(import.meta.dir, "..");
const JS_OUT_DIR = `${PROSE_OVERLAY_DIR}/js`;
const CURSORLESS_DIR = process.env.CURSORLESS_DIR || `${process.env.HOME}/code/cursorless`;

interface BundleSpec {
  name: string;
  source: string;          // relative to CURSORLESS_DIR
  outfile: string;         // absolute
}

const BUNDLES: Record<"targets" | "hats" | "actions", BundleSpec> = {
  targets: {
    name: "prose_resolve_targets.js",
    source: "packages/cursorless-engine/src/actions/proseTargetsStandalone.ts",
    outfile: `${JS_OUT_DIR}/prose_resolve_targets.js`,
  },
  hats: {
    name: "prose_allocate_hats.js",
    source: "packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts",
    outfile: `${JS_OUT_DIR}/prose_allocate_hats.js`,
  },
  actions: {
    name: "prose_actions.js",
    source: "packages/cursorless-engine/src/actions/proseActionsStandalone.ts",
    outfile: `${JS_OUT_DIR}/prose_actions.js`,
  },
};

function preflight(spec: BundleSpec): void {
  const srcAbs = `${CURSORLESS_DIR}/${spec.source}`;
  if (!existsSync(CURSORLESS_DIR)) {
    throw new Error(`CURSORLESS_DIR=${CURSORLESS_DIR} does not exist`);
  }
  if (!existsSync(srcAbs)) {
    throw new Error(`Bundle source not found: ${srcAbs}`);
  }
  if (!existsSync(JS_OUT_DIR)) {
    throw new Error(`Output dir missing: ${JS_OUT_DIR}`);
  }
}

function build(spec: BundleSpec): { rawBytes: number; gzipBytes: number } {
  preflight(spec);

  const cmd = [
    "bunx esbuild",
    `"${spec.source}"`,
    "--bundle",
    "--format=iife",
    "--platform=browser",
    "--target=es2020",
    `"--alias:lodash-es=lodash"`,
    `--outfile="${spec.outfile}"`,
  ].join(" ");

  console.log(`[build] ${spec.name}`);
  console.log(`  src:  ${CURSORLESS_DIR}/${spec.source}`);
  console.log(`  out:  ${spec.outfile}`);

  const t0 = Date.now();
  execSync(cmd, { cwd: CURSORLESS_DIR, stdio: "inherit" });
  const elapsed = Date.now() - t0;

  const raw = readFileSync(spec.outfile);
  const gz = gzipSync(raw);
  console.log(`  raw:  ${raw.length.toLocaleString()} B (${(raw.length / 1024).toFixed(1)} KB)`);
  console.log(`  gzip: ${gz.length.toLocaleString()} B (${(gz.length / 1024).toFixed(1)} KB)`);
  console.log(`  time: ${elapsed} ms`);
  return { rawBytes: raw.length, gzipBytes: gz.length };
}

function reportRatio(targets: { rawBytes: number; gzipBytes: number }, hats: { rawBytes: number; gzipBytes: number }): void {
  const rawRatio = targets.rawBytes / hats.rawBytes;
  const gzRatio = targets.gzipBytes / hats.gzipBytes;
  const cap = 1.5; // ISC-55, brain-z6m4
  const fmt = (r: number) => `${r.toFixed(3)}× ${r <= cap ? "✅" : "❌ over 1.5× cap"}`;
  console.log(`\n[ratio] targets vs hats (cap 1.5×, ISC-55):`);
  console.log(`  raw:  ${fmt(rawRatio)}`);
  console.log(`  gzip: ${fmt(gzRatio)}`);
}

function main(): void {
  const arg = process.argv[2];
  if (!arg || !["targets", "hats", "actions", "all"].includes(arg)) {
    console.error("Usage: bun scripts/build-js.ts <targets|hats|actions|all>");
    process.exit(2);
  }

  if (arg === "targets") {
    build(BUNDLES.targets);
    return;
  }
  if (arg === "hats") {
    build(BUNDLES.hats);
    return;
  }
  if (arg === "actions") {
    build(BUNDLES.actions);
    return;
  }
  // all
  const t = build(BUNDLES.targets);
  console.log();
  const h = build(BUNDLES.hats);
  console.log();
  build(BUNDLES.actions);
  reportRatio(t, h);
}

main();
