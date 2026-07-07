# whispy

A config-driven Python toolkit for running listening tests and/or perceptual
experiments. 
It provides PyQt6 UIs (drag-and-drop MUSHRA-like rating, N-AFC,
questionnaires, info screens) and audio playback via `sounddevice` / `pyfar`,
all driven by YAML configuration.
The tests run in jupyter notebooks and either predefined full experiments can 
be chosen or individual test setups can be compiled from the building blocks. 

Available predefined test setups:

- ABX
- Mushra (Drag and drop)
- Staircase N-AFC

## User Interface

The welcome screen, first seen by the participant (can be configured in <welcome.yml>):

<img src="/images/welcome_screen.png" width="600" alt="Welcome screen">

The ID and consent screen. There the participant sets his own ID, gives (or rejects)
the use of the respective data and is able to collect listening hours needed as a 
Audiocommunication and -technoligy student:

<img src="/images/ID_and_consent_screen.png" width="600" alt="Welcome screen">

The ABX-test screen:

<img src="/images/ABX_test_screen.png" width="600" alt="Welcome screen">

A drag-and-drop-MUSHRA Info-window explaining the following task:

<img src="/images/Info_window_MUSHRA.png" width="200" alt="Welcome screen">

The drag-and-drop-MUSHRA-test screen:

<img src="/images/d_a_d_MUSHRA_screen.png" width="600" alt="Welcome screen">

The Staircase N-AFC-test screen

<img src="/images/Staircase_N_ACF_Test_screen.png" width="600" alt="Welcome screen">

The thank you screen (the shown greeting can be configured in <thanks.yml>):

<img src="/images/Thank_you_screen.png" width="600" alt="Welcome screen">

## Installation

Clone the repository to your local mashine. Navigate with `cd` to your desired 
folder and run:
```
git clone https://github.com/tomstrobl/whispy.git
```
Next, run:

```bash
pip install -e .
```
in your terminal to install all required packages. After this you can open the 
jupyter notebooks in your prefered IDE and the whispy-blocks are executable.

### Requirements

Whispy runs in:
*already tested*
- Visual Studio Code
- 

and works with:
- python verions >= 3.13.13 
- anaconda >= 22.9.0


## Usage

**New to whispy (or to Python)?** Start with the step-by-step
[User Manual](docs/USER_MANUAL.md) - it covers installation, running the
demos, designing your own experiment via the YAML configs, and troubleshooting.

See the runnable demos in [`examples/`](examples/) — each test ships as a minimal
`building_block_<test>.ipynb` and a full `full_experiment_<test>.ipynb` (consent
→ test → thank-you):

- `drag_and_drop_mushra` — MUSHRA-like drag-and-drop rating.
- `staircase_n_afc` — adaptive staircase driving N-AFC trials.
- `abx` — ABX discrimination.

Each building_block_<test>.ipynb and full_experiment_<test>.ipynb provides additional 
instructions for smooth use.

### Quick start

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

## Architecture

A jupyter-notebook (the *driver*) reads one self-contained YAML config, an *orchestrator*
turns it into a sequence of screens, a *UI* presents each screen and plays its
stimuli through the audio *interface*, and every screen's answers are collected 
into a results table, combined with a participants ID.

```mermaid
%%{init: {"theme":"base","fontFamily":"Arial","themeVariables":{"fontFamily":"Arial","fontSize":"14px","lineColor":"#6b7280"},"flowchart":{"curve":"basis","nodeSpacing":80,"rankSpacing":110,"padding":18,"htmlLabels":false,"useMaxWidth":true}}}%%
flowchart TB
    subgraph DRV["Driver — examples/ notebooks"]
        NB["building_block_*  ·  full_experiment_*"]
    end

    subgraph CFG["Configuration (YAML)"]
        direction TB
        C1["design.yml (shared theme incl. progress bar)"]
        C2["drag_and_drop_mushra.yml · staircase_n_afc.yml · abx.yml · n_afc.yml"]
        C3["welcome.yml · thanks.yml"]
        C4["questionnaires/*.yml"]
    end

    subgraph ORCH["Orchestration"]
        SCH["ExperimentScheduler<br/>drives MUSHRA<br/>randomizes → yields screen dicts<br/>(incl. trial progress)"]
        STC["Staircase<br/>drives staircase N-AFC<br/>adaptive up/down (incl. trial progress)"]
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

    NB --> SCH
    NB --> STC
    NB -->|"ABX trials"| AB
    SCH -->|"screen dicts"| MU
    STC -->|"N-AFC trials"| NA
    SH --> SD
    UI -->|"play(stimulus)"| SH
    UI -->|"rows / trial"| GR
    GR --> SR

    CFG -.-> AUD
    CFG -.-> UI 
    CFG -. feeds every layer .-> ORCH

    classDef cfg fill:#E9C46A,stroke:#C9A227,stroke-width:1.5px,color:#5a4708;
    classDef orch fill:#E76F51,stroke:#c0492f,stroke-width:1.5px,color:#fff;
    classDef ui fill:#2A9D8F,stroke:#1f6f64,stroke-width:1.5px,color:#fff;
    classDef aud fill:#264653,stroke:#16303a,stroke-width:1.5px,color:#fff;
    classDef res fill:#8AB17D,stroke:#5e8a4f,stroke-width:1.5px,color:#22331b;
    classDef drv fill:#2D3142,stroke:#1b1d28,stroke-width:1.5px,color:#fff;
    class C1,C2,C3,C4 cfg;
    class SCH,STC orch;
    class MU,NA,AB,QU,IN,PI ui;
    class SH,SD aud;
    class GR,SR res;
    class NB drv;

    %% soft per-cluster background tints (a light wash of each group's colour)
    style DRV fill:#ECEDF1,stroke:#2D3142,stroke-width:1.5px,color:#2D3142;
    style CFG fill:#FBF3DC,stroke:#E9C46A,stroke-width:1.5px,color:#5a4708;
    style ORCH fill:#FBE5DE,stroke:#E76F51,stroke-width:1.5px,color:#7a2e1c;
    style UI fill:#DEF1EE,stroke:#2A9D8F,stroke-width:1.5px,color:#1f6f64;
    style AUD fill:#DEE5E8,stroke:#264653,stroke-width:1.5px,color:#264653;
    style RES fill:#E9F0E5,stroke:#8AB17D,stroke-width:1.5px,color:#3f5a33;

    %% edges: data flow in grey, the dotted config feeds in soft gold
    linkStyle default stroke:#6b7280,stroke-width:1.6px;
    linkStyle 9,10,11 stroke:#caa83f,stroke-width:1.4px;
```

> The same diagram lives in [`docs/architecture.mmd`](docs/architecture.mmd) —
> the editable source you can paste into [mermaid.live](https://mermaid.live) to
> export a PNG/SVG for slides. Keep the two in sync when you change it.

## Authors and acknowledgement

Brinkmann, Fabian; 
Strobl, Tom; 
Goldfuss, Jonathan; 
Ventura, Aron Manuel; 
Will, Maximilian; 

## License

MIT — see [`LICENSE`](LICENSE).
