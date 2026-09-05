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
