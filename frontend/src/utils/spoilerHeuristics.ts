// Heuristic: does this answer look like it reveals a match result? Used to
// decide whether to blur an answer when spoiler mode is on (SpoilerBlur).
// The backend prompt already avoids revealing current-season results when
// spoiler mode is on; this is a client-side backstop, so a few false
// positives (blurring a safe answer) are fine, false negatives are not.
const SCORE_PATTERN = /\b\d{1,3}\.\d{1,2}\s*\(\d{1,3}\)/; // AFL score format, e.g. "14.12 (96)"
const RESULT_WORDS = /\b(won|winner|beat|defeated|def\.|lost to|premiers?|premiership)\b/i;

export function looksLikeResult(text: string): boolean {
  return SCORE_PATTERN.test(text) || RESULT_WORDS.test(text);
}
