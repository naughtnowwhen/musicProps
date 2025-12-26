#!/usr/bin/env python3
"""
AeroTone Circuit Diagnosis Demo

Demonstrates using virtual test equipment (DMM, oscilloscope) to
diagnose circuit faults through systematic signal tracing.

This is what an LLM would need to do to isolate a fault:
1. Observe symptoms (audio is wrong)
2. Probe test points systematically
3. Compare to expected values
4. Isolate the faulty component
5. Propose the fix

Usage:
    python demo_diagnosis.py
"""

import sys
import numpy as np

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench


def create_healthy_voice():
    """Create a healthy voice for reference"""
    params = SpiceVoiceParams(enable_thermal=False)
    return SpiceVoice(params=params, sample_rate=44100)


def create_faulty_voice(fault_type: str):
    """Create a voice with a specific fault injected"""
    params = SpiceVoiceParams(enable_thermal=False)
    voice = SpiceVoice(params=params, sample_rate=44100)

    if fault_type == "leaky_cap":
        # Leaky loop filter capacitor
        original_update = voice.loop_filter.update
        def leaky_update(input_voltage, dt, high_z=False):
            result = original_update(input_voltage, dt, high_z=high_z)
            midpoint = voice.params.vdd / 2
            voice.loop_filter.output_voltage -= (voice.loop_filter.output_voltage - midpoint) * 0.15 * dt * 100
            voice.loop_filter.output_voltage += np.random.randn() * 0.02
            return voice.loop_filter.output_voltage
        voice.loop_filter.update = leaky_update

    elif fault_type == "burned_transistor":
        # Burned H-bridge transistor
        original_update = voice.driver.update
        def damaged_update(dt, motor_back_emf=0.0):
            result = original_update(dt, motor_back_emf)
            if voice.driver.motor_voltage > 0:
                voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 3.0)
                voice.driver.motor_voltage += np.random.randn() * 0.15
            return result
        voice.driver.update = damaged_update

    elif fault_type == "noisy_opamp":
        # Noisy signal conditioner op-amp with ESD damage
        # Characteristic: output can exceed supply rails (broken clamping diodes)
        # and has increased noise floor and intermittent oscillation
        original_update = voice.conditioner.update
        offset_drift = [0.0]  # mutable container
        def noisy_update(dt, input_voltage):
            original_update(dt, input_voltage)
            # Random noise (increased from ESD damage)
            voice.conditioner.amplified_voltage += np.random.randn() * 0.8
            # Occasional HF oscillation bursts (positive feedback from damaged stage)
            if np.random.random() < 0.3:
                voice.conditioner.amplified_voltage += np.sin(np.random.random() * 1000) * 0.6
            # Slow offset drift (damaged bias network)
            offset_drift[0] += np.random.randn() * 0.005
            offset_drift[0] = np.clip(offset_drift[0], -2.0, 2.0)
            voice.conditioner.amplified_voltage += offset_drift[0]
            # Key symptom: damaged protection diodes allow output to exceed rails
            # (healthy op-amp would saturate at ±12V, damaged one can go ±14V)
            if abs(voice.conditioner.amplified_voltage) > 11.5:
                # Damaged clamping - overshoot beyond rails
                overshoot = np.random.uniform(0.5, 2.5)
                if voice.conditioner.amplified_voltage > 0:
                    voice.conditioner.amplified_voltage += overshoot
                else:
                    voice.conditioner.amplified_voltage -= overshoot
        voice.conditioner.update = noisy_update

    return voice


def warm_up_voice(voice, duration=0.5):
    """Run the voice for a bit to reach steady state"""
    voice.set_target_frequency(220.0)  # A3
    samples = int(duration * voice.sample_rate)
    chunk = int(voice.sample_rate * 0.01)
    for i in range(0, samples, chunk):
        voice.update_physics(chunk / voice.sample_rate)


def capture_reference_measurements(voice):
    """Capture measurements from a healthy voice as reference"""
    bench = TestBench(voice)
    warm_up_voice(voice)

    reference = {}
    for point in bench.get_probe_points():
        try:
            reference[point] = bench.measure_vdc(point).value
        except:
            reference[point] = 0.0

    # Capture some waveforms too
    reference['waveform_loop_filter'] = bench.capture_waveform('loop_filter_out', 0.1)
    reference['waveform_motor_voltage'] = bench.capture_waveform('motor_voltage', 0.1)
    reference['waveform_feedback'] = bench.capture_waveform('feedback_digital', 0.1)

    return reference


def diagnose_circuit(voice, reference):
    """
    Systematically diagnose a circuit by comparing to reference.

    This is the process an LLM would follow.
    """
    print("\n" + "=" * 60)
    print("  CIRCUIT DIAGNOSIS PROCEDURE")
    print("=" * 60)

    bench = TestBench(voice)
    warm_up_voice(voice)

    findings = []
    suspects = []

    # Step 1: Check power supply
    print("\n[STEP 1] Checking Power Supply...")
    v_supply = bench.probe('v_supply')
    v_logic = bench.probe('v_logic')
    print(f"  V_SUPPLY: {v_supply:.2f}V (expected: 12.0V)")
    print(f"  V_LOGIC:  {v_logic:.2f}V (expected: 15.0V)")

    if abs(v_supply - 12.0) > 1.0:
        findings.append(f"Supply voltage anomaly: {v_supply:.2f}V")
        suspects.append("Power supply or regulator")

    # Step 2: Check PLL / CD4046
    print("\n[STEP 2] Checking PLL (CD4046)...")
    vco_ctrl = bench.probe('vco_control')
    vco_ctrl_ref = reference.get('vco_control', 7.5)
    print(f"  VCO Control: {vco_ctrl:.2f}V (reference: {vco_ctrl_ref:.2f}V)")

    phase_det = bench.probe('phase_comp_2')  # Main phase comparator
    print(f"  Phase Det:   {phase_det:.2f}V")

    if abs(vco_ctrl - vco_ctrl_ref) > 2.0:
        findings.append(f"VCO control voltage deviation: {vco_ctrl:.2f}V vs {vco_ctrl_ref:.2f}V")
        suspects.append("CD4046 or loop filter")

    # Step 3: Check Loop Filter
    print("\n[STEP 3] Checking Loop Filter...")
    lf_in = bench.probe('loop_filter_in')
    lf_out = bench.probe('loop_filter_out')
    lf_out_ref = reference.get('loop_filter_out', 7.5)
    print(f"  Input:  {lf_in:.2f}V")
    print(f"  Output: {lf_out:.2f}V (reference: {lf_out_ref:.2f}V)")

    # Capture waveform to check for instability
    lf_wave = bench.capture_waveform('loop_filter_out', 0.1)
    ref_wave = reference.get('waveform_loop_filter')
    ref_ripple = ref_wave.v_ac_rms if ref_wave else 0.001
    print(f"  Ripple: {lf_wave.v_pp:.3f}Vpp, AC RMS: {lf_wave.v_ac_rms:.3f}V (reference: {ref_ripple:.3f}V)")

    if ref_wave and lf_wave.v_ac_rms > ref_wave.v_ac_rms * 2:
        ripple_ratio = lf_wave.v_ac_rms / ref_wave.v_ac_rms
        findings.append(f"Excessive loop filter ripple: {lf_wave.v_ac_rms:.3f}V vs {ref_wave.v_ac_rms:.3f}V ({ripple_ratio:.0f}x)")
        suspects.append("Loop filter capacitor (C1)")
        suspects.append("Loop filter capacitor (C1)")  # Double weight
        if ripple_ratio > 50:  # Very high ratio = strong indicator
            suspects.append("Loop filter capacitor (C1)")
            suspects.append("Loop filter capacitor (C1)")

    # Step 4: Check Motor Driver
    print("\n[STEP 4] Checking Motor Driver (H-Bridge)...")
    motor_v = bench.probe('motor_voltage')
    motor_v_ref = reference.get('motor_voltage', 8.0)
    motor_i = bench.probe('motor_current')
    print(f"  Motor Voltage: {motor_v:.2f}V (reference: {motor_v_ref:.2f}V)")
    print(f"  Motor Current: {motor_i:.3f}A")

    # Check for asymmetric drive
    motor_wave = bench.capture_waveform('motor_voltage', 0.1)
    print(f"  Voltage Vpp:   {motor_wave.v_pp:.2f}V")

    if motor_v_ref > 0 and motor_v < motor_v_ref * 0.7:
        findings.append(f"Low motor voltage: {motor_v:.2f}V vs {motor_v_ref:.2f}V expected")
        suspects.append("H-bridge transistor (Q1-Q4)")
        suspects.append("H-bridge transistor (Q1-Q4)")  # Double weight - strong indicator
        suspects.append("H-bridge transistor (Q1-Q4)")  # Triple weight for clear voltage drop

    # Step 5: Check Motor
    print("\n[STEP 5] Checking Motor...")
    back_emf = bench.probe('motor_back_emf')
    rpm = bench.probe('motor_rpm')
    rpm_ref = reference.get('motor_rpm', 1500)
    print(f"  Back EMF: {back_emf:.2f}V")
    print(f"  RPM:      {rpm:.0f} (reference: {rpm_ref:.0f})")

    if rpm_ref > 0 and rpm < rpm_ref * 0.8:
        findings.append(f"Motor speed low: {rpm:.0f} vs {rpm_ref:.0f} RPM")
        # Could be motor or driver

    # Step 6: Check Feedback Path
    print("\n[STEP 6] Checking Feedback Signal Path...")
    pickup_raw = bench.probe('pickup_raw')
    pickup_amp = bench.probe('pickup_amplified')
    feedback = bench.probe('feedback_digital')
    print(f"  Pickup Raw:    {pickup_raw*1000:.2f}mV")
    print(f"  Amplified:     {pickup_amp:.2f}V")
    print(f"  Digital Out:   {feedback:.0f}V")

    # Capture feedback waveform for noise analysis
    fb_wave = bench.capture_waveform('pickup_amplified', 0.1)
    ref_fb_wave = reference.get('waveform_feedback')
    ref_noise = ref_fb_wave.v_ac_rms if ref_fb_wave else 10.0
    print(f"  Signal Noise:  {fb_wave.v_ac_rms:.3f}V RMS (reference: {ref_noise:.3f}V)")

    # Check for op-amp producing voltages OUTSIDE expected supply rails
    # A healthy op-amp saturates at ±12V; a faulty one may produce out-of-range values
    # Use waveform min/max to catch intermittent excursions
    supply_rails = 12.0  # ±12V typical for op-amp
    waveform_exceeds_rails = (abs(fb_wave.v_min) > supply_rails * 1.05 or
                               abs(fb_wave.v_max) > supply_rails * 1.05)
    if waveform_exceeds_rails:
        worst_val = fb_wave.v_min if abs(fb_wave.v_min) > abs(fb_wave.v_max) else fb_wave.v_max
        print(f"  ** WARNING: Waveform peak {worst_val:.2f}V exceeds supply rails (±{supply_rails}V) **")
        findings.append(f"Op-amp output exceeds rails: {worst_val:.2f}V (expected ±{supply_rails}V)")
        suspects.append("Signal conditioner op-amp")
        suspects.append("Signal conditioner op-amp")
        suspects.append("Signal conditioner op-amp")  # Strong indicator

    # Check for excessive noise RELATIVE to reference (key for noisy op-amp detection)
    noise_ratio = fb_wave.v_ac_rms / ref_noise if ref_noise > 0 else 1.0
    if noise_ratio > 1.5:
        findings.append(f"Elevated noise on feedback: {fb_wave.v_ac_rms:.3f}V vs {ref_noise:.3f}V reference ({noise_ratio:.1f}x)")
        suspects.append("Signal conditioner op-amp")
        suspects.append("Signal conditioner op-amp")  # Double weight for clear symptom

    # Apply causal reasoning to refine diagnosis
    # Key insight: downstream effects shouldn't override upstream root causes
    low_motor = any("Low motor voltage" in f for f in findings)
    high_ripple = any("loop filter ripple" in f for f in findings)
    elevated_noise = any("Elevated noise" in f for f in findings)
    opamp_rail_exceeded = any("exceeds rails" in f for f in findings) or waveform_exceeds_rails

    # Check ripple severity - very high ripple is a capacitor issue
    very_high_ripple = False
    if ref_wave and lf_wave.v_ac_rms > ref_wave.v_ac_rms * 100:
        very_high_ripple = True  # 100x+ ripple = definite capacitor problem

    # If motor voltage is low, loop filter ripple is a SECONDARY effect
    # The transistor failing causes PLL to push harder, causing ripple
    if low_motor and high_ripple:
        # Boost transistor weight, reduce capacitor weight
        suspects.append("H-bridge transistor (Q1-Q4)")
        suspects.append("H-bridge transistor (Q1-Q4)")
        # Remove some capacitor suspects (it's not the root cause)
        for _ in range(2):
            if "Loop filter capacitor (C1)" in suspects:
                suspects.remove("Loop filter capacitor (C1)")

    # If op-amp output exceeds rails, it's definitely the op-amp regardless of ripple
    if opamp_rail_exceeded:
        suspects.append("Signal conditioner op-amp")
        suspects.append("Signal conditioner op-amp")
        # Reduce capacitor weight - the op-amp is the root cause
        for _ in range(3):
            if "Loop filter capacitor (C1)" in suspects:
                suspects.remove("Loop filter capacitor (C1)")
    # If ripple is VERY high and motor voltage is normal and op-amp is OK, capacitor is the issue
    elif very_high_ripple and not low_motor and not opamp_rail_exceeded:
        suspects.append("Loop filter capacitor (C1)")
        suspects.append("Loop filter capacitor (C1)")
        # Reduce op-amp weight since the noise is from loop filter instability
        for _ in range(2):
            if "Signal conditioner op-amp" in suspects:
                suspects.remove("Signal conditioner op-amp")
    # If noise is elevated but ripple is NOT very high and motor is normal, op-amp is the issue
    elif elevated_noise and not low_motor and not very_high_ripple:
        motor_v_deviation = abs(motor_v - motor_v_ref) / motor_v_ref if motor_v_ref > 0 else 0
        if motor_v_deviation < 0.15:  # Motor voltage within 15% of reference
            suspects.append("Signal conditioner op-amp")
            suspects.append("Signal conditioner op-amp")

    # Summary
    print("\n" + "=" * 60)
    print("  DIAGNOSIS SUMMARY")
    print("=" * 60)

    if findings:
        print("\nFINDINGS:")
        for i, finding in enumerate(findings, 1):
            print(f"  {i}. {finding}")

        print("\nSUSPECT COMPONENTS:")
        unique_suspects = list(set(suspects))
        for suspect in unique_suspects:
            count = suspects.count(suspect)
            confidence = min(100, count * 40)
            print(f"  - {suspect} (confidence: {confidence}%)")

        # Primary diagnosis
        if unique_suspects:
            primary = max(set(suspects), key=suspects.count)
            print(f"\n>>> PRIMARY DIAGNOSIS: {primary}")
    else:
        print("\nNo significant anomalies detected.")
        print("Circuit appears to be functioning normally.")

    return findings, suspects


def main():
    print("#" * 60)
    print("#  AEROTONE CIRCUIT DIAGNOSIS DEMO")
    print("#  Using Virtual Test Equipment")
    print("#" * 60)

    # Create reference from healthy circuit
    print("\n[SETUP] Creating reference measurements from healthy circuit...")
    healthy = create_healthy_voice()
    reference = capture_reference_measurements(healthy)
    print("  Reference captured.")

    # Test each fault type
    faults = [
        ("leaky_cap", "Leaky Loop Filter Capacitor"),
        ("burned_transistor", "Burned H-Bridge Transistor"),
        ("noisy_opamp", "Noisy Op-Amp in Signal Conditioner"),
    ]

    for fault_type, fault_name in faults:
        print("\n" + "#" * 60)
        print(f"#  INJECTING FAULT: {fault_name}")
        print("#" * 60)

        faulty = create_faulty_voice(fault_type)
        findings, suspects = diagnose_circuit(faulty, reference)

        print("\n" + "-" * 60)
        input("Press Enter to continue to next fault...")

    print("\n" + "=" * 60)
    print("  DEMO COMPLETE")
    print("=" * 60)
    print("""
This demonstrates how systematic probing can identify faults:

1. LEAKY CAPACITOR
   - Detected by: Loop filter ripple/instability
   - Key measurement: Excessive AC on loop filter output

2. BURNED TRANSISTOR
   - Detected by: Low motor voltage despite normal control
   - Key measurement: Motor voltage < expected

3. NOISY OP-AMP
   - Detected by: Excessive noise on feedback signal
   - Key measurement: High AC RMS on amplified signal

An LLM given access to these probe points could follow
the same diagnostic procedure to isolate faults!
""")


if __name__ == '__main__':
    main()
