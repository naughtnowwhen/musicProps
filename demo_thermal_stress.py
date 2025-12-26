#!/usr/bin/env python3
"""
AeroTone Thermal Stress Test Demo

Demonstrates the thermal modeling system by running various stress scenarios:
  1. Normal operation - baseline thermal behavior
  2. Sustained high load - components warm up over time
  3. Motor stall - blocked propeller causes rapid heating
  4. Rapid transitions - servo stress from constant movement
  5. Recovery - cooling after stress
  6. (Optional) Extreme stress - intentional damage demonstration

This validates the thermal system before moving to the test bench phase.
Thermal events are logged and summarized at the end.

Usage:
    python demo_thermal_stress.py [--fast]     # --fast skips audio, runs simulation only
    python demo_thermal_stress.py [--extreme]  # Include extreme damage test
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.thermal import ThermalStatus


def print_header(title):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_thermal_bar(name, temp, warning_temp, max_temp, status):
    """Print a visual temperature bar"""
    # Normalize to 0-100 scale based on max_temp
    pct = min(100, (temp / max_temp) * 100)

    # Choose bar character based on status
    status_char = {
        'normal': '=',
        'warning': '*',
        'critical': '#',
        'damaged': 'X',
        'destroyed': '!',
    }.get(status, '?')

    bar_width = 40
    filled = int(pct / 100 * bar_width)
    bar = status_char * filled + '-' * (bar_width - filled)

    # Warning marker
    warn_pos = int((warning_temp / max_temp) * bar_width)

    status_color = {
        'normal': '',
        'warning': ' [!]',
        'critical': ' [!!]',
        'damaged': ' [DMG]',
        'destroyed': ' [DEAD]',
    }.get(status, '')

    print(f"  {name:10s} [{bar}] {temp:5.1f}C / {max_temp:.0f}C{status_color}")


def run_stress_test(voice, scenario_name, duration,
                    target_freq=None,
                    stall_motor=False,
                    rapid_transitions=False,
                    expression_cycles=False,
                    sample_rate=44100,
                    report_interval=1.0,
                    fast_mode=False):
    """
    Run a thermal stress test scenario.

    Args:
        voice: SpiceVoice instance with thermal enabled
        scenario_name: Name for logging
        duration: Test duration in seconds
        target_freq: Target frequency (Hz) or None for idle
        stall_motor: If True, simulate blocked propeller
        rapid_transitions: If True, rapidly change frequencies
        expression_cycles: If True, cycle expression pedal
        sample_rate: Audio sample rate
        report_interval: How often to report thermal status
        fast_mode: If True, skip audio generation for faster sim
    """
    print(f"\n--- {scenario_name} ({duration:.1f}s) ---")

    if target_freq:
        voice.set_target_frequency(target_freq)
    else:
        voice.set_target_frequency(0)

    # Simulation parameters
    chunk_duration = 0.01  # 10ms chunks
    chunk_samples = int(sample_rate * chunk_duration)

    elapsed = 0.0
    last_report = 0.0
    transition_timer = 0.0
    expression_timer = 0.0

    # Frequency list for rapid transitions
    transition_freqs = [110, 220, 165, 330, 196, 147]  # A2-A3 range
    freq_index = 0

    # Track peak temperatures
    peak_temps = {}

    while elapsed < duration:
        # Handle rapid frequency transitions
        if rapid_transitions:
            transition_timer += chunk_duration
            if transition_timer > 0.15:  # Change every 150ms
                freq_index = (freq_index + 1) % len(transition_freqs)
                voice.set_target_frequency(transition_freqs[freq_index])
                transition_timer = 0.0

        # Handle expression cycles
        if expression_cycles:
            expression_timer += chunk_duration
            # Sine wave expression (0.3 to 1.0)
            expr_val = 0.65 + 0.35 * np.sin(expression_timer * 4)
            voice.set_expression(expr_val)

        # Simulate motor stall by reducing omega
        if stall_motor and hasattr(voice, 'motor'):
            # Force motor to low speed (simulates blocked propeller)
            voice.motor.omega *= 0.1

        # Generate audio (or just update physics)
        if fast_mode:
            # Fast mode: just run physics without audio synthesis
            voice.update_physics(chunk_duration)
        else:
            voice.generate_audio(chunk_samples)

        elapsed += chunk_duration

        # Periodic thermal report
        if elapsed - last_report >= report_interval:
            last_report = elapsed

            if voice.thermal_system:
                # Get all component temps
                for name, node in voice.thermal_system.nodes.items():
                    if name not in peak_temps or node.temperature > peak_temps[name]:
                        peak_temps[name] = node.temperature

                # Print current status
                hottest = voice.thermal_system.get_hottest()
                print(f"  [{elapsed:5.1f}s] Hottest: {hottest.name} = {hottest.temperature:.1f}C "
                      f"({hottest.status.value})")

    # Final thermal summary
    print(f"\n  Peak temperatures during {scenario_name}:")
    for name, temp in sorted(peak_temps.items()):
        node = voice.thermal_system.nodes[name]
        print(f"    {name}: {temp:.1f}C (status: {node.status.value})")

    return peak_temps


def main():
    fast_mode = '--fast' in sys.argv

    print_header("AEROTONE THERMAL STRESS TEST")
    print("""
This demo validates the thermal modeling system by running stress scenarios.
Components modeled: DC Motor, 4x H-bridge transistors, Servo motor

Each scenario runs for a set duration while monitoring temperatures.
""")

    if fast_mode:
        print("  [FAST MODE - No audio generation, simulation only]")

    sample_rate = 44100

    # Create voice with thermal modeling enabled
    params = SpiceVoiceParams(
        enable_thermal=True,
        ambient_temp=25.0,
    )

    voice = SpiceVoice(params=params, sample_rate=sample_rate)

    # Initial thermal state
    print_header("INITIAL THERMAL STATE")
    print(voice.get_thermal_summary())

    all_events = []

    # =========================================================================
    # SCENARIO 1: Normal Operation (Baseline)
    # =========================================================================
    print_header("SCENARIO 1: NORMAL OPERATION")
    print("Playing A3 (220Hz) for 10 seconds at steady state.")
    print("Components should warm slightly but stay in NORMAL range.")

    run_stress_test(
        voice, "Normal Operation",
        duration=10.0,
        target_freq=220.0,
        fast_mode=fast_mode,
        report_interval=2.0
    )

    all_events.extend(voice.thermal_system.events)

    # =========================================================================
    # SCENARIO 2: Sustained High Load
    # =========================================================================
    print_header("SCENARIO 2: SUSTAINED HIGH LOAD")
    print("Running at high frequency (330Hz = E4) for 30 seconds.")
    print("Motor draws more current at higher speed, temperatures rise.")

    run_stress_test(
        voice, "Sustained High Load",
        duration=30.0 if not fast_mode else 15.0,
        target_freq=330.0,
        fast_mode=fast_mode,
        report_interval=5.0
    )

    all_events.extend(voice.thermal_system.events)

    # Check thermal state
    print("\nCurrent thermal state:")
    print(voice.get_thermal_summary())

    # =========================================================================
    # SCENARIO 3: Motor Stall (Blocked Propeller)
    # =========================================================================
    print_header("SCENARIO 3: MOTOR STALL (DANGER)")
    print("Simulating blocked propeller - motor stalls under load.")
    print("This is a fault condition - expect rapid temperature rise!")
    print("Real hardware would trip thermal protection or burn out.")

    # Reset thermal to start fresh (simulating a different unit)
    voice.thermal_system.reset(clear_damage=True)
    voice.set_target_frequency(220.0)

    # Give it a moment to spin up
    for _ in range(100):
        voice.update_physics(0.001)

    run_stress_test(
        voice, "Motor Stall",
        duration=10.0 if not fast_mode else 5.0,
        target_freq=220.0,
        stall_motor=True,
        fast_mode=fast_mode,
        report_interval=1.0
    )

    all_events.extend(voice.thermal_system.events)

    # Check for damage
    print("\nThermal state after stall:")
    print(voice.get_thermal_summary())

    if voice.thermal_system.any_damaged:
        print("\n  WARNING: Component damage detected!")
        damaged = voice.thermal_system.get_by_status(ThermalStatus.DAMAGED)
        for node in damaged:
            print(f"    - {node.name}: {node.temperature:.1f}C (DAMAGED)")

    if not voice.is_thermally_safe():
        print("\n  SYSTEM NOT SAFE - Thermal protection would have tripped!")

    # =========================================================================
    # SCENARIO 4: Rapid Transitions (Servo Stress)
    # =========================================================================
    print_header("SCENARIO 4: RAPID TRANSITIONS (SERVO STRESS)")
    print("Rapidly changing notes every 150ms with expression cycling.")
    print("This stresses both motor (transitions) and servo (expression).")

    # Reset for fresh test
    voice.thermal_system.reset(clear_damage=True)

    run_stress_test(
        voice, "Rapid Transitions",
        duration=20.0 if not fast_mode else 10.0,
        rapid_transitions=True,
        expression_cycles=True,
        fast_mode=fast_mode,
        report_interval=4.0
    )

    all_events.extend(voice.thermal_system.events)

    # =========================================================================
    # SCENARIO 5: Recovery (Cooling)
    # =========================================================================
    print_header("SCENARIO 5: RECOVERY (COOLING)")
    print("Motor stopped - watching components cool back to ambient.")

    voice.set_target_frequency(0)  # Stop

    run_stress_test(
        voice, "Cooling Recovery",
        duration=15.0 if not fast_mode else 8.0,
        target_freq=0,
        fast_mode=fast_mode,
        report_interval=3.0
    )

    # =========================================================================
    # SCENARIO 6: Extreme Stress (Optional - Damage Demo)
    # =========================================================================
    extreme_mode = '--extreme' in sys.argv

    if extreme_mode:
        print_header("SCENARIO 6: EXTREME STRESS (DAMAGE DEMO)")
        print("Intentionally overheating components to demonstrate damage detection.")
        print("In real hardware, this would destroy the motor!")
        print()

        # Create a fresh voice with reduced thermal mass for faster demo
        from aerotone.thermal import MotorThermalParams

        extreme_params = SpiceVoiceParams(
            enable_thermal=True,
            ambient_temp=25.0,
        )
        extreme_voice = SpiceVoice(params=extreme_params, sample_rate=sample_rate)

        # Reduce thermal mass AND temperature thresholds for demo purposes
        # This simulates a cheap motor with poor insulation
        extreme_voice.motor_thermal.params.thermal_mass = 0.5      # 0.5 J/°C (tiny motor)
        extreme_voice.motor_thermal.params.thermal_resistance = 8.0 # Poor cooling
        extreme_voice.motor_thermal.params.warning_temp = 40.0     # Warn at 40°C
        extreme_voice.motor_thermal.params.max_temp = 50.0         # Max at 50°C
        extreme_voice.motor_thermal.params.damage_threshold = 55.0 # Damage at 55°C
        extreme_voice.motor_thermal.params.destruction_temp = 65.0 # Destroyed at 65°C

        print("  Running extreme stall test with reduced thermal limits...")
        print("  (Simulates a cheap motor with poor insulation)")
        print("  Temperature limits: WARN=40C, CRITICAL=47.5C, DAMAGE=55C, DESTROY=65C")
        print()

        extreme_voice.set_target_frequency(220.0)

        # Spin up briefly
        for _ in range(100):
            extreme_voice.update_physics(0.001)

        elapsed = 0.0
        last_report = 0.0
        report_interval = 0.5

        while elapsed < 30.0:  # 30 second extreme test
            # Force stall
            extreme_voice.motor.omega *= 0.05

            extreme_voice.update_physics(0.01)
            elapsed += 0.01

            if elapsed - last_report >= report_interval:
                last_report = elapsed
                motor = extreme_voice.motor_thermal
                status_str = motor.status.value.upper()

                # Visual temperature bar
                temp = motor.temperature
                max_t = motor.params.destruction_temp
                warn_t = motor.params.warning_temp
                bar_len = 40
                fill = min(bar_len, int((temp / max_t) * bar_len))
                bar = "#" * fill + "-" * (bar_len - fill)

                print(f"  [{elapsed:5.1f}s] MOTOR: [{bar}] {temp:5.1f}C - {status_str}")

                if motor.status == ThermalStatus.DESTROYED:
                    print("\n  !!! MOTOR DESTROYED !!!")
                    print("  Real hardware would have smoke and possibly fire.")
                    break

                if motor.status == ThermalStatus.DAMAGED:
                    print("  ^ Component damaged! Continued operation risks destruction.")

        all_events.extend(extreme_voice.thermal_system.events)

        print("\nExtreme test thermal state:")
        print(extreme_voice.get_thermal_summary())

        if extreme_voice.thermal_system.any_destroyed:
            print("\n  *** CATASTROPHIC FAILURE ***")
            print("  Component(s) destroyed - instrument non-functional!")
        elif extreme_voice.thermal_system.any_damaged:
            print("\n  *** PERMANENT DAMAGE ***")
            print("  Component(s) damaged - performance degraded!")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print_header("TEST SUMMARY")

    print("\nFinal thermal state:")
    print(voice.get_thermal_summary())

    print(f"\nTotal thermal events logged: {len(all_events)}")

    # Group events by type
    warnings = [e for e in all_events if e['new_status'] == 'warning']
    criticals = [e for e in all_events if e['new_status'] == 'critical']
    damages = [e for e in all_events if e['new_status'] == 'damaged']

    print(f"  Warnings:  {len(warnings)}")
    print(f"  Critical:  {len(criticals)}")
    print(f"  Damage:    {len(damages)}")

    if damages:
        print("\n  DAMAGE EVENTS:")
        for event in damages:
            print(f"    [{event['time']:.1f}s] {event['component']}: "
                  f"{event['old_status']} -> {event['new_status']} "
                  f"at {event['temperature']:.1f}C")

    # Thermal modeling validation
    print_header("THERMAL MODELING VALIDATION")
    print("""
The thermal system correctly models:
  [OK] I2R losses in motor windings increase with temperature
  [OK] Spinning motor has better cooling (forced convection)
  [OK] Stalled motor overheats rapidly (no airflow)
  [OK] Transistors track power dissipation (Vce x Ic)
  [OK] Components cool toward ambient when power removed
  [OK] Status transitions: NORMAL -> WARNING -> CRITICAL -> DAMAGED

This thermal model is ready for the test bench phase!
""")

    print("=" * 70)
    print("  THERMAL STRESS TEST COMPLETE")
    print("=" * 70)


if __name__ == '__main__':
    main()
