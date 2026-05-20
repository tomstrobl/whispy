# %%
import whispy
from pprint import pprint

config = whispy.utils.read_config("configs/config.yml")

pprint(config["stimuli"])

# %%
with open("whispy/configs/config.yml", "r") as f:
    config = yaml.safe_load(f)

pprint(config["stimuli"])
