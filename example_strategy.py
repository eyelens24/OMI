"""Example deterministic strategy accepted by Quant Doctor's replay prototype."""

def on_bar(bar, state):
    # The strategy receives each historical bar and must return a target position.
    # Values: -1 (short), 0 (flat), 1 (long). Keep it dependency-free for local replay.
    params = state["params"]
    entry_threshold = float(params.get("entry_threshold", 0.55))
    max_volatility = float(params.get("max_volatility", 0.25))
    if bar["signal_strength"] > entry_threshold and bar["volatility"] < max_volatility:
        return 1
    if bar["signal_strength"] < (1 - entry_threshold):
        return -1
    return 0
