"""Evaluate the current diagnosis against synthetic incident ground truth."""
from server import analyse, synthetic_incident

records, truth = synthetic_incident()
diagnosis = analyse(records)
found_topics = {edge["source"] for edge in diagnosis["explanation_paths"]} | {edge["target"] for edge in diagnosis["explanation_paths"]}
matched = [topic for topic in truth["expected_mechanisms"] if topic in found_topics]

print("Ground-truth root:", truth["root_cause"])
print("Inferred root:", diagnosis["root_hypothesis"]["label"])
print(f"Mechanisms recovered: {len(matched)}/{len(truth['expected_mechanisms'])}")
print("Recovered:", ", ".join(matched))
assert diagnosis["root_hypothesis"]["label"] == truth["root_cause"]
assert len(matched) >= 4
