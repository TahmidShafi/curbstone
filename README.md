# curbstone

A toolkit to detect likely fabricated survey interviews (curbstoning) at the enumerator level using synthetic survey data with known ground truth. This project is currently a work in progress.

## Checkpoint: Generator Frozen Before Detectors

The honest synthetic survey data generator (v1) is frozen prior to the implementation of any fraud injection, ground-truth label tracking, or detection algorithms.

This commit (`Honest generator v1 frozen`) serves as tamper-evident proof that detectors and evaluation thresholds were not retrofitted or tuned to the generator during development.
