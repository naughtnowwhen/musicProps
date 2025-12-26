#!/usr/bin/env python3
"""
AeroTone Iris Aperture Demo

Demonstrates the iris volume control with auto-duck during pitch transitions.

The iris aperture provides:
  1. Independent volume control (expression pedal input)
  2. Auto-duck: automatically reduces volume during pitch changes
     (the Clara Rockmore technique for perceived note boundaries)
  3. Frequency-dependent rolloff (darker tone when closing)
  4. Turbulence noise at very small apertures

This creates more musical, articulated phrases compared to
continuous glissando without volume shaping.
"""

import sys
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed")
    sys.exit(1)

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.propeller import NOTES


def generate_scale(voice, notes, note_duration, sample_rate, show_state=False):
    """Generate a scale with the voice, optionally showing iris state."""
    chunk_size = int(sample_rate * 0.01)  # 10ms chunks
    audio = []

    for i, note in enumerate(notes):
        freq = NOTES.get(note, 110)
        voice.set_target_frequency(freq)

        num_samples = int(note_duration * sample_rate)

        for j in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - j)
            audio.append(voice.generate_audio(n))

            # Show state at start of each note
            if show_state and j == 0:
                state = voice.get_circuit_state()
                print(f"  {note:4s}: iris={state['iris_aperture']:.2f}, "
                      f"duck={state['expression_duck']:.2f}, "
                      f"atten={state['iris_attenuation_db']:.1f}dB")

    return np.concatenate(audio)


def main():
    print("=" * 70)
    print("  AEROTONE IRIS APERTURE DEMO")
    print("  Volume control with auto-duck during transitions")
    print("=" * 70)

    print("""
The iris aperture is a mechanical volume control (like a camera aperture)
that operates independently of propeller RPM.

AUTO-DUCK: During pitch transitions, the iris automatically closes slightly,
creating perceived note boundaries. This is the "Clara Rockmore technique"
that transformed the theremin from novelty to concert instrument.

Without auto-duck: All notes blend into continuous glissando
With auto-duck:    Notes feel more articulated and musical
""")

    sample_rate = 44100
    notes = ['A2', 'B2', 'C#3', 'D3', 'E3', 'F#3', 'G#3', 'A3']
    note_duration = 0.7

    # === Test 1: No duck (disabled) ===
    print("Generating scale WITHOUT auto-duck...")
    params_no_duck = SpiceVoiceParams(
        expression_duck_enabled=False,
    )
    voice_no_duck = SpiceVoice(params=params_no_duck, sample_rate=sample_rate)

    # Pre-spin
    voice_no_duck.set_target_frequency(NOTES['A2'])
    warmup = []
    for _ in range(int(1.0 * sample_rate / 441)):
        warmup.append(voice_no_duck.generate_audio(441))
    warmup = np.concatenate(warmup)

    audio_no_duck = generate_scale(voice_no_duck, notes, note_duration, sample_rate)
    audio_no_duck = np.concatenate([warmup, audio_no_duck])

    # === Test 2: With duck (enabled) ===
    print("\nGenerating scale WITH auto-duck...")
    params_duck = SpiceVoiceParams(
        expression_duck_enabled=True,
        expression_duck_depth=0.35,     # 35% volume reduction during transitions
        expression_duck_threshold=1.5,  # Hz/s to trigger
    )
    voice_duck = SpiceVoice(params=params_duck, sample_rate=sample_rate)

    # Pre-spin
    voice_duck.set_target_frequency(NOTES['A2'])
    warmup2 = []
    for _ in range(int(1.0 * sample_rate / 441)):
        warmup2.append(voice_duck.generate_audio(441))
    warmup2 = np.concatenate(warmup2)

    print("\nIris state during scale (with duck):")
    audio_duck = generate_scale(voice_duck, notes, note_duration, sample_rate, show_state=True)
    audio_duck = np.concatenate([warmup2, audio_duck])

    # === Test 3: Expression pedal sweep ===
    print("\nGenerating expression pedal demo (sustained note, volume sweep)...")
    voice_expr = SpiceVoice(sample_rate=sample_rate)
    voice_expr.set_target_frequency(NOTES['D3'])

    # Warm up at full volume
    warmup3 = []
    for _ in range(int(1.0 * sample_rate / 441)):
        warmup3.append(voice_expr.generate_audio(441))

    # Sweep expression from full to quiet to full
    expr_audio = []
    duration = 4.0
    num_samples = int(duration * sample_rate)
    chunk_size = int(sample_rate * 0.01)

    for i in range(0, num_samples, chunk_size):
        t = i / num_samples
        # Sine wave envelope: 1 -> 0.1 -> 1
        expression = 0.55 + 0.45 * np.cos(2 * np.pi * t)
        voice_expr.set_expression(expression)

        n = min(chunk_size, num_samples - i)
        expr_audio.append(voice_expr.generate_audio(n))

    audio_expr = np.concatenate(warmup3 + expr_audio)

    # Normalize all
    def normalize(audio, target=0.75):
        peak = np.max(np.abs(audio))
        return audio / peak * target if peak > 0 else audio

    audio_no_duck = normalize(audio_no_duck)
    audio_duck = normalize(audio_duck)
    audio_expr = normalize(audio_expr)

    # === Playback ===
    print("\n" + "=" * 70)
    print("PLAYBACK")
    print("=" * 70)

    print("\n1. SCALE - NO AUTO-DUCK")
    print("   Listen for: Continuous glissando, notes blend together")
    sd.play(audio_no_duck, sample_rate)
    sd.wait()

    print("\n2. SCALE - WITH AUTO-DUCK")
    print("   Listen for: Brief volume dips during transitions = articulated notes")
    sd.play(audio_duck, sample_rate)
    sd.wait()

    print("\n3. EXPRESSION PEDAL SWEEP (sustained note)")
    print("   Listen for: Volume swell, HF rolloff when quiet (darker tone)")
    sd.play(audio_expr, sample_rate)
    sd.wait()

    # === Side by side ===
    print("\n4. SIDE-BY-SIDE (no duck LEFT, with duck RIGHT)")
    min_len = min(len(audio_no_duck), len(audio_duck))
    stereo = np.column_stack([audio_no_duck[:min_len], audio_duck[:min_len]])
    sd.play(stereo, sample_rate)
    sd.wait()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
The iris aperture enables musical expression independent of pitch:

1. AUTO-DUCK: Brief volume reduction during pitch changes creates
   perceived note boundaries (the Clara Rockmore technique)

2. EXPRESSION PEDAL: Manual volume control for dynamics

3. TIMBRAL SHAPING: Closing the iris darkens the tone (HF rolloff),
   mimicking how real instruments sound quieter AND warmer at low volumes

This transforms the propeller from a "swanee whistle" novelty into
a musically expressive instrument.
""")


if __name__ == '__main__':
    main()
