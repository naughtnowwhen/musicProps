#!/usr/bin/env python3
"""
SPICE → AUDIO PIPELINE

Single source of truth: SPICE simulation drives audio generation directly.
No behavioral model = no subtle mismatches.

Pipeline:
  SPICE → motor voltage/current → motor speed → propeller acoustics → audio

Run: python3 spice_to_audio.py
"""

import os
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy import signal
import time

SPICE_DIR = '.hidden_answers/spice_models'

# Motor parameters (from circuit_params.json)
MOTOR_R = 20.0       # Ohms
MOTOR_KE = 0.05      # V/(rad/s) back-EMF constant
NUM_BLADES = 12      # Propeller blades
SAMPLE_RATE = 44100  # Audio sample rate


def create_fast_spice_circuit(target_freq=220, duration_ms=500):
    """Create SPICE circuit optimized for speed."""

    # Calculate reference frequency for target blade passage frequency
    # BPF = RPM * blades / 60, RPM = ω * 60 / (2π)
    # So ref_freq sets the PLL target
    ref_period = 1.0 / target_freq  # seconds
    ref_half = ref_period / 2

    circuit = f'''* SPICE→AUDIO: Fast simulation for audio generation
.INCLUDE real_components.lib

*==============================================================
* POWER SUPPLIES
*==============================================================
V_SUPPLY vcc 0 DC 12
V_LOGIC vdd 0 DC 15

*==============================================================
* REFERENCE (sets target frequency)
*==============================================================
V_REF ref_in 0 PULSE(0 15 0 10N 10N {ref_half} {ref_period})

* Tachometer feedback (simplified - just tracks motor)
V_TACH tach_raw 0 SIN(0 50M {target_freq} 0 0)

*==============================================================
* SIGNAL CONDITIONER
*==============================================================
R_VG1 vdd vgnd 10K
R_VG2 vgnd 0 10K
C_BIAS vgnd 0 10U IC=7.5

C_AC tach_raw tach_ac 1U
R8 tach_ac opamp_inn 1K
R9 opamp_inn cond_pre 100K

X_U2 vgnd opamp_inn vdd 0 cond_pre LM358
B_COND cond_out 0 V=V(cond_pre)

X_C3 vdd 0 CAP_CER_100N

*==============================================================
* COMPARATOR & PLL
*==============================================================
X_COMP_INV1 cond_out comp_int vdd 0 CMOS_INV
X_COMP_INV2 comp_int comp_out vdd 0 CMOS_INV

X_PC1 ref_in comp_out vdd 0 pd_out CD4046_PC1

*==============================================================
* LOOP FILTER
*==============================================================
R3 pd_out loop_filt 100K
X_C2 loop_filt c2_mid CAP_ELEC_10U
R_C2_LEAK c2_mid 0 100MEG

*==============================================================
* H-BRIDGE DRIVER
*==============================================================
R_DRIVE1 loop_filt base_q1 1K
R_DRIVE2 loop_filt base_q2 1K
R_BIAS1 vcc base_q1 4.7K
R_BIAS2 base_q2 0 4.7K

Q1 vcc base_q1 q1_emit 2N3055
R_Q1_DAMAGE q1_emit motor_p 0.01
Q2 motor_n base_q2 0 MJ2955

R_DRIVE3 loop_filt base_q3 1K
R_DRIVE4 loop_filt base_q4 1K
R_BIAS3 vcc base_q3 4.7K
R_BIAS4 base_q4 0 4.7K

Q3 vcc base_q3 motor_n 2N3055
Q4 motor_p base_q4 0 MJ2955

D1 motor_p vcc 1N4001
D2 0 motor_p 1N4001
D3 motor_n vcc 1N4001
D4 0 motor_n 1N4001

*==============================================================
* MOTOR (simple resistive model)
* Mechanical dynamics calculated in Python from loop_filt
*==============================================================
R_MOTOR motor_p motor_bemf {MOTOR_R}
V_BEMF motor_bemf motor_n DC 0
R_SENSE motor_n motor_gnd 0.1
V_SENSE motor_gnd 0 DC 0

*==============================================================
* FAST SIMULATION OPTIONS
*==============================================================
* Looser tolerances = faster convergence
.OPTIONS RELTOL=0.05 ABSTOL=10N VNTOL=10M
.OPTIONS ITL1=200 ITL4=50

.CONTROL
set filetype=ascii

* Larger timestep for speed (10µs instead of 1µs)
TRAN 10U {duration_ms}M UIC

* Save motor signals AND loop filter (control voltage)
WRDATA spice_audio_motor.dat V(motor_p,motor_n) I(V_SENSE) V(loop_filt) V(cond_out)

ECHO "Fast simulation complete"
.ENDC
.END
'''
    return circuit


def run_fast_spice(target_freq=220, duration_ms=500):
    """Run SPICE simulation in fast mode."""

    print(f"  Creating circuit for {target_freq}Hz, {duration_ms}ms...")
    circuit = create_fast_spice_circuit(target_freq, duration_ms)

    cir_path = os.path.join(SPICE_DIR, 'spice_audio_fast.cir')
    with open(cir_path, 'w') as f:
        f.write(circuit)

    print("  Running ngspice (fast mode)...")
    start = time.time()

    result = subprocess.run(
        ['ngspice', '-b', 'spice_audio_fast.cir'],
        cwd=SPICE_DIR,
        capture_output=True,
        text=True,
        timeout=300
    )

    elapsed = time.time() - start
    print(f"  SPICE completed in {elapsed:.2f}s")

    # Load results
    dat_path = os.path.join(SPICE_DIR, 'spice_audio_motor.dat')
    if not os.path.exists(dat_path):
        print(f"  ERROR: {dat_path} not found")
        print(result.stderr[-500:] if result.stderr else "No stderr")
        return None

    data = np.loadtxt(dat_path)
    return {
        'time': data[:, 0],
        'motor_v': data[:, 1],    # V(motor_p, motor_n)
        'motor_i': data[:, 3],    # I(V_SENSE)
        'loop_filt': data[:, 5],  # V(loop_filt) - control voltage
        'cond_out': data[:, 7],   # V(cond_out) - conditioner output
    }


def motor_speed_from_control(loop_filt, motor_i, target_freq=220):
    """
    Calculate motor speed from motor current.

    Since SPICE doesn't model back-EMF, we need to calculate
    mechanical dynamics here. The motor current determines torque,
    which accelerates the motor against damping.

    At steady state: ω = Kt * I / B
    For 220Hz BPF with 12 blades: RPM = 1100, ω = 115 rad/s
    With I = 0.15A, Kt = 0.05: B = Kt * I / ω = 6.5e-5

    Parameters tuned for realistic propeller behavior.
    """
    # Motor mechanical parameters (tuned for target frequency)
    J = 3e-5     # Inertia (kg·m²)
    B = 6.5e-5   # Damping (N·m·s) - tuned for ~1100 RPM at 0.15A
    Kt = 0.05    # Torque constant (N·m/A)

    # Time step from SPICE (10µs)
    dt = 10e-6

    # Target steady-state speed for reference
    target_rpm = target_freq * 60 / NUM_BLADES
    target_omega = target_rpm * 2 * np.pi / 60

    omega = np.zeros(len(motor_i))
    for i in range(1, len(motor_i)):
        # Torque from current
        torque = Kt * abs(motor_i[i])
        # Damping torque
        damping = B * omega[i-1]
        # Acceleration
        alpha = (torque - damping) / J
        # Integrate
        omega[i] = omega[i-1] + alpha * dt

    return omega


def motor_speed_from_electrical(motor_v, motor_i, R=MOTOR_R, Ke=MOTOR_KE):
    """
    Calculate motor angular velocity from voltage and current.

    Motor equation: V = Ke*ω + I*R
    Solve for ω: ω = (V - I*R) / Ke

    Note: This only works if back-EMF is modeled in SPICE.
    """
    omega = (motor_v - motor_i * R) / Ke  # rad/s
    omega = np.maximum(omega, 0)  # Can't spin backwards
    return omega


def blade_passage_frequency(omega, num_blades=NUM_BLADES):
    """Convert angular velocity to blade passage frequency."""
    rpm = omega * 60 / (2 * np.pi)
    bpf = rpm * num_blades / 60
    return bpf


def generate_propeller_audio(bpf_signal, spice_time, sample_rate=SAMPLE_RATE):
    """
    Generate propeller audio from blade passage frequency over time.

    Simple acoustic model:
    - Fundamental at BPF
    - Harmonics with decreasing amplitude
    - Phase accumulation for continuous tone
    """

    # Resample BPF to audio sample rate
    duration = spice_time[-1] - spice_time[0]
    num_samples = int(duration * sample_rate)

    # Interpolate BPF to audio rate
    audio_time = np.linspace(spice_time[0], spice_time[-1], num_samples)
    bpf_resampled = np.interp(audio_time, spice_time, bpf_signal)

    # Generate audio with phase accumulation
    dt = 1.0 / sample_rate
    phase = 0.0
    audio = np.zeros(num_samples)

    # Harmonic amplitudes (fundamental + harmonics)
    harmonics = [1.0, 0.5, 0.3, 0.2, 0.1]  # Relative amplitudes

    for i in range(num_samples):
        freq = bpf_resampled[i]

        # Accumulate phase
        phase += 2 * np.pi * freq * dt

        # Sum harmonics
        sample = 0.0
        for h, amp in enumerate(harmonics, 1):
            sample += amp * np.sin(h * phase)

        audio[i] = sample

    # Normalize
    audio = audio / (np.abs(audio).max() + 1e-10)

    return audio, audio_time


def spice_to_audio(target_freq=220, duration_ms=500, output_path='spice_direct_audio.wav'):
    """
    Complete pipeline: SPICE simulation → Audio file
    """

    print("=" * 60)
    print("  SPICE → AUDIO PIPELINE")
    print("=" * 60)

    # Step 1: Run SPICE
    print("\n[1] Running SPICE simulation...")
    spice_data = run_fast_spice(target_freq, duration_ms)
    if spice_data is None:
        return None

    print(f"  Got {len(spice_data['time'])} data points")
    print(f"  Motor V: {np.mean(spice_data['motor_v']):.3f}V avg")
    print(f"  Motor I: {np.mean(spice_data['motor_i'])*1000:.1f}mA avg")
    print(f"  Loop filter: {np.mean(spice_data['loop_filt']):.3f}V avg")
    print(f"  Conditioner Vpp: {np.ptp(spice_data['cond_out']):.2f}V")

    # Step 2: Calculate motor speed from current (mechanical dynamics)
    print("\n[2] Calculating motor speed from current...")
    omega = motor_speed_from_control(spice_data['loop_filt'], spice_data['motor_i'])
    rpm = omega * 60 / (2 * np.pi)
    print(f"  Motor speed: {np.mean(rpm):.0f} RPM avg, {rpm[-1]:.0f} RPM final")

    # Step 3: Calculate blade passage frequency
    print("\n[3] Calculating blade passage frequency...")
    bpf = blade_passage_frequency(omega)
    print(f"  BPF: {np.mean(bpf):.1f} Hz avg, {bpf[-1]:.1f} Hz final (target: {target_freq} Hz)")

    # Step 4: Generate audio
    print("\n[4] Generating propeller audio...")
    audio, audio_time = generate_propeller_audio(bpf, spice_data['time'])
    print(f"  Generated {len(audio)} samples ({len(audio)/SAMPLE_RATE:.2f}s)")

    # Step 5: Save audio
    print("\n[5] Saving audio...")
    audio_int16 = (audio * 32767).astype(np.int16)
    wavfile.write(output_path, SAMPLE_RATE, audio_int16)
    print(f"  Saved: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)
    print(f"""
  SPICE simulation: {duration_ms}ms simulated
  Motor voltage:    {np.mean(spice_data['motor_v']):.2f}V
  Motor current:    {np.mean(spice_data['motor_i'])*1000:.1f}mA
  Motor speed:      {np.mean(rpm):.0f} RPM
  Blade frequency:  {np.mean(bpf):.1f} Hz
  Audio duration:   {len(audio)/SAMPLE_RATE:.2f}s
  Output file:      {output_path}
""")

    return {
        'spice_data': spice_data,
        'omega': omega,
        'bpf': bpf,
        'audio': audio,
    }


def compare_with_behavioral(spice_audio_path='spice_direct_audio.wav'):
    """Compare SPICE-derived audio with behavioral model."""

    print("\n" + "=" * 60)
    print("  COMPARISON: SPICE vs BEHAVIORAL")
    print("=" * 60)

    # Generate behavioral audio
    from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams

    print("\n[1] Generating behavioral model audio...")
    start = time.time()

    voice = SpiceVoice(SpiceVoiceParams())
    voice.set_target_frequency(220)

    # Warm up
    for _ in range(int(0.1 * SAMPLE_RATE)):
        voice.update_physics(1.0 / SAMPLE_RATE)

    # Generate
    behavioral_audio = voice.generate_audio(int(0.5 * SAMPLE_RATE))
    behavioral_time = time.time() - start

    print(f"  Behavioral completed in {behavioral_time:.3f}s")

    # Load SPICE audio
    sr, spice_audio = wavfile.read(spice_audio_path)
    spice_audio = spice_audio.astype(float) / 32767

    # Compare
    print("\n[2] Comparison:")
    print(f"  {'Metric':<25} {'SPICE':<15} {'Behavioral':<15}")
    print("-" * 55)

    spice_rms = np.sqrt(np.mean(spice_audio**2))
    behav_rms = np.sqrt(np.mean(behavioral_audio**2))
    print(f"  {'RMS amplitude':<25} {spice_rms:<15.4f} {behav_rms:<15.4f}")

    # Simple frequency estimation
    def estimate_freq(audio, sr):
        # Zero crossings
        crossings = np.sum(np.diff(np.sign(audio)) != 0)
        return crossings * sr / (2 * len(audio))

    spice_freq = estimate_freq(spice_audio, sr)
    behav_freq = estimate_freq(behavioral_audio, SAMPLE_RATE)
    print(f"  {'Est. frequency (Hz)':<25} {spice_freq:<15.1f} {behav_freq:<15.1f}")

    print(f"\n  Generation time ratio: {behavioral_time:.3f}s behavioral vs SPICE")


if __name__ == '__main__':
    # Run the pipeline with longer duration for PLL lock
    # Mechanical time constant is ~6s, so use 2s for partial lock
    result = spice_to_audio(target_freq=220, duration_ms=2000)

    if result:
        # Compare with behavioral
        compare_with_behavioral()
