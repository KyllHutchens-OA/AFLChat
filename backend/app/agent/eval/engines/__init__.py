"""Engine adapters for the eval harness (see app/agent/eval/runner.py).

v2.py  AFLAnalyticsAgent in-process
ws.py  AFLAnalyticsAgent via a running backend's WebSocket
v3.py  (1E) single tool-calling agent loop; subclass EngineAdapter and
       return TurnResult with rows, tool_calls, tokens, latency and ttft_s.
"""
