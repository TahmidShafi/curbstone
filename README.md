# curbstone

A toolkit to detect likely fabricated survey interviews (curbstoning) at the enumerator level using synthetic survey data with known ground truth. This project is currently a work in progress.

## Checkpoints: Frozen Before Detectors

1. **Honest generator v1 frozen** (`122deb2`):
   The honest synthetic survey data generator is frozen prior to the implementation of any fraud injection, ground-truth label tracking, or detection algorithms.

2. **Fraud injection v1 frozen**:
   The full synthetic DGP — including honest generation, stratified fraud injection across the 5 active modes, ground-truth label separation, and design rules R1–R4 — is frozen prior to the implementation of any anomaly detectors, scoring rules, or evaluation metrics.

These checkpoints serve as tamper-evident proof that detectors and evaluation thresholds were not retrofitted or tuned to the generator during development.
