/**
 * Milestone 4 — validates a fixture set against the frontend zod mirror of
 * ChartSpecV1 (../src/types/chartSpec.ts). Run with:
 *
 *   npx tsx frontend/scripts/validateChartFixtures.ts
 *
 * This is NOT a new test framework — no vitest/jest is configured for this
 * project, so per the milestone plan this is a small tsx script instead.
 * Each fixture mirrors a case from backend/tests/test_recharts_builder.py so
 * both halves of the contract are exercised against the same shapes. Fixtures
 * marked `expectValid: false` are deliberately-invalid shapes (pre-M4 legacy
 * payloads, malformed specs) that must be rejected — DataTable fallback is
 * the correct behavior for those, not a chart.
 */
import { chartSpecSchema } from '../src/types/chartSpec';

interface Fixture {
  name: string;
  expectValid: boolean;
  spec: unknown;
}

const fixtures: Fixture[] = [
  {
    name: 'line (single series)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'line',
      title: "Melbourne Wins by Season",
      data: [
        { x: '2018', wins: 17 },
        { x: '2019', wins: 8 },
        { x: '2020', wins: 10 },
      ],
      series: [{ key: 'wins', name: 'Wins', color: '#C2581C' }],
      xAxis: { label: 'Season', integerOnly: true },
      yAxis: { label: 'Wins' },
      annotations: [],
      legend: false,
      colors: ['#C2581C'],
    },
  },
  {
    name: 'line (grouped multi-series)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'line',
      title: 'Disposals by Round',
      data: [
        { x: 'R1', Collingwood: 20, Carlton: 18 },
        { x: 'R2', Collingwood: 25, Carlton: 22 },
      ],
      series: [
        { key: 'Collingwood', name: 'Collingwood', color: '#C2581C' },
        { key: 'Carlton', name: 'Carlton', color: '#2D7A6F' },
      ],
      xAxis: { label: 'Round' },
      yAxis: { label: 'Disposals' },
      annotations: [],
      legend: true,
      colors: ['#C2581C', '#2D7A6F'],
    },
  },
  {
    name: 'bar (vertical)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'bar',
      title: 'Wins by Team',
      data: [{ x: 'Collingwood', wins: 15 }, { x: 'Carlton', wins: 10 }],
      series: [{ key: 'wins', name: 'Wins', color: '#C2581C' }],
      xAxis: { label: 'Team' },
      yAxis: { label: 'Wins' },
      annotations: [],
      legend: false,
      colors: ['#C2581C'],
    },
  },
  {
    name: 'bar (horizontal via orientation)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'bar',
      orientation: 'horizontal',
      title: 'Wins by Team',
      data: [{ x: 'Collingwood', wins: 15 }, { x: 'Carlton', wins: 10 }],
      series: [{ key: 'wins', name: 'Wins', color: '#C2581C' }],
      xAxis: { label: 'Wins' },
      yAxis: { label: 'Team' },
      annotations: [],
      legend: false,
      colors: ['#C2581C'],
    },
  },
  {
    name: 'groupedBar (unstacked)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'groupedBar',
      title: 'Wins by Season',
      data: [{ x: '2023', Collingwood: 15, Carlton: 10 }],
      series: [
        { key: 'Collingwood', name: 'Collingwood', color: '#C2581C' },
        { key: 'Carlton', name: 'Carlton', color: '#2D7A6F' },
      ],
      xAxis: { label: 'Season' },
      yAxis: { label: 'Value' },
      annotations: [],
      legend: true,
      colors: ['#C2581C', '#2D7A6F'],
    },
  },
  {
    name: 'groupedBar (stacked via per-series stackId)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'groupedBar',
      title: 'Wins by Season',
      data: [{ x: '2023', Collingwood: 15, Carlton: 10 }],
      series: [
        { key: 'Collingwood', name: 'Collingwood', color: '#C2581C', stackId: 'a' },
        { key: 'Carlton', name: 'Carlton', color: '#2D7A6F', stackId: 'a' },
      ],
      xAxis: { label: 'Season' },
      yAxis: { label: 'Value' },
      annotations: [],
      legend: true,
      colors: ['#C2581C', '#2D7A6F'],
    },
  },
  {
    name: 'groupedBar (former "box" — median + range)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'groupedBar',
      title: 'Disposals Distribution',
      data: [
        { x: 'Collingwood', median: 22, range: 8, q1: 19, q3: 24, min: 18, max: 26 },
        { x: 'Carlton', median: 19, range: 8, q1: 17, q3: 21, min: 15, max: 23 },
      ],
      series: [
        { key: 'median', name: 'Median', color: '#C2581C' },
        { key: 'range', name: 'Range (Max − Min)', color: '#2D7A6F' },
      ],
      xAxis: { label: 'Team' },
      yAxis: { label: 'Disposals' },
      annotations: [],
      legend: true,
      colors: ['#C2581C', '#2D7A6F'],
    },
  },
  {
    name: 'pie (<=5 slices, labels shown)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'pie',
      title: 'Scoring Breakdown',
      data: [{ name: 'Goals', value: 80 }, { name: 'Behinds', value: 20 }],
      series: [{ key: 'value', name: 'Value', color: '#C2581C' }],
      xAxis: {},
      yAxis: {},
      annotations: [],
      legend: true,
      showSliceLabels: true,
      colors: ['#C2581C', '#2D7A6F'],
    },
  },
  {
    name: 'pie (>5 slices grouped into Other, labels hidden)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'pie',
      title: 'Team Share',
      data: [
        { name: 'Team0', value: 40 }, { name: 'Team1', value: 20 },
        { name: 'Team2', value: 15 }, { name: 'Team3', value: 10 },
        { name: 'Team4', value: 8 }, { name: 'Other', value: 7 },
      ],
      series: [{ key: 'value', name: 'Value', color: '#C2581C' }],
      xAxis: {},
      yAxis: {},
      annotations: [],
      legend: true,
      showSliceLabels: false,
      colors: ['#C2581C'],
    },
  },
  {
    name: 'scatter',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'scatter',
      title: 'Disposals vs Goals',
      data: [{ x: 20, y: 1 }, { x: 25, y: 2 }],
      series: [{ key: 'scatter', name: 'Goals', color: '#C2581C' }],
      xAxis: { label: 'Disposals' },
      yAxis: { label: 'Goals' },
      annotations: [],
      legend: false,
      colors: ['#C2581C'],
    },
  },
  {
    name: 'area (reserved, not yet emitted by backend)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'area',
      title: 'Cumulative Disposals',
      data: [{ x: 'R1', disposals: 20 }, { x: 'R2', disposals: 45 }],
      series: [{ key: 'disposals', name: 'Disposals', color: '#C2581C' }],
      xAxis: { label: 'Round' },
      yAxis: { label: 'Disposals' },
      colors: ['#C2581C'],
      legend: false,
    },
  },
  {
    name: 'table (reserved, not yet emitted by backend)',
    expectValid: true,
    spec: {
      version: '1',
      chartType: 'table',
      title: 'Raw Results',
      data: [{ team: 'Collingwood', wins: 15 }],
      series: [{ key: 'wins', name: 'Wins' }],
      xAxis: {},
      yAxis: {},
    },
  },
  // ── Deliberately invalid — must fail parsing ────────────────────────
  {
    name: 'INVALID: empty data',
    expectValid: false,
    spec: {
      version: '1', chartType: 'bar', data: [], series: [{ key: 'x' }],
    },
  },
  {
    name: 'INVALID: empty series',
    expectValid: false,
    spec: {
      version: '1', chartType: 'bar', data: [{ x: 1 }], series: [],
    },
  },
  {
    name: 'INVALID: missing version',
    expectValid: false,
    spec: {
      chartType: 'bar', data: [{ x: 1 }], series: [{ key: 'x' }],
    },
  },
  {
    name: 'INVALID: legacy snake_case chartType (pre-M4 history restore)',
    expectValid: false,
    spec: {
      version: '1', chartType: 'horizontal_bar', data: [{ x: 1 }], series: [{ key: 'x' }],
    },
  },
  {
    name: 'INVALID: legacy chartType "box"',
    expectValid: false,
    spec: {
      chartType: 'box', data: [{ x: 1, median: 5 }], series: [],
    },
  },
];

let failures = 0;
for (const fixture of fixtures) {
  const result = chartSpecSchema.safeParse(fixture.spec);
  const ok = result.success === fixture.expectValid;
  const status = ok ? 'PASS' : 'FAIL';
  if (!ok) failures += 1;
  console.log(`[${status}] ${fixture.name} (expected ${fixture.expectValid ? 'valid' : 'invalid'}, got ${result.success ? 'valid' : 'invalid'})`);
  if (!ok && !result.success) {
    console.log('        ' + JSON.stringify(result.error.issues.slice(0, 3)));
  }
}

console.log(`\n${fixtures.length - failures}/${fixtures.length} fixtures behaved as expected.`);
if (failures > 0) {
  process.exit(1);
}
