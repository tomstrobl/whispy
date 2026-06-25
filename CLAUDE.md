# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`whispy` is a config-driven Python toolkit for running listening tests / perceptual experiments with PyQt6 UIs (MUSHRA-like drag-and-drop rating, N-AFC, questionnaires, info screens) and audio playback via `sounddevice`/`pyfar`.

There is no `README.md`; `AGENTS.md` is another AI-facing guide that overlaps with this file — keep both in sync if architecture changes.

## Commands

- Install in editable mode: `pip install -e .`
- Open the demo notebooks for the full experiment flow: `examples/drag_and_drop_mushra.ipynb` (MUSHRA), `examples/staircase_n_afc.ipynb` (adaptive staircase driving N-AFC trials), `examples/abx.ipynb` (ABX discrimination, fixed trial list → percent correct), `examples/questionnaire.ipynb` (questionnaire). There is no standalone single-trial N-AFC notebook; the staircase notebook is the N-AFC example (it drives `whispy.ui.NAFC`).
- Demo stimuli live under `examples/demo_stimuli/<test>/` (`mushra/`, `staircase/`, `abx/`); each folder holds that notebook's WAVs plus its generator. Regenerate by running the generator from inside its folder, e.g. `python examples/demo_stimuli/mushra/generate_mushra_stimuli.py` (`staircase/generate_staircase_stimuli.py`, `abx/generate_abx_stimuli.py`).

There is currently no test suite, linter, or formatter configured in `pyproject.toml`.

## Core data flow

1. `whispy.ExperimentScheduler(experiment=...)` reads `configs/experiment.yml` and (via the private `_course()` function in `whispy/experiment_scheduler.py`) randomizes blocks/sections/conditions and yields a list of "screen" dicts: `{block, section, reference, test, block_changed, section_changed, attribute, block_name, section_name}`.
2. Each screen dict is passed to a UI class as `screen=...`:
   - `whispy.ui.DragAndDropMUSHRA(screen=...)` — MUSHRA-like drag-and-drop rating.
   - `whispy.ui.NAFC(screen=...)` — N-alternative forced choice (screen also carries `test` as a list of choice IDs, plus `correct`/`trial_id`).
   - `whispy.ui.ABX(screen=...)` — classic ABX discrimination (screen carries `a`/`b` stimulus IDs, optional `x`; the UI plays A/B/X and the participant answers whether X matches A or B). Modeled on `NAFC` (config-driven, keyboard, window-size scaling, shared-host reuse across trials).
3. UI classes look up rating/task metadata from `configs/attributes.yml` (keyed by `screen["attribute"]`) and layout/theme from their own config (`configs/drag_and_drop_mushra.yml`, `configs/n_afc.yml`).
4. Tile/button activation triggers playback through a `StimuliHandler` (default `whispy.interfaces.SoundDevice`), keyed by the stimulus IDs in `screen["reference"]` / `screen["test"]`, which map to entries in `configs/stimuli.yml`.
5. After the window closes, `get_results()` returns a `pandas.DataFrame`; results from multiple screens are accumulated by passing the running DataFrame back in (`DragAndDropMUSHRA.get_results(results)`).

## Configuration conventions

- `whispy.utils.read_config()` (thin `yaml.safe_load` wrapper) is the single shared config loader used everywhere. It passes an already-loaded `dict`/`list` straight through, so a single combined config can be read once and its sub-sections handed to the individual consumers (e.g. `ExperimentScheduler(experiment=cfg["experiment"])`, `DragAndDropMUSHRA(attributes=cfg["attributes"])`).
- `whispy.utils.load_design()` returns the global theme from `configs/design.yml` merged with optional per-UI overrides (`load_design(overrides)`, where `overrides` is a dict or YAML path; `None`-valued keys are ignored). Every UI loads its look this way so all listening tests share one theme by default.
- Every config-consuming class resolves a default path relative to its own file's `FILEPATH` if no explicit path is passed, so configs can be overridden per-call without touching package defaults.
- `configs/design.yml`: the single source of truth for the shared look (window size, colors, fonts, button geometry/colors). It carries both the MUSHRA tile-state keys (`button_color_initial/clicked/active`) and the N-AFC button-state keys (`button_background_color`, `button_selected_*`), driven from one palette so the two UIs match.
- `configs/experiment.yml`: list of `block -> [block_name, section -> {section_name, attribute, reference, test}]`. This is the package default for `ExperimentScheduler`; the MUSHRA example no longer uses it (its experiment lives in the combined `drag_and_drop_mushra.yml`, see below).
- `configs/attributes.yml`: maps attribute name -> `{task, description, values, labels, neutral_value}` (rating scale definition shown by `DragAndDropMUSHRA` and used for the task text in `NAFC`). `NAFC` also honors a `task` set directly on the `screen` dict, which takes precedence over the `attributes.yml` lookup (lets a trial carry its prompt inline). This is the package default used when a UI is constructed without an explicit attributes config; no example notebook exercises it anymore (the MUSHRA example reads its scales from the combined `drag_and_drop_mushra.yml`, and the staircase N-AFC example sets `task` inline on the screen).
- `configs/staircase_n_afc.yml`: a single self-contained config for the `examples/staircase_n_afc.ipynb` experiment. One file feeds three consumers: `SoundDevice` (its `SoundDevice:` block), `NAFC` (its `test:`/`ui:` blocks, passed as `n_afc_config`), and the notebook (`trial:` = odd-one-out spec, `staircase:` = adaptive-rule kwargs for `whispy.Staircase`). Only the look (`design.yml`) lives elsewhere.
- `configs/abx.yml`: a single self-contained config for `examples/abx.ipynb` (ABX). One file feeds `SoundDevice` (its `SoundDevice:` block), `ABX` (its `test:` = `shuffle_ab` / `ui:` blocks, passed as `abx_config`), and the notebook (`trial:` = prompt/metadata, `pairs:` = list of `{a, b, name}` comparisons, `experiment:` = `repetitions`/`shuffle_trials`/`seed`). Demo WAVs are generated by `examples/demo_stimuli/abx/generate_abx_stimuli.py`.
- `configs/stimuli.yml`: handler-scoped (top-level keys like `SoundDevice:`, `OSCHandler:`), mapping stimulus IDs to playback info (e.g. `file:` for `SoundDevice`). Stimulus IDs are saved into experiment results — prefer descriptive names. Package default for `SoundDevice` when constructed without an explicit config; no example notebook exercises it anymore (each example reads the `SoundDevice:` block of its own self-contained config, e.g. `drag_and_drop_mushra.yml`, `staircase_n_afc.yml`, `abx.yml`).
- `configs/drag_and_drop_mushra.yml`: a single self-contained config for `examples/drag_and_drop_mushra.ipynb` (MUSHRA), mirroring `abx.yml`/`staircase_n_afc.yml`. One file feeds four consumers: `SoundDevice` (its `SoundDevice:` block), `DragAndDropMUSHRA` (its `ui:` block, passed as `drag_and_drop_mushra`, and its `attributes:` block, passed as `attributes`), and `ExperimentScheduler` (its `experiment:` block). The notebook reads the file once and hands each slice to its consumer. `DragAndDropMUSHRA` accepts either this combined file (it extracts the `ui:` block) or a flat UI config; colors/fonts come from `configs/design.yml`.
- `configs/n_afc.yml`: per-UI layout/behavior (`window_size`, `content_area_size`, autoplay, N-AFC `test:`/wording). The package default for `NAFC` when constructed without an explicit `n_afc_config`; no example notebook exercises it anymore (the staircase N-AFC example passes its own combined `staircase_n_afc.yml` as `n_afc_config`). Colors/fonts are inherited from `configs/design.yml`; any theme key may still be overridden here. `window_size: "fullscreen"` is a special-cased string.
- Area sizing: every test sizes its central area as an `[x%, y%]` percentage of the window via the same `content_area_size` key (under `ui:` for every test). All share `_BaseUIWindow._resolve_area_size()`, which clamps the percentage between a minimum and the window size minus reserved margins; the area is then centered in the window. Defaults to `[100, 100]` (max available) when the key is absent.
- `configs/participant_id.yml`: a single `ui:` block for `whispy.ui.ParticipantID`, the window shown once before an experiment to capture a participant id (`prompt`, `submit_button_text`, `invalid_hint`; colors/fonts inherited from `design.yml`). By default it shows one free-text field (`placeholder`, optional validation `pattern`). If a `fields:` list is given (each entry an optional `{prompt, placeholder, pattern}`), it shows one labeled field per entry and the id is the answers joined by `separator` (e.g. first letters of names + a birthday digit → an anonymous code). `ParticipantID(...).get_id()` returns the id. **Legacy/unused by the notebooks** (kept for possible future use): the notebooks no longer pop this window or add a `participant_id` column. Instead the participant id comes from the consent questionnaire and is baked into the result file *names* — see results naming below.
- `configs/thanks.yml`: a single `ui:` block for the "thank you for participating" screen shown once after an experiment finishes (the symmetric counterpart to `participant_id.yml`). Rendered with `whispy.ui.InfoWindow(thanks["message"], fullscreen=thanks["fullscreen"])`; carries `message` (markdown) and `fullscreen` (bool). Colors/fonts are inherited from `design.yml`. Every example notebook ends by reading this file and showing the screen after the run cell.
- `configs/questionnaires/`: holds all `Questionnaire` configs (`questionnaire.yml` — the package default/demo; `questionnaire_general.yml` — the experiment survey used by `examples/questionnaire.ipynb`; `questionnaire_consent.yml`). Each splits into `ui:` (questionnaire layout/sizing; colors inherited from `design.yml`) and `questionnaire:` (list of `{section, prompt, questions: [...]}`). Supported question `type`s: `text`, `text_box`, `numeric`, `single_choice`, `multiple_choice`. `single_choice` supports an `other_question` sub-block for a free-text "other" option. Any question may carry a `depends_on` sub-block (`{question: <controlling question id>, value: <x>}` or `values: [...]`) so it is only shown when the controlling question's answer matches; hidden questions are excluded from required-answer validation and report `None` in the results.

## UI / Qt patterns to preserve

All windows in `whispy/ui/*` (`InfoWindow`, `ParticipantID`, `Questionnaire`, `DragAndDropMUSHRA`, `NAFC`, `ABX`) follow the same shape:

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
- `ABX.get_results()` → one row per trial with `block, section, trial_id, block_name, section_name, a, b, x, correct ("A"/"B"), selected ("A"/"B"), correct_bool, rt`.
- `Questionnaire.get_results()` → one row per question with `section, question, prompt, type, required, answer`.

## Results saving / participant id

- `whispy/utils/results.py` (exported from `whispy.utils`) centralizes how every example notebook saves its CSV. `save_results(results, name)` writes into `examples/results/` and never overwrites (a numeric suffix is appended).
- Naming: always carries a timestamp. With a participant id → `<name>_<id>_<timestamp>.csv`; without one → an iterating fallback number `<name>_<NNN>_<timestamp>.csv` (`0001`..`9999`, 4 digits, raises past 9999).
- The participant id is an **in-memory value**, not a state file. The consent questionnaire (`questionnaire_consent.yml`, `pid_1..pid_4`) builds it via `participant_id_from_consent(results)`; pass that `participant_id` to `save_results(results, name, participant_id=...)` for the other blocks of the *same* notebook. The experiment building-block notebooks read it with `globals().get('participant_id')`, so pasting a consent block above wires it up automatically; standalone they fall back to the numeric form. (`whispy.utils` no longer has `set/get/clear_session_participant`; there is no `participant_id.txt`.)
- The notebooks intentionally no longer use `whispy.ui.ParticipantID` (kept as legacy) and no longer add a `participant_id` column — the id lives only in the file name.

## Editing conventions

- Keep new behavior config-driven, following the existing pattern of resolving default config paths via each module's `FILEPATH`.
- Use the established private-helper (`_foo`) and dataclass style seen in `whispy/ui/*` (e.g. `_MainWindow`, `_RatingArea`, `_DraggableTile`, `_DraggableTileSpec` in `drag_and_drop_mushra.py`).
- Preserve public exports in `whispy/__init__.py`, `whispy/ui/__init__.py`, and `whispy/interfaces/__init__.py` when adding new entry points.
- Prefer extending existing handlers/widgets (e.g. add a new `StimuliHandler` subclass, a new question-widget type in `questionnaire.py`, or a new attribute/config entry) over introducing ad hoc UI or audio code paths.