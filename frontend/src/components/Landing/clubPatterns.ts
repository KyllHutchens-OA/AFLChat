import { GuernseyPattern } from './GuernseyIcon';

// Rough real-world guernsey pattern per club (stripes/hoops/sash/halves/solid),
// used only to pick an SVG fill style. No club logos or wordmarks involved.
export const CLUB_PATTERNS: Record<string, GuernseyPattern> = {
  ADE: 'sash',
  BRI: 'sash',
  CAR: 'solid',
  COL: 'stripes',
  ESS: 'sash',
  FRE: 'solid',
  GEE: 'hoops',
  GCS: 'solid',
  GWS: 'solid',
  HAW: 'stripes',
  MEL: 'sash',
  NOR: 'solid',
  POR: 'hoops',
  RIC: 'sash',
  STK: 'sash',
  SYD: 'halves',
  WCE: 'solid',
  WBD: 'hoops',
};
