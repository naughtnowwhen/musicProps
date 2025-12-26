#!/usr/bin/env python3
"""
SPICE-BASED FAULT DIAGNOSIS TEST

A fair test of AI reasoning ability:
- Provides circuit documentation (educational)
- Provides HEALTHY SPICE reference values
- Provides FAULTY SPICE measurements
- AI must reason from differences to identify the fault

NO diagnostic hints or symptom-to-fault mappings provided.

Usage:
    python fault_challenge/spice_diagnosis_test.py [fault_number] [model]

    fault_number: 1-5 (default: random)
    model: anthropic/claude-opus, deepseek/deepseek-r1 (default: r1)
"""

import os
import sys
import json
import random
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

# =============================================================================
# CIRCUIT DOCUMENTATION - Educational, NOT diagnostic hints
# =============================================================================

CIRCUIT_DOCUMENTATION = '''
# AeroTone Model 12 Voice Card - Circuit Documentation

## System Overview

The AeroTone Model 12 is a 1979 electromechanical musical instrument that generates
tones via spinning propellers. Each voice card controls one propeller motor using
a Phase-Locked Loop (PLL) to maintain precise RPM.

**Pitch Control:** Blade Passage Frequency = RPM × 12 blades / 60
For 220 Hz (A3): RPM = 220 × 60 / 12 = 1,100 RPM

## Circuit Block Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VOICE CARD BLOCK DIAGRAM                        │
│                                                                         │
│  ┌──────────┐      ┌─────────────┐      ┌──────────────┐               │
│  │ Reference │      │   PHASE     │      │  LOOP FILTER │               │
│  │  Signal   │─────▶│  DETECTOR   │─────▶│   (R3, C2)   │──┐            │
│  │ (220 Hz)  │      │   (CD4046)  │      │  Smooths PD  │  │            │
│  └──────────┘      └─────────────┘      └──────────────┘  │            │
│                           ▲                               │            │
│                           │                               ▼            │
│  ┌──────────────────────────────────────┐      ┌──────────────┐        │
│  │     SIGNAL CONDITIONER (U2=LM358)    │      │   H-BRIDGE   │        │
│  │                                      │      │  Q1,Q2,Q3,Q4 │        │
│  │  Magnetic pickup → Gain stage (×100) │      │   D1,D2,D3,D4│        │
│  │  Converts sine to square wave        │      │              │        │
│  └──────────────────────────────────────┘      └──────┬───────┘        │
│                           ▲                           │                │
│                           │                           ▼                │
│                    ┌──────┴───────┐           ┌──────────────┐         │
│                    │   MAGNETIC   │◀──────────│   DC MOTOR   │         │
│                    │   PICKUP     │           │  (propeller) │         │
│                    └──────────────┘           └──────────────┘         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## How the PLL Works

1. **Reference Signal**: 220 Hz square wave (target frequency)
2. **Phase Detector**: CD4046 compares reference to feedback, outputs pulses
3. **Loop Filter**: R3 (100kΩ) + C2 (10µF) smooths pulses to DC voltage
4. **H-Bridge**: Converts control voltage to motor drive current
5. **Motor**: Spins propeller, speed proportional to drive voltage
6. **Pickup**: Magnetic sensor on propeller generates feedback signal
7. **Conditioner**: LM358 amplifies pickup signal (gain ≈ 100) for PLL

When locked: Motor runs at exact speed to produce 220 Hz blade passage frequency.

## Component List

| Component | Type | Value | Function |
|-----------|------|-------|----------|
| U1 | CD4046 | - | Phase-Locked Loop IC |
| U2 | LM358 | - | Signal Conditioner Op-Amp |
| Q1, Q3 | 2N3055 | NPN | H-Bridge High-Side Transistors |
| Q2, Q4 | MJ2955 | PNP | H-Bridge Low-Side Transistors |
| D1-D4 | 1N4001 | - | Flyback Protection Diodes |
| R3 | Resistor | 100kΩ | Loop Filter Resistor |
| C2 | Electrolytic | 10µF | Loop Filter Capacitor |
| C3 | Ceramic | 100nF | Loop Filter HF Bypass |
| R8 | Resistor | 1kΩ | Conditioner Input Resistor |
| R9 | Resistor | 100kΩ | Conditioner Feedback Resistor |

## Power Supplies

- V_supply: +12V DC (motor power)
- V_logic: +15V DC (CD4046, op-amp)

## Measurement Points

| Point | Description |
|-------|-------------|
| v_supply | Motor supply voltage |
| v_logic | Logic supply voltage |
| loop_filter | Output of loop filter (DC control voltage) |
| loop_filter_ripple | AC component on loop filter output |
| motor_voltage | Voltage across motor terminals |
| motor_current | Current through motor |
| cond_opamp_out | Signal conditioner output (Vpp, waveform) |
| motor_rpm | Motor speed |
'''

TROUBLESHOOTING_PRINCIPLES = '''
## General Troubleshooting Principles

1. **Power First**: Always verify supply voltages before investigating other issues.

2. **Compare to Known Good**: The most reliable diagnostic method is comparing
   measurements from a faulty circuit to a known-good reference.

3. **Signal Flow**: Trace the signal path from reference input through each
   stage to identify where the problem originates.

4. **Component Behavior**:
   - Resistors can open (infinite resistance) or rarely short
   - Capacitors can leak (partial short to ground) or open
   - Transistors can short (C-E), open, or have increased resistance
   - Diodes can short or open
   - Op-amps can oscillate, saturate, or fail to amplify

5. **Loading Effects**: A shorted component may create unexpected current paths.
   An open component may remove expected feedback or filtering.

6. **Symptoms vs Root Cause**: Multiple symptoms often trace to a single
   component failure. Look for the common element.
'''

# =============================================================================
# SPICE-VALIDATED REFERENCE DATA (from ngspice run_all_faults.cir)
# =============================================================================

HEALTHY_SPICE_VALUES = {
    'v_supply': 12.0,
    'v_logic': 15.0,
    'loop_filter_dc': 7.17,
    'loop_filter_ripple_mV': 0.072,
    'motor_voltage': 6.31,
    'motor_current': 0.28,
    'cond_opamp_vpp': 10.1,
    'cond_opamp_waveform': 'clean sine/square',
}

# Faulty SPICE values - DIRECTLY FROM NGSPICE SIMULATION
FAULTY_SPICE_VALUES = {
    'F001': {
        'v_supply': 12.0,
        'v_logic': 15.0,
        'loop_filter_dc': 5.57,        # DOWN from 7.17V (leakage pulls down)
        'loop_filter_ripple_mV': 0.26,  # UP 3.6x (capacitor can't filter)
        'motor_voltage': 4.90,          # DOWN (less drive)
        'motor_current': 0.28,          # Normal
        'cond_opamp_vpp': 10.1,
        'cond_opamp_waveform': 'clean sine/square',
    },
    'F002': {
        'v_supply': 12.0,
        'v_logic': 15.0,
        'loop_filter_dc': 7.17,
        'loop_filter_ripple_mV': 0.072,
        'motor_voltage': 3.56,          # DOWN 44%
        'motor_current': 0.028,         # DOWN 90% - KEY DIFFERENTIATOR
        'cond_opamp_vpp': 10.1,
        'cond_opamp_waveform': 'clean sine/square',
    },
    'F003': {
        'v_supply': 12.0,
        'v_logic': 15.0,
        'loop_filter_dc': 7.17,
        'loop_filter_ripple_mV': 0.072,
        'motor_voltage': 6.31,
        'motor_current': 0.28,
        'cond_opamp_vpp': 16.1,         # UP 60% (noise/oscillation)
        'cond_opamp_waveform': 'noisy, 15kHz oscillation superimposed',
    },
    'F004': {
        'v_supply': 12.0,
        'v_logic': 15.0,
        'loop_filter_dc': 7.17,
        'loop_filter_ripple_mV': 0.072,
        'motor_voltage': 6.31,
        'motor_current': 0.28,
        'cond_opamp_vpp': 24.0,         # Saturated at ±12V rails
        'cond_opamp_waveform': 'square wave saturated at ±12V rails',
    },
    'F005': {
        'v_supply': 12.0,
        'v_logic': 15.0,
        'loop_filter_dc': 7.17,
        'loop_filter_ripple_mV': 0.072,
        'motor_voltage': 6.31,
        'motor_current': 2.42,          # UP 8.6x - KEY DIFFERENTIATOR
        'cond_opamp_vpp': 10.1,
        'cond_opamp_waveform': 'clean sine/square',
    },
}

FAULTS = [
    {'id': 'F001', 'name': 'Leaky Electrolytic Capacitor C2', 'component': 'C2'},
    {'id': 'F002', 'name': 'Burned Power Transistor Q1', 'component': 'Q1'},
    {'id': 'F003', 'name': 'Noisy Op-Amp U2', 'component': 'U2'},
    {'id': 'F004', 'name': 'Open Feedback Resistor R9', 'component': 'R9'},
    {'id': 'F005', 'name': 'Shorted Flyback Diode D2', 'component': 'D2'},
]

# Keywords for matching diagnosis - STRICT: must match specific component
FAULT_KEYWORDS = {
    'F001': ['c2'],  # Must specifically identify C2
    'F002': ['q1'],  # Must specifically identify Q1
    'F003': ['u2'],  # Must specifically identify U2
    'F004': ['r9'],  # Must specifically identify R9 (not R8!)
    'F005': ['d2'],  # Must specifically identify D2
}


def format_spice_comparison(healthy: dict, faulty: dict) -> str:
    """Format SPICE values as a comparison table"""
    lines = [
        "## SPICE Simulation Results",
        "",
        "| Measurement | HEALTHY (Reference) | THIS CIRCUIT (Faulty) | Delta |",
        "|-------------|--------------------|-----------------------|-------|",
    ]

    for key in healthy:
        h_val = healthy[key]
        f_val = faulty[key]

        if isinstance(h_val, float):
            if h_val != 0:
                delta_pct = ((f_val - h_val) / h_val) * 100
                delta_str = f"{delta_pct:+.1f}%"
            else:
                delta_str = "-"
            lines.append(f"| {key} | {h_val} | {f_val} | {delta_str} |")
        else:
            match = "✓" if h_val == f_val else "≠"
            lines.append(f"| {key} | {h_val} | {f_val} | {match} |")

    return "\n".join(lines)


def run_diagnosis_test(fault_num=None, model="deepseek/deepseek-r1"):
    """Run SPICE-based diagnosis test"""

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY in .env")
        return None

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Select fault
    if fault_num is None:
        fault = random.choice(FAULTS)
    else:
        fault = FAULTS[fault_num - 1]

    faulty_values = FAULTY_SPICE_VALUES[fault['id']]

    print("=" * 70)
    print("  SPICE-BASED FAULT DIAGNOSIS TEST")
    print("  (No diagnostic hints - pure reasoning from SPICE comparison)")
    print("=" * 70)
    print(f"  Model: {model}")
    print(f"  Fault: {fault['name']} (hidden from AI)")
    print("=" * 70)
    print()

    # Build the prompt
    spice_comparison = format_spice_comparison(HEALTHY_SPICE_VALUES, faulty_values)

    prompt = f"""{CIRCUIT_DOCUMENTATION}

{TROUBLESHOOTING_PRINCIPLES}

---

# FAULT DIAGNOSIS TASK

A technician has reported that this voice card is malfunctioning. You have been
provided with SPICE simulation results comparing a known-good circuit to this
faulty unit.

{spice_comparison}

## Your Task

Analyze the differences between the HEALTHY reference and THIS CIRCUIT.
Based on your understanding of the circuit topology and component behavior,
identify which specific component has failed.

**Provide your diagnosis in this format:**

1. **Observations**: What differences do you see between healthy and faulty?
2. **Analysis**: What could cause these specific symptoms?
3. **Diagnosis**: The faulty component is: [component designator]
4. **Explanation**: Why this component failure explains all observed symptoms.
"""

    print("Sending to model...")
    print()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert electronics technician. Analyze circuit faults by comparing measurements to known-good references."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096,
            extra_headers={
                "HTTP-Referer": "https://github.com/aerotone-project",
                "X-Title": "SPICE Diagnosis Test"
            }
        )

        reply = response.choices[0].message.content

    except Exception as e:
        print(f"API Error: {e}")
        return None

    # Check if diagnosis is correct
    # Look for explicit diagnosis statement, not just keyword mention
    correct = False
    diagnosis_component = None

    reply_lower = reply.lower()

    # Look for the diagnosis section specifically
    diagnosis_patterns = [
        "the faulty component is:",
        "diagnosis:",
        "faulty component:",
        "the fault is:",
        "failed component:",
    ]

    diagnosis_section = ""
    for pattern in diagnosis_patterns:
        if pattern in reply_lower:
            start = reply_lower.find(pattern)
            # Get the next 100 chars after the pattern
            diagnosis_section = reply_lower[start:start+150]
            break

    # If no explicit diagnosis section, use full reply (fallback)
    if not diagnosis_section:
        diagnosis_section = reply_lower

    for kw in FAULT_KEYWORDS[fault['id']]:
        if kw in diagnosis_section:
            correct = True
            diagnosis_component = kw
            break

    # Print results
    print("=" * 70)
    print("  MODEL RESPONSE")
    print("=" * 70)
    print(reply)
    print()
    print("=" * 70)
    print("  RESULT")
    print("=" * 70)
    print(f"  Actual Fault: {fault['name']} ({fault['component']})")
    print(f"  Correct: {'YES' if correct else 'NO'}")
    if diagnosis_component:
        print(f"  Matched keyword: {diagnosis_component}")
    print()

    # Save report
    report_dir = Path(__file__).parent / 'reports' / 'spice_diagnosis'
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_short = model.split('/')[-1]
    report_path = report_dir / f"{model_short}_{fault['id']}_{timestamp}.md"

    report = f"""# SPICE-Based Fault Diagnosis Test

## Result: {'CORRECT' if correct else 'INCORRECT'}

| Field | Value |
|-------|-------|
| Model | `{model}` |
| Date | {datetime.now().strftime('%Y-%m-%d %H:%M')} |
| Actual Fault | {fault['name']} |
| Component | {fault['component']} |
| Correct | {'Yes' if correct else 'No'} |

## Test Design

This test provides:
- Circuit schematic and component list (educational)
- Brief explanation of PLL operation
- General troubleshooting principles
- SPICE reference values (healthy circuit)
- SPICE measurements (faulty circuit)

**NOT provided**: Specific fault signatures or diagnostic hints.

## SPICE Comparison Given

{spice_comparison}

## Model Response

{reply}

---
*SPICE-Based Diagnosis Test - No diagnostic hints provided*
"""

    report_path.write_text(report)
    print(f"  Report saved: {report_path}")

    return {
        'fault': fault,
        'correct': correct,
        'model': model,
        'response': reply
    }


if __name__ == "__main__":
    fault_num = None
    model = "deepseek/deepseek-r1"

    if len(sys.argv) > 1:
        try:
            fault_num = int(sys.argv[1])
            if fault_num < 1 or fault_num > 5:
                print("Fault number must be 1-5")
                sys.exit(1)
        except ValueError:
            print("Usage: python spice_diagnosis_test.py [fault_num 1-5] [model]")
            sys.exit(1)

    if len(sys.argv) > 2:
        model = sys.argv[2]

    run_diagnosis_test(fault_num, model)
