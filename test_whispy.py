# %%
import yaml
from pprint import pprint

with open("whispy/configs/config.yml", "r") as f:
    config = yaml.safe_load(f)

pprint(config["stimuli"])
