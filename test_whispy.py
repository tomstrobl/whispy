# %%
import whispy

config = whispy.utils.read_config("configs/mushra_like_2d.yml")

type(config["window_size"])

# %%
import whispy

whispy.methods.MushraLike2D()

# %%
from whispy.interfaces import SounddeviceHandler

playback = SounddeviceHandler()
# %%
playback.stop()
