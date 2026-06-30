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
from whispy.interfaces import SoundDevice

config = "configs/drag_and_drop_mushra.yml"   # one self-contained experiment file
cfg = whispy.utils.read_config(config)
handler = SoundDevice(config, "examples/demo_stimuli/mushra")  # reads the SoundDevice: block

# Randomized course of trials from the config's `experiment:` block
schedule = whispy.ExperimentScheduler(experiment=cfg)

results = None
for screen in schedule:
    ui = whispy.ui.DragAndDropMUSHRA(
        screen=screen, stimuli_handler=handler, drag_and_drop_mushra=cfg)
    results = ui.get_results(results)
```

See the runnable demos in [`examples/`](examples/) — each test ships as a minimal
`building_block_<test>.ipynb` and a full `full_experiment_<test>.ipynb` (consent
→ test → thank-you):

- `drag_and_drop_mushra` — MUSHRA-like drag-and-drop rating.
- `staircase_n_afc` — adaptive staircase driving N-AFC trials.
- `abx` — ABX discrimination.

## Configuration

All UIs are configured from YAML in [`configs/`](configs/). The shared look of
every UI lives in [`configs/design.yml`](configs/design.yml) (the single global
theme); per-UI files hold layout/behavior and may override individual theme
keys. See `CLAUDE.md` for a full description of the configuration conventions
and architecture.

## License

MIT — see [`LICENSE`](LICENSE).
