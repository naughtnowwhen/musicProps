#!/usr/bin/env python3
"""
AeroTone Acoustics Comparison Demo

Compares the original simple acoustic model with the advanced v2 model.

V1 (Original):
  - Simple additive synthesis (sine harmonics)
  - Basic filtered noise
  - No chamber modeling

V2 (Advanced):
  - Realistic blade passage waveform (asymmetric pulse)
  - Doppler modulation from blade tips
  - Acoustic chamber resonance
  - Correlated turbulence noise

Listen for the difference in character and realism!

Caching: Audio is cached after first run. Use --no-cache to regenerate.
"""

import sys
import os
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed")
    sys.exit(1)

sys.path.insert(0, '.')

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'acoustics_compare.npz')

from aerotone.acoustics import PropellerSynth, AcousticParams
from aerotone.acoustics_v2 import AdvancedPropellerSynth, AdvancedAcousticParams


def generate_sweep(synth, start_freq, end_freq, duration, sample_rate):
    """Generate a frequency sweep."""
    num_samples = int(duration * sample_rate)
    chunk_size = int(sample_rate * 0.01)  # 10ms chunks

    audio = []

    for i in range(0, num_samples, chunk_size):
        t = i / num_samples
        # Logarithmic sweep
        freq = start_freq * ((end_freq / start_freq) ** t)

        synth.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)

        n = min(chunk_size, num_samples - i)
        audio.append(synth.generate(n))

    return np.concatenate(audio)


def generate_note_sequence(synth, notes, note_duration, sample_rate):
    """Generate a sequence of notes."""
    from aerotone.propeller import NOTES

    audio = []
    chunk_size = int(sample_rate * 0.01)

    for note in notes:
        freq = NOTES.get(note, 110)
        synth.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)

        # Pre-settle
        synth.bpf_smooth = freq
        synth.amp_smooth = 0.75

        num_samples = int(note_duration * sample_rate)
        for i in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - i)
            audio.append(synth.generate(n))

    return np.concatenate(audio)


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE ACOUSTICS COMPARISON")
    print("  Original (v1) vs Advanced (v2)")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print("""
Comparing two acoustic synthesis approaches:

V1 (Original):
  - Sine wave harmonics with rolloff
  - Simple filtered white noise
  - Basic amplitude/frequency modulation

V2 (Advanced):
  - Realistic blade passage pulse shape
  - Doppler shift from rotating blade tips
  - Acoustic chamber resonance modeling
  - Correlated turbulence (tip vortex, trailing edge)
""")

    sample_rate = 44100

    # === Normalize helper ===
    def normalize(audio, target=0.8):
        peak = np.max(np.abs(audio))
        return audio / peak * target if peak > 0 else audio

    # Check cache first
    audio_v1_note = None
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            data = np.load(CACHE_FILE)
            audio_v1_note = data['v1_note']
            audio_v2_note = data['v2_note']
            audio_v1_scale = data['v1_scale']
            audio_v2_scale = data['v2_scale']
            print("[Loaded from cache]")
        except:
            audio_v1_note = None

    if audio_v1_note is None:
        # Create both synths
        synth_v1 = PropellerSynth(sample_rate)
        synth_v2 = AdvancedPropellerSynth(sample_rate)

        # === Test 1: Sustained Note ===
        print("Generating sustained note comparison (A3 = 220 Hz)...")

        freq = 220  # A3
        duration = 3.0
        num_samples = int(duration * sample_rate)
        chunk_size = int(sample_rate * 0.01)

        # V1
        synth_v1.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)
        synth_v1.bpf_smooth = freq
        synth_v1.amp_smooth = 0.8

        audio_v1_note = []
        for i in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - i)
            audio_v1_note.append(synth_v1.generate(n))
        audio_v1_note = np.concatenate(audio_v1_note)

        # V2
        synth_v2.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)
        synth_v2.bpf_smooth = freq
        synth_v2.amp_smooth = 0.75

        audio_v2_note = []
        for i in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - i)
            audio_v2_note.append(synth_v2.generate(n))
        audio_v2_note = np.concatenate(audio_v2_note)

        # === Test 2: Scale ===
        print("Generating scale comparison...")

        notes = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
        note_duration = 0.6

        synth_v1.reset()
        synth_v2.reset()

        audio_v1_scale = generate_note_sequence(synth_v1, notes, note_duration, sample_rate)
        audio_v2_scale = generate_note_sequence(synth_v2, notes, note_duration, sample_rate)

        # Normalize before caching
        audio_v1_note = normalize(audio_v1_note)
        audio_v2_note = normalize(audio_v2_note)
        audio_v1_scale = normalize(audio_v1_scale)
        audio_v2_scale = normalize(audio_v2_scale)

        # Save to cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.savez(CACHE_FILE,
                 v1_note=audio_v1_note,
                 v2_note=audio_v2_note,
                 v1_scale=audio_v1_scale,
                 v2_scale=audio_v2_scale)
        print("[Saved to cache]")

    # === Playback ===
    print("\n" + "=" * 70)
    print("PLAYBACK")
    print("=" * 70)

    print("\n1. SUSTAINED NOTE - V1 (Original, simple harmonics)")
    print("   Listen for: Pure, synth-like tone")
    sd.play(audio_v1_note, sample_rate)
    sd.wait()

    print("\n2. SUSTAINED NOTE - V2 (Advanced, realistic waveform)")
    print("   Listen for: Blade character, chamber resonance, subtle swirl")
    sd.play(audio_v2_note, sample_rate)
    sd.wait()

    print("\n3. SCALE - V1 (Original)")
    sd.play(audio_v1_scale, sample_rate)
    sd.wait()

    print("\n4. SCALE - V2 (Advanced)")
    sd.play(audio_v2_scale, sample_rate)
    sd.wait()

    # === Side by Side ===
    print("\n5. SIDE-BY-SIDE (V1 left, V2 right) - Sustained note")
    stereo = np.column_stack([audio_v1_note, audio_v2_note])
    sd.play(stereo, sample_rate)
    sd.wait()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
V2 improvements you may have noticed:

1. WAVEFORM: Less "synthy", more mechanical/air-displacement character
2. DOPPLER: Subtle pitch swirling from blade tips approaching/receding
3. CHAMBER: Slight resonance/coloration from acoustic enclosure
4. TURBULENCE: More realistic noise correlated with blade passage

The V2 model captures more of the physics of a real spinning propeller
in an acoustic chamber, making it sound more like an electromechanical
instrument and less like a basic synthesizer.
""")


if __name__ == '__main__':
    main()
