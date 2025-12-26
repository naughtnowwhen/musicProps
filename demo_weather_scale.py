#!/usr/bin/env python3
"""
AeroTone Weather Scale Demo

Full major scale run with glissandos between notes, demonstrating
how the weather system affects pitch stability during transitions.

Scale pattern:
  Ascending:  1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 (hold)
  Rest
  Descending: 8 - 7 - 6 - 5 - 4 - 3 - 2 - 1 (hold)

Each transition is a smooth glissando, not an instant jump.
The weather creates varying resistance that the control loop must fight.

Caching: Audio is cached after first run. Use --no-cache to regenerate.
"""

import sys
import os
import hashlib
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice
from aerotone.propeller import NOTES
from aerotone.weather import Weather, WeatherParams, TurbulentWeather

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')

# A major scale (A2 to A3) - we'll add A3 for the full octave
SCALE_FREQS = [
    110.00,   # A2  - 1
    123.47,   # B2  - 2
    138.59,   # C#3 - 3
    146.83,   # D3  - 4
    164.81,   # E3  - 5
    185.00,   # F#3 - 6
    207.65,   # G#3 - 7
    220.00,   # A3  - 8 (octave)
]

SCALE_NAMES = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']


def get_cache_path(name: str, params: dict) -> str:
    """Generate cache file path based on name and parameters"""
    param_str = str(sorted(params.items()))
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{name}_{param_hash}.npz")


def load_cached(cache_path: str):
    """Load cached audio if available"""
    if os.path.exists(cache_path):
        try:
            data = np.load(cache_path, allow_pickle=True)
            return data['audio']
        except:
            pass
    return None


def save_cache(cache_path: str, audio: np.ndarray):
    """Save audio to cache"""
    np.savez(cache_path, audio=audio)


def generate_scale_run(voice, weather, label, sample_rate=44100):
    """
    Generate a full scale run with glissandos.

    Pattern: 1-2-3-4-5-6-7-8 (hold) (rest) 8-7-6-5-4-3-2-1 (hold)

    Tempo: ~72 BPM (quarter note = 0.83s)
    Each scale degree gets a full, sustained note.
    """
    print(f"\n{label}")
    print("=" * 60)

    # Timing parameters - musical tempo around 72 BPM
    note_duration = 0.85     # Hold each note - like a quarter note at ~72 BPM
    gliss_duration = 0.12    # Quick slide between notes (not the focus)
    hold_duration = 1.1      # Slightly longer than a regular note (resolution)
    rest_duration = 0.3      # Brief breath before descending

    # Attach weather
    voice.set_weather(weather)

    # Spin up to first note
    voice.set_target_frequency(SCALE_FREQS[0])
    print(f"Spinning up to {SCALE_NAMES[0]}...")
    for _ in range(3000):
        voice.update_physics(0.001)

    audio_chunks = []
    samples_per_ms = sample_rate // 1000

    def generate_segment(duration_s, desc=""):
        """Generate audio for a time segment"""
        samples = int(duration_s * sample_rate)
        chunk_size = samples_per_ms * 5  # 5ms chunks
        audio = []
        for i in range(0, samples, chunk_size):
            n = min(chunk_size, samples - i)
            audio.append(voice.generate_audio(n))
        return np.concatenate(audio)

    def glissando(start_freq, end_freq, duration_s):
        """Generate a smooth glissando between frequencies"""
        samples = int(duration_s * sample_rate)
        chunk_size = samples_per_ms * 5  # 5ms chunks
        audio = []

        for i in range(0, samples, chunk_size):
            # Interpolate frequency (logarithmic for musical pitch)
            t = i / samples
            # Log interpolation for perceptually linear pitch change
            freq = start_freq * ((end_freq / start_freq) ** t)
            voice.set_target_frequency(freq)

            n = min(chunk_size, samples - i)
            audio.append(voice.generate_audio(n))

        return np.concatenate(audio)

    # === ASCENDING: 1 -> 8 ===
    print("\nAscending:")
    for i in range(len(SCALE_FREQS)):
        freq = SCALE_FREQS[i]
        name = SCALE_NAMES[i]

        # Hold on this note
        voice.set_target_frequency(freq)
        state = voice.get_circuit_state()
        weather_info = ""
        if weather:
            weather_info = f" [weather: {state.get('weather_variation_pct', 0):+.1f}%]"
        print(f"  {i+1}. {name:4s} ({freq:6.1f} Hz){weather_info}")

        audio_chunks.append(generate_segment(note_duration))

        # Glissando to next note (except on last)
        if i < len(SCALE_FREQS) - 1:
            next_freq = SCALE_FREQS[i + 1]
            audio_chunks.append(glissando(freq, next_freq, gliss_duration))

    # Hold at top
    print(f"  (holding at {SCALE_NAMES[-1]}...)")
    audio_chunks.append(generate_segment(hold_duration))

    # Rest (silence would be weird, so just hold the note quietly)
    print(f"  (rest)")
    audio_chunks.append(generate_segment(rest_duration))

    # === DESCENDING: 8 -> 1 ===
    print("\nDescending:")
    for i in range(len(SCALE_FREQS) - 1, -1, -1):
        freq = SCALE_FREQS[i]
        name = SCALE_NAMES[i]

        # Hold on this note
        voice.set_target_frequency(freq)
        state = voice.get_circuit_state()
        weather_info = ""
        if weather:
            weather_info = f" [weather: {state.get('weather_variation_pct', 0):+.1f}%]"
        print(f"  {i+1}. {name:4s} ({freq:6.1f} Hz){weather_info}")

        audio_chunks.append(generate_segment(note_duration))

        # Glissando to next note (except on last)
        if i > 0:
            next_freq = SCALE_FREQS[i - 1]
            audio_chunks.append(glissando(freq, next_freq, gliss_duration))

    # Final hold
    print(f"  (final hold at {SCALE_NAMES[0]}...)")
    audio_chunks.append(generate_segment(hold_duration))

    # Concatenate
    audio = np.concatenate(audio_chunks)
    duration = len(audio) / sample_rate
    print(f"\nTotal duration: {duration:.1f}s")

    return audio


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE WEATHER SCALE DEMO")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print("""
A major scale with glissandos, comparing weather effects.

  Tempo: ~72 BPM (relaxed, musical pace)
  Pattern: 1-2-3-4-5-6-7-8 (hold) (rest) 8-7-6-5-4-3-2-1 (hold)

Each note is sustained like a musician practicing scales.
Quick glissando slides connect the notes.
Weather creates resistance variations the control loop must fight.

Listen for:
  - Without weather: Clean, consistent, "perfect" scale
  - With weather: Organic variation, subtle pitch drift on sustained notes
""")

    sample_rate = 44100

    cache_params = {
        'scale': 'A_major',
        'sample_rate': sample_rate,
        'version': 4,  # Bumped: shorter hold at top
    }

    # === Generate without weather ===
    cache_path = get_cache_path('scale_no_weather', cache_params)
    audio_clean = None

    if use_cache:
        audio_clean = load_cached(cache_path)

    if audio_clean is not None:
        print("\n=== NO WEATHER (Clean) === [CACHED]")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        audio_clean = generate_scale_run(
            voice, None,
            "=== NO WEATHER (Clean) ==="
        )
        save_cache(cache_path, audio_clean)
        print("[Saved to cache]")

    # === Generate with weather ===
    cache_path = get_cache_path('scale_weather', cache_params)
    audio_weather = None

    if use_cache:
        audio_weather = load_cached(cache_path)

    if audio_weather is not None:
        print("\n=== WITH WEATHER (±15% density) === [CACHED]")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        weather = Weather(seed=123)  # Different seed for variety
        audio_weather = generate_scale_run(
            voice, weather,
            "=== WITH WEATHER (±15% density) ==="
        )
        save_cache(cache_path, audio_weather)
        print("[Saved to cache]")

    # === Generate with turbulent weather ===
    cache_path = get_cache_path('scale_turbulent', cache_params)
    audio_turb = None

    if use_cache:
        audio_turb = load_cached(cache_path)

    if audio_turb is not None:
        print("\n=== TURBULENT WEATHER (±25% + gusts) === [CACHED]")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        weather = TurbulentWeather(seed=456)
        audio_turb = generate_scale_run(
            voice, weather,
            "=== TURBULENT WEATHER (±25% + gusts) ==="
        )
        save_cache(cache_path, audio_turb)
        print("[Saved to cache]")

    # === Playback ===
    print("\n" + "=" * 70)
    print("PLAYBACK")
    print("=" * 70)

    def normalize(audio):
        peak = np.max(np.abs(audio))
        return audio / peak * 0.8 if peak > 0 else audio

    print("\n1. NO WEATHER (clean, consistent)")
    print("   Listen for: Smooth, predictable glissandos")
    sd.play(normalize(audio_clean), sample_rate)
    sd.wait()

    print("\n2. NORMAL WEATHER (±15% density variation)")
    print("   Listen for: Slight unevenness, organic feel")
    sd.play(normalize(audio_weather), sample_rate)
    sd.wait()

    print("\n3. TURBULENT WEATHER (±25% + gusts)")
    print("   Listen for: Control loop hunting, audible effort")
    sd.play(normalize(audio_turb), sample_rate)
    sd.wait()

    print("\n" + "=" * 70)
    print("Done!")
    print("""
The weather effect adds organic variation to the glissandos:
  - Clean: Mathematically smooth pitch transitions
  - Weather: The motor fights varying drag, creating natural wobble
  - Turbulent: Audible struggle, like playing in a windstorm

This is unique - no other synth simulates atmospheric physics!
""")
    print("Run with --no-cache to regenerate audio.")


if __name__ == '__main__':
    main()
