#!/usr/bin/env python3
"""
AeroTone Major Scale Demo

Plays a major scale up and down using propeller tones.
Now with REALISTIC transitions - you hear the motor speed changing!
"""

import sys
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.voice import PropellerVoice
from aerotone.propeller import NOTES

# A major scale (fits perfectly in our A2-G#3 range!)
A_MAJOR_SCALE = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3']


def generate_continuous_audio(voice, duration, sample_rate):
    """
    Generate audio with continuous physics simulation.

    This properly couples the motor dynamics to the audio output,
    so you hear the actual motor speed changes as pitch glides.
    """
    # Generate in small chunks to keep physics coupled
    chunk_ms = 10  # 10ms chunks = 100 physics updates per second of audio
    chunk_samples = int(sample_rate * chunk_ms / 1000)
    total_samples = int(duration * sample_rate)

    audio = np.zeros(total_samples)

    for i in range(0, total_samples, chunk_samples):
        end = min(i + chunk_samples, total_samples)
        n_samples = end - i
        audio[i:end] = voice.generate_audio(n_samples)

    return audio


def main():
    print("\n=== AeroTone Major Scale Demo ===")
    print("Playing A major scale with REALISTIC motor transitions")
    print("(Listen for the pitch glide as the motor changes speed!)\n")

    sample_rate = 44100
    note_duration = 0.8   # seconds to hold each note

    # Build the scale: up then down
    scale = A_MAJOR_SCALE + list(reversed(A_MAJOR_SCALE[:-1]))

    print("Scale:", ' -> '.join(scale))
    print()

    # Create voice
    voice = PropellerVoice(sample_rate=sample_rate)

    # Start motor at first note
    first_note = scale[0]
    voice.set_target_note(first_note)

    # Pre-spin to first note (let PLL lock)
    print(f"Spinning up to {first_note}...")
    for _ in range(2000):  # 2 seconds warmup
        voice.update_physics(0.001)
    print(f"  Locked at {voice.current_frequency:.2f} Hz\n")

    # Generate all audio continuously
    all_audio = []

    for i, note in enumerate(scale):
        freq = NOTES[note]

        # Set new target - motor will slew to it
        voice.set_target_note(note)

        print(f"  {note:4s} -> target {freq:6.2f} Hz", end='', flush=True)

        # Generate audio for this note duration
        # The motor physics runs continuously, so you hear the transition!
        audio = generate_continuous_audio(voice, note_duration, sample_rate)
        all_audio.append(audio)

        # Show where we ended up
        print(f" ... settled at {voice.current_frequency:.2f} Hz")

    # Concatenate
    full_audio = np.concatenate(all_audio)

    # Normalize
    peak = np.max(np.abs(full_audio))
    if peak > 0:
        full_audio = full_audio / peak * 0.8

    print(f"\nPlaying {len(full_audio)/sample_rate:.1f}s of audio...")
    print("Listen for the pitch GLIDING between notes (motor spin-up/down)!")

    sd.play(full_audio, sample_rate)
    sd.wait()

    print("\nDone!")


if __name__ == '__main__':
    main()
