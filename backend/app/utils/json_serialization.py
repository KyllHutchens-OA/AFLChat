"""
JSON Serialization Utilities

Handles conversion of non-JSON-serializable Python objects to JSON-compatible formats.
"""
from datetime import datetime, date
from typing import Any
import pandas as pd
import numpy as np
from decimal import Decimal


def make_json_serializable(obj: Any) -> Any:
    """
    Recursively convert non-JSON-serializable objects to JSON-compatible formats.

    Handles:
    - datetime/date/Timestamp → ISO format strings
    - Decimal → float
    - numpy int/float types → Python int/float
    - numpy arrays → lists
    - pandas DataFrame → dict
    - pandas Series → list
    - Sets → lists
    - Custom objects with __dict__ → dict

    Args:
        obj: Any Python object

    Returns:
        JSON-serializable version of the object
    """
    # Handle None
    if obj is None:
        return None

    # Handle numpy integer types (must check before regular int)
    if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)

    # Handle numpy float types (must check before regular float)
    if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        # Handle NaN values
        if np.isnan(obj):
            return None
        return float(obj)

    # Handle numpy bool
    if isinstance(obj, np.bool_):
        return bool(obj)

    # Handle numpy arrays
    if isinstance(obj, np.ndarray):
        return [make_json_serializable(item) for item in obj.tolist()]

    # Handle datetime/date/Timestamp
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()

    # Handle Decimal
    if isinstance(obj, Decimal):
        return float(obj)

    # Handle pandas DataFrame
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')

    # Handle pandas Series
    if isinstance(obj, pd.Series):
        return [make_json_serializable(item) for item in obj.tolist()]

    # Handle dictionaries recursively
    if isinstance(obj, dict):
        return {str(key): make_json_serializable(value) for key, value in obj.items()}

    # Handle lists/tuples recursively
    if isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]

    # Handle sets
    if isinstance(obj, set):
        return [make_json_serializable(item) for item in obj]

    # Handle basic JSON-serializable types
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # Handle Enums
    if hasattr(obj, 'value'):
        return obj.value

    # Handle objects with __dict__ (convert to dict)
    if hasattr(obj, '__dict__'):
        return make_json_serializable(obj.__dict__)

    # Fallback: convert to string
    return str(obj)
