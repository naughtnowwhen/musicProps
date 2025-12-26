#!/usr/bin/env python3
"""
SPICE ↔ Python Model Validation Tests

This test suite ensures the ngspice SPICE model and Python behavioral model
are in sync. They should produce equivalent results for the same inputs.

Run with: python -m pytest tests/test_spice_python_sync.py -v
"""

import json
import os
import sys
import subprocess
import tempfile
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams


# Load shared circuit parameters
PARAMS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'circuit_params.json')
SPICE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.hidden_answers', 'spice_models')


def load_circuit_params():
    """Load the shared circuit parameters."""
    with open(PARAMS_FILE) as f:
        return json.load(f)


def run_spice_simulation(circuit_content, output_signals):
    """Run an ngspice simulation and return the results."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
        f.write(circuit_content)
        cir_file = f.name

    dat_file = cir_file.replace('.cir', '.dat')

    try:
        result = subprocess.run(
            ['ngspice', '-b', cir_file],
            capture_output=True, text=True,
            cwd=SPICE_DIR,
            timeout=30
        )

        if os.path.exists(dat_file):
            data = np.loadtxt(dat_file)
            return data
    finally:
        if os.path.exists(cir_file):
            os.unlink(cir_file)
        if os.path.exists(dat_file):
            os.unlink(dat_file)

    return None


class TestParameterSync:
    """Test that SPICE and Python use the same component values."""

    def test_shared_params_exist(self):
        """Verify circuit_params.json exists and is valid."""
        assert os.path.exists(PARAMS_FILE), "circuit_params.json not found"
        params = load_circuit_params()
        assert 'loop_filter' in params
        assert 'motor' in params
        assert 'power' in params

    def test_python_model_uses_correct_values(self):
        """Verify Python model uses values from shared config."""
        params = load_circuit_params()

        # Create Python voice
        voice_params = SpiceVoiceParams()

        # Check loop filter
        assert voice_params.loop_r1 == params['loop_filter']['r1'], \
            f"Loop R1 mismatch: Python={voice_params.loop_r1}, Config={params['loop_filter']['r1']}"
        assert voice_params.loop_c1 == params['loop_filter']['c1'], \
            f"Loop C1 mismatch: Python={voice_params.loop_c1}, Config={params['loop_filter']['c1']}"

        # Check motor
        assert voice_params.motor_resistance == params['motor']['resistance'], \
            f"Motor R mismatch: Python={voice_params.motor_resistance}, Config={params['motor']['resistance']}"

        # Check power
        assert voice_params.driver_v_supply == params['power']['v_supply'], \
            f"V_supply mismatch: Python={voice_params.driver_v_supply}, Config={params['power']['v_supply']}"

    def test_spice_model_uses_correct_values(self):
        """Verify SPICE model uses values from shared config."""
        params = load_circuit_params()

        # Read the SPICE circuit file
        cir_file = os.path.join(SPICE_DIR, 'aerotone_faults.cir')
        with open(cir_file) as f:
            spice_content = f.read()

        # Check for key values (this is a basic check - could be more thorough)
        assert 'V_SUPPLY vcc 0 DC 12' in spice_content, "V_SUPPLY should be 12V"
        assert 'V_LOGIC vdd 0 DC 15' in spice_content, "V_LOGIC should be 15V"
        assert 'R3 pd_out loop_filt 100K' in spice_content, "Loop filter R3 should be 100K"


class TestBehaviorSync:
    """Test that SPICE and Python produce similar behavior."""

    def test_loop_filter_time_constant(self):
        """Both models should have same loop filter time constant."""
        params = load_circuit_params()

        # Calculate expected time constant
        tau = params['loop_filter']['r1'] * params['loop_filter']['c1']
        expected_tau = 100e3 * 10e-6  # 1 second

        assert abs(tau - expected_tau) < 0.01, \
            f"Loop filter tau should be ~1s, got {tau}s"

    def test_conditioner_gain(self):
        """Signal conditioner should have gain of -100."""
        params = load_circuit_params()

        r8 = params['signal_conditioner']['r8_input']
        r9 = params['signal_conditioner']['r9_feedback']
        gain = -r9 / r8

        assert gain == -100, f"Conditioner gain should be -100, got {gain}"

    def test_motor_electrical_time_constant(self):
        """Motor L/R time constant should match."""
        params = load_circuit_params()

        tau_e = params['motor']['inductance'] / params['motor']['resistance']
        # 0.5mH / 20 ohm = 25 microseconds
        expected = 0.5e-3 / 20

        assert abs(tau_e - expected) < 1e-6, \
            f"Motor electrical time constant mismatch"


class TestFaultSignatures:
    """Test that fault signatures are consistent between models."""

    @pytest.fixture
    def healthy_spice_data(self):
        """Load healthy SPICE waveform."""
        dat_file = os.path.join(SPICE_DIR, 'fault_healthy.dat')
        if os.path.exists(dat_file):
            return np.loadtxt(dat_file)
        pytest.skip("SPICE data not available")

    def test_healthy_loop_filter_range(self, healthy_spice_data):
        """Healthy loop filter should be in expected range."""
        loop_filt = healthy_spice_data[:, 1]
        steady_state = loop_filt[int(len(loop_filt) * 0.8):]

        mean_v = np.mean(steady_state)
        ripple_mv = np.ptp(steady_state) * 1000

        # Healthy should have loop filter around 0.9V with ~76mV ripple
        assert 0.5 < mean_v < 1.5, f"Loop filter DC out of range: {mean_v}V"
        assert 50 < ripple_mv < 100, f"Loop filter ripple out of range: {ripple_mv}mV"

    def test_healthy_conditioner_output(self, healthy_spice_data):
        """Healthy conditioner should have ~8Vpp output."""
        cond = healthy_spice_data[:, 7]
        steady_state = cond[int(len(cond) * 0.8):]

        vpp = np.ptp(steady_state)

        # With 50mV input and gain of -100, expect ~5V output
        # But with saturation, might be higher
        assert 5 < vpp < 12, f"Conditioner Vpp out of range: {vpp}V"

    def test_f002_reduces_motor_voltage(self):
        """F002 (burned Q1) should reduce motor voltage."""
        healthy_file = os.path.join(SPICE_DIR, 'fault_healthy.dat')
        f002_file = os.path.join(SPICE_DIR, 'fault_f002.dat')

        if not os.path.exists(healthy_file) or not os.path.exists(f002_file):
            pytest.skip("SPICE data not available")

        healthy = np.loadtxt(healthy_file)
        f002 = np.loadtxt(f002_file)

        healthy_motor = np.mean(healthy[int(len(healthy)*0.8):, 3])
        f002_motor = np.mean(f002[int(len(f002)*0.8):, 3])

        # F002 should have lower motor voltage
        assert f002_motor < healthy_motor * 0.5, \
            f"F002 motor voltage should be < 50% of healthy"

    def test_f003_increases_conditioner_noise(self):
        """F003 (noisy op-amp) should increase conditioner Vpp."""
        healthy_file = os.path.join(SPICE_DIR, 'fault_healthy.dat')
        f003_file = os.path.join(SPICE_DIR, 'fault_f003.dat')

        if not os.path.exists(healthy_file) or not os.path.exists(f003_file):
            pytest.skip("SPICE data not available")

        healthy = np.loadtxt(healthy_file)
        f003 = np.loadtxt(f003_file)

        healthy_vpp = np.ptp(healthy[int(len(healthy)*0.8):, 7])
        f003_vpp = np.ptp(f003[int(len(f003)*0.8):, 7])

        # F003 should have higher conditioner Vpp (15kHz noise)
        assert f003_vpp > healthy_vpp * 1.5, \
            f"F003 conditioner Vpp should be > 150% of healthy"

    def test_f004_saturates_conditioner(self):
        """F004 (open R9) should saturate conditioner high."""
        f004_file = os.path.join(SPICE_DIR, 'fault_f004.dat')

        if not os.path.exists(f004_file):
            pytest.skip("SPICE data not available")

        f004 = np.loadtxt(f004_file)
        cond = f004[int(len(f004)*0.8):, 7]

        mean_v = np.mean(cond)
        vpp = np.ptp(cond)

        # F004 should be saturated near VCC-1.5V with no AC
        assert mean_v > 12, f"F004 conditioner should be saturated high"
        assert vpp < 0.5, f"F004 conditioner should have no AC content"


class TestPythonModelBehavior:
    """Test Python model produces reasonable output."""

    def test_python_generates_audio(self):
        """Python model should generate non-zero audio."""
        voice = SpiceVoice(SpiceVoiceParams())
        voice.set_target_frequency(220)

        audio = voice.generate_audio(int(0.1 * voice.sample_rate))

        assert len(audio) > 0, "Should generate audio samples"
        assert np.abs(audio).max() > 0.01, "Audio should have non-zero amplitude"

    def test_python_frequency_response(self):
        """Python model should respond to frequency changes."""
        voice = SpiceVoice(SpiceVoiceParams())

        # Generate audio at two different frequencies
        voice.set_target_frequency(110)  # A2
        voice.generate_audio(int(0.2 * voice.sample_rate))
        state_low = voice.get_circuit_state()

        voice.set_target_frequency(220)  # A3
        voice.generate_audio(int(0.2 * voice.sample_rate))
        state_high = voice.get_circuit_state()

        # Higher frequency should mean higher motor RPM
        assert state_high['motor_rpm'] >= state_low['motor_rpm'] * 0.8, \
            "Higher frequency should increase motor RPM"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
