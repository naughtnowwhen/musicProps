#!/usr/bin/env python3
"""
FAULT CHALLENGE GENERATOR (Hidden Side)

This script:
1. Randomly selects a fault from a pool
2. Injects it into a circuit
3. Saves the answer in an ENCRYPTED file
4. Provides ONLY a probe interface to the troubleshooter

The troubleshooter MUST NOT read this file or the answer file!
"""

import os
import sys
import json
import random
import hashlib
import base64
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench


# ============================================================
# FAULT DEFINITIONS (SECRET - troubleshooter should not see)
# ============================================================

FAULT_POOL = [
    {
        'id': 'F001',
        'name': 'Leaky Electrolytic Capacitor C1',
        'component': 'Loop Filter Capacitor (C1)',
        'category': 'capacitor',
        'description': 'The 10µF electrolytic in the loop filter has dried out, causing high leakage current and inability to hold charge.',
        'symptoms': ['Pitch instability', 'VCO control voltage drift', 'Excessive ripple on loop filter output'],
    },
    {
        'id': 'F002',
        'name': 'Burned Power Transistor Q1',
        'component': 'H-Bridge High-Side Transistor (Q1)',
        'category': 'transistor',
        'description': 'The 2N3055 high-side driver has thermal damage from heatsink failure. Increased Vce_sat causing voltage drop.',
        'symptoms': ['Reduced motor voltage', 'Slow acceleration', 'Asymmetric drive'],
    },
    {
        'id': 'F003',
        'name': 'Noisy Op-Amp U2',
        'component': 'Signal Conditioner Op-Amp (U2)',
        'category': 'opamp',
        'description': 'The 741 op-amp in signal conditioning has ESD damage. Produces excess noise and occasional oscillation.',
        'symptoms': ['Noisy feedback signal', 'Intermittent squealing', 'Output exceeding rails'],
    },
    {
        'id': 'F004',
        'name': 'Open Feedback Resistor R3',
        'component': 'Feedback Resistor (R3)',
        'category': 'resistor',
        'description': 'The feedback resistor in the op-amp circuit has cracked open, causing maximum gain.',
        'symptoms': ['Saturated op-amp output', 'No linear amplification', 'Clipped feedback signal'],
    },
    {
        'id': 'F005',
        'name': 'Shorted Flyback Diode D2',
        'component': 'H-Bridge Flyback Diode (D2)',
        'category': 'diode',
        'description': 'Flyback diode D2 has failed short, creating a partial short across motor terminal.',
        'symptoms': ['Reduced motor torque', 'Excessive current draw', 'Motor runs slow'],
    },
    {
        'id': 'F006',
        'name': 'Degraded CD4046 VCO',
        'component': 'CD4046 PLL IC (U1)',
        'category': 'ic',
        'description': 'The CD4046 VCO section has degraded, producing a narrower frequency range than spec.',
        'symptoms': ['Limited pitch range', 'Cannot reach high frequencies', 'VCO output jittery'],
    },
]


def inject_fault(voice, fault_id):
    """Inject a specific fault into the voice circuit"""

    if fault_id == 'F001':  # Leaky capacitor
        original_update = voice.loop_filter.update
        def leaky_update(input_voltage, dt, high_z=False):
            result = original_update(input_voltage, dt, high_z=high_z)
            midpoint = voice.params.vdd / 2
            voice.loop_filter.output_voltage -= (voice.loop_filter.output_voltage - midpoint) * 0.15 * dt * 100
            voice.loop_filter.output_voltage += np.random.randn() * 0.02
            return voice.loop_filter.output_voltage
        voice.loop_filter.update = leaky_update

    elif fault_id == 'F002':  # Burned transistor
        original_update = voice.driver.update
        def damaged_update(dt, motor_back_emf=0.0):
            result = original_update(dt, motor_back_emf)
            if voice.driver.motor_voltage > 0:
                voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 3.0)
                voice.driver.motor_voltage += np.random.randn() * 0.15
            return result
        voice.driver.update = damaged_update

    elif fault_id == 'F003':  # Noisy op-amp
        original_update = voice.conditioner.update
        offset_drift = [0.0]
        def noisy_update(dt, input_voltage):
            original_update(dt, input_voltage)
            voice.conditioner.amplified_voltage += np.random.randn() * 0.8
            if np.random.random() < 0.3:
                voice.conditioner.amplified_voltage += np.sin(np.random.random() * 1000) * 0.6
            offset_drift[0] += np.random.randn() * 0.005
            offset_drift[0] = np.clip(offset_drift[0], -2.0, 2.0)
            voice.conditioner.amplified_voltage += offset_drift[0]
            if abs(voice.conditioner.amplified_voltage) > 11.5:
                overshoot = np.random.uniform(0.5, 2.5)
                if voice.conditioner.amplified_voltage > 0:
                    voice.conditioner.amplified_voltage += overshoot
                else:
                    voice.conditioner.amplified_voltage -= overshoot
        voice.conditioner.update = noisy_update

    elif fault_id == 'F004':  # Open feedback resistor
        original_update = voice.conditioner.update
        def saturated_update(dt, input_voltage):
            original_update(dt, input_voltage)
            # With open feedback resistor, gain goes to infinity -> saturation
            voice.conditioner.amplified_voltage = 12.0 if input_voltage > 0 else -12.0
        voice.conditioner.update = saturated_update

    elif fault_id == 'F005':  # Shorted flyback diode
        original_update = voice.driver.update
        def shorted_diode_update(dt, motor_back_emf=0.0):
            result = original_update(dt, motor_back_emf)
            # Partial short reduces effective voltage and wastes current
            voice.driver.motor_voltage *= 0.6
            voice.driver.motor_current *= 1.5
            return result
        voice.driver.update = shorted_diode_update

    elif fault_id == 'F006':  # Degraded CD4046
        # Reduce VCO range
        voice.cd4046.f_max = voice.cd4046.f_max * 0.5
        voice.cd4046.kvco = (voice.cd4046.f_max - voice.cd4046.f_min) / voice.params.vdd


def create_challenge(difficulty='medium'):
    """
    Create a new fault challenge.

    Returns a challenge_id that can be used to verify the answer.
    """

    # Select random fault
    if difficulty == 'easy':
        # Only basic faults
        pool = [f for f in FAULT_POOL if f['category'] in ['capacitor', 'transistor', 'opamp']]
    elif difficulty == 'hard':
        # All faults including tricky ones
        pool = FAULT_POOL
    else:
        # Medium - exclude the trickiest
        pool = [f for f in FAULT_POOL if f['category'] != 'ic']

    fault = random.choice(pool)

    # Generate challenge ID
    timestamp = datetime.now().isoformat()
    challenge_id = hashlib.sha256(f"{timestamp}{fault['id']}".encode()).hexdigest()[:12]

    # Create the faulty circuit
    params = SpiceVoiceParams(enable_thermal=False)
    voice = SpiceVoice(params=params, sample_rate=44100)

    # Inject the fault
    inject_fault(voice, fault['id'])

    # Warm up
    voice.set_target_frequency(220.0)
    for _ in range(int(44100 * 0.5)):
        voice.update_physics(1/44100)

    # Create test bench (this is what the troubleshooter gets)
    bench = TestBench(voice)

    # Save the answer (encrypted/hidden)
    answer = {
        'challenge_id': challenge_id,
        'fault_id': fault['id'],
        'fault_name': fault['name'],
        'component': fault['component'],
        'category': fault['category'],
        'description': fault['description'],
        'symptoms': fault['symptoms'],
        'created': timestamp,
        'difficulty': difficulty,
    }

    # Simple obfuscation (not cryptographically secure, but prevents casual peeking)
    answer_json = json.dumps(answer)
    encoded = base64.b64encode(answer_json.encode()).decode()

    os.makedirs('fault_challenge/answers', exist_ok=True)
    with open(f'fault_challenge/answers/{challenge_id}.ans', 'w') as f:
        f.write(f"# DO NOT READ - This file contains the answer!\n")
        f.write(f"# Challenge ID: {challenge_id}\n")
        f.write(f"# Decode with: base64 -d\n")
        f.write(encoded)

    print(f"Challenge created: {challenge_id}")
    print(f"Difficulty: {difficulty}")
    print(f"Answer saved to: fault_challenge/answers/{challenge_id}.ans")
    print()
    print("=" * 60)
    print("  TROUBLESHOOTER INSTRUCTIONS")
    print("=" * 60)
    print(f"""
The circuit has a fault. Your task:

1. Use the probe interface to systematically test the circuit
2. Compare measurements to expected values
3. Identify the faulty component
4. Explain your reasoning

You have access to:
- All 99 probe points (IC pins, component terminals, etc.)
- DMM functions (VDC, VAC, frequency, current)
- Oscilloscope capture

You must NOT:
- Read the answer file
- Look at challenge_generator.py
- Guess randomly

Start troubleshooting with: python fault_challenge/troubleshoot.py {challenge_id}
""")

    return challenge_id, voice, bench, fault


def verify_answer(challenge_id, diagnosis):
    """Verify if the troubleshooter's diagnosis is correct"""

    answer_file = f'fault_challenge/answers/{challenge_id}.ans'
    if not os.path.exists(answer_file):
        return None, "Challenge not found"

    with open(answer_file, 'r') as f:
        lines = f.readlines()
        encoded = lines[-1]  # Last line is the encoded answer

    answer_json = base64.b64decode(encoded.encode()).decode()
    answer = json.loads(answer_json)

    # Check if diagnosis matches
    correct_component = answer['component'].lower()
    diagnosis_lower = diagnosis.lower()

    # Flexible matching
    matches = [
        answer['component'].lower() in diagnosis_lower,
        answer['category'] in diagnosis_lower,
        any(keyword in diagnosis_lower for keyword in answer['component'].lower().split()),
    ]

    is_correct = any(matches)

    return is_correct, answer


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate a fault challenge')
    parser.add_argument('--difficulty', choices=['easy', 'medium', 'hard'], default='medium')
    args = parser.parse_args()

    challenge_id, voice, bench, fault = create_challenge(args.difficulty)
