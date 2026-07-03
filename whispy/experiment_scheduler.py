from whispy.utils import read_config
import numpy as np
import time
from typing import Optional, List, Dict

class ExperimentScheduler():
    """
    Generate a randomized experimental schedule from configuration.

    Parameters
    ----------
    experiment : list, dict, or str
        The experiment definition: a list of blocks, a combined experiment
        config that nests them under an ``experiment:`` block, or a path to a
        YAML file containing either. Required (raises ``ValueError`` if
        ``None``).
    randomize_blocks : bool, optional
        Whether to randomize the order of blocks of the experiment. The default
        is ``True``.
    randomize_sections : bool, optional
        Whether to randomize the order of sections within blocks of the
        experiment. The default is ``True``.
    randomize_conditions : bool, optional
        Whether to randomize the order of conditions within sections of the
        experiment. The default is ``True``.
    max_conditions_per_gui : int, optional
        Maximum number of conditions to display per GUI screen. The default is
        ``7``.
    random_seed : int, optional
        Seed for random number generator. If ``None``, the current internet
        time in seconds ``time.time()`` is used.

    Returns
    -------
    schedule:
        Experimental schedule class. Contains the schedule in
        `schedule.schedule` and can be iterated to run the experiment.

    Examples
    --------
    .. code-block:: python

        import whispy

        # create the scheduler from a combined experiment config (it reads the
        # `experiment:` block)
        scheduler = whispy.ExperimentScheduler(
            experiment="configs/drag_and_drop_mushra.yml")

        # initalize results
        results = None

        # iterate over rating screens
        for screen in scheduler:

            # verbose information of current conditions
            print(screen)

            # run a drag and drop MUSHRA-like experiment
            mushra_like = whispy.DragAndDropMushra(screen)

            # update results
            results = mushra_like.get_results(results)
    """

    def __init__(
            self,
            experiment: Optional[str] = None,
            randomize_blocks: Optional[bool] = True,
            randomize_sections: Optional[bool] = True,
            randomize_conditions: Optional[bool] = True,
            max_conditions_per_gui: Optional[int] = 7,
            random_seed: Optional[int] = None
        ):

        self.schedule = _course(
            experiment,
            randomize_blocks,
            randomize_sections,
            randomize_conditions,
            max_conditions_per_gui,
            random_seed)

    def __iter__(self):
        return iter(self.schedule)


def _course(
        experiment: Optional[str] = None,
        randomize_blocks: Optional[bool] = True,
        randomize_sections: Optional[bool] = True,
        randomize_conditions: Optional[bool] = True,
        max_conditions_per_gui: Optional[int] = 7,
        random_seed: Optional[int] = None) -> List[Dict]:
    """Generate a randomized experimental course from configuration.

    Parameters
    ----------
    experiment : list, dict, or str
        The experiment definition: a list of blocks, a combined experiment
        config that nests them under an ``experiment:`` block, or a path to a
        YAML file containing either. Required (raises ``ValueError`` if
        ``None``).
    randomize_blocks : bool, optional
        Whether to randomize the order of blocks of the experiment. The default
        is ``True``.
    randomize_sections : bool, optional
        Whether to randomize the order of sections within blocks of the
        experiment. The default is ``True``.
    randomize_conditions : bool, optional
        Whether to randomize the order of conditions within sections of the
        experiment. The default is ``True``.
    max_conditions_per_gui : int, optional
        Maximum number of conditions to display per GUI screen. The default is
        ``7``.
    random_seed : int, optional
        Seed for random number generator. If ``None``, the current internet
        time in seconds ``time.time()`` is used.

    Returns
    -------
    experimental_course: list of dict
        Experimental course as a list. Each element contains the keys
        blocks, sections, references, test conditions, and flags indicating
        block/section changes.
    """

    # load config
    if experiment is None:
        raise ValueError(
            "ExperimentScheduler needs an experiment: pass experiment=<list of "
            "blocks>, the combined experiment config that nests them under an "
            "`experiment:` block, or a path to a YAML file with either.")

    experiment = read_config(experiment)
    # accept either the experiment list directly or a combined experiment
    # config that nests it under an `experiment:` block
    if isinstance(experiment, dict):
        if "experiment" not in experiment:
            raise ValueError(
                "experiment config dict has no `experiment:` block")
        experiment = experiment["experiment"]

    # initialize experimental_course
    experimental_course = []

    # initialize random generator
    if random_seed is None:
        random_seed = int(time.time())

    rng = np.random.default_rng(random_seed)

    # randomize blocks
    n_blocks = len(experiment)

    if randomize_blocks and n_blocks > 1:
        blocks = rng.permutation(n_blocks)
    else:
        blocks = np.arange(n_blocks)

    # loop blocks
    for b_idx in blocks:

        # get current block
        block_raw = experiment[b_idx]["block"]
        # filter out everything that is not a section (block meta data)
        block = [b for b in block_raw if 'section' in b]
        block_name = [b['block_name'] for b in block_raw if 'block_name' in b]

        # randomize sections
        n_sections = len(block)

        if randomize_sections and n_sections > 1:
            sections = rng.permutation(n_sections)
        else:
            sections = np.arange(n_sections)

        # loop sections
        for s_idx in sections:
            section = block[s_idx]["section"]

            # randomize conditions
            n_conditions = len(section["test"])
            conditions = section["test"]

            if randomize_conditions and n_conditions > 1:
                conditions = rng.permutation(conditions)

            # split conditions across multiple rating GUIs
            n_gui = int(np.ceil(n_conditions / max_conditions_per_gui))

            for g_idx in range(n_gui):

                # check if block or section changed
                if experimental_course:
                    block_changed = \
                        experimental_course[-1]["block"] != b_idx
                    section_changed = \
                        experimental_course[-1]["section"] != s_idx
                    # ignore section change at the start of a new block
                    section_changed = section and not block_changed
                else:
                    # beginning of the experiment
                    block_changed, section_changed = (True, True)

                # get current conditions (if split across multiple GUIs)
                t_start = g_idx * max_conditions_per_gui
                t_end = min(n_conditions, t_start + max_conditions_per_gui)

                # append current line of the experiment
                # `reference` and `attribute` are MUSHRA-specific; sections of
                # other tests (e.g. scale testing) simply omit them -> None.
                experimental_course.append(
                    {"block": int(b_idx),
                     "section": int(s_idx),
                     "reference": section.get("reference"),
                     "test": conditions[t_start:t_end],
                     "block_changed": bool(block_changed),
                     "section_changed": bool(section_changed),
                     "attribute": section.get("attribute"),
                     "block_name": block_name[0],
                     "section_name": section.get("section_name"),}
                )

    # attach the position within the whole schedule to every screen, so the
    # UIs can show a trial-progress bar (`show_progress` in their ui: block)
    total = len(experimental_course)
    for position, screen in enumerate(experimental_course, start=1):
        screen["progress"] = {"current": position, "total": total}

    return experimental_course
