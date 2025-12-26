#!/usr/bin/env python3
"""
Generate all demo audio caches.

This script pre-generates cached audio for all demos so they play instantly.
Run this once, then subsequent demo runs will load from cache.
"""

import sys
import os
import time

sys.path.insert(0, '.')

# Disable sounddevice to avoid playback
class MockSoundDevice:
    def play(self, *args, **kwargs): pass
    def wait(self): pass

sys.modules['sounddevice'] = MockSoundDevice()

import numpy as np

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.audio_cache')
os.makedirs(CACHE_DIR, exist_ok=True)


def generate_spice_scale():
    """Generate SPICE scale cache"""
    from aerotone.spice_voice import SpiceVoice
    from aerotone.propeller import NOTES

    print("\n[1/6] Generating SPICE scale...")
    start = time.time()

    A_MAJOR = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3']
    scale = A_MAJOR + list(reversed(A_MAJOR[:-1]))
    sample_rate = 44100
    note_duration = 1.0

    voice = SpiceVoice(sample_rate=sample_rate)

    # Pre-spin
    first_freq = NOTES[scale[0]]
    voice.set_target_frequency(first_freq)
    for _ in range(3000):
        voice.update_physics(0.001)

    # Generate scale
    all_audio = []
    chunk_size = int(sample_rate * 0.005)

    for note in scale:
        freq = NOTES[note]
        voice.set_target_frequency(freq)
        samples = int(note_duration * sample_rate)
        for i in range(0, samples, chunk_size):
            n = min(chunk_size, samples - i)
            all_audio.append(voice.generate_audio(n))

    full_audio = np.concatenate(all_audio)
    peak = np.max(np.abs(full_audio))
    if peak > 0:
        full_audio = full_audio / peak * 0.8

    cache_path = os.path.join(CACHE_DIR, 'spice_scale.npz')
    np.savez(cache_path, audio=full_audio)

    print(f"   Done in {time.time()-start:.1f}s ({len(full_audio)/sample_rate:.1f}s audio)")


def generate_duck_scale():
    """Generate duck scale cache"""
    from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
    from aerotone.propeller import NOTES

    print("\n[2/6] Generating duck scale...")
    start = time.time()

    sample_rate = 44100
    params = SpiceVoiceParams(
        expression_duck_enabled=True,
        expression_duck_depth=0.45,
        expression_duck_threshold=5.0,
        expression_duck_attack=0.06,
        expression_duck_release=0.14,
    )
    voice = SpiceVoice(params=params, sample_rate=sample_rate)

    notes = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
    note_duration = 0.65
    chunk_size = int(sample_rate * 0.01)
    audio_chunks = []

    # Pre-spin
    voice.set_target_frequency(NOTES['A2'])
    warmup_samples = int(0.8 * sample_rate)
    for i in range(0, warmup_samples, chunk_size):
        n = min(chunk_size, warmup_samples - i)
        audio_chunks.append(voice.generate_audio(n))

    # Ascending
    for note in notes:
        voice.set_target_frequency(NOTES[note])
        num_samples = int(note_duration * sample_rate)
        for j in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - j)
            audio_chunks.append(voice.generate_audio(n))

    # Hold at top
    hold_samples = int(0.4 * sample_rate)
    for i in range(0, hold_samples, chunk_size):
        n = min(chunk_size, hold_samples - i)
        audio_chunks.append(voice.generate_audio(n))

    # Descending
    for note in reversed(notes):
        voice.set_target_frequency(NOTES[note])
        num_samples = int(note_duration * sample_rate)
        for j in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - j)
            audio_chunks.append(voice.generate_audio(n))

    # Final hold
    hold_samples = int(0.5 * sample_rate)
    for i in range(0, hold_samples, chunk_size):
        n = min(chunk_size, hold_samples - i)
        audio_chunks.append(voice.generate_audio(n))

    audio = np.concatenate(audio_chunks)

    # Fade out
    fade_samples = int(0.5 * sample_rate)
    fade = np.linspace(1, 0, fade_samples)
    audio[-fade_samples:] *= fade

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.8

    cache_path = os.path.join(CACHE_DIR, 'duck_scale_major.npy')
    np.save(cache_path, audio)

    print(f"   Done in {time.time()-start:.1f}s ({len(audio)/sample_rate:.1f}s audio)")


def generate_weather_scale():
    """Generate weather scale caches"""
    from aerotone.spice_voice import SpiceVoice
    from aerotone.weather import Weather, TurbulentWeather
    import hashlib

    print("\n[3/6] Generating weather scale (3 variants)...")
    start = time.time()

    sample_rate = 44100
    SCALE_FREQS = [110.00, 123.47, 138.59, 146.83, 164.81, 185.00, 207.65, 220.00]

    cache_params = {
        'scale': 'A_major',
        'sample_rate': sample_rate,
        'version': 4,
    }
    param_str = str(sorted(cache_params.items()))
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]

    def generate_run(voice, weather, label):
        note_duration = 0.85
        gliss_duration = 0.12
        hold_duration = 1.1
        rest_duration = 0.3

        voice.set_weather(weather)
        voice.set_target_frequency(SCALE_FREQS[0])
        for _ in range(3000):
            voice.update_physics(0.001)

        audio_chunks = []
        samples_per_ms = sample_rate // 1000
        chunk_size = samples_per_ms * 5

        def generate_segment(duration_s):
            samples = int(duration_s * sample_rate)
            audio = []
            for i in range(0, samples, chunk_size):
                n = min(chunk_size, samples - i)
                audio.append(voice.generate_audio(n))
            return np.concatenate(audio)

        def glissando(start_freq, end_freq, duration_s):
            samples = int(duration_s * sample_rate)
            audio = []
            for i in range(0, samples, chunk_size):
                t = i / samples
                freq = start_freq * ((end_freq / start_freq) ** t)
                voice.set_target_frequency(freq)
                n = min(chunk_size, samples - i)
                audio.append(voice.generate_audio(n))
            return np.concatenate(audio)

        # Ascending
        for i in range(len(SCALE_FREQS)):
            freq = SCALE_FREQS[i]
            voice.set_target_frequency(freq)
            audio_chunks.append(generate_segment(note_duration))
            if i < len(SCALE_FREQS) - 1:
                next_freq = SCALE_FREQS[i + 1]
                audio_chunks.append(glissando(freq, next_freq, gliss_duration))

        audio_chunks.append(generate_segment(hold_duration))
        audio_chunks.append(generate_segment(rest_duration))

        # Descending
        for i in range(len(SCALE_FREQS) - 1, -1, -1):
            freq = SCALE_FREQS[i]
            voice.set_target_frequency(freq)
            audio_chunks.append(generate_segment(note_duration))
            if i > 0:
                next_freq = SCALE_FREQS[i - 1]
                audio_chunks.append(glissando(freq, next_freq, gliss_duration))

        audio_chunks.append(generate_segment(hold_duration))
        return np.concatenate(audio_chunks)

    # No weather
    voice = SpiceVoice(sample_rate=sample_rate)
    audio_clean = generate_run(voice, None, "clean")
    np.savez(os.path.join(CACHE_DIR, f'scale_no_weather_{param_hash}.npz'), audio=audio_clean)
    print(f"   - No weather done")

    # Normal weather
    voice = SpiceVoice(sample_rate=sample_rate)
    weather = Weather(seed=123)
    audio_weather = generate_run(voice, weather, "weather")
    np.savez(os.path.join(CACHE_DIR, f'scale_weather_{param_hash}.npz'), audio=audio_weather)
    print(f"   - Normal weather done")

    # Turbulent weather
    voice = SpiceVoice(sample_rate=sample_rate)
    weather = TurbulentWeather(seed=456)
    audio_turb = generate_run(voice, weather, "turbulent")
    np.savez(os.path.join(CACHE_DIR, f'scale_turbulent_{param_hash}.npz'), audio=audio_turb)
    print(f"   - Turbulent weather done")

    print(f"   Total: {time.time()-start:.1f}s")


def generate_silent_night():
    """Generate Silent Night cache"""
    from aerotone.spice_voice import SpiceVoice
    from aerotone.weather import Weather, WeatherParams

    print("\n[4/6] Generating Silent Night...")
    start = time.time()

    MELODY_NOTES = {
        'G2': 98.00, 'A2': 110.00, 'B2': 123.47, 'C3': 130.81,
        'D3': 146.83, 'E3': 164.81, 'F3': 174.61, 'G3': 196.00, 'A3': 220.00,
    }

    sample_rate = 44100
    quarter = 0.8
    half = 1.6
    dotted_half = 2.4
    eighth = 0.4

    silent_night = [
        ('G3', quarter + eighth), ('A3', eighth), ('G3', half),
        ('E3', dotted_half),
        ('G3', quarter + eighth), ('A3', eighth), ('G3', half),
        ('E3', dotted_half),
        (None, 0.3),
        ('D3', half), ('D3', quarter), ('B2', dotted_half),
        ('C3', half), ('C3', quarter), ('G2', dotted_half),
        (None, 0.3),
        ('A2', quarter), ('A2', quarter + eighth), ('C3', eighth), ('B2', quarter), ('A2', quarter),
        ('G3', quarter + eighth), ('A3', eighth), ('G3', quarter), ('E3', half),
        ('A2', quarter), ('A2', quarter + eighth), ('C3', eighth), ('B2', quarter), ('A2', quarter),
        ('G3', quarter + eighth), ('A3', eighth), ('G3', quarter), ('E3', half),
        (None, 0.4),
        ('D3', half), ('D3', quarter + eighth), ('F3', eighth), ('D3', quarter), ('B2', quarter),
        ('C3', half), ('E3', quarter), ('C3', dotted_half),
        (None, 0.5),
        ('D3', half), ('D3', half), ('F3', quarter), ('D3', quarter), ('B2', half),
        ('C3', half), ('E3', half), ('C3', dotted_half * 1.5),
        (None, 2.0),
    ]

    weather_params = WeatherParams(density_variation=0.05, time_scale=0.02)
    weather = Weather(weather_params)
    voice = SpiceVoice(sample_rate=sample_rate, weather=weather)

    # Pre-spin
    first_freq = MELODY_NOTES['G3']
    voice.set_target_frequency(first_freq)
    warmup_samples = int(1.5 * sample_rate)
    chunk_size = int(sample_rate * 0.01)
    warmup_audio = []
    for i in range(0, warmup_samples, chunk_size):
        n = min(chunk_size, warmup_samples - i)
        warmup_audio.append(voice.generate_audio(n))
    warmup_audio = np.concatenate(warmup_audio)

    # Generate melody
    melody_audio = []
    for note, duration in silent_night:
        num_samples = int(duration * sample_rate)
        if note is None:
            voice.set_target_frequency(0)
        else:
            voice.set_target_frequency(MELODY_NOTES.get(note, 110))
        for i in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - i)
            melody_audio.append(voice.generate_audio(n))
    melody_audio = np.concatenate(melody_audio)

    # Combine with fades
    fade_in = np.linspace(0, 1, len(warmup_audio))
    warmup_audio = warmup_audio * fade_in

    fade_out_samples = int(2.0 * sample_rate)
    if len(melody_audio) > fade_out_samples:
        fade_out = np.linspace(1, 0, fade_out_samples)
        melody_audio[-fade_out_samples:] *= fade_out

    full_audio = np.concatenate([warmup_audio, melody_audio])
    peak = np.max(np.abs(full_audio))
    if peak > 0:
        full_audio = full_audio / peak * 0.8

    cache_path = os.path.join(CACHE_DIR, 'silent_night.npy')
    np.save(cache_path, full_audio)

    print(f"   Done in {time.time()-start:.1f}s ({len(full_audio)/sample_rate:.1f}s audio)")


def generate_concert():
    """Generate concert scale cache"""
    from aerotone.concert_voice import ConcertVoice
    from aerotone.propeller import NOTES

    print("\n[5/6] Generating concert scale...")
    start = time.time()

    sample_rate = 44100
    voice = ConcertVoice(sample_rate=sample_rate)

    # Spinup
    voice.set_target_frequency(NOTES['A2'])
    for _ in range(5000):
        voice.update_physics(0.001)

    # Generate scale
    scale = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
    note_duration = 0.85
    gliss_duration = 0.12

    all_audio = []
    samples_per_ms = sample_rate // 1000
    chunk_size = samples_per_ms * 5

    def generate_segment(duration_s):
        samples = int(duration_s * sample_rate)
        audio = []
        for i in range(0, samples, chunk_size):
            n = min(chunk_size, samples - i)
            audio.append(voice.generate_audio(n))
        return np.concatenate(audio)

    def glissando(start_freq, end_freq, duration_s):
        samples = int(duration_s * sample_rate)
        audio = []
        for i in range(0, samples, chunk_size):
            t = i / samples
            freq = start_freq * ((end_freq / start_freq) ** t)
            voice.set_target_frequency(freq)
            n = min(chunk_size, samples - i)
            audio.append(voice.generate_audio(n))
        return np.concatenate(audio)

    # Ascending
    for i, note in enumerate(scale):
        voice.set_target_frequency(NOTES[note])
        all_audio.append(generate_segment(note_duration))
        if i < len(scale) - 1:
            all_audio.append(glissando(NOTES[note], NOTES[scale[i + 1]], gliss_duration))

    all_audio.append(generate_segment(1.0))

    # Descending
    for i in range(len(scale) - 1, -1, -1):
        voice.set_target_frequency(NOTES[scale[i]])
        all_audio.append(generate_segment(note_duration))
        if i > 0:
            all_audio.append(glissando(NOTES[scale[i]], NOTES[scale[i - 1]], gliss_duration))

    all_audio.append(generate_segment(1.0))

    audio = np.concatenate(all_audio)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.8

    cache_path = os.path.join(CACHE_DIR, 'concert_scale.npy')
    np.save(cache_path, audio)

    print(f"   Done in {time.time()-start:.1f}s ({len(audio)/sample_rate:.1f}s audio)")


def generate_acoustics_compare():
    """Generate acoustics comparison cache"""
    from aerotone.acoustics import PropellerSynth
    from aerotone.acoustics_v2 import AdvancedPropellerSynth
    from aerotone.propeller import NOTES

    print("\n[6/6] Generating acoustics comparison...")
    start = time.time()

    sample_rate = 44100
    synth_v1 = PropellerSynth(sample_rate)
    synth_v2 = AdvancedPropellerSynth(sample_rate)

    freq = 220
    duration = 3.0
    num_samples = int(duration * sample_rate)
    chunk_size = int(sample_rate * 0.01)

    # V1 note
    synth_v1.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)
    synth_v1.bpf_smooth = freq
    synth_v1.amp_smooth = 0.8
    audio_v1_note = []
    for i in range(0, num_samples, chunk_size):
        n = min(chunk_size, num_samples - i)
        audio_v1_note.append(synth_v1.generate(n))
    audio_v1_note = np.concatenate(audio_v1_note)

    # V2 note
    synth_v2.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)
    synth_v2.bpf_smooth = freq
    synth_v2.amp_smooth = 0.75
    audio_v2_note = []
    for i in range(0, num_samples, chunk_size):
        n = min(chunk_size, num_samples - i)
        audio_v2_note.append(synth_v2.generate(n))
    audio_v2_note = np.concatenate(audio_v2_note)

    # Scales
    notes = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
    note_duration = 0.6

    synth_v1.reset()
    synth_v2.reset()

    def generate_note_sequence(synth, notes, note_duration, sample_rate):
        audio = []
        chunk_size = int(sample_rate * 0.01)
        for note in notes:
            freq = NOTES.get(note, 110)
            synth.set_operating_point(bpf=freq, thrust=1.0, num_blades=12)
            synth.bpf_smooth = freq
            synth.amp_smooth = 0.75
            num_samples = int(note_duration * sample_rate)
            for i in range(0, num_samples, chunk_size):
                n = min(chunk_size, num_samples - i)
                audio.append(synth.generate(n))
        return np.concatenate(audio)

    audio_v1_scale = generate_note_sequence(synth_v1, notes, note_duration, sample_rate)
    audio_v2_scale = generate_note_sequence(synth_v2, notes, note_duration, sample_rate)

    def normalize(audio, target=0.8):
        peak = np.max(np.abs(audio))
        return audio / peak * target if peak > 0 else audio

    audio_v1_note = normalize(audio_v1_note)
    audio_v2_note = normalize(audio_v2_note)
    audio_v1_scale = normalize(audio_v1_scale)
    audio_v2_scale = normalize(audio_v2_scale)

    cache_path = os.path.join(CACHE_DIR, 'acoustics_compare.npz')
    np.savez(cache_path,
             v1_note=audio_v1_note,
             v2_note=audio_v2_note,
             v1_scale=audio_v1_scale,
             v2_scale=audio_v2_scale)

    print(f"   Done in {time.time()-start:.1f}s")


def main():
    print("=" * 70)
    print("  AEROTONE CACHE GENERATOR")
    print("  Pre-generating audio for instant playback")
    print("=" * 70)

    total_start = time.time()

    generate_spice_scale()
    generate_duck_scale()
    generate_weather_scale()
    generate_silent_night()
    generate_concert()
    generate_acoustics_compare()

    print("\n" + "=" * 70)
    print(f"All caches generated in {time.time()-total_start:.1f}s")
    print(f"Cache directory: {CACHE_DIR}")
    print("=" * 70)

    # List cached files
    print("\nCached files:")
    for f in sorted(os.listdir(CACHE_DIR)):
        size = os.path.getsize(os.path.join(CACHE_DIR, f))
        print(f"  {f}: {size/1024/1024:.1f} MB")


if __name__ == '__main__':
    main()
