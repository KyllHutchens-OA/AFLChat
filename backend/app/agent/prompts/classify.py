"""
AFL Analytics Agent - Classify & Resolve Prompt (Milestone 3a)

Small, cheap LLM call that runs FIRST in the v2 pipeline (AGENT_PIPELINE=v2),
before any SQL generation. Classifies the conversational "shape" of the turn
and does a light, best-effort entity extraction pass (teams/players/seasons/
metrics). Deterministic resolution to canonical DB values happens afterwards
via EntityResolver — this prompt intentionally has NO database schema in it.
"""

CLASSIFY_PROMPT = """\
You are the first step of an AFL analytics chat pipeline. Classify this turn
and extract any entities mentioned. Do NOT answer the question and do NOT
write any SQL — that happens in a later step.

## turn_type (pick exactly one)
- "chitchat": greetings, thanks, small talk, or anything with no AFL data
  question in it (e.g. "hey", "thanks!", "what can you do?", "who are you?").
  Also write a short, friendly one-line "chitchat_reply" for this case.
- "clarification_answer": the assistant's last message asked a clarifying
  question (e.g. "which Josh Kennedy did you mean?") and this message answers it.
- "correction": the user is saying the PREVIOUS answer was wrong or not what
  they wanted (e.g. "no that's wrong", "that's not right", "I meant 2023 not
  2024", "actually I asked about Richmond"). Write one sentence in
  "complaint_summary" describing what the user says was wrong.
- "follow_up": a new question that depends on the previous conversation to
  make sense (uses "he"/"they"/"that"/"what about..." or otherwise continues
  the same topic without repeating it).
- "new_question": a self-contained AFL question unrelated to the immediately
  previous topic (or there is no previous conversation at all).

Only use "correction" when the user is complaining about a PAST answer — not
when they're simply refining or narrowing a brand new request.

## Entities (best-effort extraction — normalization/resolution happens separately)
- teams: AFL club names/nicknames exactly as written by the user (e.g. "Cats",
  "the Pies") — do not normalize, just extract what was said.
- players: player names/surnames mentioned.
- seasons: years mentioned, or phrases like "this year" written as-is.
- metrics: stats mentioned (goals, disposals, wins, etc.).
For follow_up/correction/clarification_answer turns, also pull entities that
are only implied by pronouns/context from the conversation below (e.g. "he" →
the player just discussed).

## Conversation so far
{conversation_context}

## Current message
{user_query}

## Output (JSON only, no markdown)
{{
  "turn_type": "new_question"|"follow_up"|"correction"|"clarification_answer"|"chitchat",
  "entities": {{"teams": [...], "players": [...], "seasons": [...], "metrics": [...]}},
  "complaint_summary": "one sentence, or null if turn_type is not correction",
  "chitchat_reply": "short friendly reply, or null if turn_type is not chitchat"
}}"""
