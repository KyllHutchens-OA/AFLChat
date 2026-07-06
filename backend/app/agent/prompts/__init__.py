"""
Prompt templates for the v2 agent pipeline (Milestone 3+).

One module per LLM-calling node, so each prompt can be reviewed/edited in
isolation from the node logic that calls it:
    - classify.py   → classify_resolve node (Milestone 3a)
    - generate_sql.py → generate_sql node (Milestone 3b, not yet added)
    - review.py       → review node (Milestone 3d, not yet added)
    - respond.py      → respond node (Milestone 3e, not yet added)
"""
