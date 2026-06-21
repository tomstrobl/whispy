# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`whispy` is a config-driven Python toolkit for running listening tests / perceptual experiments with PyQt6 UIs (MUSHRA-like drag-and-drop rating, N-AFC, questionnaires, info screens) and audio playback via `sounddevice`/`pyfar`.

There is no `README.md`; `AGENTS.md` is another AI-facing guide that overlaps with this file — keep both in sync if architecture changes.

## Commands

- Install in editable mode: `pip install -e .`
- Open the demo notebooks for the full experiment flow: `examples/drag_and_drop_mushra.ipynb` (MUSHRA), `examples/n_afc.ipynb` (single N-AFC trial), `examples/staircase_n_afc.ipynb` (adaptive staircase driving N-AFC trials)
- Regenerate the demo WAV stimuli: `python examples/stimuli/generate_example_stimli.py` (run from inside `examples/stimuli/`)

There is currently no test suite, linter, or formatter configured in `pyproject.toml`.

## Core data flow

1. `whispy.ExperimentScheduler(experiment=...)` reads `configs/experiment.yml` and (via the private `_course()` function in `whispy/experiment_scheduler.py`) randomizes blocks/sections/conditions and yields a list of "screen" dicts: `{block, section, reference, test, block_changed, section_changed, attribute, block_name, section_name}`.
2. Each screen dict is passed to a UI class as `screen=...`:
   - `whispy.ui.DragAndDropMUSHRA(screen=...)` — MUSHRA-like drag-and-drop rating.
   - `whispy.ui.NAFC(screen=...)` — N-alternative forced choice (screen also carries `test` as a list of choice IDs, plus `correct`/`trial_id`).
3. UI classes look up rating/task metadata from `configs/attributes.yml` (keyed by `screen["attribute"]`) and layout/theme from their own config (`configs/drag_and_drop_mushra.yml`, `configs/n_afc.yml`).
4. Tile/button activation triggers playback through a `StimuliHandler` (default `whispy.interfaces.SoundDevice`), keyed by the stimulus IDs in `screen["reference"]` / `screen["test"]`, which map to entries in `configs/stimuli.yml`.
5. After the window closes, `get_results()` returns a `pandas.DataFrame`; results from multiple screens are accumulated by passing the running DataFrame back in (`DragAndDropMUSHRA.get_results(results)`).

## Configuration conventions

- `whispy.utils.read_config()` (thin `yaml.safe_load` wrapper) is the single shared config loader used everywhere.
- `whispy.utils.load_design()` returns the global theme from `configs/design.yml` merged with optional per-UI overrides (`load_design(overrides)`, where `overrides` is a dict or YAML path; `None`-valued keys are ignored). Every UI loads its look this way so all listening tests share one theme by default.
- Every config-consuming class resolves a default path relative to its own file's `FILEPATH` if no explicit path is passed, so configs can be overridden per-call without touching package defaults.
- `configs/design.yml`: the single source of truth for the shared look (window size, colors, fonts, button geometry/colors). It carries both the MUSHRA tile-state keys (`button_color_initial/clicked/active`) and the N-AFC button-state keys (`button_background_color`, `button_selected_*`), driven from one palette so the two UIs match.
- `configs/experiment.yml`: list of `block -> [block_name, section -> {section_name, attribute, reference, test}]`.
- `configs/attributes.yml`: maps attribute name -> `{task, description, values, labels, neutral_value}` (rating scale definition shown by `DragAndDropMUSHRA` and used for the task text in `NAFC`).
- `configs/stimuli.yml`: handler-scoped (top-level keys like `SoundDevice:`, `OSCHandler:`), mapping stimulus IDs to playback info (e.g. `file:` for `SoundDevice`). Stimulus IDs are saved into experiment results — prefer descriptive names.
- `configs/drag_and_drop_mushra.yml` / `configs/n_afc.yml`: per-UI layout/behavior (`window_size`, `rating_area_size`, autoplay, N-AFC `test:`/wording). Colors/fonts are inherited from `configs/design.yml`; any theme key may still be overridden here. `window_size: "fullscreen"` is a special-cased string.
- `configs/questionnaire.yml`: splits into `ui:` (questionnaire layout/sizing; colors inherited from `design.yml`) and `questionnaire:` (list of `{section, prompt, questions: [...]}`). Supported question `type`s: `text`, `text_box`, `numeric`, `single_choice`, `multiple_choice`. `single_choice` supports an `other_question` sub-block for a free-text "other" option.

## UI / Qt patterns to preserve

All windows in `whispy/ui/*` (`InfoWindow`, `Questionnaire`, `DragAndDropMUSHRA`, `NAFC`) follow the same shape:

- A module-level `_qapp` reference is created on first use (`QApplication(sys.argv[:1])`, only if `QApplication.instance() is None`) and kept alive for the process so windows can be constructed/destroyed repeatedly (e.g. in notebooks).
- When running inside an IPython kernel, `get_ipython().enable_gui("qt6")` is called so the Qt event loop runs alongside the kernel.
- Blocking is implemented via a private `QEventLoop` started in `wait_until_closed()`, invoked when `blocking=True`.
- Closing is gated by `_allow_close`, which is `False` unless `debug=True`. `closeEvent` ignores the close request until the gating condition is satisfied (e.g. Continue clicked, or for `DragAndDropMUSHRA`/`NAFC`/`Questionnaire`, until required interactions/answers are complete). `InfoWindow` is reused as a blocking "please complete X" prompt when validation fails.
- `InfoWindow` also maintains an `_orphaned_windows` registry so top-level info popups the caller doesn't store stay alive until closed.

## Audio / stimulus rules

- `whispy.interfaces.StimuliHandler` is an ABC with `play(stimulus)` / `stop(stimulus=None)`.
- `SoundDevice` (the default handler) loads audio via `pyfar.io.read_audio()`, rejects clipping (`max(abs(sample)) >= 1`), and requires all loaded stimuli to share one sampling rate (set as `sd.default.samplerate`).

## Results shapes

- `DragAndDropMUSHRA.get_results()` → long-form `pandas.DataFrame`, one row per test stimulus, combining the screen metadata with a `rating` column (rating decoded from tile position back into the attribute's value scale).
- `NAFC.get_results()` → one row per trial with `block, section, trial_id, block_name, section_name, choices, correct, selected, correct_bool, rt`.
- `Questionnaire.get_results()` → one row per question with `section, question, prompt, type, required, answer`.

## Editing conventions

- Keep new behavior config-driven, following the existing pattern of resolving default config paths via each module's `FILEPATH`.
- Use the established private-helper (`_foo`) and dataclass style seen in `whispy/ui/*` (e.g. `_MainWindow`, `_RatingArea`, `_DraggableTile`, `_DraggableTileSpec` in `drag_and_drop_mushra.py`).
- Preserve public exports in `whispy/__init__.py`, `whispy/ui/__init__.py`, and `whispy/interfaces/__init__.py` when adding new entry points.
- Prefer extending existing handlers/widgets (e.g. add a new `StimuliHandler` subclass, a new question-widget type in `questionnaire.py`, or a new attribute/config entry) over introducing ad hoc UI or audio code paths.