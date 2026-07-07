# whispy — User Manual

*A step-by-step guide for running listening tests with whispy. No prior
experience with the codebase is required, and only minimal Python knowledge
(running cells in a Jupyter notebook) is assumed.*

---

## Table of contents

1. [What is whispy?](#1-what-is-whispy)
2. [What you need](#2-what-you-need)
3. [Installation](#3-installation)
4. [Your first test in 5 minutes](#4-your-first-test-in-5-minutes)
5. [How whispy is organized](#5-how-whispy-is-organized)
6. [The one idea you must understand: config files](#6-the-one-idea-you-must-understand-config-files)
7. [The available tests](#7-the-available-tests)
8. [Using your own audio files](#8-using-your-own-audio-files)
9. [Running a real experiment with participants](#9-running-a-real-experiment-with-participants)
10. [Where your results end up](#10-where-your-results-end-up)
11. [Changing the look and the wording](#11-changing-the-look-and-the-wording)
12. [Troubleshooting](#12-troubleshooting)
13. [Glossary](#13-glossary)

---

## 1. What is whispy?

whispy is a Python toolkit for **listening tests** (also called perceptual
experiments): you play sounds to a participant, they answer questions about
what they heard, and their answers are saved to a table you can analyze later.

The key design decision: **you describe your experiment in a text file (a
YAML config), not in Python code.** The Python side is already written for
you — ready-made Jupyter notebooks in the `examples/` folder run each kind of
test. To make your own experiment you typically only:

1. put your audio files (WAVs) in a folder,
2. edit one config file (which sounds, how many trials, what the question says),
3. press "Run All" in the matching notebook.

## 2. What you need

- **A computer with audio output** (Windows, macOS, or Linux) and good
  headphones/loudspeakers for the actual test.
- **Python 3.11 or newer.** The easiest way to get it is
  [Anaconda](https://www.anaconda.com/download) (recommended if you're new to
  Python) or [python.org](https://www.python.org/downloads/).
- **Git** to download the repository ([git-scm.com](https://git-scm.com/downloads)).
- **A program that opens Jupyter notebooks.** We recommend
  [Visual Studio Code](https://code.visualstudio.com/) with the *Python* and
  *Jupyter* extensions (already tested with whispy). PyCharm or the classic
  `jupyter lab` in the browser also work.
- **Your stimuli as WAV files** — only needed for your own experiment; the
  demos ship with generated example sounds.

## 3. Installation

Open a terminal (on Windows: "Anaconda Prompt" if you use Anaconda, otherwise
PowerShell) and run the following commands one by one.

**Step 1 — get the code.** `cd` into the folder where you want whispy to
live, then:

```bash
git clone https://github.com/tomstrobl/whispy.git
cd whispy
```

**Step 2 (recommended) — create a separate Python environment**, so whispy's
packages don't interfere with anything else on your machine. With Anaconda:

```bash
conda create -n whispy python=3.12
conda activate whispy
```

(Every time you come back later, run `conda activate whispy` again first.)

**Step 3 — install whispy and everything it needs:**

```bash
pip install -e .
```

This single command pulls in all required packages (PyQt6 for the windows,
sounddevice/pyfar for audio, pandas for results, Jupyter support, …). The
`-e` means "editable": if you later pull an update of the repository with
`git pull`, you don't need to reinstall.

**Step 4 — check it works.** Open the whispy folder in VS Code, open
`examples/building_block_abx.ipynb`, and when asked to pick a *kernel* /
*Python environment*, choose the `whispy` environment you just created. Then
read on.

## 4. Your first test in 5 minutes

1. In VS Code, open **`examples/building_block_abx.ipynb`**.
2. Click **Run All** (or run the cells top to bottom with `Shift+Enter`).
3. A window opens: this is the ABX test. You hear three sounds — A, B, and X —
   and answer whether X sounds like A or B. Use the on-screen buttons or the
   keyboard (keys `A`/`B`/`X` to listen, `←`/`→` to choose, `Enter` to submit).
4. Complete the four demo trials. The window closes by itself after the last one.

   > **Note:** the test windows deliberately **cannot be closed with the ✕
   > button** — a participant must finish the screen first. To abort during
   > development, interrupt/restart the notebook kernel (see
   > [Troubleshooting](#12-troubleshooting)).
5. Run the final cell — your answers are saved as a CSV file in
   `examples/results/`.

That's the entire workflow. Every other test works the same way, just with a
different notebook and config file.

## 5. How whispy is organized

```
whispy/
├── configs/            ← the files YOU edit to design an experiment
│   ├── abx.yml                    (one self-contained experiment each)
│   ├── drag_and_drop_mushra.yml
│   ├── staircase_n_afc.yml
│   ├── scale_testing.yml
│   ├── design.yml                 (shared look: colors, fonts, window size)
│   ├── welcome.yml / thanks.yml   (the framing screens' text)
│   └── questionnaires/            (consent + survey questions)
├── examples/           ← the notebooks YOU run
│   ├── building_block_<test>.ipynb   (minimal: just the test + saving)
│   ├── full_experiment_<test>.ipynb  (welcome → consent → test → thank-you)
│   ├── demo_stimuli/                 (example WAVs for each demo)
│   └── results/                      (your saved CSV files land here)
└── whispy/             ← the Python package itself (you normally never touch it)
```

Each test exists in two notebook flavors:

- **`building_block_<test>.ipynb`** — the minimal version: load the config,
  run the test, save results. Use this to try things out, and as the
  copy-paste source when assembling your own notebook.
- **`full_experiment_<test>.ipynb`** — the version you run with a real
  participant: welcome screen → consent questionnaire (which creates an
  anonymous participant ID) → the test → thank-you screen.

For a visual overview of how these pieces fit together (notebooks → configs →
scheduler → UI windows → audio → results), see the architecture diagram in the
[README](../README.md#architecture). Its editable source lives right next to
this manual in [`docs/architecture.mmd`](architecture.mmd) — paste that file's
contents into [mermaid.live](https://mermaid.live) to view it interactively or
export a PNG/SVG for slides.

## 6. The one idea you must understand: config files

Everything about an experiment lives in one YAML file in `configs/`. YAML is
just structured text — three rules cover almost everything you'll see:

```yaml
key: value            # a setting
parent:               # a group of settings — note the indentation below
  child: 123          #   indentation is 2 spaces and it MATTERS
my_list:              # a list
  - first item
  - second item
```

Use spaces (never tabs), keep the indentation exactly as in the existing
files, and put text containing special characters in quotes (`"like: this"`).
Every config in `configs/` has **inline comments explaining each setting** —
open one and read along.

Each experiment config (e.g. `configs/abx.yml`) is *self-contained*: it holds
the stimulus list, the test behavior, the on-screen wording, and the trial
plan for that one experiment. Only the shared visual theme lives elsewhere,
in `configs/design.yml` (section 11).

**Golden rule: to change your experiment, edit the YAML — you should never
need to edit the Python in the notebooks.**

## 7. The available tests

| Test | What it measures | Notebook(s) | Config |
|---|---|---|---|
| **ABX** | Can two sounds be told apart at all? Participant hears A, B, and X (a copy of A or B) and says which one X matches. Chance level is 50 %. | `building_block_abx.ipynb`, `full_experiment_abx.ipynb` | `configs/abx.yml` |
| **MUSHRA (drag & drop)** | How do several versions of a sound *rate* against a reference (e.g. audio quality)? Participant drags one tile per stimulus onto a rating scale. | `building_block_drag_and_drop_mushra.ipynb`, `full_experiment_drag_and_drop_mushra.ipynb` | `configs/drag_and_drop_mushra.yml` |
| **Staircase N-AFC** | What is the *threshold* of hearing a difference? An adaptive procedure makes trials harder after correct answers and easier after mistakes; each trial is an N-alternative forced choice ("which of these N sounds is the odd one out?"). | `building_block_staircase_n_afc.ipynb`, `full_experiment_staircase_n_afc.ipynb` | `configs/staircase_n_afc.yml` |
| **Scale testing** | How does a single sound score on one or more rating scales (Likert buttons or sliders)? One stimulus per screen, several questions stacked below it. | `building_block_scale_testing.ipynb` (building block only) | `configs/scale_testing.yml` |

Two more building blocks provide the framing around a test:

- `building_block_welcome_and_thanks.ipynb` — the welcome screen shown before
  everything and the thank-you screen shown at the end
  (`configs/welcome.yml`, `configs/thanks.yml`).
- `building_block_consent.ipynb` — the consent questionnaire that also
  creates the anonymous participant ID (section 9).

**To build your own custom experiment**, create a new notebook and paste
cells from the building blocks in the order you want (welcome → consent →
one or more tests → thanks). The full-experiment notebooks are exactly that,
already assembled.

## 8. Using your own audio files

The demo sounds in `examples/demo_stimuli/` are synthetic examples. For a
real experiment you swap in your own WAVs — again without touching Python:

**Step 1.** Put your WAV files into one folder (anywhere on your computer).

**Step 2.** In the notebook's setup cell, point `stimuli_dir` at that folder:

```python
stimuli_dir = Path(r"C:\my_experiment\stimuli")
```

**Step 3.** In the experiment's config, map a short **stimulus id** to each
file under the `SoundDevice:` block, then use those ids in the trial plan.
For ABX, for example:

```yaml
SoundDevice:
  ref:  { file: reference.wav }
  proc: { file: processed.wav }

pairs:
  - { a: ref, b: proc, name: my comparison }
```

The ids (`ref`, `proc`, …) are what gets written into the results file, so
choose descriptive names.

**Rules your files must follow** (whispy checks them when loading and stops
with a clear error if violated):

- **WAV format.**
- **No clipping** — every sample must stay below full scale
  (|amplitude| < 1). Normalize with some headroom, e.g. to a peak of ~0.7.
- **One sampling rate for all files** — you can't mix 44.1 kHz and 48 kHz in
  one experiment.
- **Every id used in the trial plan must be defined** under `SoundDevice:`.

The ABX and other notebooks include a **pre-flight check cell** that lists
every file with its sampling rate and peak level and flags problems — run it
after any change to your stimuli, *before* seating a participant.

## 9. Running a real experiment with participants

Use the `full_experiment_<test>.ipynb` notebook. It runs, in order:

1. **Welcome screen** — a fullscreen greeting; edit the text in
   `configs/welcome.yml` (markdown formatting works).
2. **Consent questionnaire** — records consent and general questions, and
   builds an **anonymous participant ID** from four of the answers (e.g.
   initials + a birthday digit → `HPo1`). No name is ever stored. The ID is
   kept in memory for the rest of the notebook and is baked into the *names*
   of all files saved for this participant.
3. **The test itself** — one window per trial/screen; each cell blocks until
   the participant finishes.
4. **Thank-you screen** — edit `configs/thanks.yml`.

**Checklist per participant:**

- [ ] Restart the notebook kernel (fresh start, no leftover variables).
- [ ] Check audio output device and a comfortable, fixed playback level.
- [ ] Run the notebook top to bottom (or "Run All"); hand over the keyboard/mouse.
- [ ] After the thank-you screen, confirm the CSV files appeared in
      `examples/results/` with the participant's ID in the filename.

The test windows can't be closed by the participant until the current screen
is completed, so a stray click on ✕ won't lose data.

## 10. Where your results end up

Every notebook ends with a call to `save_results(...)`, which writes a CSV
file into **`examples/results/`**. Files are **never overwritten** — a
number is appended if the name already exists — and every filename carries a
timestamp:

- with a participant ID: `abx_HPo1_20260707-143000.csv`
- without one (building blocks run standalone): `abx_0001_20260707-143000.csv`

A CSV is a plain table: open it in Excel, or in Python with
`pandas.read_csv(...)`. One row per trial (ABX, N-AFC) or per rating
(MUSHRA, scale testing), with columns for the block/section names, the
stimulus ids, the answer, whether it was correct (where applicable), and the
response time `rt` in seconds.

## 11. Changing the look and the wording

- **Wording** (the task question, button labels, hints, welcome/thank-you
  text) lives in each experiment's config under `ui:`, or in
  `welcome.yml`/`thanks.yml`/the questionnaire configs. Just edit the text.
- **Look** (window size, colors, fonts, button geometry) lives centrally in
  `configs/design.yml`, so all tests share one theme. Any design key can be
  overridden for a single experiment by adding it to that experiment's `ui:`
  block — e.g. `configs/abx.yml` narrows its content area with
  `content_area_size: [60, 80]`.
- Useful `design.yml` keys: `window_size` (`"fullscreen"` or `[width,
  height]`), `screen` (which monitor windows open on: `"primary"`,
  `"cursor"`, or a monitor index/name — handy when the experimenter's screen
  differs from the participant's), and one `*_fontsize` key per on-screen
  text.
- A **"Trial X of Y" progress bar** can be switched on per test with
  `show_progress: true` in its `ui:` block; the wording is set with
  `progress_text`.

## 12. Troubleshooting

**A test window is open and I can't close it.**
By design — participants must finish the screen first. During development,
interrupt or restart the notebook kernel (VS Code: the ⏹/restart buttons at
the top of the notebook), and the window disappears. For quick testing you
can also construct UIs with `debug=True`, which re-enables the ✕ button.

**`ValueError` when the notebook loads the stimuli.**
Read the message — it tells you exactly which rule from section 8 was broken
(clipping file, mixed sampling rates, missing file, or an id used in the
trial plan that isn't defined under `SoundDevice:`). Run the pre-flight
check cell for a full report.

**No sound, or sound on the wrong device.**
whispy plays through your system's *default* output device via the
`sounddevice` package. Set the right device as default in your operating
system's sound settings before starting, then restart the kernel.

**`ModuleNotFoundError: No module named 'whispy'` (or `PyQt6`, `pyfar`, …).**
The notebook is running in the wrong Python environment. In VS Code, click
the kernel picker (top right of the notebook) and select the environment
where you ran `pip install -e .` (e.g. `whispy`).

**I edited a config but nothing changed.**
Configs are read when the setup cell runs. Re-run the notebook from the
setup cell (or restart and Run All) after saving the YAML.

**YAML error when loading a config** (`ScannerError`/`ParserError`).
Almost always an indentation problem — YAML needs consistent spaces, no
tabs. Compare your edit against the untouched parts of the file, or against
the version on GitHub.

**Windows open on the wrong monitor.**
Set the `screen:` key in `configs/design.yml` (see section 11).

**The notebook cell seems stuck / never finishes.**
It's probably *waiting* — the test cells block until the window is
completed. Look for an open whispy window (possibly on another monitor or
behind other windows).

## 13. Glossary

- **Stimulus** — one sound (a WAV file) played to the participant, referred
  to by its short **stimulus id** from the config.
- **Trial** — one question answered by the participant (e.g. one A/B/X
  presentation).
- **Screen** — one window's worth of content; some tests put several stimuli
  on one screen (MUSHRA), others one trial per screen (ABX, N-AFC).
- **Block / section** — grouping levels for trials in the config; their
  names are written into the results so you can filter by them.
- **Reference** — the known "original" sound that test stimuli are compared
  against (used by MUSHRA).
- **N-AFC** — *N-alternative forced choice*: the participant *must* pick one
  of N options (no "don't know").
- **Staircase** — an adaptive procedure that homes in on a perception
  threshold by making trials harder after correct answers and easier after
  wrong ones.
- **MUSHRA** — *MUltiple Stimuli with Hidden Reference and Anchor*, a
  standard method for rating audio quality of several versions at once.
- **YAML** — the human-readable text format of the config files.
- **Kernel** — the Python process behind a Jupyter notebook; restarting it
  gives you a clean slate.
