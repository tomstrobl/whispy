# whispy

A config-driven Python toolkit for running listening tests and/or perceptual
experiments. 
It provides PyQt6 UIs (drag-and-drop MUSHRA-like rating, N-AFC, ABX, rating
scales, questionnaires, info screens) and stimulus playback via
`sounddevice` / `pyfar` - or OSC messages to external audio software - all
driven by YAML configuration.
The tests run in Jupyter notebooks: either run a predefined full experiment
or compile your own setup from the building blocks. 

> 📑 **Presentation:** for a quick visual introduction to the project, see our
> final presentation [slide deck (PDF, in German)](docs/AbschlussPraes_PyAk.pdf).

Available predefined test setups:

- ### ABX
    Simple comparison test to distinguish perceptual differences. A reference signal and a manipulated signal are randomly assigned to A and B; one of the two is copied to X, and the participant's task is to identify whether X is equal to A or to B.
    
- ### MUSHRA (drag and drop)
    Multiple Stimuli with Hidden Reference and Anchor - test, a standardized methodology used to evaluate the perceived quality of intermediate-to-high quality audio systems, such as audio codecs, generative speech models, and spatial audio. Defined by the ITU-R BS.1534 recommendation, it allows listeners to compare multiple audio samples simultaneously against a known reference and rate them on a continuous scale from 0 to 100 (e.g., rate a difference) or -50 to 50 (e.g., lower or higher comparison).

    In this case (drag-and-drop) the participant can drag and drop the test stimuli into a rating area which allows for a more natural interaction.

- ### Staircase N-AFC
    N-AFC (N-Alternative Forced Choice): In every trial, the participant is presented with N options (usually 2, 3, or 4). For example, in a 3-AFC test, the participant is given three stimuli (e.g., three different flavors, or three time intervals) and is "forced" to choose which one is different or more intense, even if they have to guess. This prevents participants from relying on arbitrary "yes/no" criteria.

    
    Staircase (Up-Down) Method: This is the adaptive testing algorithm. The test gets harder when the participant gets answers right and easier when they get answers wrong.

- ### Scale test
    Rating test for a given stimulus (e.g., "How rough is this tone?"), answered on one or more Likert-button or slider scales stacked below a single play button.

Additionally, **questionnaires** can be added anywhere in an experiment: fully config-driven surveys with free-text, numeric, single-choice and multiple-choice questions, including follow-up questions that only appear depending on earlier answers. The predefined ones (see [`configs/questionnaires/`](configs/questionnaires/)) are a consent form - which also builds the anonymous participant ID used in the result file names - and a general questionnaire about the participant and the listening setup.

> **Config-driven:** every test can be tailored in its `configs/<test>.yml`
> file - wording, stimuli, scales, trial plan - without touching any Python.


## Installation

Clone the repository to your local machine. Navigate with `cd` to your desired 
folder and run:
```
git clone https://github.com/tomstrobl/whispy.git
```
Then change into the cloned folder and install the package with all required
dependencies:

```bash
cd whispy
pip install -e .
```

After this you can open the Jupyter notebooks in [`examples/`](examples/) in
your preferred IDE and run them.

### Requirements

- Python >= 3.11
- All Python dependencies (PyQt6, pyfar, sounddevice, pandas, ...) are
  installed automatically by `pip install -e .`

## Usage

**New to whispy (or to Python)?** Start with the step-by-step
[User Manual](docs/USER_MANUAL.md) - it covers installation, running the
demos, designing your own experiment via the YAML configs, and troubleshooting.

See the runnable demos in [`examples/`](examples/) - each test ships as a minimal
`building_block_<test>.ipynb` and a full `full_experiment_<test>.ipynb`
(welcome → consent → test → thank-you, all presented inside one shared
fullscreen window):

- `drag_and_drop_mushra` - MUSHRA-like drag-and-drop rating.
- `staircase_n_afc` - adaptive staircase driving N-AFC trials.
- `abx` - ABX discrimination.
- `scale_testing` - attribute rating on Likert-button/slider scales.

There are also building blocks for the questionnaire and the framing
welcome/thank-you screens, and `full_experiment_audience_demo.ipynb`, a
~7-minute live demo chaining all UI types.

Each notebook contains step-by-step instructions. Results are saved as CSV
files into `examples/results/`; the full experiments additionally autosave
after every trial, so even a crash mid-run loses at most the trial in
progress.


## Architecture

A Jupyter notebook (the *driver*) reads one self-contained YAML config, an *orchestrator*
turns it into a sequence of screens, a *UI* presents each screen - all inside
one shared experiment window - and plays its stimuli through the audio
*interface*, and every screen's answers are collected into a results table,
combined with a participant's ID.

```mermaid
%% whispy architecture - paste into https://mermaid.live to export PNG/SVG
%%{init: {"theme":"base","fontFamily":"Arial","themeVariables":{"fontFamily":"Arial","fontSize":"38px","lineColor":"#6b7280"},"flowchart":{"curve":"basis","nodeSpacing":80,"rankSpacing":110,"padding":18,"htmlLabels":false,"useMaxWidth":true}}}%%

flowchart TB
    subgraph DRV["Driver - examples/ notebooks"]
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
        EH["ExperimentHost<br/>(one shared window per experiment)"]
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
    class MU,NA,AB,ST,QU,IN,PI,EH ui;
    class SH,SD,FAC,OSC aud;
    class GR,SR res;
    class NB drv;
    class PL,SP plt;

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

> The same diagram lives in [`docs/architecture.mmd`](docs/architecture.mmd) -
> the editable source you can paste into [mermaid.live](https://mermaid.live) to
> export a PNG/SVG for slides. Keep the two in sync when you change it.


## Example User Interfaces

The ABX-test screen:

<img src="docs/images/ABX_test_screen.png" width="450" alt="ABX Test Screen">

The drag-and-drop-MUSHRA-test screen:

<img src="docs/images/d_a_d_MUSHRA_screen.png" width="450" alt="Drag-and-drop-MUSHRA Test Screen">

## Authors and acknowledgement

- Brinkmann, Fabian
- Strobl, Tom
- Ventura, Aron Manuel
- Will, Maximilian

## License

MIT - see [`LICENSE`](LICENSE).
