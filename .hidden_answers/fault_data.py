# HIDDEN FAULT DATA - DO NOT READ
# This file contains the answer key and raw SPICE waveform data
# Generated from REAL ngspice simulations with actual component models

import os
import numpy as np

_SPICE_DIR = os.path.join(os.path.dirname(__file__), 'spice_models')

def _load_raw_waveform(filename):
    """Load raw ngspice waveform data from real component simulation."""
    filepath = os.path.join(_SPICE_DIR, filename)
    if not os.path.exists(filepath):
        return None

    data = np.loadtxt(filepath)

    # Format: interleaved time,value pairs for each signal
    # Signals: loop_filter, motor_voltage, motor_current, conditioner
    time = data[:, 0].tolist()

    signals = {
        'loop_filter': data[:, 1].tolist(),
        'motor_voltage': data[:, 3].tolist(),
        'motor_current': data[:, 5].tolist(),
        'conditioner': data[:, 7].tolist(),
    }

    return {
        'time_seconds': time,
        'signals': signals,
        'sample_count': len(time),
        'simulation_type': 'Real SPICE: NS LM358, CMOS CD4046, 2N3055/MJ2955, 1N4001',
    }

# Load REAL SPICE waveforms (from actual transistor/op-amp models)
HEALTHY_WAVEFORM = _load_raw_waveform('fault_healthy.dat')

FAULTY_WAVEFORMS = {
    'F001': _load_raw_waveform('fault_f001.dat'),
    'F002': _load_raw_waveform('fault_f002.dat'),
    'F003': _load_raw_waveform('fault_f003.dat'),
    'F004': _load_raw_waveform('fault_f004.dat'),
    'F005': _load_raw_waveform('fault_f005.dat'),
}

# Answer key
FAULT_ANSWERS = {
    'F001': 'C2',
    'F002': 'Q1',
    'F003': 'U2',
    'F004': 'R9',
    'F005': 'D2',
}

# Summary values from real SPICE simulation (updated 2024-12)
HEALTHY_SPICE = {
    'v_supply': 12.0,
    'v_logic': 15.0,
    'loop_filter_dc': 0.928,
    'loop_filter_ripple_mV': 76.3,
    'motor_voltage': 1.008,
    'motor_current': 0.151,
    'cond_opamp_vpp': 8.22,
    'cond_opamp_dc': 7.68,
    'cond_opamp_waveform': 'clean_sine',
}

FAULTY_SPICE = {
    'F001': {  # Leaky capacitor C2 (3K leakage)
        'loop_filter_dc': 0.915,
        'loop_filter_ripple_mV': 71.5,
        'motor_voltage': 1.003,
        'motor_current': 0.150,
        'cond_opamp_vpp': 8.22,
        'cond_opamp_dc': 7.68,
        'cond_opamp_waveform': 'clean_sine',
    },
    'F002': {  # Burned transistor Q1 (100 ohm series resistance)
        'loop_filter_dc': 1.400,
        'loop_filter_ripple_mV': 90.0,
        'motor_voltage': 0.358,
        'motor_current': 0.139,
        'cond_opamp_vpp': 8.22,
        'cond_opamp_dc': 7.68,
        'cond_opamp_waveform': 'clean_sine',
    },
    'F003': {  # Noisy op-amp U2 (15kHz oscillation)
        'loop_filter_dc': 0.926,
        'loop_filter_ripple_mV': 76.1,
        'motor_voltage': 1.007,
        'motor_current': 0.151,
        'cond_opamp_vpp': 14.21,
        'cond_opamp_dc': 7.68,
        'cond_opamp_waveform': 'noisy_15kHz',
    },
    'F004': {  # Open feedback resistor R9
        'loop_filter_dc': 0.908,
        'loop_filter_ripple_mV': 76.3,
        'motor_voltage': 1.000,
        'motor_current': 0.150,
        'cond_opamp_vpp': 0.0,
        'cond_opamp_dc': 14.02,
        'cond_opamp_waveform': 'saturated_high',
    },
    'F005': {  # Shorted flyback diode D2 (5 ohm)
        'loop_filter_dc': 0.620,
        'loop_filter_ripple_mV': 68.3,
        'motor_voltage': 0.286,
        'motor_current': 0.103,
        'cond_opamp_vpp': 8.22,
        'cond_opamp_dc': 7.68,
        'cond_opamp_waveform': 'clean_sine',
    },
}
