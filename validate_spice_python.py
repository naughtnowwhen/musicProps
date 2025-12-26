#!/usr/bin/env python3
"""
SPICE ↔ Python Model Validation

Ensures the ngspice SPICE model and Python behavioral model are in sync.
Run this after making changes to either model.

Usage: python3 validate_spice_python.py
"""

import json
import os
import sys
import numpy as np

sys.path.insert(0, '.')

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams


# Paths
PARAMS_FILE = 'circuit_params.json'
SPICE_DIR = '.hidden_answers/spice_models'


class ValidationResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def check(self, condition, message):
        if condition:
            print(f"  ✓ {message}")
            self.passed += 1
        else:
            print(f"  ✗ {message}")
            self.failed += 1
            self.errors.append(message)

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY: {self.passed}/{total} passed")
        if self.failed > 0:
            print(f"\nFailed checks:")
            for e in self.errors:
                print(f"  - {e}")
        print(f"{'='*60}")
        return self.failed == 0


def load_params():
    with open(PARAMS_FILE) as f:
        return json.load(f)


def validate_parameter_sync(result):
    """Check that Python model uses same values as config."""
    print("\n[1] PARAMETER SYNC")
    print("-" * 40)

    params = load_params()
    py_params = SpiceVoiceParams()

    # Loop filter
    result.check(
        py_params.loop_r1 == params['loop_filter']['r1'],
        f"Loop R1: Python={py_params.loop_r1}, Config={params['loop_filter']['r1']}"
    )
    result.check(
        py_params.loop_c1 == params['loop_filter']['c1'],
        f"Loop C1: Python={py_params.loop_c1}, Config={params['loop_filter']['c1']}"
    )

    # Motor
    result.check(
        py_params.motor_resistance == params['motor']['resistance'],
        f"Motor R: Python={py_params.motor_resistance}, Config={params['motor']['resistance']}"
    )

    # Power supply
    result.check(
        py_params.driver_v_supply == params['power']['v_supply'],
        f"V_supply: Python={py_params.driver_v_supply}, Config={params['power']['v_supply']}"
    )


def validate_spice_values(result):
    """Check that SPICE file uses correct values."""
    print("\n[2] SPICE FILE VALUES")
    print("-" * 40)

    params = load_params()
    cir_file = os.path.join(SPICE_DIR, 'aerotone_faults.cir')

    with open(cir_file) as f:
        spice = f.read()

    result.check(
        'V_SUPPLY vcc 0 DC 12' in spice,
        "SPICE V_SUPPLY = 12V"
    )
    result.check(
        'V_LOGIC vdd 0 DC 15' in spice,
        "SPICE V_LOGIC = 15V"
    )
    result.check(
        'R3 pd_out loop_filt 100K' in spice,
        "SPICE Loop R3 = 100K"
    )
    result.check(
        'R8 tach_ac opamp_inn 1K' in spice,
        "SPICE Conditioner R8 = 1K"
    )


def validate_fault_signatures(result):
    """Check that SPICE fault data shows expected signatures."""
    print("\n[3] FAULT SIGNATURES")
    print("-" * 40)

    healthy_file = os.path.join(SPICE_DIR, 'fault_healthy.dat')
    if not os.path.exists(healthy_file):
        print("  ! SPICE data not found, skipping")
        return

    # Load healthy
    healthy = np.loadtxt(healthy_file)
    h_loop = healthy[int(len(healthy)*0.8):, 1]
    h_cond = healthy[int(len(healthy)*0.8):, 7]

    result.check(
        0.5 < np.mean(h_loop) < 1.5,
        f"Healthy loop filter DC: {np.mean(h_loop):.3f}V (expected 0.5-1.5V)"
    )
    result.check(
        5 < np.ptp(h_cond) < 12,
        f"Healthy conditioner Vpp: {np.ptp(h_cond):.2f}V (expected 5-12V)"
    )

    # Check F002 (burned Q1)
    f002_file = os.path.join(SPICE_DIR, 'fault_f002.dat')
    if os.path.exists(f002_file):
        f002 = np.loadtxt(f002_file)
        f002_motor = np.mean(f002[int(len(f002)*0.8):, 3])
        h_motor = np.mean(healthy[int(len(healthy)*0.8):, 3])
        result.check(
            f002_motor < h_motor * 0.5,
            f"F002 motor voltage drops: {f002_motor:.3f}V < {h_motor*0.5:.3f}V"
        )

    # Check F003 (noisy op-amp)
    f003_file = os.path.join(SPICE_DIR, 'fault_f003.dat')
    if os.path.exists(f003_file):
        f003 = np.loadtxt(f003_file)
        f003_vpp = np.ptp(f003[int(len(f003)*0.8):, 7])
        h_vpp = np.ptp(h_cond)
        result.check(
            f003_vpp > h_vpp * 1.3,
            f"F003 conditioner Vpp increases: {f003_vpp:.2f}V > {h_vpp*1.3:.2f}V"
        )

    # Check F004 (open R9)
    f004_file = os.path.join(SPICE_DIR, 'fault_f004.dat')
    if os.path.exists(f004_file):
        f004 = np.loadtxt(f004_file)
        f004_cond = f004[int(len(f004)*0.8):, 7]
        result.check(
            np.mean(f004_cond) > 12,
            f"F004 conditioner saturates high: {np.mean(f004_cond):.2f}V > 12V"
        )


def validate_python_model(result):
    """Check that Python model produces reasonable output."""
    print("\n[4] PYTHON MODEL BEHAVIOR")
    print("-" * 40)

    voice = SpiceVoice(SpiceVoiceParams())
    voice.set_target_frequency(220)

    # Generate audio
    audio = voice.generate_audio(int(0.1 * voice.sample_rate))

    result.check(
        len(audio) > 0,
        f"Generates audio: {len(audio)} samples"
    )
    result.check(
        np.abs(audio).max() > 0.01,
        f"Audio has content: max={np.abs(audio).max():.4f}"
    )

    # Check circuit state
    state = voice.get_circuit_state()
    result.check(
        state['motor_rpm'] > 0,
        f"Motor spinning: {state['motor_rpm']:.0f} RPM"
    )
    result.check(
        0 < state['motor_current'] < 2,
        f"Motor current reasonable: {state['motor_current']:.3f}A"
    )


def validate_circuit_equations(result):
    """Check fundamental circuit equations match."""
    print("\n[5] CIRCUIT EQUATIONS")
    print("-" * 40)

    params = load_params()

    # Loop filter time constant
    tau = params['loop_filter']['r1'] * params['loop_filter']['c1']
    result.check(
        abs(tau - 1.0) < 0.1,
        f"Loop filter tau: {tau:.2f}s (expected ~1.0s)"
    )

    # Conditioner gain
    gain = -params['signal_conditioner']['r9_feedback'] / params['signal_conditioner']['r8_input']
    result.check(
        gain == -100,
        f"Conditioner gain: {gain} (expected -100)"
    )

    # Motor electrical time constant
    tau_e = params['motor']['inductance'] / params['motor']['resistance']
    result.check(
        tau_e < 1e-3,
        f"Motor electrical tau: {tau_e*1e6:.1f}µs (expected < 1ms)"
    )


def main():
    print("=" * 60)
    print("  SPICE ↔ PYTHON VALIDATION")
    print("  Ensuring models are in sync")
    print("=" * 60)

    result = ValidationResult()

    validate_parameter_sync(result)
    validate_spice_values(result)
    validate_fault_signatures(result)
    validate_python_model(result)
    validate_circuit_equations(result)

    success = result.summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
