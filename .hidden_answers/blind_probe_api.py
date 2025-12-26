#!/usr/bin/env python3
"""
BLIND PROBE API

This module provides a "blind" interface for an LLM troubleshooter.
The troubleshooter gets ONLY measurement functions - no access to fault details.

Usage for LLM Agent:
    from fault_challenge.blind_probe_api import BlindProbeInterface

    # Create challenge (returns only the interface, not the fault info)
    probe = BlindProbeInterface.create_random_challenge()

    # Use probe functions
    probe.measure_vdc('loop_filter_out')
    probe.capture_waveform('motor_voltage', 0.1)

    # Submit diagnosis
    result = probe.submit_diagnosis("Loop filter capacitor C1")
"""

import os
import sys
import json
import random
import hashlib
import base64
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


@dataclass
class ProbeResult:
    """Result of a probe measurement"""
    point: str
    value: float
    unit: str
    measurement_type: str


@dataclass
class WaveformResult:
    """Result of waveform capture"""
    point: str
    v_min: float
    v_max: float
    v_pp: float
    v_avg: float
    v_ac_rms: float
    frequency: float
    duty_cycle: float
    duration: float


@dataclass
class DiagnosisResult:
    """Result of diagnosis submission"""
    is_correct: bool
    submitted: str
    actual_fault: str
    actual_component: str
    description: str
    symptoms: List[str]
    measurements_taken: int


class BlindProbeInterface:
    """
    Blind probe interface for LLM troubleshooting.

    This class exposes ONLY measurement functions.
    The fault details are completely hidden.
    """

    def __init__(self, voice, bench, challenge_id, answer_data):
        """Private constructor - use create_random_challenge() instead"""
        self._voice = voice
        self._bench = bench
        self._challenge_id = challenge_id
        self._answer = answer_data  # Hidden from public interface
        self._measurements: List[Dict] = []
        self._diagnosis_submitted = False

    @classmethod
    def create_random_challenge(cls, difficulty: str = 'medium') -> 'BlindProbeInterface':
        """
        Create a new random fault challenge.

        Args:
            difficulty: 'easy', 'medium', or 'hard'

        Returns:
            BlindProbeInterface with hidden fault injected
        """
        from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
        from aerotone.test_equipment import TestBench

        # Fault pool (hidden from troubleshooter)
        FAULT_POOL = [
            {'id': 'F001', 'name': 'Leaky Electrolytic Capacitor C1',
             'component': 'Loop Filter Capacitor (C1)', 'category': 'capacitor',
             'symptoms': ['Pitch instability', 'VCO control voltage drift', 'Excessive ripple']},
            {'id': 'F002', 'name': 'Burned Power Transistor Q1',
             'component': 'H-Bridge High-Side Transistor (Q1)', 'category': 'transistor',
             'symptoms': ['Reduced motor voltage', 'Slow acceleration', 'Asymmetric drive']},
            {'id': 'F003', 'name': 'Noisy Op-Amp U2',
             'component': 'Signal Conditioner Op-Amp (U2)', 'category': 'opamp',
             'symptoms': ['Noisy feedback signal', 'Output exceeding rails', 'Intermittent squealing']},
            {'id': 'F004', 'name': 'Open Feedback Resistor R3',
             'component': 'Feedback Resistor (R3)', 'category': 'resistor',
             'symptoms': ['Saturated op-amp output', 'No linear amplification']},
            {'id': 'F005', 'name': 'Shorted Flyback Diode D2',
             'component': 'H-Bridge Flyback Diode (D2)', 'category': 'diode',
             'symptoms': ['Reduced motor torque', 'Excessive current draw', 'Motor runs slow']},
        ]

        # Select based on difficulty
        if difficulty == 'easy':
            pool = [f for f in FAULT_POOL if f['category'] in ['capacitor', 'transistor', 'opamp']]
        elif difficulty == 'hard':
            pool = FAULT_POOL
        else:
            pool = [f for f in FAULT_POOL if f['category'] != 'resistor']

        fault = random.choice(pool)

        # Create circuit
        params = SpiceVoiceParams(enable_thermal=False)
        voice = SpiceVoice(params=params, sample_rate=44100)

        # Inject fault
        cls._inject_fault(voice, fault['id'])

        # Warm up
        voice.set_target_frequency(220.0)
        for _ in range(int(44100 * 0.5)):
            voice.update_physics(1/44100)

        bench = TestBench(voice)

        # Generate challenge ID
        challenge_id = hashlib.sha256(
            f"{datetime.now().isoformat()}{fault['id']}".encode()
        ).hexdigest()[:12]

        return cls(voice, bench, challenge_id, fault)

    @staticmethod
    def _inject_fault(voice, fault_id):
        """Inject fault into voice circuit (private)"""
        if fault_id == 'F001':  # Leaky capacitor
            original = voice.loop_filter.update
            def leaky(input_voltage, dt, high_z=False):
                result = original(input_voltage, dt, high_z=high_z)
                mid = voice.params.vdd / 2
                voice.loop_filter.output_voltage -= (voice.loop_filter.output_voltage - mid) * 0.15 * dt * 100
                voice.loop_filter.output_voltage += np.random.randn() * 0.02
                return voice.loop_filter.output_voltage
            voice.loop_filter.update = leaky

        elif fault_id == 'F002':  # Burned transistor
            original = voice.driver.update
            def damaged(dt, motor_back_emf=0.0):
                result = original(dt, motor_back_emf)
                if voice.driver.motor_voltage > 0:
                    voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 3.0)
                    voice.driver.motor_voltage += np.random.randn() * 0.15
                return result
            voice.driver.update = damaged

        elif fault_id == 'F003':  # Noisy op-amp
            original = voice.conditioner.update
            drift = [0.0]
            def noisy(dt, input_voltage):
                original(dt, input_voltage)
                voice.conditioner.amplified_voltage += np.random.randn() * 0.8
                if np.random.random() < 0.3:
                    voice.conditioner.amplified_voltage += np.sin(np.random.random() * 1000) * 0.6
                drift[0] += np.random.randn() * 0.005
                drift[0] = np.clip(drift[0], -2.0, 2.0)
                voice.conditioner.amplified_voltage += drift[0]
                if abs(voice.conditioner.amplified_voltage) > 11.5:
                    overshoot = np.random.uniform(0.5, 2.5)
                    voice.conditioner.amplified_voltage += overshoot if voice.conditioner.amplified_voltage > 0 else -overshoot
            voice.conditioner.update = noisy

        elif fault_id == 'F004':  # Open feedback resistor
            original = voice.conditioner.update
            def saturated(dt, input_voltage):
                original(dt, input_voltage)
                voice.conditioner.amplified_voltage = 12.0 if input_voltage > 0 else -12.0
            voice.conditioner.update = saturated

        elif fault_id == 'F005':  # Shorted diode
            original = voice.driver.update
            def shorted(dt, motor_back_emf=0.0):
                result = original(dt, motor_back_emf)
                voice.driver.motor_voltage *= 0.6
                voice.driver.motor_current *= 1.5
                return result
            voice.driver.update = shorted

    # ================================================================
    # PUBLIC INTERFACE - These are the ONLY methods the troubleshooter
    # should use. They provide measurements but NO fault information.
    # ================================================================

    def get_challenge_id(self) -> str:
        """Get the challenge ID (for tracking, not cheating!)"""
        return self._challenge_id

    def get_available_probes(self) -> List[str]:
        """Get list of all available probe points"""
        return self._bench.get_probe_points()

    def get_probes_by_category(self, category: str) -> List[str]:
        """Get probe points filtered by category"""
        points = self._bench.get_probe_points()
        categories = {
            'power': ['v_supply', 'v_logic', 'gnd'],
            'cd4046': [p for p in points if p.startswith('cd4046')],
            'filter': [p for p in points if 'loop_filter' in p],
            'hbridge': [p for p in points if 'hbridge' in p],
            'motor': [p for p in points if p.startswith('motor')],
            'driver': [p for p in points if p.startswith('driver')],
            'pickup': [p for p in points if 'pickup' in p],
            'conditioner': [p for p in points if 'cond' in p],
        }
        return categories.get(category, [])

    def probe(self, point: str) -> ProbeResult:
        """Read instantaneous value at probe point"""
        value = self._bench.probe(point)
        self._measurements.append({'type': 'probe', 'point': point, 'value': value})
        return ProbeResult(point=point, value=value, unit='V', measurement_type='instantaneous')

    def measure_vdc(self, point: str) -> ProbeResult:
        """Measure DC voltage (averaged)"""
        m = self._bench.measure_vdc(point)
        self._measurements.append({'type': 'vdc', 'point': point, 'value': m.value})
        return ProbeResult(point=point, value=m.value, unit='VDC', measurement_type='dc_average')

    def measure_vac(self, point: str) -> ProbeResult:
        """Measure AC voltage (RMS of AC component)"""
        m = self._bench.measure_vac(point)
        self._measurements.append({'type': 'vac', 'point': point, 'value': m.value})
        return ProbeResult(point=point, value=m.value, unit='VAC', measurement_type='ac_rms')

    def measure_frequency(self, point: str) -> ProbeResult:
        """Measure signal frequency"""
        m = self._bench.measure_frequency(point)
        self._measurements.append({'type': 'freq', 'point': point, 'value': m.value})
        return ProbeResult(point=point, value=m.value, unit='Hz', measurement_type='frequency')

    def capture_waveform(self, point: str, duration: float = 0.1) -> WaveformResult:
        """Capture and analyze waveform"""
        w = self._bench.capture_waveform(point, duration)
        self._measurements.append({
            'type': 'waveform', 'point': point,
            'vpp': w.v_pp, 'freq': w.frequency
        })
        return WaveformResult(
            point=point,
            v_min=w.v_min, v_max=w.v_max, v_pp=w.v_pp,
            v_avg=w.v_avg, v_ac_rms=w.v_ac_rms,
            frequency=w.frequency, duty_cycle=w.duty_cycle,
            duration=duration
        )

    def set_target_frequency(self, freq: float):
        """Change the target operating frequency"""
        self._voice.set_target_frequency(freq)
        # Let it settle
        for _ in range(int(44100 * 0.3)):
            self._voice.update_physics(1/44100)

    def get_circuit_status(self) -> Dict[str, float]:
        """Get basic circuit operating status"""
        rpm = self._voice.motor.omega * 60 / (2 * np.pi)
        bpf = rpm * self._voice.params.prop_num_blades / 60
        return {
            'target_frequency': self._voice.target_frequency,
            'motor_rpm': rpm,
            'blade_passage_frequency': bpf,
        }

    def get_measurement_count(self) -> int:
        """Get number of measurements taken"""
        return len(self._measurements)

    def submit_diagnosis(self, diagnosis: str) -> DiagnosisResult:
        """
        Submit your diagnosis.

        Args:
            diagnosis: Description of the faulty component
                      (e.g., "Loop filter capacitor C1")

        Returns:
            DiagnosisResult with correctness and actual fault info
        """
        if self._diagnosis_submitted:
            raise RuntimeError("Diagnosis already submitted!")

        self._diagnosis_submitted = True

        # Check if correct
        correct_component = self._answer['component'].lower()
        diagnosis_lower = diagnosis.lower()

        is_correct = (
            self._answer['component'].lower() in diagnosis_lower or
            self._answer['category'] in diagnosis_lower or
            any(kw in diagnosis_lower for kw in self._answer['component'].lower().split())
        )

        return DiagnosisResult(
            is_correct=is_correct,
            submitted=diagnosis,
            actual_fault=self._answer['name'],
            actual_component=self._answer['component'],
            description=self._answer.get('description', ''),
            symptoms=self._answer['symptoms'],
            measurements_taken=len(self._measurements)
        )


# ================================================================
# Example usage for LLM agent
# ================================================================

def example_troubleshooting_session():
    """Example of how an LLM agent would use this interface"""

    print("=" * 60)
    print("  BLIND TROUBLESHOOTING EXAMPLE")
    print("=" * 60)

    # Create random challenge
    probe = BlindProbeInterface.create_random_challenge(difficulty='medium')
    print(f"\nChallenge ID: {probe.get_challenge_id()}")
    print(f"Available probes: {len(probe.get_available_probes())}")

    # Systematic troubleshooting (what an LLM would do)
    print("\n--- Step 1: Check Power Supply ---")
    v_supply = probe.measure_vdc('v_supply')
    v_logic = probe.measure_vdc('v_logic')
    print(f"V_supply: {v_supply.value:.2f}V (expected: 12V)")
    print(f"V_logic: {v_logic.value:.2f}V (expected: 15V)")

    print("\n--- Step 2: Check Loop Filter ---")
    lf_out = probe.measure_vdc('loop_filter_out')
    lf_wave = probe.capture_waveform('loop_filter_cap_voltage', 0.1)
    print(f"Loop filter output: {lf_out.value:.2f}V")
    print(f"Loop filter ripple: {lf_wave.v_ac_rms:.4f}V RMS")

    print("\n--- Step 3: Check Motor Driver ---")
    motor_v = probe.measure_vdc('motor_voltage')
    motor_i = probe.measure_vdc('motor_current')
    print(f"Motor voltage: {motor_v.value:.2f}V")
    print(f"Motor current: {motor_i.value:.3f}A")

    print("\n--- Step 4: Check Feedback Path ---")
    cond_out = probe.capture_waveform('cond_opamp_out', 0.1)
    print(f"Conditioner output Vpp: {cond_out.v_pp:.2f}V")
    print(f"Conditioner output exceeds rails: {cond_out.v_max > 12.5 or cond_out.v_min < -12.5}")

    print(f"\nMeasurements taken: {probe.get_measurement_count()}")

    # Submit diagnosis (LLM would reason about measurements first)
    print("\n--- Submitting Diagnosis ---")
    # This is just an example - real LLM would analyze measurements
    result = probe.submit_diagnosis("Unknown - this is just an example")

    print(f"\nCorrect: {result.is_correct}")
    print(f"Actual fault: {result.actual_fault}")
    print(f"Component: {result.actual_component}")


if __name__ == '__main__':
    example_troubleshooting_session()
