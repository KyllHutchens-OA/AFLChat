/**
 * Milestone 4 — validates the live e2e chart captures written by
 * scripts/m4_chart_check.py (repo-root `scripts/benchmark_results/m4_chart_check.json`)
 * against the frontend zod mirror of ChartSpecV1. Run with:
 *
 *   npx tsx frontend/scripts/validateCapturedSpecs.ts [path-to-json]
 *
 * Mutates the input file in place, adding a `zod_valid` / `zod_errors` field
 * to each case so the JSON deliverable records both the raw capture and
 * whether it would actually render as a chart (vs DataTable fallback) on
 * the frontend.
 */
import { readFileSync, writeFileSync } from 'fs';
import { chartSpecSchema } from '../src/types/chartSpec';

const path = process.argv[2] || '../scripts/benchmark_results/m4_chart_check.json';
const raw = JSON.parse(readFileSync(path, 'utf-8'));

let allOk = true;
for (const c of raw.cases ?? []) {
  const result = chartSpecSchema.safeParse(c.visualization_spec);
  c.zod_valid = result.success;
  c.zod_errors = result.success ? null : result.error.issues;
  allOk = allOk && result.success;
  console.log(`[${result.success ? 'PASS' : 'FAIL'}] ${c.id} — zod ${result.success ? 'accepts' : 'REJECTS'} the captured spec`);
  if (!result.success) {
    console.log('        ' + JSON.stringify(result.error.issues.slice(0, 5)));
  }
}

raw.meta = raw.meta || {};
raw.meta.zod_validation_all_pass = allOk;
writeFileSync(path, JSON.stringify(raw, null, 2));

console.log(`\n${allOk ? 'ALL CAPTURES PARSE' : 'SOME CAPTURES FAILED TO PARSE'} — ${path} updated.`);
if (!allOk) process.exit(1);
