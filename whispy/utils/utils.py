import os

import yaml

# Directory holding the package-default configs (``configs/`` at the repo root).
_CONFIGS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "configs")


def read_config(file):
    """Read a YAML configuration file.

    Parameters
    ----------
    file : str, os.PathLike, dict, or list
        Path to the YAML configuration file. An already-loaded config (``dict``
        or ``list``) is returned unchanged.

    Returns
    -------
    config : dict
        The configuration.
    """

    # Allow an already-loaded config (dict/list) to pass through unchanged. This
    # lets a single combined config be read once and its sub-sections handed to
    # the individual consumers (e.g. ExperimentScheduler, DragAndDropMUSHRA), so
    # a whole experiment can be described in one file.
    if isinstance(file, (dict, list)):
        return file

    # Always decode as UTF-8. Without an explicit encoding, Python uses the
    # locale default (cp1252 on Windows), which fails on the non-ASCII bytes in
    # the configs (e.g. the ℹ️ glyph); macOS/Linux default to UTF-8.
    with open(file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def load_design(overrides=None, *, path=None):
    """Return the global UI theme, merged with optional per-UI overrides.

    ``configs/design.yml`` is the single source of truth for the look shared by
    every whispy UI (colors, fonts, button styling). Individual UIs load it via
    this helper and may layer their own theme tweaks on top, so all listening
    tests look alike by default while remaining individually customizable.

    Parameters
    ----------
    overrides : dict, str, os.PathLike, or None, optional
        A mapping of theme keys to override, or a path to a YAML file of such
        keys. Keys whose value is ``None`` are ignored, so a per-UI config can
        keep a key as a commented placeholder without clobbering the global
        default.
    path : str, optional
        Path to the global design file. Defaults to ``configs/design.yml``.

    Returns
    -------
    dict
        The merged theme: global defaults updated with ``overrides``.
    """
    if path is None:
        path = os.path.join(_CONFIGS_DIR, "design.yml")

    design = read_config(path) or {}
    merged = dict(design)

    # A non-dict, non-None override is treated as a path to a YAML file
    # (str or os.PathLike, e.g. pathlib.Path).
    if overrides is not None and not isinstance(overrides, dict):
        overrides = read_config(overrides) or {}
    if isinstance(overrides, dict):
        merged.update({k: v for k, v in overrides.items() if v is not None})

    return merged