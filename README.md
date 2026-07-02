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

## Architecture

A notebook (the *driver*) reads one self-contained YAML config, an *orchestrator*
turns it into a sequence of screens, a *UI* presents each screen and plays its
stimuli through the audio *interface*, and every screen's answers are collected
into a results table.

```mermaid
%%{init: {"theme":"base","fontFamily":"Arial","themeVariables":{"fontFamily":"Arial","fontSize":"14px","lineColor":"#6b7280"},"flowchart":{"curve":"natural","nodeSpacing":55,"rankSpacing":70,"padding":12,"htmlLabels":false,"useMaxWidth":true}}}%%
flowchart TB
    subgraph DRV["Driver — examples/ notebooks"]
        NB["building_block_*  ·  full_experiment_*"]
    end

    subgraph CFG["Configuration (YAML)"]
        direction TB
        C1["design.yml"]
        C2["drag_and_drop_mushra.yml · staircase_n_afc.yml · abx.yml"]
        C5["questionnaire_*.yml"]
        C6["thanks.yml"]
    end

    subgraph ORCH["Orchestration"]
        SCH["ExperimentScheduler<br/>drives MUSHRA<br/>randomizes → yields screen dicts"]
        STC["Staircase<br/>drives staircase N-AFC<br/>adaptive up/down"]
    end

    subgraph UI["UI layer (PyQt6)"]
        MU["DragAndDropMUSHRA"]
        NA["NAFC"]
        AB["ABX"]
        QU["Questionnaire"]
        IN["InfoWindow"]
        PI["ParticipantID (legacy)"]
    end

    subgraph AUD["Interface"]
        SH["StimuliHandler (ABC)"]
        SD["SoundDevice"]
    end

    subgraph RES["Results"]
        GR["get_results() → pandas DataFrame"]
        SR["save_results() → examples/results/*.csv"]
    end

    NB --> ORCH
    SCH -->|screen dicts| MU
    STC -->|N-AFC trials| NA
    UI -->|"play(stimulus)"| AUD
    SH --> SD
    UI -->|rows / trial| RES
    GR --> SR

    CFG -. feeds every layer .-> ORCH
    CFG -.-> UI
    CFG -.-> AUD

    classDef cfg fill:#E9C46A,stroke:#C9A227,stroke-width:1.5px,color:#5a4708;
    classDef orch fill:#E76F51,stroke:#c0492f,stroke-width:1.5px,color:#fff;
    classDef ui fill:#2A9D8F,stroke:#1f6f64,stroke-width:1.5px,color:#fff;
    classDef aud fill:#264653,stroke:#16303a,stroke-width:1.5px,color:#fff;
    classDef res fill:#8AB17D,stroke:#5e8a4f,stroke-width:1.5px,color:#22331b;
    classDef drv fill:#2D3142,stroke:#1b1d28,stroke-width:1.5px,color:#fff;
    class C1,C2,C5,C6 cfg;
    class SCH,STC orch;
    class MU,NA,AB,QU,IN,PI ui;
    class SH,SD aud;
    class GR,SR res;
    class NB drv;

    style DRV fill:#ECEDF1,stroke:#2D3142,stroke-width:1.5px,color:#2D3142;
    style CFG fill:#FBF3DC,stroke:#E9C46A,stroke-width:1.5px,color:#5a4708;
    style ORCH fill:#FBE5DE,stroke:#E76F51,stroke-width:1.5px,color:#7a2e1c;
    style UI fill:#DEF1EE,stroke:#2A9D8F,stroke-width:1.5px,color:#1f6f64;
    style AUD fill:#DEE5E8,stroke:#264653,stroke-width:1.5px,color:#264653;
    style RES fill:#E9F0E5,stroke:#8AB17D,stroke-width:1.5px,color:#3f5a33;

    linkStyle default stroke:#6b7280,stroke-width:1.6px;
    linkStyle 7,8,9 stroke:#caa83f,stroke-width:1.4px;
```

> The same diagram lives in [`docs/architecture.mmd`](docs/architecture.mmd) —
> the editable source you can paste into [mermaid.live](https://mermaid.live) to
> export a PNG/SVG for slides. Keep the two in sync when you change it.

## License

MIT — see [`LICENSE`](LICENSE).
