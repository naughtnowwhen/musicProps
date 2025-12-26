#!/usr/bin/env python3
"""
AeroTone Fault Injection Demo

Deliberately breaks 3 different components in realistic ways,
then runs normal musical playback to observe how failures manifest.

Faults:
  1. WORN MOTOR - Damaged bearings cause friction, noise, pitch wobble
  2. BURNED TRANSISTOR - H-bridge transistor partially failed
  3. STRIPPED SERVO - Iris gear teeth stripped, can't hold position

For each fault:
  - Inject the failure
  - Play "Silent Night" melody
  - Save the audio
  - Generate a diagnostic report

Usage:
    python demo_fault_injection.py
"""

import sys
import os
import numpy as np
from datetime import datetime

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'fault_injection_output')


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_wav(filename, audio, sample_rate):
    """Save audio as WAV file"""
    import wave
    import struct

    filepath = os.path.join(OUTPUT_DIR, filename)

    # Normalize and convert to 16-bit
    audio = np.clip(audio, -1.0, 1.0)
    audio_int = (audio * 32767).astype(np.int16)

    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_int.tobytes())

    return filepath


def get_silent_night_melody():
    """Return Silent Night melody (first phrase)"""
    quarter = 0.7
    half = 1.4
    dotted_half = 2.1
    eighth = 0.35

    NOTES = {
        'G3': 196.00, 'A3': 220.00, 'E3': 164.81,
        'D3': 146.83, 'B2': 123.47, 'C3': 130.81,
        'G2': 98.00, 'A2': 110.00, 'F3': 174.61,
    }

    melody = [
        ('G3', quarter + eighth), ('A3', eighth), ('G3', half), ('E3', dotted_half),
        ('G3', quarter + eighth), ('A3', eighth), ('G3', half), ('E3', dotted_half),
        (None, 0.3),
        ('D3', half), ('D3', quarter), ('B2', dotted_half),
        ('C3', half), ('C3', quarter), ('G2', dotted_half),
        (None, 0.5),
    ]

    return melody, NOTES


def generate_audio(voice, melody, notes, sample_rate, warmup=1.0):
    """Generate audio for a melody with warmup"""
    chunk_size = int(sample_rate * 0.01)
    audio = []

    # Warmup on first note
    if melody and melody[0][0]:
        first_freq = notes.get(melody[0][0], 110)
        voice.set_target_frequency(first_freq)

        warmup_samples = int(warmup * sample_rate)
        warmup_audio = []
        for i in range(0, warmup_samples, chunk_size):
            n = min(chunk_size, warmup_samples - i)
            warmup_audio.append(voice.generate_audio(n))
        warmup_audio = np.concatenate(warmup_audio)

        # Fade in
        fade = np.linspace(0, 1, len(warmup_audio))
        warmup_audio = warmup_audio * fade
        audio.append(warmup_audio)

    # Play melody
    for note, duration in melody:
        num_samples = int(duration * sample_rate)

        if note is None:
            voice.set_target_frequency(0)
        else:
            freq = notes.get(note, 110)
            voice.set_target_frequency(freq)

        for i in range(0, num_samples, chunk_size):
            n = min(chunk_size, num_samples - i)
            audio.append(voice.generate_audio(n))

    full_audio = np.concatenate(audio)

    # Fade out
    fade_samples = int(1.0 * sample_rate)
    if len(full_audio) > fade_samples:
        fade = np.linspace(1, 0, fade_samples)
        full_audio[-fade_samples:] *= fade

    # Normalize
    peak = np.max(np.abs(full_audio))
    if peak > 0:
        full_audio = full_audio / peak * 0.8

    return full_audio


def analyze_audio(audio, sample_rate):
    """Analyze audio for artifacts"""
    results = {}

    # RMS level
    results['rms'] = np.sqrt(np.mean(audio ** 2))

    # Peak level
    results['peak'] = np.max(np.abs(audio))

    # Crest factor (peak/RMS) - high values indicate transients/clicks
    results['crest_factor'] = results['peak'] / max(results['rms'], 1e-10)

    # Zero crossings per second (rough frequency/noise estimate)
    zero_crossings = np.sum(np.abs(np.diff(np.sign(audio))) > 0)
    duration = len(audio) / sample_rate
    results['zero_crossing_rate'] = zero_crossings / duration

    # Check for DC offset
    results['dc_offset'] = np.mean(audio)

    # Check for clipping
    results['clipping_samples'] = np.sum(np.abs(audio) > 0.99)

    # Noise floor estimate (using quiet sections)
    # Find the quietest 10% of the signal
    sorted_abs = np.sort(np.abs(audio))
    quiet_portion = sorted_abs[:len(sorted_abs)//10]
    results['noise_floor'] = np.mean(quiet_portion) if len(quiet_portion) > 0 else 0

    return results


# =============================================================================
# FAULT 1: LEAKY LOOP FILTER CAPACITOR
# =============================================================================

def inject_leaky_capacitor(voice):
    """
    Simulate a leaky electrolytic capacitor in the PLL loop filter.

    Physical effects:
    - Capacitor has high leakage current (aged electrolytic)
    - Loop filter time constant reduced
    - PLL becomes unstable/oscillates
    - Control voltage drifts

    This is the C1 capacitor in the loop filter (nominally 10uF).
    Leaky caps are extremely common in vintage electronics.
    """
    # The loop filter smooths the phase detector output
    # A leaky cap means it can't hold charge -> faster discharge

    original_update = voice.loop_filter.update

    # Leakage causes voltage to decay toward zero
    leakage_rate = 0.15  # Much faster than normal RC decay

    def leaky_filter_update(input_voltage, dt, high_z=False):
        # Call original
        result = original_update(input_voltage, dt, high_z=high_z)

        # Apply leakage - voltage decays toward midpoint
        midpoint = voice.params.vdd / 2
        voice.loop_filter.output_voltage -= (voice.loop_filter.output_voltage - midpoint) * leakage_rate * dt * 100

        # Also add some noise from the leakage current
        voice.loop_filter.output_voltage += np.random.randn() * 0.02

        return voice.loop_filter.output_voltage

    voice.loop_filter.update = leaky_filter_update

    return {
        'fault_name': 'Leaky Loop Filter Capacitor (C1)',
        'description': 'The 10uF electrolytic capacitor in the PLL loop filter has '
                      'developed high leakage current due to age. This prevents the '
                      'loop filter from holding the control voltage steady.',
        'physical_cause': 'Electrolytic capacitor aging (dried electrolyte), heat damage, '
                         'or exceeded voltage rating causing dielectric breakdown',
        'expected_symptoms': [
            'Pitch instability (warbling/oscillation)',
            'Slow pitch drift between notes',
            'Poor phase lock - rough/buzzy tone',
            'Audible low-frequency modulation',
        ],
    }


# =============================================================================
# FAULT 2: BURNED H-BRIDGE TRANSISTOR
# =============================================================================

def inject_burned_transistor(voice):
    """
    Simulate a partially failed H-bridge power transistor.

    Physical effects:
    - One transistor (Q1, high-side forward) has thermal damage
    - Increased on-resistance (Vce_sat goes from 0.4V to ~2V)
    - Asymmetric drive capability
    - Reduced power in forward direction only

    This is a 2N3055 or TIP3055 power transistor in TO-3 package.
    Common failure mode from heatsink failure or overcurrent.
    """
    # Store original driver update
    original_update = voice.driver.update

    # Q1 damaged - increases voltage drop in forward drive
    q1_extra_vdrop = 3.0  # Volts lost across damaged transistor

    def damaged_driver_update(dt, motor_back_emf=0.0):
        # Call original
        result = original_update(dt, motor_back_emf)

        # If driving forward (positive motor voltage), reduce voltage
        if voice.driver.motor_voltage > 0:
            # Damaged Q1 drops extra voltage
            voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - q1_extra_vdrop)

            # Damaged transistor also has noise from thermal damage
            voice.driver.motor_voltage += np.random.randn() * 0.15

        return result

    voice.driver.update = damaged_driver_update

    return {
        'fault_name': 'Burned H-Bridge Transistor (Q1)',
        'description': 'High-side power transistor Q1 (2N3055) has thermal damage '
                      'from heatsink failure. Collector-emitter saturation voltage '
                      'increased from 0.4V to ~2.5V, causing voltage loss in forward drive.',
        'physical_cause': 'Heatsink thermal compound dried out, heatsink loosened, '
                         'or sustained overcurrent from blocked propeller',
        'expected_symptoms': [
            'Motor accelerates slowly (upward pitch glides sluggish)',
            'Asymmetric response - faster decel than accel',
            'Reduced maximum pitch/frequency',
            'Audible asymmetry in vibrato',
        ],
    }


# =============================================================================
# FAULT 3: NOISY OP-AMP IN SIGNAL CONDITIONER
# =============================================================================

def inject_noisy_opamp(voice):
    """
    Simulate a failing op-amp in the signal conditioning circuit.

    Physical effects:
    - Op-amp has increased noise (degraded input stage)
    - Intermittent oscillation (internal feedback issue)
    - Offset voltage drift
    - Reduced slew rate

    This is likely a 741 or TL071 op-amp in the signal path from
    the magnetic pickup to the CD4046 phase comparator input.
    """
    # Store original conditioner update method
    original_update = voice.conditioner.update

    # Fault parameters
    noise_amplitude = 0.5       # Increased noise on amplified signal
    oscillation_freq = 8000     # High-frequency parasitic oscillation
    offset_drift = 0.0          # Will accumulate
    offset_drift_rate = 0.002   # Slow drift

    def noisy_conditioner_update(dt, input_voltage):
        nonlocal offset_drift

        # Call original
        original_update(dt, input_voltage)

        # Add increased noise to amplified output (degraded input transistors)
        noise = np.random.randn() * noise_amplitude
        voice.conditioner.amplified_voltage += noise

        # Add intermittent HF oscillation (positive feedback issue)
        if not hasattr(voice.conditioner, '_osc_phase'):
            voice.conditioner._osc_phase = 0.0
        voice.conditioner._osc_phase += dt * oscillation_freq * 2 * np.pi

        # Oscillation comes and goes (30% of the time it's active)
        if np.random.random() < 0.3:
            osc = np.sin(voice.conditioner._osc_phase) * 0.4
            voice.conditioner.amplified_voltage += osc

        # Offset drift (thermal instability in input stage)
        offset_drift += (np.random.randn() * offset_drift_rate)
        offset_drift = np.clip(offset_drift, -1.0, 1.0)
        voice.conditioner.amplified_voltage += offset_drift

        # Re-run comparator with corrupted signal
        if voice.conditioner.amplified_voltage > voice.conditioner.upper_threshold:
            voice.conditioner.digital_output = True
        elif voice.conditioner.amplified_voltage < voice.conditioner.lower_threshold:
            voice.conditioner.digital_output = False

    voice.conditioner.update = noisy_conditioner_update

    return {
        'fault_name': 'Degraded Op-Amp (Signal Conditioner)',
        'description': 'The 741 op-amp in the signal conditioning stage has degraded, '
                      'causing increased noise, intermittent HF oscillation, and offset drift. '
                      'This corrupts the feedback signal to the CD4046 PLL.',
        'physical_cause': 'Age-related degradation, ESD damage to input stage, '
                         'or thermal stress from nearby power components',
        'expected_symptoms': [
            'Increased background noise/hiss',
            'Occasional high-frequency squealing',
            'Pitch instability from corrupted feedback',
            'Intermittent problems (comes and goes)',
        ],
    }


# =============================================================================
# MAIN
# =============================================================================

def run_fault_test(fault_name, inject_func, sample_rate=44100):
    """Run a single fault test"""
    print(f"\n{'='*60}")
    print(f"  FAULT: {fault_name}")
    print('='*60)

    # Create fresh voice
    params = SpiceVoiceParams(
        enable_thermal=False,  # Disable thermal for this test
        use_circuit_iris=True,
    )
    voice = SpiceVoice(params=params, sample_rate=sample_rate)

    # Inject fault
    fault_info = inject_func(voice)
    print(f"\n  Injecting: {fault_info['fault_name']}")
    print(f"  Cause: {fault_info['physical_cause']}")
    print(f"\n  Expected symptoms:")
    for symptom in fault_info['expected_symptoms']:
        print(f"    - {symptom}")

    # Generate audio
    print("\n  Generating audio...")
    melody, notes = get_silent_night_melody()
    audio = generate_audio(voice, melody, notes, sample_rate)

    # Analyze
    print("  Analyzing audio...")
    analysis = analyze_audio(audio, sample_rate)

    # Save audio
    filename = f"fault_{fault_name.lower().replace(' ', '_')}.wav"
    filepath = save_wav(filename, audio, sample_rate)
    print(f"  Saved: {filepath}")

    # Generate report
    report = generate_report(fault_info, analysis, filepath)

    return audio, analysis, report


def run_healthy_baseline(sample_rate=44100):
    """Generate healthy baseline for comparison"""
    print(f"\n{'='*60}")
    print("  BASELINE: Healthy System")
    print('='*60)

    params = SpiceVoiceParams(
        enable_thermal=False,
        use_circuit_iris=True,
    )
    voice = SpiceVoice(params=params, sample_rate=sample_rate)

    print("\n  Generating healthy audio...")
    melody, notes = get_silent_night_melody()
    audio = generate_audio(voice, melody, notes, sample_rate)

    analysis = analyze_audio(audio, sample_rate)

    filename = "baseline_healthy.wav"
    filepath = save_wav(filename, audio, sample_rate)
    print(f"  Saved: {filepath}")

    return audio, analysis


def generate_report(fault_info, analysis, audio_path):
    """Generate diagnostic report for a fault"""
    report = []
    report.append("=" * 60)
    report.append(f"FAULT DIAGNOSTIC REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 60)

    report.append(f"\nFAULT: {fault_info['fault_name']}")
    report.append("-" * 40)
    report.append(f"Description: {fault_info['description']}")
    report.append(f"Physical Cause: {fault_info['physical_cause']}")

    report.append(f"\nEXPECTED SYMPTOMS:")
    for symptom in fault_info['expected_symptoms']:
        report.append(f"  - {symptom}")

    report.append(f"\nAUDIO ANALYSIS:")
    report.append("-" * 40)
    report.append(f"  RMS Level: {analysis['rms']:.4f}")
    report.append(f"  Peak Level: {analysis['peak']:.4f}")
    report.append(f"  Crest Factor: {analysis['crest_factor']:.2f}")
    report.append(f"  Zero Crossing Rate: {analysis['zero_crossing_rate']:.0f} Hz")
    report.append(f"  DC Offset: {analysis['dc_offset']:.6f}")
    report.append(f"  Noise Floor: {analysis['noise_floor']:.6f}")
    report.append(f"  Clipping Samples: {analysis['clipping_samples']}")

    report.append(f"\nAUDIO FILE: {audio_path}")

    report.append("\n" + "=" * 60)

    return "\n".join(report)


def main():
    print("\n" + "#" * 60)
    print("#  AEROTONE FAULT INJECTION DEMO")
    print("#  Breaking components to observe failure behavior")
    print("#" * 60)

    ensure_output_dir()
    sample_rate = 44100

    # Generate healthy baseline first
    baseline_audio, baseline_analysis = run_healthy_baseline(sample_rate)

    # Run each fault (electronic components only)
    faults = [
        ("Leaky Capacitor", inject_leaky_capacitor),
        ("Burned Transistor", inject_burned_transistor),
        ("Noisy Op-Amp", inject_noisy_opamp),
    ]

    all_reports = []

    for fault_name, inject_func in faults:
        audio, analysis, report = run_fault_test(fault_name, inject_func, sample_rate)
        all_reports.append(report)

        # Compare to baseline
        print("\n  Comparison to healthy baseline:")
        rms_diff = (analysis['rms'] - baseline_analysis['rms']) / baseline_analysis['rms'] * 100
        noise_diff = (analysis['noise_floor'] - baseline_analysis['noise_floor']) / max(baseline_analysis['noise_floor'], 1e-10) * 100

        print(f"    RMS change: {rms_diff:+.1f}%")
        print(f"    Noise floor change: {noise_diff:+.1f}%")
        print(f"    Crest factor: {analysis['crest_factor']:.2f} (baseline: {baseline_analysis['crest_factor']:.2f})")

    # Save combined report
    report_path = os.path.join(OUTPUT_DIR, "fault_injection_report.txt")
    with open(report_path, 'w') as f:
        f.write("AEROTONE FAULT INJECTION ANALYSIS\n")
        f.write("=" * 60 + "\n\n")
        f.write("This report documents the behavior of the AeroTone voice card\n")
        f.write("under three different component failure scenarios.\n\n")

        for report in all_reports:
            f.write(report)
            f.write("\n\n")

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print('='*60)
    print(f"\n  Output directory: {OUTPUT_DIR}")
    print(f"  Generated files:")
    print(f"    - baseline_healthy.wav")
    print(f"    - fault_leaky_capacitor.wav")
    print(f"    - fault_burned_transistor.wav")
    print(f"    - fault_noisy_op-amp.wav")
    print(f"    - fault_injection_report.txt")
    print(f"\n  Listen to each file and compare to baseline!")
    print(f"  The report contains detailed analysis of each fault.\n")


if __name__ == '__main__':
    main()
