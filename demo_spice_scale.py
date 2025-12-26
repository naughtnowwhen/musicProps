#!/usr/bin/env python3
"""
AeroTone SPICE-Level Scale Demo

Plays a major scale using the full circuit simulation.
Listen for:
  - Realistic PLL lock acquisition on each note
  - Smooth motor speed transitions (not instant jumps)
  - Slight overshoot/settling as the PLL locks

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

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.propeller import NOTES

# A major scale
A_MAJOR = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3']

# Cache
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'spice_scale.npz')


def generate_continuous(voice, duration, sample_rate):
    """Generate audio with tight physics coupling"""
    chunk_ms = 5  # 5ms chunks for responsive physics
    chunk_samples = int(sample_rate * chunk_ms / 1000)
    total_samples = int(duration * sample_rate)

    audio = np.zeros(total_samples)
    for i in range(0, total_samples, chunk_samples):
        end = min(i + chunk_samples, total_samples)
        audio[i:end] = voice.generate_audio(end - i)

    return audio


def main():
    use_cache = '--no-cache' not in sys.argv

    print("\n" + "=" * 70)
    print("  AEROTONE SPICE-LEVEL SCALE DEMO")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print("""
Playing A major scale with REAL PLL circuit simulation.

The motor speed is controlled by closed-loop PI control.
You'll hear:
  - PLL lock acquisition (slight pitch settling)
  - Continuous motor speed changes (not jumps)
  - Realistic electromechanical behavior
""")

    sample_rate = 44100
    note_duration = 1.0  # seconds per note
    scale = A_MAJOR + list(reversed(A_MAJOR[:-1]))

    print("Scale:", ' -> '.join(scale))
    print()

    # Try loading from cache
    full_audio = None
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            data = np.load(CACHE_FILE)
            full_audio = data['audio']
            print("[Loaded from cache]")
        except:
            pass

    if full_audio is None:
        # Generate fresh
        voice = SpiceVoice(sample_rate=sample_rate)

        # Pre-spin to first note
        first_freq = NOTES[scale[0]]
        voice.set_target_frequency(first_freq)
        print(f"Spinning up to {scale[0]} ({first_freq:.1f} Hz)...")

        for _ in range(3000):  # 3 second warmup
            voice.update_physics(0.001)

        state = voice.get_circuit_state()
        print(f"  Locked at {state['prop_frequency']:.2f} Hz "
              f"(ctrl={state['control_voltage']:.2f}V)")
        print()

        # Generate scale
        all_audio = []
        print("Generating scale...")

        for note in scale:
            freq = NOTES[note]
            voice.set_target_frequency(freq)

            print(f"  {note:4s} ({freq:6.1f} Hz)", end='', flush=True)

            # Generate audio for this note
            audio = generate_continuous(voice, note_duration, sample_rate)
            all_audio.append(audio)

            state = voice.get_circuit_state()
            print(f" -> settled at {state['prop_frequency']:.1f} Hz "
                  f"(err={state['frequency_error_hz']:+.1f} Hz)")

        # Concatenate and normalize
        full_audio = np.concatenate(all_audio)
        peak = np.max(np.abs(full_audio))
        if peak > 0:
            full_audio = full_audio / peak * 0.8

        # Save to cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.savez(CACHE_FILE, audio=full_audio)
        print("\n[Saved to cache]")

    print(f"\nPlaying {len(full_audio)/sample_rate:.1f}s of audio...")
    print("Listen for smooth pitch transitions as the PLL relocks!")

    sd.play(full_audio, sample_rate)
    sd.wait()

    print("\nDone!")
    print("Run with --no-cache to regenerate.")


if __name__ == '__main__':
    main()
