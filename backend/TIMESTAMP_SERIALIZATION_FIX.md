# Timestamp Serialization Error - Fixed

## Date: 2026-01-26

---

## Issue

**Error Message:** `Error: Object of type Timestamp is not JSON serializable`

**When It Occurred:**
- User asked: "How many goals did dangerfield kick in 2022" ✅ (worked)
- User then asked: "What about 2023?" ❌ (failed with serialization error)

**Frequency:** Occurred on follow-up questions in conversations

---

## Root Cause

### Location: `/backend/app/api/websocket.py:109-112`

When saving assistant responses to conversation history, the code passed the agent's `entities` dictionary as metadata:

```python
ConversationService.add_message(
    conversation_id=conversation_id,
    role="assistant",
    content=response_text,
    metadata={
        "entities": final_state.get("entities", {}),  # ← Contains Timestamp objects!
        "intent": str(final_state.get("intent", "")),
        "confidence": final_state.get("confidence", 0.0)
    }
)
```

### Why It Failed:

1. The `entities` dictionary comes from the agent state
2. During entity resolution, database queries may return results with `pandas.Timestamp` or `datetime` objects
3. When `ConversationService.add_message()` tries to store the metadata in a JSONB database column, SQLAlchemy uses `json.dumps()`
4. Python's `json.dumps()` **cannot serialize** `Timestamp` or `datetime` objects
5. Error: `TypeError: Object of type Timestamp is not JSON serializable`

---

## Solution

### Created: `/backend/app/utils/json_serialization.py`

A utility function that recursively converts non-JSON-serializable objects to JSON-compatible formats:

```python
def make_json_serializable(obj: Any) -> Any:
    """
    Recursively convert non-JSON-serializable objects to JSON-compatible formats.

    Handles:
    - datetime/date/Timestamp → ISO format strings
    - Decimal → float
    - pandas DataFrame → dict
    - pandas Series → list
    - Sets → lists
    - Custom objects with __dict__ → dict
    """
```

**Example:**
```python
# Before (fails):
entities = {
    "players": ["Patrick Dangerfield"],
    "match_date": pd.Timestamp('2022-09-24 14:30:00')  # ← Not JSON serializable
}
json.dumps(entities)  # ❌ TypeError!

# After (works):
sanitized = make_json_serializable(entities)
# {
#     "players": ["Patrick Dangerfield"],
#     "match_date": "2022-09-24T14:30:00"  # ← Now a string!
# }
json.dumps(sanitized)  # ✅ Success!
```

---

## Files Modified

### 1. `/backend/app/api/websocket.py`

**Added import:**
```python
from app.utils.json_serialization import make_json_serializable
```

**Updated line 109-114:**
```python
# Sanitize metadata to ensure JSON serializability (remove Timestamp objects, etc.)
metadata = {
    "entities": make_json_serializable(final_state.get("entities", {})),
    "intent": str(final_state.get("intent", "")),
    "confidence": final_state.get("confidence", 0.0)
}
ConversationService.add_message(
    conversation_id=conversation_id,
    role="assistant",
    content=response_text,
    metadata=metadata
)
```

### 2. Created `/backend/app/utils/json_serialization.py`

New utility module with `make_json_serializable()` function.

### 3. Created `/backend/app/utils/__init__.py`

Module initialization file.

---

## Testing

### Test File: `/backend/test_json_serialization_fix.py`

Verifies that:
1. Original entities with Timestamp objects **FAIL** to serialize ✅
2. Sanitized entities with ISO strings **SUCCEED** in serialization ✅
3. Nested objects are properly handled ✅
4. Lists/dicts with Timestamps are recursively converted ✅

**Test Output:**
```
✅ EXPECTED FAILURE: Object of type Timestamp is not JSON serializable
✅ SUCCESS: Sanitized entities serialized successfully

Sanitized output:
{
  "match_date": "2022-09-24T14:30:00",  ← Converted to ISO string
  "created_at": "2026-01-26T20:21:31.753501",
  "nested": {
    "player_dob": "1990-04-05T00:00:00",
    "stats": [
      {"date": "2022-03-20T00:00:00", "goals": 2},
      {"date": "2022-03-27T00:00:00", "goals": 1}
    ]
  }
}
```

---

## Impact

### Before Fix:
- ❌ Follow-up questions in conversations failed with serialization error
- ❌ Conversation history could not be saved if entities contained dates
- ❌ Users experienced cryptic "Object of type Timestamp is not JSON serializable" errors

### After Fix:
- ✅ All entities are automatically sanitized before storage
- ✅ Timestamps/datetimes converted to ISO 8601 strings
- ✅ Follow-up questions in conversations work correctly
- ✅ Conversation history saves successfully
- ✅ No user-facing errors

---

## Prevention

To prevent similar issues in the future:

1. **Always sanitize** before storing in JSONB columns
2. **Always sanitize** before calling `json.dumps()` or `jsonify()`
3. **Use `make_json_serializable()`** whenever passing agent state or database results to storage/API responses
4. **Test with database results** that contain datetime columns

### Where to Apply:

- ✅ WebSocket handlers (already fixed)
- Any future REST API endpoints that return agent state
- Any code that stores agent state in databases
- Any code that logs agent state to JSON files

---

## Related Files

- `/backend/app/agent/state.py` - Agent state schema (contains non-serializable objects)
- `/backend/app/services/conversation_service.py` - Stores messages in JSONB
- `/backend/app/api/routes.py` - REST API endpoints (currently safe, only extracts strings)
- `/backend/app/data/models.py` - Conversation model with JSONB messages column

---

## Status

✅ **RESOLVED** - Timestamp serialization error fixed and tested.
