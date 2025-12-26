#!/usr/bin/env python3
"""
AeroTone Silent Night - PID Comparison Demo

Compares two versions of Silent Night:
  1. PI only (D=0) - Original behavior, may overshoot on transitions
  2. Full PID (D>0) - Anticipatory braking, smoother note approaches

Listen for the difference in how notes are approached - especially
on larger intervals where motor acceleration/deceleration is significant.

Caching: Both versions cached after first run. Use --no-cache to regenerate.
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
CACHE_FILE = os.path.join(CACHE_DIR, 'silent_night_pid_compare.npz')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams


# Note frequencies
MELODY_NOTES = {
    'G2':  98.00,
    'A2':  110.00,
    'B2':  123.47,
    'C3':  130.81,
    'D3':  146.83,
    'E3':  164.81,
    'F3':  174.61,
    'G3':  196.00,
    'A3':  220.00,
}


def generate_melody(voice, melody, sample_rate):
    """Generate audio for a melody."""
    chunk_size = int(sample_rate * 0.01)  # 10ms chunks
    audio = []

    for note, duration in melody:
        num_samples = int(duration * sample_rate)

        if note is None:
            voice.set_target_frequency(0)
            for i in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - i)
                audio.append(voice.generate_audio(n))
        else:
            freq = MELODY_NOTES.get(note, 110)
            voice.set_target_frequency(freq)

            for i in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - i)
                audio.append(voice.generate_audio(n))

    return np.concatenate(audio)


def get_silent_night_melody():
    """Return Silent Night melody with timing."""
    # Tempo: ~60 BPM
    quarter = 0.8
    half = 1.6
    dotted_half = 2.4
    eighth = 0.4

    # First phrase only (shorter for comparison)
    melody = [
        # "Silent night"
        ('G3', quarter + eighth),
        ('A3', eighth),
        ('G3', half),
        ('E3', dotted_half),

        # "Holy night"
        ('G3', quarter + eighth),
        ('A3', eighth),
        ('G3', half),
        ('E3', dotted_half),

        (None, 0.3),

        # "All is calm"
        ('D3', half),
        ('D3', quarter),
        ('B2', dotted_half),

        # "All is bright"
        ('C3', half),
        ('C3', quarter),
        ('G2', dotted_half),

        (None, 0.3),

        # "Round yon Virgin"
        ('A2', quarter),
        ('A2', quarter + eighth),
        ('C3', eighth),
        ('B2', quarter),
        ('A2', quarter),

        # "Mother and Child"
        ('G3', quarter + eighth),
        ('A3', eighth),
        ('G3', quarter),
        ('E3', half),

        (None, 0.5),

        # Final "Sleep in heavenly peace"
        ('D3', half),
        ('D3', half),
        ('F3', quarter),
        ('D3', quarter),
        ('B2', half),

        ('C3', half),
        ('E3', half),
        ('C3', dotted_half * 1.5),

        (None, 1.0),
    ]
    return melody


def generate_version(use_derivative, sample_rate):
    """Generate Silent Night with or without D term."""

    voice = SpiceVoice(sample_rate=sample_rate)

    if use_derivative:
        # Enable D term for anticipatory braking
        voice.enable_derivative(enabled=True, gain=0.025)
        print("  D term: ENABLED (gain=0.025) - smoother approaches")
    else:
        # Disable D term (default)
        voice.enable_derivative(enabled=False)
        print("  D term: DISABLED - may overshoot on transitions")

    melody = get_silent_night_melody()

    # Pre-spin to first note
    first_freq = MELODY_NOTES[melody[0][0]]
    voice.set_target_frequency(first_freq)

    warmup_samples = int(1.0 * sample_rate)
    chunk_size = int(sample_rate * 0.01)
    warmup_audio = []
    for i in range(0, warmup_samples, chunk_size):
        n = min(chunk_size, warmup_samples - i)
        warmup_audio.append(voice.generate_audio(n))
    warmup_audio = np.concatenate(warmup_audio)

    # Generate melody
    melody_audio = generate_melody(voice, melody, sample_rate)

    # Fade in warmup
    fade_in = np.linspace(0, 1, len(warmup_audio))
    warmup_audio = warmup_audio * fade_in

    # Fade out end
    fade_out_samples = int(1.5 * sample_rate)
    if len(melody_audio) > fade_out_samples:
        fade_out = np.linspace(1, 0, fade_out_samples)
        melody_audio[-fade_out_samples:] *= fade_out

    full_audio = np.concatenate([warmup_audio, melody_audio])

    # Normalize
    peak = np.max(np.abs(full_audio))
    if peak > 0:
        full_audio = full_audio / peak * 0.8

    return full_audio


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE - SILENT NIGHT PID COMPARISON")
    print("  Comparing PI-only vs Full PID control")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    sample_rate = 44100

    # Check cache
    audio_pi = None
    audio_pid = None

    if use_cache and os.path.exists(CACHE_FILE):
        try:
            data = np.load(CACHE_FILE)
            audio_pi = data['pi_only']
            audio_pid = data['full_pid']
            print("\n[Loaded from cache]")
        except:
            pass

    if audio_pi is None:
        print("\n" + "-" * 70)
        print("Generating PI-only version (no derivative term)...")
        print("-" * 70)
        audio_pi = generate_version(use_derivative=False, sample_rate=sample_rate)

        print("\n" + "-" * 70)
        print("Generating Full PID version (with derivative term)...")
        print("-" * 70)
        audio_pid = generate_version(use_derivative=True, sample_rate=sample_rate)

        # Save cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.savez(CACHE_FILE, pi_only=audio_pi, full_pid=audio_pid)
        print("\n[Saved to cache]")

    duration = len(audio_pi) / sample_rate

    # Playback
    print("\n" + "=" * 70)
    print("PLAYBACK COMPARISON")
    print("=" * 70)

    print(f"""
Listen for differences in note transitions:

PI ONLY (D=0):
  - Motor accelerates toward target note
  - No braking until overshoot occurs
  - May hear slight pitch wobble on arrival
  - More "mechanical" character

FULL PID (D>0):
  - Motor accelerates, then brakes on approach
  - Smoother landing on target pitch
  - Less overshoot/oscillation
  - More "musical" transitions
""")

    print("-" * 70)
    print(f"1. PI ONLY - Duration: {duration:.1f}s")
    print("-" * 70)
    sd.play(audio_pi, sample_rate)
    sd.wait()

    print("\n" + "-" * 70)
    print(f"2. FULL PID - Duration: {duration:.1f}s")
    print("-" * 70)
    sd.play(audio_pid, sample_rate)
    sd.wait()

    # Side by side
    print("\n" + "-" * 70)
    print("3. SIDE BY SIDE (PI left, PID right)")
    print("-" * 70)

    # Make same length
    min_len = min(len(audio_pi), len(audio_pid))
    stereo = np.column_stack([audio_pi[:min_len], audio_pid[:min_len]])
    sd.play(stereo, sample_rate)
    sd.wait()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
The D (derivative) term provides "anticipatory braking":

  - Senses rapid decrease in frequency error
  - Applies counter-voltage to slow motor before reaching target
  - Results in smoother pitch transitions

Circuit equivalent: Differentiator (capacitor to op-amp input)

For musical use, a small D gain (0.02-0.05) typically sounds better.
For authentic 1979 behavior, D=0 is more historically accurate.
""")


if __name__ == '__main__':
    main()
