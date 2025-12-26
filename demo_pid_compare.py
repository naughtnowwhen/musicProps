#!/usr/bin/env python3
"""
AeroTone PID Comparison Demo

Compare PI (authentic 1979) vs PID (with derivative braking):
  - PI: Overshoots, hunts, then settles (authentic vintage behavior)
  - PID: Smooth approach, minimal overshoot (modern servo behavior)

Both are implemented as circuit equivalents:
  P = Resistor voltage divider
  I = Capacitor charging (10µF through 100kΩ)
  D = Differentiator circuit (cap in series with op-amp input)

Caching: Audio is cached to disk after first run for fast playback.
         Use --no-cache to force regeneration.
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

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')


def get_cache_path(name: str, params: dict) -> str:
    """Generate cache file path based on name and parameters"""
    # Create hash of parameters for cache key
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


def run_test(voice, label, start_freq, end_freq, duration=4.0):
    """Run a frequency jump test and collect data"""
    sample_rate = 44100

    # Start at initial frequency
    voice.set_target_frequency(start_freq)
    for _ in range(3000):  # 3s warmup
        voice.update_physics(0.001)

    print(f"\n{label}")
    print(f"Jump: {start_freq:.0f} Hz → {end_freq:.0f} Hz")
    print("-" * 50)

    # Now jump to new frequency
    voice.set_target_frequency(end_freq)

    # Collect data
    times = []
    freqs = []
    errors = []

    audio_chunks = []
    samples_per_step = int(sample_rate * 0.05)  # 50ms chunks

    for i in range(int(duration / 0.05)):
        t = i * 0.05
        times.append(t)

        # Generate audio (also updates physics)
        chunk = voice.generate_audio(samples_per_step)
        audio_chunks.append(chunk)

        state = voice.get_circuit_state()
        freqs.append(state['prop_frequency'])
        errors.append(state['frequency_error_hz'])

        # Print key moments
        if i < 20 or i % 10 == 0:
            err = state['frequency_error_hz']
            status = "LOCKED" if abs(err) < 0.5 else f"err={err:+.1f}Hz"
            print(f"  {t:.2f}s: {state['prop_frequency']:.1f} Hz ({status})")

    # Find overshoot
    if end_freq > start_freq:
        overshoot = max(freqs) - end_freq
    else:
        overshoot = end_freq - min(freqs)

    # Find settling time (when error stays < 1 Hz)
    settling_time = duration
    for i, err in enumerate(errors):
        if abs(err) < 1.0:
            if all(abs(e) < 1.0 for e in errors[i:min(i+10, len(errors))]):
                settling_time = times[i]
                break

    print(f"\n  Overshoot: {overshoot:+.1f} Hz")
    print(f"  Settling time: {settling_time:.2f}s")

    audio = np.concatenate(audio_chunks)
    return audio, {'overshoot': overshoot, 'settling': settling_time}


def main():
    use_cache = '--no-cache' not in sys.argv

    print("=" * 60)
    print("  PID COMPARISON: PI (Vintage) vs PID (With D Term)")
    print("=" * 60)

    if use_cache:
        print("  (Using cache - run with --no-cache to regenerate)")

    print("""
Testing a large frequency jump (A2 → E3 = 110Hz → 165Hz)

PI Control (Authentic 1979):
  - Integral winds up during approach
  - Overshoots target, then hunts back
  - Sounds like vintage servo behavior

PID Control (With Derivative):
  - D term sees approach velocity
  - Applies "braking" before arrival
  - Smoother landing, less overshoot
""")

    sample_rate = 44100
    start_freq = NOTES['A2']   # 110 Hz
    end_freq = NOTES['E3']     # 165 Hz (more achievable jump)

    # Cache parameters
    test_params = {
        'start': start_freq,
        'end': end_freq,
        'duration': 4.0,
        'sample_rate': sample_rate,
    }

    # === Test 1: PI Only (Authentic) ===
    pi_cache = get_cache_path('pi_test', {**test_params, 'd_gain': 0})
    audio_pi, stats_pi = None, None

    if use_cache:
        audio_pi, stats_pi = load_cached(pi_cache)

    if audio_pi is not None:
        print("=== PI CONTROL (Authentic 1979) === [CACHED]")
        print(f"  Overshoot: {stats_pi['overshoot']:+.1f} Hz")
        print(f"  Settling time: {stats_pi['settling']:.2f}s")
    else:
        voice_pi = SpiceVoice(sample_rate=sample_rate)
        voice_pi.enable_derivative(enabled=False)

        audio_pi, stats_pi = run_test(
            voice_pi, "=== PI CONTROL (Authentic 1979) ===",
            start_freq, end_freq
        )
        save_cache(pi_cache, audio_pi, stats_pi)
        print("  [Saved to cache]")

    # === Test 2: PID (With Derivative) ===
    pid_cache = get_cache_path('pid_test', {**test_params, 'd_gain': 0.03})
    audio_pid, stats_pid = None, None

    if use_cache:
        audio_pid, stats_pid = load_cached(pid_cache)

    if audio_pid is not None:
        print("\n=== PID CONTROL (With D Term) === [CACHED]")
        print(f"  Overshoot: {stats_pid['overshoot']:+.1f} Hz")
        print(f"  Settling time: {stats_pid['settling']:.2f}s")
    else:
        voice_pid = SpiceVoice(sample_rate=sample_rate)
        voice_pid.enable_derivative(enabled=True, gain=0.03)

        audio_pid, stats_pid = run_test(
            voice_pid, "\n=== PID CONTROL (With D Term) ===",
            start_freq, end_freq
        )
        save_cache(pid_cache, audio_pid, stats_pid)
        print("  [Saved to cache]")

    # === Summary ===
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"""
                    PI (Vintage)    PID (Modern)
                    ────────────    ────────────
  Overshoot:        {stats_pi['overshoot']:+.1f} Hz        {stats_pid['overshoot']:+.1f} Hz
  Settling time:    {stats_pi['settling']:.2f}s           {stats_pid['settling']:.2f}s
""")

    # === Play Audio ===
    print("Playing PI (vintage) response...")
    audio_pi_norm = audio_pi / np.max(np.abs(audio_pi)) * 0.8
    sd.play(audio_pi_norm, sample_rate)
    sd.wait()

    print("\nPlaying PID (with derivative) response...")
    audio_pid_norm = audio_pid / np.max(np.abs(audio_pid)) * 0.8
    sd.play(audio_pid_norm, sample_rate)
    sd.wait()

    print("\nDone! Which sounds better for your application?")
    print("  - PI: More 'vintage servo' character, hunting sound")
    print("  - PID: Smoother, more precise, less character")
    print("\nRun with --no-cache to regenerate audio.")


if __name__ == '__main__':
    main()
