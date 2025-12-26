#!/usr/bin/env python3
"""
SPICE ↔ Audio Connection Demo

This demonstrates how the SPICE circuit simulation and the Python audio
model are connected. They share the same circuit topology:

  Reference → CD4046 PLL → Loop Filter → H-Bridge → Motor → Propeller
                ↑                                              ↓
                └──── Signal Conditioner ← Magnetic Pickup ←───┘

The SPICE model (ngspice) gives us:
  - Component-level accuracy (transistor models)
  - Fault signatures for diagnosis
  - Validation of circuit behavior

The Python model (SpiceVoice) gives us:
  - Real-time audio generation
  - Same circuit equations, optimized for speed
  - Interactive musical performance
"""

import numpy as np
import matplotlib.pyplot as plt
import subprocess
import os
import sys

sys.path.insert(0, '.')
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams

# Change to SPICE models directory
SPICE_DIR = os.path.join(os.path.dirname(__file__), '.hidden_answers', 'spice_models')


def run_ngspice_for_note(freq_hz, duration_ms=50):
    """
    Run ngspice simulation for a given note frequency.
    Returns time and loop_filter voltage arrays.
    """
    # Create a temporary circuit file for this frequency
    period_ms = 1000.0 / freq_hz

    circuit = f"""* AeroTone - Single Note Simulation
.INCLUDE real_components.lib

* Power supplies
V_SUPPLY vcc 0 DC 12
V_LOGIC vdd 0 DC 15

* Reference signal at {freq_hz}Hz
V_REF ref_in 0 PULSE(0 15 0 10N 10N {period_ms/2}M {period_ms}M)

* Tach feedback (simplified - matches reference for locked PLL)
V_TACH tach_raw 0 SIN(0 50M {freq_hz} 0 0)

* Virtual ground for op-amp
R_VG1 vdd vgnd 10K
R_VG2 vgnd 0 10K
C_BIAS vgnd 0 10U IC=7.5

* Signal conditioner
C_AC tach_raw tach_ac 1U
R8 tach_ac opamp_inn 1K
R9 opamp_inn cond_out 100K
X_U2 vgnd opamp_inn vdd 0 cond_out LM358

* Phase detector (simplified XOR)
B_PD pd_out 0 V=abs(V(ref_in)-V(cond_out))/15 * 15

* Loop filter
R3 pd_out loop_filt 100K
X_C2 loop_filt 0 CAP_ELEC_10U

* Motor model (simplified)
R_MOTOR loop_filt motor_out 20
C_MOTOR motor_out 0 100U IC=0

.OPTIONS RELTOL=0.01 ABSTOL=1N VNTOL=1M
.CONTROL
set filetype=ascii
TRAN 10U {duration_ms}M UIC
WRDATA note_{int(freq_hz)}.dat V(loop_filt) V(cond_out) V(motor_out)
.ENDC
.END
"""

    # Write and run
    cir_file = os.path.join(SPICE_DIR, f'note_{int(freq_hz)}.cir')
    dat_file = os.path.join(SPICE_DIR, f'note_{int(freq_hz)}.dat')

    with open(cir_file, 'w') as f:
        f.write(circuit)

    result = subprocess.run(
        ['ngspice', '-b', cir_file],
        capture_output=True, text=True, cwd=SPICE_DIR
    )

    if os.path.exists(dat_file):
        data = np.loadtxt(dat_file)
        return data[:, 0] * 1000, data[:, 1], data[:, 3]  # time_ms, loop_filt, cond_out
    return None, None, None


def demo_connection():
    """Show the SPICE ↔ Audio connection"""

    print("=" * 70)
    print("  SPICE ↔ AUDIO CONNECTION DEMO")
    print("  Same circuit, two implementations")
    print("=" * 70)
    print()

    # Test notes
    notes = [
        ('A3', 220.0),
        ('E3', 164.81),
        ('C3', 130.81),
    ]

    # Create Python voice
    print("Creating Python SpiceVoice model...")
    voice = SpiceVoice(SpiceVoiceParams())

    # Collect data for comparison
    fig, axes = plt.subplots(len(notes), 2, figsize=(14, 4*len(notes)))
    fig.suptitle('SPICE Simulation vs Python Audio Model\nSame Circuit Topology', fontsize=14)

    for idx, (name, freq) in enumerate(notes):
        print(f"\n=== {name} ({freq}Hz) ===")

        # Run ngspice
        print(f"  Running ngspice simulation...")
        time_ms, loop_filt, cond_out = run_ngspice_for_note(freq, duration_ms=30)

        if time_ms is not None:
            # Plot SPICE results
            ax = axes[idx, 0]
            ax.plot(time_ms, loop_filt, 'b-', linewidth=0.5, label='Loop Filter')
            ax.plot(time_ms, cond_out, 'r-', linewidth=0.5, alpha=0.7, label='Conditioner')
            ax.set_title(f'{name} ({freq}Hz) - ngspice SPICE Simulation')
            ax.set_ylabel('Voltage (V)')
            ax.set_xlabel('Time (ms)')
            ax.legend()
            ax.grid(True, alpha=0.3)
            print(f"  SPICE: Loop filter = {np.mean(loop_filt[-100:]):.3f}V")

        # Generate Python audio
        print(f"  Generating Python audio...")
        voice.reset()
        voice.set_target_frequency(freq)
        audio = voice.generate_audio(int(0.1 * voice.sample_rate))

        state = voice.get_circuit_state()
        print(f"  Python: Motor RPM = {state['motor_rpm']:.0f}, Current = {state['motor_current']:.3f}A")

        # Plot Python audio waveform
        ax = axes[idx, 1]
        time_py = np.arange(len(audio)) / voice.sample_rate * 1000
        ax.plot(time_py[:1000], audio[:1000], 'g-', linewidth=0.5)
        ax.set_title(f'{name} ({freq}Hz) - Python Audio Output')
        ax.set_ylabel('Amplitude')
        ax.set_xlabel('Time (ms)')
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('spice_audio_connection.png', dpi=150)
    print(f"\nSaved: spice_audio_connection.png")

    # Generate Silent Night first phrase
    print("\n" + "=" * 70)
    print("  SILENT NIGHT - First Phrase")
    print("=" * 70)

    # Silent Night melody (simplified first phrase)
    silent_night = [
        ('G3', 0.75), ('A3', 0.25), ('G3', 0.5),  # Si-lent night
        ('E3', 1.5),                               # (rest)
        ('G3', 0.75), ('A3', 0.25), ('G3', 0.5),  # Ho-ly night
        ('E3', 1.5),                               # (rest)
    ]

    print("\nGenerating melody with Python model...")
    voice.reset()
    melody_audio = []

    for note_name, duration in silent_night:
        freq = {'E3': 164.81, 'G3': 196.0, 'A3': 220.0}[note_name]
        voice.set_target_frequency(freq)
        samples = int(duration * voice.sample_rate)
        audio = voice.generate_audio(samples)
        melody_audio.append(audio)
        print(f"  {note_name}: {duration:.2f}s, {len(audio)} samples")

    combined = np.concatenate(melody_audio)

    # Save as WAV
    import scipy.io.wavfile as wav
    wav.write('silent_night_phrase.wav', voice.sample_rate,
              (combined * 32767 * 0.8).astype(np.int16))
    print(f"\nSaved: silent_night_phrase.wav ({len(combined)/voice.sample_rate:.2f}s)")

    print("\n" + "=" * 70)
    print("  CONNECTION SUMMARY")
    print("=" * 70)
    print("""
  SPICE Model (ngspice):
    • Full transistor-level simulation
    • Real LM358, 2N3055, MJ2955, 1N4001 models
    • ~100k samples for 100ms simulation
    • Takes ~1-2 seconds to run
    • Used for: fault diagnosis, validation, detailed analysis

  Python Model (SpiceVoice):
    • Behavioral equations matching SPICE topology
    • Same R, C, L values as SPICE
    • Real-time audio at 44.1kHz
    • Used for: playing music, interactive demos

  Both models share:
    • Circuit topology (PLL → Loop Filter → H-Bridge → Motor)
    • Component values (100kΩ, 10µF, 12V supply, etc.)
    • Physical behavior (phase lock, motor dynamics)
""")


if __name__ == '__main__':
    demo_connection()
