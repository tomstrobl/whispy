# whispy

A config-driven Python toolkit for running listening tests / perceptual
experiments. It provides PyQt6 UIs (drag-and-drop MUSHRA-like rating, N-AFC,
questionnaires, info screens) and audio playback via `sounddevice` / `pyfar`,
all driven by YAML configuration.

## Installation

```bash
pip install -e .
```

## Quick start

```python
import whispy

# Randomized course of trials from configs/experiment.yml
schedule = whispy.ExperimentScheduler("configs/experiment.yml")

for screen in schedule:
    ui = whispy.ui.DragAndDropMUSHRA(screen=screen)
    results = ui.get_results()
```

See the runnable demos in [`examples/`](examples/):

- `examples/drag_and_drop_mushra.ipynb` — MUSHRA-like drag-and-drop rating.
- `examples/n_afc.ipynb` — a single N-AFC trial, explained step by step.
- `examples/staircase_n_afc.ipynb` — adaptive staircase driving N-AFC trials.

## Configuration

All UIs are configured from YAML in [`configs/`](configs/). The shared look of
every UI lives in [`configs/design.yml`](configs/design.yml) (the single global
theme); per-UI files hold layout/behavior and may override individual theme
keys. See `CLAUDE.md` for a full description of the configuration conventions
and architecture.

## License

MIT — see [`LICENSE`](LICENSE).
