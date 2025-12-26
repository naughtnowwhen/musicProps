#!/usr/bin/env python3
"""
AeroTone Beat Frequency Demo

Demonstrates the beat frequency phenomenon that occurs when two
propellers are slightly out of tune - exactly like synchrophaser systems!

This is the core acoustic phenomenon we're simulating:
  - Two props at exact same frequency: smooth tone
  - Two props slightly different: audible "wobble" at f_beat = |f1 - f2|

Usage:
    python demo_beats.py

The demo will:
1. Play two props in perfect unison (no beats)
2. Gradually detune one prop (beats appear)
3. Show how beat frequency matches the detuning amount
"""

import sys
import time
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.voice import PropellerVoice
from aerotone.propeller import NOTES


def main():
    print("\n" + "=" * 60)
    print("  AEROTONE BEAT FREQUENCY DEMONSTRATION")
    print("=" * 60)
    print("""
This demo shows the beat frequency phenomenon:
  - Two propellers at the same frequency = smooth tone
  - Small frequency difference = audible "wobble"
  - Beat frequency = |freq1 - freq2|

This is exactly what happens with out-of-sync aircraft propellers!

""")

    sample_rate = 44100
    block_size = 512

    # Create two voices
    voice1 = PropellerVoice(sample_rate=sample_rate)
    voice2 = PropellerVoice(sample_rate=sample_rate)

    # Base frequency (A2)
    base_freq = NOTES['A2']  # 110 Hz
    voice1.set_target_frequency(base_freq)
    voice2.set_target_frequency(base_freq)

    # Pre-spin motors
    print("Starting motors...")
    for _ in range(500):
        voice1.update_physics(0.001)
        voice2.update_physics(0.001)

    print(f"Base frequency: {base_freq:.2f} Hz")
    print()

    # Detuning schedule
    phases = [
        (0.0, 5.0, "Perfect unison - no beats"),
        (0.5, 5.0, "0.5 Hz detune - 0.5 Hz beat (2 sec period)"),
        (1.0, 5.0, "1 Hz detune - 1 Hz beat (1 sec period)"),
        (2.0, 5.0, "2 Hz detune - 2 Hz beat (0.5 sec period)"),
        (5.0, 5.0, "5 Hz detune - 5 Hz beat (fast wobble)"),
        (0.0, 5.0, "Back to unison - beats gone"),
    ]

    # State for detuning
    current_detune = [0.0]

    def audio_callback(outdata, frames, time_info, status):
        if status:
            print(status)

        audio1 = voice1.generate_audio(frames)
        audio2 = voice2.generate_audio(frames)

        # Mix 50/50
        mixed = (audio1 + audio2) / np.sqrt(2)
        outdata[:, 0] = np.clip(mixed, -1.0, 1.0)

    # Start audio
    stream = sd.OutputStream(
        samplerate=sample_rate,
        channels=1,
        blocksize=block_size,
        callback=audio_callback
    )
    stream.start()

    try:
        for detune, duration, description in phases:
            print(f"\n>> {description}")
            print(f"   Freq 1: {base_freq:.2f} Hz")
            print(f"   Freq 2: {base_freq + detune:.2f} Hz")
            if detune > 0:
                print(f"   Expected beat: {detune:.1f} Hz "
                      f"({1/detune:.2f} sec period)")
            print()

            # Smoothly transition to new detuning
            target_detune = detune
            transition_time = 0.5  # seconds
            start_detune = current_detune[0]
            start_time = time.time()

            while time.time() - start_time < duration:
                # Smooth transition
                elapsed = time.time() - start_time
                if elapsed < transition_time:
                    alpha = elapsed / transition_time
                    new_detune = start_detune + alpha * (target_detune - start_detune)
                    voice2.set_target_frequency(base_freq + new_detune)
                    current_detune[0] = new_detune
                elif elapsed < transition_time + 0.1:
                    voice2.set_target_frequency(base_freq + target_detune)
                    current_detune[0] = target_detune

                # Print status
                f1 = voice1.current_frequency
                f2 = voice2.current_frequency
                actual_beat = abs(f1 - f2)
                print(f"\r   Actual: f1={f1:.2f} Hz, f2={f2:.2f} Hz, "
                      f"beat={actual_beat:.2f} Hz   ",
                      end='', flush=True)

                time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        stream.stop()
        stream.close()

    print("\n\n" + "=" * 60)
    print("Demo complete!")
    print()
    print("Key insight:")
    print("  The beat frequency equals exactly the frequency difference.")
    print("  This is why synchrophasers work - they eliminate beats by")
    print("  synchronizing propeller frequencies and phases.")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()
