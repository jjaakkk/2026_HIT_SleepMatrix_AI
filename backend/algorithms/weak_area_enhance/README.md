# Weak-pressure enhancement

This module enhances weak human-contact regions in a `44 x 24` smart-mattress
pressure frame while suppressing isolated background sensor noise.  It uses an
adaptive, non-learning pipeline:

1. robust per-frame normalization;
2. reliable body-region seed detection;
3. local-density and body-proximity confidence filtering;
4. selective gamma enhancement of measured weak values;
5. conservative interpolation only inside small body-region gaps.

Measured weak boundary cells remain eligible for enhancement, but intensity is
not propagated beyond the selected body support.

The confidence mask prevents Gaussian smoothing from spreading a wide halo
around the body.  Original readings outside the selected body region are kept
unchanged rather than being amplified.

Comparison figures show the original and enhanced matrices on the same color
scale.  Bilinear interpolation is used only for smoother visualization; it
does not change the matrix returned by the algorithm.

The core enhancement code depends only on NumPy.  The comparison command uses
Matplotlib when available and otherwise falls back to Pillow.

Joint annotations are used only for offline evaluation and parameter tuning.
They are not required by the real-time `enhance_pressure(matrix)` API.

## Python API

```python
from backend.algorithms.weak_area_enhance import enhance_pressure

enhanced = enhance_pressure(raw_matrix)
```

`enhanced` has the same shape as `raw_matrix` and uses the same approximate
numeric scale.  The result is intended for visualization or optional algorithm
preprocessing.  It is not calibrated physical pressure and should not be used
for weight estimation.

## Compare a real dataset frame

Run the command from the repository root:

```powershell
python -m backend.algorithms.weak_area_enhance.compare `
  "path\to\person_1.txt" --frame 0 --output comparison.png
```

The loader understands the official dataset's `44 x 24` frames and skips the
single-value `0/1/2` label rows found in dynamic recordings.

## Evaluate with the joint-position dataset

The joint JSON contains pressure data and 14 labelled points for each record.
Select a person, action, frame and occurrence to create a comparison with a
skeleton overlay:

```powershell
python -m backend.algorithms.weak_area_enhance.compare `
  "C:\path\to\关节位置.json" `
  --folder SAI --action 1 --frame 0 --occurrence 0 `
  --output weak_pressure_joint_SAI_1_0.png
```

Most person/action/frame combinations occur twice because an augmented
counterpart is included.  Use `--occurrence 0` for the first record and
`--occurrence 1` for the second.  The command prints these additional metrics:

- `anatomy_added_ratio`: fraction of added intensity near the labelled body;
- `outside_added_ratio`: fraction of added intensity outside that corridor;
- `torso_weak_gain_ratio`: weak-pressure gain around the labelled torso;
- `leg_weak_gain_ratio`: weak-pressure gain along hip-knee-ankle segments;
- `leg_continuity_before/after`: visible coverage along labelled leg segments.

These annotations make incorrect background enhancement measurable without
making the production algorithm depend on manually labelled joints.

## Dataset check

The default parameters were smoke-tested on the middle frame of all 693 static
person/action TXT files in the supplied dataset:

- all 693 files parsed successfully;
- median weak-region mean gain: `1.47x`;
- median connected components: `6` before and `4` after enhancement;
- continuity improved in 628 samples, stayed equal in 65, and worsened in 0.

These are enhancement diagnostics rather than classification accuracy.  Final
report figures should include representative supine, prone, left-side and
right-side examples.
