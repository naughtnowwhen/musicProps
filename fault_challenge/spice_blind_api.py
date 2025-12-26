#!/usr/bin/env python3
"""
SPICE-BASED BLIND PROBE API

A circuit fault diagnosis challenge. Use this API to:
1. Get measurements from a healthy reference circuit
2. Get measurements from a faulty circuit
3. Compare them to identify which component failed
4. Submit your diagnosis

Usage:
    python spice_blind_api.py server

Then use HTTP requests to interact with the challenge.
"""

import sys
import os
import random
import hashlib
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List

# Load hidden test data (answers are in parent directory, outside agent's scope)
_HIDDEN_PATH = os.path.join(os.path.dirname(__file__), '..', '.hidden_answers')
sys.path.insert(0, _HIDDEN_PATH)
try:
    import fault_data as _answers
except ImportError:
    print("Error: Hidden answer data not found. Contact test administrator.")
    sys.exit(1)


@dataclass
class DiagnosisResult:
    correct: bool
    submitted: str
    actual_component: str
    measurements_taken: int


class SpiceBlindProbe:
    """
    Blind probe interface for circuit fault diagnosis.

    The agent receives:
    - Raw SPICE transient waveform data from healthy circuit
    - Raw SPICE transient waveform data from faulty circuit
    - Circuit component information

    The agent must analyze the waveforms and determine which component is faulty.
    """

    def __init__(self, test_id: str, challenge_id: str):
        self._test_id = test_id
        self._challenge_id = challenge_id
        self._measurements_taken = 0
        self._diagnosis_submitted = False

    @classmethod
    def create_challenge(cls) -> 'SpiceBlindProbe':
        """Create a new random fault diagnosis challenge."""
        test_ids = list(_answers.FAULT_ANSWERS.keys())
        test_id = random.choice(test_ids)

        challenge_id = hashlib.sha256(
            f"{datetime.now().isoformat()}{test_id}{random.random()}".encode()
        ).hexdigest()[:12]

        return cls(test_id, challenge_id)

    def get_challenge_id(self) -> str:
        return self._challenge_id

    def get_healthy_waveform(self) -> Dict:
        """Get raw SPICE transient waveform data from healthy circuit."""
        return _answers.HEALTHY_WAVEFORM

    def get_faulty_waveform(self) -> Dict:
        """Get raw SPICE transient waveform data from faulty circuit."""
        self._measurements_taken += 1
        return _answers.FAULTY_WAVEFORMS.get(self._test_id, {})

    def get_available_signals(self) -> List[str]:
        """Get list of signal names in waveform data."""
        if _answers.HEALTHY_WAVEFORM:
            return list(_answers.HEALTHY_WAVEFORM.get('signals', {}).keys())
        return []

    # Keep old methods for backwards compatibility
    def get_healthy_reference(self) -> Dict:
        """Get summary measurements from healthy circuit (legacy)."""
        return _answers.HEALTHY_SPICE.copy()

    def get_available_measurements(self) -> List[str]:
        """Get list of measurement points (legacy)."""
        return list(_answers.HEALTHY_SPICE.keys())

    def measure_faulty_circuit(self) -> Dict:
        """Get summary measurements from faulty circuit (legacy)."""
        self._measurements_taken += 1
        faulty = _answers.FAULTY_SPICE.get(self._test_id, {})
        return {**_answers.HEALTHY_SPICE, **faulty}

    def compare_healthy_to_faulty(self) -> Dict:
        """Get side-by-side comparison (legacy)."""
        healthy = _answers.HEALTHY_SPICE
        faulty_spice = _answers.FAULTY_SPICE.get(self._test_id, {})
        faulty = {**healthy, **faulty_spice}

        comparison = {}
        for key in healthy:
            h_val = healthy[key]
            f_val = faulty.get(key, h_val)

            if isinstance(h_val, (int, float)) and isinstance(f_val, (int, float)):
                delta_pct = ((f_val - h_val) / h_val * 100) if h_val else 0
                comparison[key] = {
                    'healthy': h_val,
                    'faulty': f_val,
                    'delta_pct': round(delta_pct, 1),
                    'significant_change': abs(delta_pct) > 5,
                }
            else:
                comparison[key] = {
                    'healthy': h_val,
                    'faulty': f_val,
                    'significant_change': h_val != f_val,
                }

        return comparison

    def submit_diagnosis(self, component: str) -> DiagnosisResult:
        """
        Submit your diagnosis of which component is faulty.

        Args:
            component: Component designator (e.g., C2, Q1, U2, R9, D2)
        """
        if self._diagnosis_submitted:
            raise RuntimeError("Diagnosis already submitted for this challenge!")

        self._diagnosis_submitted = True
        correct_answer = _answers.FAULT_ANSWERS.get(self._test_id, "")
        is_correct = component.upper().strip() == correct_answer.upper()

        return DiagnosisResult(
            correct=is_correct,
            submitted=component,
            actual_component=correct_answer if not is_correct else "",
            measurements_taken=self._measurements_taken,
        )


def create_flask_server():
    """Create HTTP server for remote access to the challenge."""
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("Flask not installed. Run: pip install flask")
        return None

    app = Flask(__name__)
    active_challenges = {}

    @app.route('/challenge/new', methods=['POST'])
    def new_challenge():
        """Create a new fault diagnosis challenge."""
        probe = SpiceBlindProbe.create_challenge()
        active_challenges[probe.get_challenge_id()] = probe

        return jsonify({
            'challenge_id': probe.get_challenge_id(),
            'circuit_info': {
                'name': 'AeroTone Model 12 Voice Card',
                'description': 'PLL-based motor speed controller for electromechanical tone generator',
                'components': [
                    'C2: Loop filter capacitor (10uF electrolytic)',
                    'C3: Bypass capacitor (100nF ceramic)',
                    'Q1, Q3: High-side NPN transistors (2N3055)',
                    'Q2, Q4: Low-side PNP transistors (MJ2955)',
                    'D1, D2, D3, D4: Flyback diodes (1N4001)',
                    'U1: PLL IC (CD4046)',
                    'U2: Op-amp signal conditioner (LM358)',
                    'R3: Loop filter resistor (100k)',
                    'R8: Conditioner input resistor (1k)',
                    'R9: Conditioner feedback resistor (100k)',
                ],
                'operation': 'Phase-locked loop compares reference frequency to motor feedback. Loop filter smooths phase detector output. H-bridge drives DC motor. Magnetic pickup and op-amp provide feedback signal.',
            },
            'data_format': {
                'type': 'Raw SPICE transient simulation output',
                'signals': probe.get_available_signals(),
                'description': 'Time-series voltage/current waveforms from ngspice transient analysis. Time in seconds, voltages in V, currents in A.',
            },
            'instructions': 'Analyze raw SPICE waveform data from healthy and faulty circuits. Find anomalies in the transient behavior. Determine which component failure would cause the observed differences. Submit component designator.',
        })

    @app.route('/challenge/<challenge_id>/healthy', methods=['GET'])
    def healthy_waveform(challenge_id):
        """Get raw SPICE waveform data from healthy circuit."""
        if challenge_id not in active_challenges:
            return jsonify({'error': 'Challenge not found'}), 404
        return jsonify(active_challenges[challenge_id].get_healthy_waveform())

    @app.route('/challenge/<challenge_id>/faulty', methods=['GET'])
    def faulty_waveform(challenge_id):
        """Get raw SPICE waveform data from faulty circuit."""
        if challenge_id not in active_challenges:
            return jsonify({'error': 'Challenge not found'}), 404
        return jsonify(active_challenges[challenge_id].get_faulty_waveform())

    # Legacy endpoints (summary data)
    @app.route('/challenge/<challenge_id>/measure', methods=['POST'])
    def measure(challenge_id):
        """Get summary measurements from the faulty circuit (legacy)."""
        if challenge_id not in active_challenges:
            return jsonify({'error': 'Challenge not found'}), 404
        return jsonify(active_challenges[challenge_id].measure_faulty_circuit())

    @app.route('/challenge/<challenge_id>/compare', methods=['GET'])
    def compare(challenge_id):
        """Get healthy vs faulty comparison (legacy)."""
        if challenge_id not in active_challenges:
            return jsonify({'error': 'Challenge not found'}), 404
        return jsonify(active_challenges[challenge_id].compare_healthy_to_faulty())

    @app.route('/challenge/<challenge_id>/diagnose', methods=['POST'])
    def diagnose(challenge_id):
        """Submit diagnosis."""
        if challenge_id not in active_challenges:
            return jsonify({'error': 'Challenge not found'}), 404

        data = request.json or {}
        component = data.get('component', '')

        if not component:
            return jsonify({'error': 'Missing component in request body'}), 400

        result = active_challenges[challenge_id].submit_diagnosis(component)

        response = {
            'correct': result.correct,
            'your_answer': result.submitted,
            'measurements_taken': result.measurements_taken,
        }
        if not result.correct:
            response['correct_answer'] = result.actual_component

        return jsonify(response)

    return app


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'server':
        app = create_flask_server()
        if app:
            print("=" * 50)
            print("  FAULT DIAGNOSIS CHALLENGE SERVER")
            print("=" * 50)
            print()
            print("Server running at: http://localhost:5001")
            print()
            print("Endpoints:")
            print("  POST /challenge/new           - Start new challenge")
            print("  GET  /challenge/{id}/healthy  - Raw SPICE waveform (healthy)")
            print("  GET  /challenge/{id}/faulty   - Raw SPICE waveform (faulty)")
            print("  POST /challenge/{id}/diagnose - Submit answer")
            print()
            print("Legacy (summary data):")
            print("  POST /challenge/{id}/measure  - Summary measurements")
            print("  GET  /challenge/{id}/compare  - Summary comparison")
            print()
            app.run(debug=False, port=5001)
    else:
        print("Fault Diagnosis Challenge Server")
        print()
        print("Usage: python spice_blind_api.py server")
        print()
        print("This starts an HTTP server for the fault diagnosis challenge.")
        print("Use curl or any HTTP client to interact with the API.")
