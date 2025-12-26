#!/usr/bin/env python3
"""
AeroTone Weather Effects Demo

Demonstrates how atmospheric pressure variations affect propeller aerodynamics
and how the control loop compensates for these disturbances.

Physics:
  - Air density ρ varies with pressure (ideal gas law)
  - Propeller drag ∝ ρ × n² × D⁵
  - Higher pressure = more drag = harder to spin = PLL pushes harder
  - Lower pressure = less drag = easier to spin = PLL backs off

The Perlin noise creates smooth, natural "weather fronts" that drift
through the simulation, causing the control loop to continuously adapt.

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
from aerotone.weather import Weather, WeatherParams, TurbulentWeather, CalmWeather

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')


def get_cache_path(name: str, params: dict) -> str:
    """Generate cache file path based on name and parameters"""
    param_str = str(sorted(params.items()))
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{name}_{param_hash}.npz")


def load_cached(cache_path: str):
    """Load cached audio and stats if available"""
    if os.path.exists(cache_path):
        try:
            data = np.load(cache_path, allow_pickle=True)
            return data['audio'], data['stats'].item()
        except:
            pass
    return None, None


def save_cache(cache_path: str, audio: np.ndarray, stats: dict):
    """Save audio and stats to cache"""
    np.savez(cache_path, audio=audio, stats=stats)


def run_weather_test(voice, weather, label, note, duration=8.0):
    """Run a weather test holding a single note"""
    sample_rate = 44100
    freq = NOTES[note]

    # Attach weather to voice
    voice.set_weather(weather)

    # Start at target frequency
    voice.set_target_frequency(freq)
    for _ in range(3000):  # 3s warmup
        voice.update_physics(0.001)

    print(f"\n{label}")
    print(f"Holding {note} ({freq:.0f} Hz) for {duration:.0f}s")
    print("-" * 60)

    # Collect data
    times = []
    freqs = []
    errors = []
    densities = []

    audio_chunks = []
    samples_per_step = int(sample_rate * 0.1)  # 100ms chunks

    max_error = 0.0
    max_density_var = 0.0

    for i in range(int(duration / 0.1)):
        t = i * 0.1
        times.append(t)

        # Generate audio (also updates physics + weather)
        chunk = voice.generate_audio(samples_per_step)
        audio_chunks.append(chunk)

        state = voice.get_circuit_state()
        freqs.append(state['prop_frequency'])
        errors.append(state['frequency_error_hz'])

        density_factor = state.get('weather_density_factor', 1.0)
        densities.append(density_factor)
        density_var = abs(density_factor - 1.0) * 100

        if abs(state['frequency_error_hz']) > abs(max_error):
            max_error = state['frequency_error_hz']
        if density_var > max_density_var:
            max_density_var = density_var

        # Print periodic updates
        if i % 10 == 0:
            gust = "GUST!" if state.get('weather_gust_active', False) else ""
            print(f"  {t:5.1f}s: {state['prop_frequency']:6.1f} Hz  "
                  f"err={state['frequency_error_hz']:+5.2f} Hz  "
                  f"ρ={density_factor:.3f}x  {gust}")

    # Calculate stats
    rms_error = np.sqrt(np.mean(np.array(errors) ** 2))

    print(f"\n  Max error: {max_error:+.2f} Hz")
    print(f"  RMS error: {rms_error:.3f} Hz")
    print(f"  Max density variation: {max_density_var:.1f}%")

    audio = np.concatenate(audio_chunks)
    stats = {
        'max_error': max_error,
        'rms_error': rms_error,
        'max_density_var': max_density_var,
    }
    return audio, stats


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 70)
    print("  AEROTONE WEATHER EFFECTS DEMO")
    print("=" * 70)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print("""
Testing control loop robustness against atmospheric disturbances.

Weather affects propeller aerodynamics via air density:
  - High pressure → more drag → motor works harder → slower spin
  - Low pressure → less drag → motor runs easier → faster spin

The PLL must continuously compensate to maintain pitch accuracy.
Listen for slight pitch variations as the control loop tracks weather.
""")

    sample_rate = 44100
    note = 'D3'  # 146.83 Hz - middle of our range
    duration = 8.0

    test_params = {
        'note': note,
        'duration': duration,
        'sample_rate': sample_rate,
    }

    results = {}

    # === Test 1: No Weather (baseline) ===
    cache_key = get_cache_path('weather_none', {**test_params, 'weather': 'none'})
    audio_none, stats_none = None, None

    if use_cache:
        audio_none, stats_none = load_cached(cache_key)

    if audio_none is not None:
        print("=== NO WEATHER (Baseline) === [CACHED]")
        print(f"  RMS error: {stats_none['rms_error']:.3f} Hz")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        audio_none, stats_none = run_weather_test(
            voice, None, "=== NO WEATHER (Baseline) ===", note, duration
        )
        save_cache(cache_key, audio_none, stats_none)
        print("  [Saved to cache]")

    results['none'] = stats_none

    # === Test 2: Calm Weather ===
    cache_key = get_cache_path('weather_calm', {**test_params, 'weather': 'calm'})
    audio_calm, stats_calm = None, None

    if use_cache:
        audio_calm, stats_calm = load_cached(cache_key)

    if audio_calm is not None:
        print("\n=== CALM WEATHER (±5% density) === [CACHED]")
        print(f"  Max density var: {stats_calm['max_density_var']:.1f}%")
        print(f"  RMS error: {stats_calm['rms_error']:.3f} Hz")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        weather = CalmWeather(seed=42)
        audio_calm, stats_calm = run_weather_test(
            voice, weather, "=== CALM WEATHER (±5% density) ===", note, duration
        )
        save_cache(cache_key, audio_calm, stats_calm)
        print("  [Saved to cache]")

    results['calm'] = stats_calm

    # === Test 3: Normal Weather ===
    cache_key = get_cache_path('weather_normal', {**test_params, 'weather': 'normal'})
    audio_normal, stats_normal = None, None

    if use_cache:
        audio_normal, stats_normal = load_cached(cache_key)

    if audio_normal is not None:
        print("\n=== NORMAL WEATHER (±15% density) === [CACHED]")
        print(f"  Max density var: {stats_normal['max_density_var']:.1f}%")
        print(f"  RMS error: {stats_normal['rms_error']:.3f} Hz")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        weather = Weather(seed=42)  # Default params: ±15% variation
        audio_normal, stats_normal = run_weather_test(
            voice, weather, "=== NORMAL WEATHER (±15% density) ===", note, duration
        )
        save_cache(cache_key, audio_normal, stats_normal)
        print("  [Saved to cache]")

    results['normal'] = stats_normal

    # === Test 4: Turbulent Weather ===
    cache_key = get_cache_path('weather_turbulent', {**test_params, 'weather': 'turbulent'})
    audio_turb, stats_turb = None, None

    if use_cache:
        audio_turb, stats_turb = load_cached(cache_key)

    if audio_turb is not None:
        print("\n=== TURBULENT WEATHER (±25% density + gusts) === [CACHED]")
        print(f"  Max density var: {stats_turb['max_density_var']:.1f}%")
        print(f"  RMS error: {stats_turb['rms_error']:.3f} Hz")
    else:
        voice = SpiceVoice(sample_rate=sample_rate)
        weather = TurbulentWeather(seed=42)
        audio_turb, stats_turb = run_weather_test(
            voice, weather, "=== TURBULENT WEATHER (±25% density + gusts) ===",
            note, duration
        )
        save_cache(cache_key, audio_turb, stats_turb)
        print("  [Saved to cache]")

    results['turbulent'] = stats_turb

    # === Summary ===
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"""
                        None      Calm      Normal    Turbulent
                        ────      ────      ──────    ─────────
  Density variation:    0.0%      ±5%       ±15%      ±25%+gusts
  RMS error (Hz):       {results['none']['rms_error']:.3f}     {results['calm']['rms_error']:.3f}     {results['normal']['rms_error']:.3f}     {results['turbulent']['rms_error']:.3f}
  Max error (Hz):       {results['none']['max_error']:+.2f}    {results['calm']['max_error']:+.2f}    {results['normal']['max_error']:+.2f}    {results['turbulent']['max_error']:+.2f}
""")

    # === Play Audio ===
    all_audio = [
        ("No weather (baseline)", audio_none),
        ("Calm weather", audio_calm),
        ("Normal weather", audio_normal),
        ("Turbulent weather", audio_turb),
    ]

    for label, audio in all_audio:
        print(f"Playing: {label}...")
        audio_norm = audio / np.max(np.abs(audio)) * 0.8
        sd.play(audio_norm, sample_rate)
        sd.wait()
        print()

    print("Done!")
    print("\nListen for:")
    print("  - Baseline: Steady pitch, minimal variation")
    print("  - Calm: Barely noticeable drift")
    print("  - Normal: Audible pitch tracking as weather changes")
    print("  - Turbulent: Control loop hunting to maintain pitch")
    print("\nRun with --no-cache to regenerate audio.")


if __name__ == '__main__':
    main()
