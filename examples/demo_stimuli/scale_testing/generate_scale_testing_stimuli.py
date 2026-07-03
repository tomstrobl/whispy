#%% Generate stimuli for the scale-testing demo
#
# A scale-testing screen presents ONE stimulus and asks the participant to
# rate it on several scales (the demo config asks for roughness, brightness
# and pleasantness). This makes four harmonic tones spanning a 2x2 grid of
# the first two attributes, so the demo ratings have something to find:
#   - smooth_dark   : few, weak harmonics, no modulation
#   - smooth_bright : many, strong harmonics, no modulation
#   - rough_dark    : few, weak harmonics, 70 Hz amplitude modulation
#   - rough_bright  : many, strong harmonics, 70 Hz amplitude modulation
# Brightness comes from the harmonic spectrum (count + spectral slope),
# roughness from amplitude modulation in the roughness-sensitive range.
# These match configs/scale_testing.yml. Run this script from inside the
# examples/demo_stimuli/scale_testing/ directory to (re)create the WAVs next
# to it.
#
# This is intentionally separate from the other example stimulus generators.
import numpy as np
import pyfar as pf

sampling_rate = 44100
duration = 1.5            # seconds
fundamental = 220.0       # Hz
modulation_frequency = 70.0   # Hz, in the roughness-sensitive range
fade = 0.02               # seconds of raised-cosine fade in/out (no clicks)

# Shared peak amplitude for every stimulus. Level-matching ensures the
# stimuli differ only in timbre, and the value stays below 1 so nothing clips
# (SoundDevice rejects stimuli with |sample| >= 1).
target_amplitude = 0.7

# (id, number_of_harmonics, spectral_slope_db_per_harmonic, modulated)
stimuli = [
    ("smooth_dark", 4, -12.0, False),
    ("smooth_bright", 20, -2.0, False),
    ("rough_dark", 4, -12.0, True),
    ("rough_bright", 20, -2.0, True),
]

t = np.arange(int(sampling_rate * duration)) / sampling_rate
n_fade = int(sampling_rate * fade)
envelope = np.ones_like(t)
ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(n_fade) / n_fade)
envelope[:n_fade] = ramp
envelope[-n_fade:] = ramp[::-1]

for stim_id, n_harmonics, slope_db, modulated in stimuli:
    tone = np.zeros_like(t)
    for k in range(1, n_harmonics + 1):
        amplitude = 10 ** (slope_db * (k - 1) / 20)
        tone += amplitude * np.sin(2 * np.pi * fundamental * k * t)
    if modulated:
        # Full-depth amplitude modulation -> strong roughness sensation.
        tone *= 0.5 * (1 + np.sin(2 * np.pi * modulation_frequency * t))
    tone *= envelope

    stimulus = pf.Signal(tone, sampling_rate)
    # Normalise each stimulus to the same peak so loudness is (roughly) not a
    # cue and nothing clips.
    stimulus = pf.dsp.normalize(stimulus) * target_amplitude
    peak = float(np.max(np.abs(stimulus.time)))
    assert peak < 1, (
        f"{stim_id} clips (peak={peak:.3f}); lower target_amplitude")
    pf.io.write_audio(stimulus, f"{stim_id}.wav")
    print(f"wrote {stim_id}.wav  ({n_harmonics} harmonics, {slope_db} dB/harmonic,"
          f" {'modulated' if modulated else 'unmodulated'}, peak={peak:.3f})")
