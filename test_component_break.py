#!/usr/bin/env python3
"""
SYSTEMATIC COMPONENT BREAK TESTING

Tests individual component failures in both SPICE and Python models.
Each test:
1. States hypothesis
2. Injects fault in SPICE (via parameter)
3. Injects fault in Python (via monkey-patch)
4. Compares results
5. Validates against hypothesis

Run: python3 test_component_break.py
"""

import os
import sys
import subprocess
import numpy as np
from scipy.io import wavfile

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams

SPICE_DIR = '.hidden_answers/spice_models'
OUTPUT_DIR = 'component_test_output'


def run_spice_test(test_name, param_changes):
    """Run SPICE with specific parameter changes."""

    # Create test circuit file - output goes to same directory as .cir
    cir_content = f'''* COMPONENT BREAK TEST: {test_name}
.INCLUDE real_components.lib

* Power supplies
V_SUPPLY vcc 0 DC 12
V_LOGIC vdd 0 DC 15

* Reference & tachometer
V_REF ref_in 0 PULSE(0 15 0 10N 10N 2.27M 4.545M)
V_TACH tach_raw 0 SIN(0 50M 220 0 0)

* Virtual ground
R_VG1 vdd vgnd 10K
R_VG2 vgnd 0 10K
C_BIAS vgnd 0 10U IC=7.5

* Signal conditioner
C_AC tach_raw tach_ac 1U

* R8 - INPUT RESISTOR (test point)
.PARAM R8_VAL = 1K
R8 tach_ac opamp_inn {{R8_VAL}}

* R9 - FEEDBACK RESISTOR
.PARAM R9_VAL = 100K
R9 opamp_inn cond_pre {{R9_VAL}}

* Op-amp
X_U2 vgnd opamp_inn vdd 0 cond_pre LM358
B_COND cond_out 0 V=V(cond_pre)

X_C3 vdd 0 CAP_CER_100N

* Comparator
X_COMP_INV1 cond_out comp_int vdd 0 CMOS_INV
X_COMP_INV2 comp_int comp_out vdd 0 CMOS_INV

* Phase detector
X_PC1 ref_in comp_out vdd 0 pd_out CD4046_PC1

* Loop filter
.PARAM R3_VAL = 100K
R3 pd_out loop_filt {{R3_VAL}}
X_C2 loop_filt c2_mid CAP_ELEC_10U
R_C2_LEAK c2_mid 0 100MEG

* H-bridge
R_DRIVE1 loop_filt base_q1 1K
R_DRIVE2 loop_filt base_q2 1K

.PARAM R_BIAS1_VAL = 4.7K
R_BIAS1 vcc base_q1 {{R_BIAS1_VAL}}
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

* Flyback diodes
D1 motor_p vcc 1N4001
D2 0 motor_p 1N4001
D3 motor_n vcc 1N4001
D4 0 motor_n 1N4001

* Motor
R_MOTOR motor_p motor_bemf 20
V_BEMF motor_bemf motor_n DC 0
R_SENSE motor_n motor_gnd 0.1
V_SENSE motor_gnd 0 DC 0

.OPTIONS RELTOL=0.01 ABSTOL=1N VNTOL=1M ITL1=500 ITL4=100

.CONTROL
set filetype=ascii

* Apply parameter changes
{param_changes}

reset
TRAN 1U 100M UIC
WRDATA {test_name}.dat V(loop_filt) V(motor_p,motor_n) I(V_SENSE) V(cond_out) V(cond_pre) V(opamp_inn) V(vgnd) V(tach_ac)

ECHO "{test_name} complete"
.ENDC
.END
'''

    cir_path = os.path.abspath(os.path.join(SPICE_DIR, f'{test_name}.cir'))
    with open(cir_path, 'w') as f:
        f.write(cir_content)

    # Run ngspice from SPICE_DIR so include paths work
    result = subprocess.run(
        ['ngspice', '-b', os.path.basename(cir_path)],
        cwd=os.path.dirname(cir_path),
        capture_output=True,
        text=True,
        timeout=120
    )

    # Load results - file is written to cwd of ngspice (SPICE_DIR)
    dat_path = os.path.join(os.path.dirname(cir_path), f'{test_name}.dat')
    if os.path.exists(dat_path):
        data = np.loadtxt(dat_path)
        steady = int(len(data) * 0.8)
        return {
            'loop_filt': data[steady:, 1],
            'motor_v': data[steady:, 3],
            'motor_i': data[steady:, 5],
            'cond_out': data[steady:, 7],
            'cond_pre': data[steady:, 9],
            'opamp_inn': data[steady:, 11],
            'vgnd': data[steady:, 13],
            'tach_ac': data[steady:, 15] if data.shape[1] > 15 else None,
        }
    return None


def run_python_test(fault_injection_func, duration=0.5, sample_rate=44100):
    """Run Python behavioral model with fault injection."""
    voice = SpiceVoice(SpiceVoiceParams())
    voice.set_target_frequency(220)

    # Apply fault injection
    if fault_injection_func:
        fault_injection_func(voice)

    # Warm up
    for _ in range(int(0.2 * sample_rate)):
        voice.update_physics(1.0 / sample_rate)

    # Record state samples
    num_samples = int(duration * sample_rate)
    sample_interval = 100
    num_state = num_samples // sample_interval

    loop_filt = np.zeros(num_state)
    motor_v = np.zeros(num_state)
    cond_out = np.zeros(num_state)

    for i in range(num_state):
        for _ in range(sample_interval):
            voice.update_physics(1.0 / sample_rate)
        state = voice.get_circuit_state()
        loop_filt[i] = state.get('control_voltage', 0)
        motor_v[i] = state.get('motor_voltage', 0)
        cond_out[i] = state.get('conditioner_output', 0)

    # Generate audio
    audio = voice.generate_audio(num_samples)

    return {
        'loop_filt': loop_filt,
        'motor_v': motor_v,
        'cond_out': cond_out,
        'audio': audio,
        'state': voice.get_circuit_state(),
    }


def analyze_results(name, hypothesis, spice_healthy, spice_faulty, python_healthy, python_faulty):
    """Analyze and report results."""
    print(f"\n{'='*70}")
    print(f"  COMPONENT TEST: {name}")
    print(f"{'='*70}")

    print(f"\n[HYPOTHESIS]")
    print(hypothesis)

    print(f"\n[SPICE RESULTS]")
    print("-" * 50)

    # SPICE comparisons
    h_loop = np.mean(spice_healthy['loop_filt'])
    f_loop = np.mean(spice_faulty['loop_filt'])
    h_cond_dc = np.mean(spice_healthy['cond_out'])
    f_cond_dc = np.mean(spice_faulty['cond_out'])
    h_cond_vpp = np.ptp(spice_healthy['cond_out'])
    f_cond_vpp = np.ptp(spice_faulty['cond_out'])
    h_motor = np.mean(spice_healthy['motor_v'])
    f_motor = np.mean(spice_faulty['motor_v'])

    print(f"  Loop filter:  {h_loop:.3f}V → {f_loop:.3f}V (Δ{f_loop-h_loop:+.3f}V)")
    print(f"  Cond DC:      {h_cond_dc:.3f}V → {f_cond_dc:.3f}V (Δ{f_cond_dc-h_cond_dc:+.3f}V)")
    print(f"  Cond Vpp:     {h_cond_vpp:.3f}V → {f_cond_vpp:.3f}V (Δ{f_cond_vpp-h_cond_vpp:+.3f}V)")
    print(f"  Motor V:      {h_motor:.3f}V → {f_motor:.3f}V (Δ{f_motor-h_motor:+.3f}V)")

    print(f"\n[PYTHON RESULTS]")
    print("-" * 50)

    # Python comparisons
    h_rpm = python_healthy['state'].get('motor_rpm', 0)
    f_rpm = python_faulty['state'].get('motor_rpm', 0)
    h_amp = np.sqrt(np.mean(python_healthy['audio']**2))
    f_amp = np.sqrt(np.mean(python_faulty['audio']**2))

    print(f"  Motor RPM:    {h_rpm:.0f} → {f_rpm:.0f} (Δ{f_rpm-h_rpm:+.0f})")
    print(f"  Audio RMS:    {h_amp:.4f} → {f_amp:.4f} ({f_amp/h_amp*100:.0f}%)")

    # Save audio
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio_path = os.path.join(OUTPUT_DIR, f'{name}_faulty.wav')
    audio_norm = python_faulty['audio'] / (np.abs(python_faulty['audio']).max() + 1e-10)
    wavfile.write(audio_path, 44100, (audio_norm * 32767).astype(np.int16))
    print(f"\n  Audio saved: {audio_path}")

    return {
        'spice_loop_change': f_loop - h_loop,
        'spice_cond_vpp_change': f_cond_vpp - h_cond_vpp,
        'python_rpm_change': f_rpm - h_rpm,
        'python_amp_ratio': f_amp / (h_amp + 1e-10),
    }


# =============================================================================
# TEST CASES
# =============================================================================

def test_r8_open():
    """Test R8 (op-amp input resistor) open circuit."""

    name = "R8_OPEN"
    hypothesis = """
    R8 connects tach_ac to op-amp inverting input.
    If R8 opens:
    - No tachometer signal reaches op-amp
    - Op-amp input floats → output stays near VGND or drifts
    - No feedback to PLL → loop filter drifts to rail
    - Motor speed uncontrolled

    Expected:
    - SPICE cond_out Vpp → ~0 (no signal)
    - SPICE loop_filt → drifts high or low
    - Python motor speed wrong/unstable
    """

    # Run healthy baseline
    print("\n  Running SPICE healthy baseline...")
    spice_healthy = run_spice_test("healthy_baseline", "* No changes")

    # Run faulty SPICE
    print("  Running SPICE with R8 open...")
    spice_faulty = run_spice_test(name, "alterparam R8_VAL = 100MEG")

    # Run healthy Python
    print("  Running Python healthy baseline...")
    python_healthy = run_python_test(None)

    # Run faulty Python
    print("  Running Python with R8 open...")
    def inject_r8_open(voice):
        # R8 open = no tachometer signal reaches op-amp
        # Op-amp input floats, output goes to rail or stays at bias
        # Comparator sees constant level = PLL gets no transitions
        original_update = voice.conditioner.update
        def open_input(dt, input_voltage):
            original_update(dt, 0.0)  # No input signal
            # Output stays at VGND (7.5V) with no modulation
            voice.conditioner.amplified_voltage = 7.5  # Stuck at bias
            voice.conditioner.digital_out = 0  # Comparator sees constant
        voice.conditioner.update = open_input

    python_faulty = run_python_test(inject_r8_open)

    # Analyze
    results = analyze_results(name, hypothesis, spice_healthy, spice_faulty,
                              python_healthy, python_faulty)

    # Validate hypothesis
    print(f"\n[HYPOTHESIS VALIDATION]")
    print("-" * 50)

    checks = []

    # Check 1: Conditioner Vpp should drop significantly
    cond_vpp_dropped = results['spice_cond_vpp_change'] < -3
    checks.append(("SPICE cond Vpp drops significantly", cond_vpp_dropped))

    # Check 2: Python audio should be affected
    audio_changed = results['python_amp_ratio'] < 0.9 or results['python_amp_ratio'] > 1.1
    checks.append(("Python audio amplitude changes", audio_changed))

    passed = 0
    for desc, result in checks:
        status = "✓" if result else "✗"
        print(f"  {status} {desc}")
        if result:
            passed += 1

    print(f"\n  Result: {passed}/{len(checks)} hypothesis checks passed")

    return passed == len(checks)


def test_r_vg1_open():
    """Test R_VG1 (virtual ground high-side resistor) open circuit."""

    name = "R_VG1_OPEN"
    hypothesis = """
    R_VG1 forms voltage divider with R_VG2 to create VGND (7.5V).
    If R_VG1 opens:
    - VGND pulled to 0V by R_VG2
    - Op-amp bias point destroyed
    - Op-amp output likely saturates
    - PLL feedback corrupted

    Expected:
    - SPICE vgnd → 0V (instead of 7.5V)
    - SPICE cond_out → saturated (0V or 15V)
    - Python motor behavior erratic
    """

    print("\n  Running SPICE healthy baseline...")
    spice_healthy = run_spice_test("healthy_baseline2", "* No changes")

    print("  Running SPICE with R_VG1 open...")
    # Modify circuit to make R_VG1 openable
    cir_content = '''* COMPONENT BREAK TEST: R_VG1_OPEN
.INCLUDE real_components.lib

V_SUPPLY vcc 0 DC 12
V_LOGIC vdd 0 DC 15

V_REF ref_in 0 PULSE(0 15 0 10N 10N 2.27M 4.545M)
V_TACH tach_raw 0 SIN(0 50M 220 0 0)

* Virtual ground - R_VG1 OPEN (100MEG instead of 10K)
R_VG1 vdd vgnd 100MEG
R_VG2 vgnd 0 10K
C_BIAS vgnd 0 10U IC=0

C_AC tach_raw tach_ac 1U
R8 tach_ac opamp_inn 1K
R9 opamp_inn cond_pre 100K

X_U2 vgnd opamp_inn vdd 0 cond_pre LM358
B_COND cond_out 0 V=V(cond_pre)

X_C3 vdd 0 CAP_CER_100N

X_COMP_INV1 cond_out comp_int vdd 0 CMOS_INV
X_COMP_INV2 comp_int comp_out vdd 0 CMOS_INV

X_PC1 ref_in comp_out vdd 0 pd_out CD4046_PC1

R3 pd_out loop_filt 100K
X_C2 loop_filt c2_mid CAP_ELEC_10U
R_C2_LEAK c2_mid 0 100MEG

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

R_MOTOR motor_p motor_bemf 20
V_BEMF motor_bemf motor_n DC 0
R_SENSE motor_n motor_gnd 0.1
V_SENSE motor_gnd 0 DC 0

.OPTIONS RELTOL=0.01 ABSTOL=1N VNTOL=1M ITL1=500 ITL4=100

.CONTROL
set filetype=ascii
TRAN 1U 100M UIC
WRDATA R_VG1_OPEN.dat V(loop_filt) V(motor_p,motor_n) I(V_SENSE) V(cond_out) V(cond_pre) V(opamp_inn) V(vgnd) V(tach_ac)
ECHO "R_VG1_OPEN complete"
.ENDC
.END
'''
    cir_path = os.path.join(SPICE_DIR, 'R_VG1_OPEN.cir')
    with open(cir_path, 'w') as f:
        f.write(cir_content)

    subprocess.run(['ngspice', '-b', os.path.basename(cir_path)],
                   cwd=os.path.dirname(cir_path),
                   capture_output=True, timeout=120)

    dat_path = os.path.join(SPICE_DIR, 'R_VG1_OPEN.dat')
    if not os.path.exists(dat_path):
        print(f"  ! Warning: {dat_path} not found")
        return False
    data = np.loadtxt(dat_path)
    steady = int(len(data) * 0.8)
    spice_faulty = {
        'loop_filt': data[steady:, 1],
        'motor_v': data[steady:, 3],
        'motor_i': data[steady:, 5],
        'cond_out': data[steady:, 7],
        'vgnd': data[steady:, 13],
    }

    print("  Running Python healthy baseline...")
    python_healthy = run_python_test(None)

    print("  Running Python with R_VG1 open...")
    def inject_r_vg1_open(voice):
        # VGND goes to 0V, op-amp bias destroyed
        # Conditioner output saturates
        original_update = voice.conditioner.update
        def saturated_update(dt, input_voltage):
            original_update(dt, input_voltage)
            # With VGND at 0V, op-amp saturates negative
            voice.conditioner.amplified_voltage = -12.0
        voice.conditioner.update = saturated_update

    python_faulty = run_python_test(inject_r_vg1_open)

    results = analyze_results(name, hypothesis, spice_healthy, spice_faulty,
                              python_healthy, python_faulty)

    print(f"\n[HYPOTHESIS VALIDATION]")
    print("-" * 50)

    # Check VGND dropped
    h_vgnd = np.mean(spice_healthy.get('vgnd', [7.5]))
    f_vgnd = np.mean(spice_faulty['vgnd'])
    vgnd_dropped = f_vgnd < 2.0
    print(f"  VGND: {h_vgnd:.2f}V → {f_vgnd:.2f}V")

    checks = [
        ("SPICE VGND drops to ~0V", vgnd_dropped),
        ("Python audio affected", results['python_amp_ratio'] != 1.0),
    ]

    passed = 0
    for desc, result in checks:
        status = "✓" if result else "✗"
        print(f"  {status} {desc}")
        if result:
            passed += 1

    print(f"\n  Result: {passed}/{len(checks)} hypothesis checks passed")
    return passed == len(checks)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("  SYSTEMATIC COMPONENT BREAK TESTING")
    print("  Testing individual component failures")
    print("=" * 70)

    results = {}

    # Test 1: R8 open
    print("\n" + "=" * 70)
    print("  TEST 1: R8 (Op-amp input resistor) OPEN")
    print("=" * 70)
    results['R8_OPEN'] = test_r8_open()

    # Test 2: R_VG1 open
    print("\n" + "=" * 70)
    print("  TEST 2: R_VG1 (Virtual ground bias) OPEN")
    print("=" * 70)
    results['R_VG1_OPEN'] = test_r_vg1_open()

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test}")

    total_passed = sum(results.values())
    print(f"\n  Total: {total_passed}/{len(results)} tests passed")

    return all(results.values())


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
