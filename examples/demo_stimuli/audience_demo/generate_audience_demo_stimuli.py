#%% Generate stimuli for the audience demo (full_experiment_audience_demo.ipynb)
#
# The audience demo chains three short listening tests, and this one script
# generates the WAVs for all of them (matching configs/demo_configs/):
#
#   1. Staircase 2-AFC (staircase_demo.yml): pure-tone frequency
#      discrimination. `tone_standard` is a 1000 Hz reference; the targets are
#      tones ABOVE it, ordered from the smallest offset (hardest to tell
#      apart) to the largest (easiest). The staircase starts at the easiest
#      (+100 Hz, i.e. 1100 Hz) and narrows toward 1000 Hz as the participant
#      keeps hearing the difference.
#   2. ABX (abx_demo.yml): two clearly different, fun pairs - a major vs.
#      minor chord ("happy vs. sad") and a steady vs. vibrato tone.
#   3. Scale testing (scale_testing_demo.yml): funny/memorable novelty clips -
#      a cartoon "boing", a sad trombone, and alien chatter (a spare; swap it
#      into the config's `experiment:` block if you want a third screen).
#
# All stimuli are level-matched so loudness is not a cue, and every peak stays
# below 1 so nothing clips (SoundDevice rejects stimuli with |sample| >= 1).
# Run this script from inside the examples/demo_stimuli/audience_demo/
# directory to (re)create the WAVs next to it.
#
# This is intentionally separate from the other example stimulus generators.
import numpy as np
import pyfar as pf

sampling_rate = 44100
fade = 0.02               # seconds of raised-cosine fade in/out (no clicks)

# Shared peak amplitude for every stimulus (headroom below 1 -> no clipping).
target_amplitude = 0.7


def envelope(n_samples, n_fade=int(sampling_rate * fade)):
    """Raised-cosine fade in/out so tones start and stop without clicks."""
    env = np.ones(n_samples)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(n_fade) / n_fade)
    env[:n_fade] = ramp
    env[-n_fade:] = ramp[::-1]
    return env


def write(stim_id, samples, describe):
    """Level-match, check for clipping, and write one stimulus."""
    stimulus = pf.Signal(samples, sampling_rate)
    stimulus = pf.dsp.normalize(stimulus) * target_amplitude
    peak = float(np.max(np.abs(stimulus.time)))
    assert peak < 1, (
        f"{stim_id} clips (peak={peak:.3f}); lower target_amplitude")
    pf.io.write_audio(stimulus, f"{stim_id}.wav")
    print(f"wrote {stim_id}.wav  ({describe}, peak={peak:.3f})")


# ------------------- 1. staircase tones (2-AFC, pitch) ---------------------- #
# Reference frequency of the standard interval, in Hz.
standard_frequency = 1000.0

# Frequency offset of each target from the standard, in Hz, ordered from
# hardest (smallest) to easiest (largest). These offsets double as the
# stimulus ids in staircase_demo.yml, so Staircase.threshold() reports the
# threshold directly in Hz. The largest offset (+100 Hz = 1100 Hz) is where
# the staircase starts (start_index: -1 = easiest level).
target_offsets = [2, 4, 8, 15, 25, 40, 60, 100]

tone_duration = 2.0       # seconds per interval (kept short for demo pacing)
t = np.arange(int(sampling_rate * tone_duration)) / sampling_rate
tone_env = envelope(t.size)

write("tone_standard", np.sin(2 * np.pi * standard_frequency * t) * tone_env,
      f"{standard_frequency:.0f} Hz standard")
for offset in target_offsets:
    frequency = standard_frequency + offset
    write(f"tone_plus_{offset}hz",
          np.sin(2 * np.pi * frequency * t) * tone_env,
          f"{frequency:.0f} Hz target, +{offset} Hz")

# ----------------------- 2. ABX pairs (clearly different) ------------------- #
abx_duration = 1.5
t = np.arange(int(sampling_rate * abx_duration)) / sampling_rate
abx_env = envelope(t.size)

# Pair 1: major vs. minor triad on C5 - same root and fifth, only the third
# differs, but the "happy vs. sad" character is unmistakable.
c5, e5, e_flat5, g5 = 523.25, 659.25, 622.25, 783.99
major = sum(np.sin(2 * np.pi * f * t) for f in (c5, e5, g5))
minor = sum(np.sin(2 * np.pi * f * t) for f in (c5, e_flat5, g5))
write("major_chord", major * abx_env, "C major triad")
write("minor_chord", minor * abx_env, "C minor triad")

# Pair 2: steady 440 Hz tone vs. the same tone with strong 6 Hz vibrato.
vibrato_rate, vibrato_depth = 6.0, 20.0   # Hz
steady_phase = 2 * np.pi * 440.0 * t
vibrato_phase = steady_phase + (vibrato_depth / vibrato_rate) * (
    1 - np.cos(2 * np.pi * vibrato_rate * t))
write("steady_tone", np.sin(steady_phase) * abx_env, "steady 440 Hz")
write("vibrato_tone", np.sin(vibrato_phase) * abx_env,
      "440 Hz with 6 Hz vibrato")

# --------------------- 3. funny clips (scale testing) ----------------------- #
# Cartoon "boing": a spring - fast exponential pitch drop with a wobble that
# slows down as it decays.
boing_duration = 2.0
t = np.arange(int(sampling_rate * boing_duration)) / sampling_rate
base = 300.0 + 900.0 * np.exp(-t * 4.0)            # 1200 Hz -> 300 Hz
wobble = 80.0 * np.exp(-t * 2.0) * np.sin(2 * np.pi * 18.0 * np.exp(-t) * t)
phase = 2 * np.pi * np.cumsum(base + wobble) / sampling_rate
boing = np.sin(phase) * np.exp(-t * 2.5)
write("boing", boing * envelope(t.size), "cartoon spring")

# Sad trombone: the classic "wah wah wah waaah" - four descending notes
# (Bb4, A4, Ab4, G4), the last one long with vibrato. A few harmonics give it
# a brassy feel.
notes = [(466.16, 0.45), (440.00, 0.45), (415.30, 0.45), (392.00, 1.2)]
parts = []
for i, (frequency, duration) in enumerate(notes):
    tn = np.arange(int(sampling_rate * duration)) / sampling_rate
    freq = np.full_like(tn, frequency)
    if i == len(notes) - 1:                          # vibrato on the last note
        freq = freq + 8.0 * np.sin(2 * np.pi * 5.0 * tn)
    phase = 2 * np.pi * np.cumsum(freq) / sampling_rate
    note = sum(10 ** (-6.0 * (k - 1) / 20) * np.sin(k * phase)
               for k in range(1, 6))
    parts.append(note * envelope(tn.size, int(sampling_rate * 0.03)))
write("sad_trombone", np.concatenate(parts), "wah wah wah waaah")

# Alien chatter: a burst of random short bleeps (seeded, so re-running the
# script reproduces the same file).
rng = np.random.default_rng(2001)
parts = []
for _ in range(14):
    duration = rng.uniform(0.05, 0.16)
    tn = np.arange(int(sampling_rate * duration)) / sampling_rate
    frequency = rng.uniform(500.0, 2500.0)
    sweep = frequency * (1 + rng.uniform(-0.4, 0.4) * tn / duration)
    phase = 2 * np.pi * np.cumsum(sweep) / sampling_rate
    parts.append(np.sin(phase) * envelope(tn.size, int(sampling_rate * 0.01)))
    parts.append(np.zeros(int(sampling_rate * rng.uniform(0.02, 0.08))))
write("alien_chatter", np.concatenate(parts), "random bleeps")
