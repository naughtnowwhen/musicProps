#!/usr/bin/env python3
"""
AeroTone Silent Night Demo

A peaceful Christmas melody played on the propeller instrument.
The sustained tones and gentle transitions suit the instrument's character.

Silent Night transposed to fit our A2-A3 range.

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
CACHE_FILE = os.path.join(CACHE_DIR, 'silent_night.npy')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.weather import Weather, WeatherParams


# Extended note frequencies (we need a couple notes below A2)
MELODY_NOTES = {
    # Below our normal range (extend for melody)
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
    """
    Generate audio for a melody.

    melody: list of (note, duration) tuples
            note can be a note name or None for rest
    """
    chunk_size = int(sample_rate * 0.01)  # 10ms chunks
    audio = []

    for note, duration in melody:
        num_samples = int(duration * sample_rate)

        if note is None:
            # Rest - spin down
            voice.set_target_frequency(0)
            for i in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - i)
                audio.append(voice.generate_audio(n))
        else:
            # Play note
            freq = MELODY_NOTES.get(note, 110)
            voice.set_target_frequency(freq)

            for i in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - i)
                audio.append(voice.generate_audio(n))

    return np.concatenate(audio)


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE - SILENT NIGHT")
    print("  A Christmas melody on the propeller instrument")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    sample_rate = 44100

    # Check cache first
    full_audio = None
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            full_audio = np.load(CACHE_FILE)
            print("\n[Loaded from cache]")
        except:
            pass

    # Silent Night melody (first verse)
    # Transposed to fit A2-A3 range
    # Format: (note, duration in seconds)

    # Tempo: ~60 BPM (peaceful, slow)
    quarter = 0.8      # quarter note
    half = 1.6         # half note
    dotted_half = 2.4  # dotted half
    eighth = 0.4       # eighth note

    # "Silent Night, Holy Night"
    # Si - lent night, ho - ly night
    silent_night = [
        # "Si - lent" (G. A G)
        ('G3', quarter + eighth),  # Si-
        ('A3', eighth),            # -lent
        ('G3', half),              # (hold)

        # "night" (E)
        ('E3', dotted_half),       # night

        # "Ho - ly" (G. A G)
        ('G3', quarter + eighth),  # Ho-
        ('A3', eighth),            # -ly
        ('G3', half),              # (hold)

        # "night" (E)
        ('E3', dotted_half),       # night

        # Brief pause between phrases
        (None, 0.3),

        # "All is calm" (D D B)
        ('D3', half),              # All
        ('D3', quarter),           # is
        ('B2', dotted_half),       # calm

        # "All is bright" (C C G)
        ('C3', half),              # All
        ('C3', quarter),           # is
        ('G2', dotted_half),       # bright

        # Brief pause
        (None, 0.3),

        # "Round yon Virgin" (A A C. B A)
        ('A2', quarter),           # Round
        ('A2', quarter + eighth),  # yon
        ('C3', eighth),            # Vir-
        ('B2', quarter),           # -gin
        ('A2', quarter),           # (breath)

        # "Mother and Child" (G. A G E)
        ('G3', quarter + eighth),  # Mo-
        ('A3', eighth),            # -ther
        ('G3', quarter),           # and
        ('E3', half),              # Child

        # "Holy Infant so" (A A C. B A)
        ('A2', quarter),           # Ho-
        ('A2', quarter + eighth),  # -ly
        ('C3', eighth),            # In-
        ('B2', quarter),           # -fant
        ('A2', quarter),           # so

        # "tender and mild" (G. A G E)
        ('G3', quarter + eighth),  # ten-
        ('A3', eighth),            # -der
        ('G3', quarter),           # and
        ('E3', half),              # mild

        # Pause before final phrase
        (None, 0.4),

        # "Sleep in heavenly peace" (D D F. D B)
        ('D3', half),              # Sleep
        ('D3', quarter + eighth),  # in
        ('F3', eighth),            # hea-
        ('D3', quarter),           # -ven-
        ('B2', quarter),           # -ly

        # "peace" (C E C)
        ('C3', half),              # peace
        ('E3', quarter),           # (echo)
        ('C3', dotted_half),       # (hold)

        # Pause
        (None, 0.5),

        # "Sleep in heavenly peace" (repeat, slower)
        ('D3', half),              # Sleep
        ('D3', half),              # in
        ('F3', quarter),           # hea-
        ('D3', quarter),           # -ven-
        ('B2', half),              # -ly

        # Final "peace" (C E C - slower, fading)
        ('C3', half),              # peace
        ('E3', half),              # (rise)
        ('C3', dotted_half * 1.5), # (final hold)

        # Fade out
        (None, 2.0),
    ]

    if full_audio is None:
        # Create voice with gentle weather for organic feel
        weather_params = WeatherParams(
            density_variation=0.05,   # Very subtle - 5%
            time_scale=0.02,          # Slow, gentle variations
        )
        weather = Weather(weather_params)

        voice = SpiceVoice(sample_rate=sample_rate, weather=weather)

        print("\nGenerating 'Silent Night'...")
        print("This may take a moment as we simulate the full physics.\n")

        # Pre-spin to first note for cleaner start
        print("Spinning up propeller...")
        first_note = silent_night[0][0]
        first_freq = MELODY_NOTES[first_note]
        voice.set_target_frequency(first_freq)

        # Warm up for 1.5 seconds
        warmup_samples = int(1.5 * sample_rate)
        chunk_size = int(sample_rate * 0.01)
        warmup_audio = []
        for i in range(0, warmup_samples, chunk_size):
            n = min(chunk_size, warmup_samples - i)
            warmup_audio.append(voice.generate_audio(n))
        warmup_audio = np.concatenate(warmup_audio)

        # Generate melody
        print("Playing melody...")
        melody_audio = generate_melody(voice, silent_night, sample_rate)

        # Combine with fade in on warmup
        fade_in = np.linspace(0, 1, len(warmup_audio))
        warmup_audio = warmup_audio * fade_in

        # Fade out at end
        fade_out_samples = int(2.0 * sample_rate)
        if len(melody_audio) > fade_out_samples:
            fade_out = np.linspace(1, 0, fade_out_samples)
            melody_audio[-fade_out_samples:] *= fade_out

        full_audio = np.concatenate([warmup_audio, melody_audio])

        # Normalize
        peak = np.max(np.abs(full_audio))
        if peak > 0:
            full_audio = full_audio / peak * 0.8

        # Save to cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        np.save(CACHE_FILE, full_audio)
        print("\n[Saved to cache]")

    duration = len(full_audio) / sample_rate
    print(f"\nTotal duration: {duration:.1f} seconds")

    # Playback
    print("\n" + "=" * 70)
    print("  PLAYBACK: Silent Night")
    print("=" * 70)
    print("\nListening notes:")
    print("  - Propeller motor glissandos between notes")
    print("  - Gentle weather variations for organic warmth")
    print("  - Advanced acoustics: blade pulse, Doppler, chamber resonance")
    print()

    sd.play(full_audio, sample_rate)
    sd.wait()

    print("\n" + "=" * 70)
    print("  Merry Christmas!")
    print("=" * 70)


if __name__ == '__main__':
    main()
