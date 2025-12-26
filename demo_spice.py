#!/usr/bin/env python3
"""
AeroTone SPICE-Level Demo

This demo uses the full circuit-level simulation:
  - CD4046 PLL with real timing components
  - RC loop filter
  - H-bridge motor driver
  - Magnetic pickup feedback

You can see the actual circuit behavior: control voltage,
phase detector states, motor current, etc.
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


def main():
    note = 'A2'
    if len(sys.argv) > 1:
        note = sys.argv[1].upper()

    freq = NOTES.get(note, 110.0)

    print("\n" + "=" * 70)
    print("  AEROTONE SPICE-LEVEL SIMULATION")
    print("=" * 70)
    print(f"""
Target: {note} = {freq:.2f} Hz

Circuit Components:
  CD4046 VCO:    R1=10kΩ, C1=100nF, R2=100kΩ
  Loop Filter:   R=47kΩ, C=1µF (τ = 47ms)
  Motor Driver:  12V H-bridge, 2A limit
  Motor:         R=2Ω, L=1mH, Ke=0.01 V/(rad/s)
  Propeller:     12-blade, 100mm diameter
  Pickup:        Magnetic, 1 pulse/rev
""")

    sample_rate = 44100

    # Create SPICE-level voice with component values
    params = SpiceVoiceParams(
        # VCO timing (sets frequency range)
        vco_r1=10e3,       # 10kΩ
        vco_c1=100e-9,     # 100nF
        vco_r2=100e3,      # 100kΩ

        # Loop filter
        loop_r1=47e3,      # 47kΩ
        loop_c1=1e-6,      # 1µF

        # Motor
        motor_resistance=2.0,
        motor_ke=0.01,

        # 12-blade propeller
        prop_num_blades=12,
    )

    voice = SpiceVoice(params, sample_rate=sample_rate)
    voice.set_target_frequency(freq)

    print("Starting PLL - watch the lock acquisition...")
    print("-" * 70)
    print(f"{'Time':>6} | {'Ctrl V':>7} | {'VCO Hz':>8} | {'Motor RPM':>9} | "
          f"{'BPF Hz':>7} | {'Error':>7} | Status")
    print("-" * 70)

    # Warmup with detailed status
    warmup_steps = 3000  # 3 seconds at 1ms steps
    for i in range(warmup_steps):
        voice.update_physics(0.001)

        # Print status every 100ms
        if i % 100 == 0:
            state = voice.get_circuit_state()
            t = i / 1000
            ctrl_v = state['control_voltage']
            vco_f = state['vco_frequency']
            rpm = state['motor_rpm']
            bpf = state['prop_frequency']
            err = state['frequency_error_hz']

            if state['is_locked']:
                status = "LOCKED"
            elif state['pd_state'] == 'high':
                status = "pumping UP"
            elif state['pd_state'] == 'low':
                status = "pumping DOWN"
            else:
                status = "holding"

            print(f"{t:5.1f}s | {ctrl_v:6.2f}V | {vco_f:7.1f} | {rpm:8.1f} | "
                  f"{bpf:6.1f} | {err:+6.1f} | {status}")

    print("-" * 70)

    # Final state
    state = voice.get_circuit_state()
    print(f"""
Final State:
  Control Voltage: {state['control_voltage']:.3f} V
  VCO Frequency:   {state['vco_frequency']:.2f} Hz
  Motor RPM:       {state['motor_rpm']:.1f}
  Motor Current:   {state['motor_current']:.3f} A
  Prop BPF:        {state['prop_frequency']:.2f} Hz
  Target:          {freq:.2f} Hz
  Error:           {state['frequency_error_hz']:+.2f} Hz ({state['frequency_error_hz']/freq*100:+.2f}%)
  Locked:          {state['is_locked']}
""")

    # Generate audio
    print("Generating audio...")
    duration = 4.0
    total_samples = int(duration * sample_rate)
    chunk_size = int(0.1 * sample_rate)

    audio_chunks = []
    for i in range(0, total_samples, chunk_size):
        n = min(chunk_size, total_samples - i)
        chunk = voice.generate_audio(n)
        audio_chunks.append(chunk)

    audio = np.concatenate(audio_chunks)

    # Normalize
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.8

    print(f"Playing {len(audio)/sample_rate:.1f}s of audio...")
    sd.play(audio, sample_rate)
    sd.wait()

    print("\nDone!")
    print("\nThis was a REAL PLL simulation with actual component values.")
    print("The motor speed is controlled by the CD4046 phase-locked loop!")


if __name__ == '__main__':
    main()
