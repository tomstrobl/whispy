# whispy

A config-driven Python toolkit for running listening tests and/or perceptual
experiments. 
It provides PyQt6 UIs (drag-and-drop MUSHRA-like rating, N-AFC,
questionnaires, info screens) and audio playback via `sounddevice` / `pyfar`,
all driven by YAML configuration.
The tests run in jupyter notebooks and either predefined full experiments can 
be chosen or individual test setups can be compiled from the building blocks. 

> 📑 **Presentation:** for a quick visual introduction to the project, see our
> final presentation [slide deck (PDF, in German)](docs/AbschlussPraes_PyAk.pdf).

Available predefined test setups:

- ### ABX
    Simple comparison test to distinguish perceptual differences. A reference signal and a manipulated signal is randomly assigned to A and B and also to X and the participant's task is to identify whether A is equal to X or B is equal to X.
    
- ### MUSHRA (drag and drop)
    MUltiple Stimuli with Hidden Reference and Anchor - test, a standardized methodology used to evaluate the perceived quality of intermediate-to-high quality audio systems, such as audio codecs, generative speech models, and spatial audio. Defined by the ITU-R BS. 1534 recommendation, it allows listeners to compare multiple audio samples simultaneously against a known reference and rate them on a continuous scale from 0 to 100 (e.g., rate a difference) or -50 to 50 (e.g., lower or higher comparison).

    In this case (drag-and-drop) the participant can drag and drop the test stimuli into a rating area which allows for a more natural interaction.

- ### Staircase N-AFC
    N-AFC (N-Alternative Forced Choice): In every trial, the participant is presented with N options (usually 2, 3, or 4). For example, in a 3-AFC test, the participant is given three stimuli (e.g., three different flavors, or three time intervals) and is "forced" to choose which one is different or more intense, even if they have to guess. This prevents participants from relying on arbitrary "yes/no" criteria.

    
    Staircase (Up-Down) Method: This is the adaptive testing algorithm. The test gets harder when the participant gets answers right and easier when they get answers wrong.

- ### Scale test
    Rating test for a given stimulus (e.g., "How rough is this tone?")

#### *`Every test can be tailored in the respective <test>.yml config-files to meet the individual requirements.`*


## Installation

Clone the repository to your local machine. Navigate with `cd` to your desired 
folder and run:
```
git clone https://github.com/tomstrobl/whispy.git
```
Next, run:

```bash
pip install -e .
```
in your terminal to install all required packages. After this you can open the 
jupyter notebooks in your preferred IDE and the whispy-blocks are executable.

### Requirements

works with:
- python versions >= 3.13.13 
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

Each building_block_<test>.ipynb- and full_experiment_<test>.ipynb-file provides additional 
instructions for smooth use.


## Architecture

A jupyter-notebook (the *driver*) reads one self-contained YAML config, an *orchestrator*
turns it into a sequence of screens, a *UI* presents each screen and plays its
stimuli through the audio *interface*, and every screen's answers are collected 
into a results table, combined with a participant's ID.

```mermaid
%% whispy architecture — paste into https://mermaid.live to export PNG/SVG
%%{init: {"theme":"base","fontFamily":"Arial","themeVariables":{"fontFamily":"Arial","fontSize":"38px","lineColor":"#6b7280"},"flowchart":{"curve":"basis","nodeSpacing":80,"rankSpacing":110,"padding":18,"htmlLabels":false,"useMaxWidth":true}}}%%

flowchart TB
    subgraph DRV["Driver — examples/ notebooks"]
        NB["building_block_*  ·  full_experiment_*"]
    end

    subgraph CFG["Configuration (YAML)"]
        direction TB
        C1["design.yml (shared theme incl. progress bar)"]
        C2["drag_and_drop_mushra.yml · staircase_n_afc.yml · abx.yml · n_afc.yml · scale_testing.yml"]
        C3["welcome.yml · thanks.yml"]
        C4["questionnaires/*.yml"]
    end

    subgraph ORCH["Orchestration"]
        SCH["ExperimentScheduler<br/>drives MUSHRA & ScaleTest<br/>randomizes → yields screen dicts<br/>(incl. trial progress)"]
        STC["Staircase<br/>drives staircase N-AFC<br/>adaptive up/down (incl. trial progress)"]
    end

    subgraph UI["UI layer (PyQt6)"]
        QU["Questionnaire"]
        IN["InfoWindow"]
        MU["DragAndDropMUSHRA"]
        PI["ParticipantID (legacy)"]
        NA["NAFC"]
        AB["ABX"]
        ST["ScaleTest"]
    end

    subgraph AUD["Interface"]
        FAC["build_stimuli_handler()<br/>reads output: key"]
        SH["StimuliHandler (ABC)"]
        SD["SoundDevice"]
        OSC["OSCHandler"]
    end

    subgraph RES["Results"]
        direction LR
        GR["get_results() → pandas DataFrame"]
        SR["save_results() → examples/results/*.csv"]
    end

    subgraph PLT["Plots"]
        direction LR
        PL["plot_results() → in Notebook"]
        SP["save_plots() → examples/results/*.png"]
    end


    NB -->|"build_stimuli_handler(cfg)"| FAC
    NB --> SCH
    NB --> STC
    NB -->|"screen dicts (ABX)"| AB
    
    SCH -->|"screen dicts"| MU
    SCH -->|"screen dicts"| ST
    STC -->|"screen dicts (N-AFC)"| NA
    FAC -->|"output: sounddevice"| SD
    FAC -->|"output: osc"| OSC
    SD -.-> SH
    OSC -.-> SH
    UI -->|"play(stimulus)"| SH
    UI -->|"rows / trial"| GR
    GR --> SR

    SR -->|"reads results.csv"| PL
    PL -.-> SP

    CFG -.-> AUD
    CFG -. feeds every layer .-> ORCH
    CFG -.-> UI


    classDef cfg fill:#E9C46A,stroke:#C9A227,stroke-width:1.5px,color:#5a4708;
    classDef orch fill:#E76F51,stroke:#c0492f,stroke-width:1.5px,color:#fff;
    classDef ui fill:#2A9D8F,stroke:#1f6f64,stroke-width:1.5px,color:#fff;
    classDef aud fill:#264653,stroke:#16303a,stroke-width:1.5px,color:#fff;
    classDef res fill:#8AB17D,stroke:#5e8a4f,stroke-width:1.5px,color:#22331b;
    classDef drv fill:#2D3142,stroke:#1b1d28,stroke-width:1.5px,color:#fff;
    classDef plt fill:#94b1ff,stroke:#5E72A3,stroke-width:1.5px,color:#fff;

    class C1,C2,C3,C4 cfg;
    class SCH,STC orch;
    class MU,NA,AB,ST,QU,IN,PI ui;
    class SH,SD,FAC,OSC aud;
    class GR,SR res;
    class NB drv;
    class PL,SP, plt;

    %% soft per-cluster background tints (a light wash of each group's colour)
    style DRV fill:#ECEDF1,stroke:#2D3142,stroke-width:1.5px,color:#2D3142;
    style CFG fill:#FBF3DC,stroke:#E9C46A,stroke-width:1.5px,color:#5a4708;
    style ORCH fill:#FBE5DE,stroke:#E76F51,stroke-width:1.5px,color:#7a2e1c;
    style UI fill:#DEF1EE,stroke:#2A9D8F,stroke-width:1.5px,color:#1f6f64;
    style AUD fill:#DEE5E8,stroke:#264653,stroke-width:1.5px,color:#264653;
    style RES fill:#E9F0E5,stroke:#8AB17D,stroke-width:1.5px,color:#3f5a33;
    style PLT fill:#D3DFFF,stroke:#94b1ff,stroke-width:1.5px,color:#94b1ff;


    %% edges: data flow in grey, the dotted config feeds in soft gold
    linkStyle default stroke:#6b7280,stroke-width:1.6px;
    linkStyle 16,17,18 stroke:#caa83f,stroke-width:1.4px;
```

> The same diagram lives in [`docs/architecture.mmd`](docs/architecture.mmd) —
> the editable source you can paste into [mermaid.live](https://mermaid.live) to
> export a PNG/SVG for slides. Keep the two in sync when you change it.


## Example User Interfaces

The ABX-test screen:

<img src="docs/images/ABX_test_screen.png" width="450" alt="ABX Test Screen">

The drag-and-drop-MUSHRA-test screen:

<img src="docs/images/d_a_d_MUSHRA_screen.png" width="450" alt="Drag-and-drop-MUSHRA Test Screen">

## Authors and acknowledgement

Brinkmann, Fabian; 
Strobl, Tom; 
Goldfuss, Jonathan; 
Ventura, Aron Manuel; 
Will, Maximilian; 

## License

MIT — see [`LICENSE`](LICENSE).
