import yaml

def read_config(file):
    """Read a YAML configuration file.

    Parameters
    ----------
    file : str
        Path to the YAML configuration file.

    Returns
    -------
    config : dict
        The configuration.
    """

    with open(file, "r") as f:
        config = yaml.safe_load(f)
    return config
