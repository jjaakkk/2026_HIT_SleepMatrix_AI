# Dataset directory

Dataset files are not committed to Git. After obtaining the official data,
place unchanged source files under `dataset/raw/`. Put reproducible converted
or cleaned files under `dataset/processed/`.

Recommended local layout:

```text
dataset/
├── README.md
├── raw/
│   └── participant_action.txt
└── processed/
```

The current TXT loader searches recursively, so either of these commands is
valid:

```powershell
python -m backend.algorithms.posture_svm.train_svm
python -m backend.algorithms.posture_svm.train_svm --dataset-dir dataset/raw
```

See `shared/contracts/posture.json` and
`shared/contracts/pressure-frame.schema.json` for the committed format and
labels. Local source documents under `assets/` are intentionally not tracked.
