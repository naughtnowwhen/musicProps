#!/usr/bin/env python3
"""
AeroTone Duck Scale Demo

Major scale with aggressive iris ducking to create clear tonal centers.
Each note (1-8) should be distinctly heard with volume dips during transitions.

Cached for fast replay.
"""

import sys
import os
import numpy as np
import hashlib

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.propeller import NOTES

# Cache directory
CACHE_DIR = ".audio_cache"


def get_cache_path(name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{name}.npy")


def main():
    print("=" * 70)
    print("  AEROTONE DUCK SCALE - Clear Tonal Centers")
    print("=" * 70)

    sample_rate = 44100
    cache_path = get_cache_path("duck_scale_major")

    # Check cache
    if os.path.exists(cache_path) and '--no-cache' not in sys.argv:
        print("\n[Loading from cache - use --no-cache to regenerate]\n")
        audio = np.load(cache_path)
    else:
        print("\nGenerating major scale with iris ducking...")
        print("Duck depth: 50% volume reduction during transitions\n")

        # Envelope duck for consistent articulation
        # Each note change triggers a timed volume dip
        params = SpiceVoiceParams(
            expression_duck_enabled=True,
            expression_duck_depth=0.45,     # 45% reduction at peak
            expression_duck_threshold=5.0,  # Hz - minimum note change to trigger
            expression_duck_attack=0.06,    # 60ms to peak (during glissando start)
            expression_duck_release=0.14,   # 140ms back to full (as note settles)
        )
        voice = SpiceVoice(params=params, sample_rate=sample_rate)

        # A major scale: 1  2  3  4  5  6  7  8
        notes = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
        note_duration = 0.65  # Each note duration

        chunk_size = int(sample_rate * 0.01)
        audio_chunks = []

        # Pre-spin to first note
        print("Spinning up to A2...")
        voice.set_target_frequency(NOTES['A2'])
        warmup_samples = int(0.8 * sample_rate)
        for i in range(0, warmup_samples, chunk_size):
            n = min(chunk_size, warmup_samples - i)
            audio_chunks.append(voice.generate_audio(n))

        # Play ascending scale
        print("\nAscending: 1 -> 8")
        for i, note in enumerate(notes):
            degree = i + 1
            freq = NOTES[note]
            voice.set_target_frequency(freq)

            num_samples = int(note_duration * sample_rate)

            # Track peak duck during this note
            max_duck = 0.0
            for j in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - j)
                audio_chunks.append(voice.generate_audio(n))

                state = voice.get_circuit_state()
                if state['expression_duck'] > max_duck:
                    max_duck = state['expression_duck']

            # Report peak duck seen during transition
            atten = voice.get_circuit_state()['iris_attenuation_db']
            print(f"  {degree}. {note:4s} ({freq:5.1f} Hz) - peak duck: {max_duck*100:4.1f}%")

        # Brief hold at top
        print("\n  (hold at 8...)")
        hold_samples = int(0.4 * sample_rate)
        for i in range(0, hold_samples, chunk_size):
            n = min(chunk_size, hold_samples - i)
            audio_chunks.append(voice.generate_audio(n))

        # Play descending scale
        print("\nDescending: 8 -> 1")
        for i, note in enumerate(reversed(notes)):
            degree = 8 - i
            freq = NOTES[note]
            voice.set_target_frequency(freq)

            num_samples = int(note_duration * sample_rate)

            # Track peak duck during this note
            max_duck = 0.0
            for j in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - j)
                audio_chunks.append(voice.generate_audio(n))

                state = voice.get_circuit_state()
                if state['expression_duck'] > max_duck:
                    max_duck = state['expression_duck']

            print(f"  {degree}. {note:4s} ({freq:5.1f} Hz) - peak duck: {max_duck*100:4.1f}%")

        # Brief final hold
        print("\n  (final hold at 1...)")
        hold_samples = int(0.5 * sample_rate)
        for i in range(0, hold_samples, chunk_size):
            n = min(chunk_size, hold_samples - i)
            audio_chunks.append(voice.generate_audio(n))

        # Fade out
        audio = np.concatenate(audio_chunks)

        fade_samples = int(0.5 * sample_rate)
        fade = np.linspace(1, 0, fade_samples)
        audio[-fade_samples:] *= fade

        # Normalize
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.8

        # Cache
        np.save(cache_path, audio)
        print(f"\n[Cached to {cache_path}]")

    duration = len(audio) / sample_rate
    print(f"\nTotal duration: {duration:.1f}s")

    # Playback
    print("\n" + "=" * 70)
    print("PLAYBACK - Listen for clear 1-2-3-4-5-6-7-8 tonal centers")
    print("=" * 70)
    print("\nVolume dips during glissando transitions create note boundaries.")
    print("Each scale degree should be distinctly audible.\n")

    sd.play(audio, sample_rate)
    sd.wait()

    print("Done!")


if __name__ == '__main__':
    main()
