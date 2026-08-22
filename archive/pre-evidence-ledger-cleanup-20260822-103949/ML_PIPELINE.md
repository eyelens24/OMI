# ML diagnosis pipeline

## What is implemented

`train_diagnosis_model.py` trains a transparent, standardised nearest-centroid
baseline from accepted reviewer-labelled incidents. It uses an earlier-time
training set and a later-time test set, and returns
`unknown_or_insufficient_evidence` when a new incident lies outside the learned
range of its nearest label.

```bash
python3 sample_data/generate_labelled_incidents.py
python3 train_diagnosis_model.py \
  --input sample_data/labelled_incidents.synthetic.csv \
  --model data/diagnosis_model.json \
  --report data/diagnosis_model_report.json
```

The supplied input is deliberately synthetic. Its scores validate the pipeline
only; they are not evidence of market accuracy.

## Hybrid diagnosis in the app

The live diagnosis keeps four distinct jobs separate:

1. **K-means pattern detection** groups fundamental, market, and data-lineage
   observations into normal/stressed clusters.
2. **Change-point detection** identifies when a material shift began.
3. **Reviewed evidence routes** explain only supported mechanisms from an
   upstream candidate to P&L.
4. **The labelled model** can later provide a secondary opinion once it has
   real accepted labels; it must abstain for unfamiliar inputs.

A cluster is never displayed as a proven external cause. Numeric fields that
shift but are outside the reviewed route vocabulary are shown as unclassified
patterns for reviewer labelling.

## Required real training row

```text
timestamp,strategy_id,symbol,label,review_status,...numeric_features
```

- `label` must be one of [INCIDENT_LABELS.md](INCIDENT_LABELS.md).
- `review_status` must be `accepted`; unreviewed or rejected labels are
  excluded from training.
- Numeric features must be values available at or before `timestamp`.
- Keep `strategy_id` to audit generalisation. A model should be tested on a
  later period and ideally an unseen strategy, not a random row split.

## Before connecting predictions to the app

Collect enough reviewed examples per label, compare the baseline with a
tree/boosting model, calibrate confidence, test abstention on genuinely novel
incidents, and retain the rules engine as the evidence/explanation layer.
