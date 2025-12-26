#!/usr/bin/env python3
"""
AeroTone Phase 0 Demo - Simple Proof of Sound

This is the minimal "can we hear it?" demo.
Plays a single propeller tone and lets you hear the characteristic sound.

Usage:
    python demo_simple.py [note]

    note: Optional note name (A2, C3, etc.) Default: A2 (110 Hz)
"""

import sys
import time
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)

# Add project to path
sys.path.insert(0, '.')

from aerotone.voice import PropellerVoice
from aerotone.propeller import NOTES


def main():
    # Parse arguments
    note = 'A2'
    if len(sys.argv) > 1:
        note = sys.argv[1].upper()
        if note not in NOTES:
            print(f"Unknown note: {note}")
            print(f"Available: {', '.join(NOTES.keys())}")
            return

    freq = NOTES[note]
    print(f"\n=== AeroTone Phase 0 Demo ===")
    print(f"Note: {note}")
    print(f"Target frequency: {freq:.2f} Hz")
    print(f"Target RPM: {freq * 60 / 12:.0f} (12-blade propeller)")
    print()

    # Create voice
    sample_rate = 44100
    voice = PropellerVoice(sample_rate=sample_rate)
    voice.set_target_note(note)

    # Pre-run physics to get motor spinning (2 seconds warmup)
    print("Starting motor...")
    for _ in range(2000):
        voice.update_physics(0.001)

    print(f"Current RPM: {voice.current_rpm:.0f}")
    print(f"Current frequency: {voice.current_frequency:.2f} Hz")
    print(f"Locked: {voice.is_locked}")
    print()

    # Generate audio in chunks (safer than real-time callback)
    duration = 4.0
    chunk_duration = 0.5  # Generate 0.5s chunks

    print(f"Playing {duration}s of propeller sound...")
    print("Listen for:")
    print("  - Clear pitched tone (the BPF)")
    print("  - Harmonics giving it 'body'")
    print("  - Subtle broadband 'air' noise")
    print()

    try:
        # Pre-generate all audio (avoids callback timing issues)
        print("Generating audio...")
        total_samples = int(duration * sample_rate)
        chunk_samples = int(chunk_duration * sample_rate)

        audio_chunks = []
        for i in range(0, total_samples, chunk_samples):
            chunk = voice.generate_audio(min(chunk_samples, total_samples - i))
            audio_chunks.append(chunk)

            # Show progress
            state = voice.get_state()
            rpm = state['current_rpm']
            freq_now = state['current_frequency']
            locked = "LOCKED" if state['is_locked'] else "hunting"
            progress = (i + chunk_samples) / total_samples * 100
            print(f"\r  {progress:5.1f}% | RPM: {rpm:7.1f} | "
                  f"Freq: {freq_now:6.2f} Hz | {locked}   ",
                  end='', flush=True)

        # Concatenate all chunks
        audio = np.concatenate(audio_chunks)
        print(f"\n\nPlaying {len(audio)/sample_rate:.1f}s of audio...")

        # Play using blocking call (much more stable)
        sd.play(audio, sample_rate)
        sd.wait()

    except KeyboardInterrupt:
        sd.stop()
        print("\n\nStopped by user")

    print("\nDone!")
    print("\nDid you hear a propeller-like musical tone?")
    print("If yes, Phase 0 is complete!")


if __name__ == '__main__':
    main()
