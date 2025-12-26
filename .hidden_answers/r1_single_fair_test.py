#!/usr/bin/env python3
"""
R1 SINGLE FAIR TEST

Runs ONE fault diagnosis with FULL documentation (same as Claude had).
Saves complete reasoning to a report.

Usage:
    python fault_challenge/r1_single_fair_test.py [fault_number]

    fault_number: 1-5 (default: random)
        1 = Leaky Capacitor C2
        2 = Burned Transistor Q1
        3 = Noisy Op-Amp U2
        4 = Open Resistor R9
        5 = Shorted Diode D2
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
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench
import numpy as np

MODEL = "deepseek/deepseek-r1"

# =============================================================================
# FULL DOCUMENTATION - EXACTLY what Claude had access to
# =============================================================================

FULL_DOCUMENTATION = '''
# AeroTone Model 12 - Complete Technical Documentation

## System Overview

The AeroTone Model 12 is a 1979 electromechanical musical instrument that generates
tones via spinning propellers. Pitch is determined by propeller RPM (Blade Passage
Frequency = RPM × 12 blades / 60).

For 220 Hz (A3): RPM = 220 × 5 = 1,100 RPM

## Voice Card Circuit Schematic

```
                            VOICE CARD SCHEMATIC
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   +15V (V_logic) ──────────┬──────────────────────────────────────────     │
│                            │                                                │
│                     ┌──────┴──────┐                                         │
│                     │   CD4046    │                                         │
│   REF IN ──────────┤3  PLL IC    │                                         │
│   (target freq)    │             ├──13── PC2 OUT ──┐                       │
│                    │             │                 │                        │
│   COMP IN ────┬────┤14  SIG IN  │                 │                        │
│   (feedback)  │    └─────────────┘                 │                        │
│               │                                    │                        │
│               │        LOOP FILTER                 │                        │
│               │        ───────────                 │                        │
│               │              ┌─────────────────────┘                        │
│               │              │                                              │
│               │              ▼                                              │
│               │           R3 100kΩ                                          │
│               │              │                                              │
│               │              ├───────────────┐                              │
│               │              │               │                              │
│               │             ═╪═ C2          ═╪═ C3                          │
│               │              │ 10µF          │ 100nF                        │
│               │              ▼               ▼                              │
│               │             GND             GND                             │
│               │              │                                              │
│               │              └───────┬───────────────────────────────┐     │
│               │                      │  CONTROL VOLTAGE              │     │
│               │                      ▼                               │     │
│   +12V (V_supply) ───────────────────┤                               │     │
│               │                      │                               │     │
│               │    ┌─────────────────┴──────────────────┐            │     │
│               │    │           H-BRIDGE                 │            │     │
│               │    │                                    │            │     │
│               │    ▼                                    ▼            │     │
│               │ ┌──────┐                            ┌──────┐         │     │
│               │ │ Q1   │ (2N3055 NPN)               │ Q3   │         │     │
│               │ │HIGH  │                            │HIGH  │         │     │
│               │ │SIDE  │                            │SIDE  │         │     │
│               │ └──┬───┘                            └──┬───┘         │     │
│               │    │      ┌───────────────────┐       │             │     │
│               │    ├──────┤    DC MOTOR       ├───────┤             │     │
│               │    │      │  (motor_voltage)  │       │             │     │
│               │    │      └───────────────────┘       │             │     │
│               │ ┌──┴───┐        │                 ┌──┴───┐          │     │
│               │ │ Q2   │ (MJ2955 PNP)            │ Q4   │          │     │
│               │ │LOW   │        │                │LOW   │          │     │
│               │ │SIDE  │        │                │SIDE  │          │     │
│               │ └──┬───┘        │                └──┬───┘          │     │
│               │    ▼            │                   ▼              │     │
│               │   GND           │                  GND             │     │
│               │                 │                                  │     │
│               │   D1-D4: 1N4001 flyback diodes across transistors  │     │
│               │                 │                                  │     │
│               │   MAGNETIC PICKUP (on propeller hub)               │     │
│               │                 │                                  │     │
│               │                 ▼                                  │     │
│               │   ┌─────────────────────────────────────┐          │     │
│               │   │  SIGNAL CONDITIONER (U2 = LM358)   │          │     │
│               │   │                                     │          │     │
│               │   │  pickup → GAIN STAGE (×100) → OUT  │          │     │
│               │   │           (R8=1k, R9=100k)         │          │     │
│               │   │                                     │          │     │
│               │   │  Output: cond_opamp_out            │          │     │
│               │   │  (square wave to PLL feedback)     │          │     │
│               │   └─────────────────────────────────────┘          │     │
│               │                 │                                  │     │
│               └─────────────────┴──────────────────────────────────┘     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Component List

| Component | Value | Function |
|-----------|-------|----------|
| U1 | CD4046 | Phase-Locked Loop IC |
| U2 | LM358 | Signal Conditioner Op-Amp |
| Q1, Q3 | 2N3055 NPN | H-Bridge High-Side Transistors |
| Q2, Q4 | MJ2955 PNP | H-Bridge Low-Side Transistors |
| D1-D4 | 1N4001 | Flyback Diodes |
| R3 | 100kΩ | Loop Filter Resistor |
| C2 | 10µF | Loop Filter Capacitor (ELECTROLYTIC) |
| C3 | 100nF | Loop Filter HF Bypass |
| R8 | 1kΩ | Conditioner Input Resistor |
| R9 | 100kΩ | Conditioner Feedback Resistor |

## Expected Healthy Values (220 Hz Target) - SPICE VALIDATED

| Probe Point | Expected Value | Notes |
|-------------|----------------|-------|
| v_supply | 12.0V DC | Motor supply |
| v_logic | 15.0V DC | CD4046 supply |
| loop_filter_out | ~7.5V DC | VCO control voltage, stable |
| loop_filter (AC) | <2mV ripple | Minimal ripple when healthy |
| motor_voltage | ~6.0V DC | Depends on load |
| motor_current | ~0.44A | Normal running current |
| motor_rpm | ~1100 RPM | For 220 Hz target |
| cond_opamp_out | Vpp ~10V | Clean sine/square, ~220 Hz |

## Fault Signatures - CRITICAL DIAGNOSTIC INFORMATION

### F001: Leaky Electrolytic Capacitor C2 (Loop Filter)
**Component:** Loop Filter Capacitor C2 (10µF electrolytic)
**Root Cause:** Electrolyte degradation causes DC leakage current
**Symptoms:**
- loop_filter_out voltage DRIFTS toward V_supply/2 (~6V instead of ~7.5V)
- Voltage is UNSTABLE, may wander up/down
- Increased AC ripple on loop_filter_out (>80mV vs <50mV normal)
- Motor speed may hunt/oscillate as PLL struggles to lock
**Key Test:** Measure loop_filter_out DC voltage - if LOW and DRIFTING, suspect C2

### F002: Burned Power Transistor Q1 (H-Bridge High-Side)
**Component:** 2N3055 NPN Transistor Q1
**Root Cause:** Excessive current caused junction damage
**Symptoms:**
- motor_voltage REDUCED (~3V instead of ~6V)
- motor_current REDUCED (~0.03A instead of ~0.44A) - CRITICAL DIFFERENTIATOR
- Damaged transistor has high series resistance, restricting BOTH voltage AND current
**Key Test:** If motor_voltage LOW AND motor_current LOW, suspect Q1

### F003: Noisy Op-Amp U2 (Signal Conditioner)
**Component:** LM358 Dual Op-Amp U2
**Root Cause:** Internal noise, oscillation, or degradation
**Symptoms:**
- cond_opamp_out shows EXCESSIVE NOISE or random spikes
- Output may have HIGH FREQUENCY oscillation superimposed
- Vpp may exceed normal 24V (overshoots beyond ±12V rails)
- Feedback signal to PLL is corrupted
**Key Test:** Capture cond_opamp_out waveform - if Vpp > 24V or noisy, suspect U2

### F004: Open Feedback Resistor R9 (Signal Conditioner)
**Component:** 100kΩ Feedback Resistor R9
**Root Cause:** Resistor open (broken lead, burned)
**Symptoms:**
- cond_opamp_out SATURATED at +12V or -12V constantly
- Op-amp has infinite gain (no feedback)
- No linear amplification - just rail-to-rail output
**Key Test:** If cond_opamp_out is stuck at ±12V with no signal variation, suspect R9

### F005: Shorted Flyback Diode D2
**Component:** 1N4001 Flyback Diode D2
**Root Cause:** Diode shorted internally
**Symptoms:**
- motor_voltage REDUCED (~3V instead of ~6V)
- motor_current INCREASED (~0.75A instead of ~0.44A) - CRITICAL DIFFERENTIATOR
- Short creates parallel current path, INCREASING total current while reducing voltage
**Key Test:** If motor_voltage LOW AND motor_current HIGH, suspect shorted diode D2

## Diagnostic Strategy - SPICE VALIDATED

1. **ALWAYS check power supplies first** (v_supply, v_logic)
2. **Check loop filter output** - central to PLL operation
   - Ripple > 20mV (vs <2mV healthy) = Leaky capacitor C2
3. **Check motor parameters** - CRITICAL for F002 vs F005
   - Low voltage (~3V) + LOW current (~0.03A) = Burned transistor Q1
   - Low voltage (~3V) + HIGH current (~0.75A) = Shorted diode D2
4. **Check signal conditioner output** - cond_opamp_out
   - Vpp > 10V with noise = Noisy op-amp U2
   - Vpp = 24V exactly (square wave at rails) = Open resistor R9
'''

FAULTS = [
    {'id': 'F001', 'name': 'Leaky Electrolytic Capacitor C2',
     'component': 'Loop Filter Capacitor C2',
     'keywords': ['capacitor', 'c2', 'loop filter', 'electrolytic']},
    {'id': 'F002', 'name': 'Burned Power Transistor Q1',
     'component': 'H-Bridge Transistor Q1',
     'keywords': ['transistor', 'q1', 'h-bridge', 'burned', '2n3055']},
    {'id': 'F003', 'name': 'Noisy Op-Amp U2',
     'component': 'Signal Conditioner Op-Amp U2',
     'keywords': ['op-amp', 'opamp', 'u2', 'lm358', 'conditioner', 'noisy']},
    {'id': 'F004', 'name': 'Open Feedback Resistor R9',
     'component': 'Feedback Resistor R9',
     'keywords': ['resistor', 'r9', 'feedback', 'open']},
    {'id': 'F005', 'name': 'Shorted Flyback Diode D2',
     'component': 'Flyback Diode D2',
     'keywords': ['diode', 'd2', 'flyback', 'shorted', '1n4001']},
]

PROBE_TOOLS = [
    {"type": "function", "function": {
        "name": "measure_vdc",
        "description": "Measure DC voltage at a probe point",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "measure_vac",
        "description": "Measure AC voltage (RMS) - detects ripple/noise",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "measure_current",
        "description": "Measure current (use 'motor_current')",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "capture_waveform",
        "description": "Capture waveform: Vpp, Vavg, Vac_rms, frequency",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"},
            "duration": {"type": "number", "default": 0.1}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Get circuit status: target freq, motor RPM",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "submit_diagnosis",
        "description": "Submit final diagnosis with component name",
        "parameters": {"type": "object", "properties": {
            "diagnosis": {"type": "string", "description": "Faulty component name"}
        }, "required": ["diagnosis"]}
    }}
]


def inject_fault(voice, fault_id):
    """Inject fault into circuit"""
    if fault_id == 'F001':  # Leaky capacitor
        original = voice.loop_filter.update
        def faulty(input_voltage, dt, high_z=False):
            result = original(input_voltage, dt, high_z=high_z)
            mid = voice.params.vdd / 2
            voice.loop_filter.output_voltage -= (voice.loop_filter.output_voltage - mid) * 0.15 * dt * 100
            voice.loop_filter.output_voltage += np.random.randn() * 0.02
            return voice.loop_filter.output_voltage
        voice.loop_filter.update = faulty

    elif fault_id == 'F002':  # Burned transistor
        original = voice.driver.update
        def faulty(dt, motor_back_emf=0.0):
            result = original(dt, motor_back_emf)
            if voice.driver.motor_voltage > 0:
                # Reduce voltage (damaged transistor has high resistance)
                voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 3.0)
                # MUST recalculate current based on new voltage
                if voice.driver.motor_voltage > motor_back_emf:
                    voice.driver.motor_current = (voice.driver.motor_voltage - motor_back_emf) / 2.0
                else:
                    voice.driver.motor_current = 0.0
            return result
        voice.driver.update = faulty

    elif fault_id == 'F003':  # Noisy op-amp
        original = voice.conditioner.update
        drift = [0.0]
        def faulty(dt, input_voltage):
            original(dt, input_voltage)
            voice.conditioner.amplified_voltage += np.random.randn() * 0.8
            drift[0] += np.random.randn() * 0.005
            drift[0] = np.clip(drift[0], -2.0, 2.0)
            voice.conditioner.amplified_voltage += drift[0]
            # Occasional overshoot beyond rails
            if abs(voice.conditioner.amplified_voltage) > 11.5:
                voice.conditioner.amplified_voltage += np.random.uniform(0.5, 2.0) * np.sign(voice.conditioner.amplified_voltage)
        voice.conditioner.update = faulty

    elif fault_id == 'F004':  # Open resistor
        original = voice.conditioner.update
        def faulty(dt, input_voltage):
            original(dt, input_voltage)
            voice.conditioner.amplified_voltage = 12.0 if input_voltage > 0 else -12.0
        voice.conditioner.update = faulty

    elif fault_id == 'F005':  # Shorted diode
        original = voice.driver.update
        def faulty(dt, motor_back_emf=0.0):
            result = original(dt, motor_back_emf)
            voice.driver.motor_voltage *= 0.6
            voice.driver.motor_current *= 1.5
            return result
        voice.driver.update = faulty


def execute_tool(bench, voice, name, args):
    """Execute probe tool"""
    try:
        if name == "measure_vdc":
            m = bench.measure_vdc(args["point"])
            return f"{args['point']}: {m.value:.4f} VDC"
        elif name == "measure_vac":
            m = bench.measure_vac(args["point"])
            return f"{args['point']}: {m.value:.4f} VAC RMS"
        elif name == "measure_current":
            m = bench.measure_vdc(args["point"])
            return f"{args['point']}: {m.value:.4f} A"
        elif name == "capture_waveform":
            w = bench.capture_waveform(args["point"], args.get("duration", 0.1))
            return f"{args['point']}: Vpp={w.v_pp:.3f}V, Vavg={w.v_avg:.3f}V, Vac_rms={w.v_ac_rms:.4f}V, freq={w.frequency:.1f}Hz"
        elif name == "get_status":
            rpm = voice.motor.omega * 60 / (2 * np.pi)
            return f"Target: {voice.target_frequency:.0f}Hz, Motor RPM: {rpm:.0f}"
        elif name == "submit_diagnosis":
            return args.get("diagnosis", "")
        return f"Unknown: {name}"
    except Exception as e:
        return f"Error: {e}"


def run_single_test(fault_num=None):
    """Run single fair test"""

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY in .env")
        return

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Select fault
    if fault_num is None:
        fault = random.choice(FAULTS)
    else:
        fault = FAULTS[fault_num - 1]

    print("=" * 70)
    print("  R1 FAIR TEST - WITH FULL DOCUMENTATION")
    print("  (Same information Claude had access to)")
    print("=" * 70)
    print(f"  Model: {MODEL}")
    print(f"  Fault: {fault['name']}")
    print(f"  Component: {fault['component']}")
    print("=" * 70)
    print()

    # Create circuit
    params = SpiceVoiceParams(enable_thermal=False)
    voice = SpiceVoice(params=params, sample_rate=44100)
    inject_fault(voice, fault['id'])

    # Warm up
    voice.set_target_frequency(220.0)
    for _ in range(int(44100 * 0.5)):
        voice.update_physics(1/44100)

    bench = TestBench(voice)

    SYSTEM = f"""You are an expert electronics technician diagnosing a fault.

{FULL_DOCUMENTATION}

YOUR TASK: Use probe tools systematically, then submit_diagnosis with the component name."""

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "A fault has been injected into this circuit. Diagnose it."}
    ]

    reasoning_log = []
    measurements_log = []
    diagnosis = None
    max_turns = 15

    for turn in range(1, max_turns + 1):
        print(f"Turn {turn}:", end=" ", flush=True)

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=PROBE_TOOLS,
                max_tokens=4096,
                extra_headers={
                    "HTTP-Referer": "https://github.com/aerotone-project",
                    "X-Title": "R1 Fair Test"
                }
            )

            msg = resp.choices[0].message
            content = msg.content or ""

            if content:
                reasoning_log.append({"turn": turn, "content": content})
                print(f"[reasoning: {len(content)} chars]", end=" ")

            if msg.tool_calls:
                tc_list = [{"id": tc.id, "type": "function",
                           "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                          for tc in msg.tool_calls]
                messages.append({"role": "assistant", "content": content, "tool_calls": tc_list})

                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except:
                        args = {}

                    result = execute_tool(bench, voice, tc.function.name, args)
                    print(f"{tc.function.name}", end=" ", flush=True)
                    measurements_log.append({"tool": tc.function.name, "args": args, "result": result})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

                    if tc.function.name == "submit_diagnosis":
                        diagnosis = args.get("diagnosis", "")
                        break

                print()
                if diagnosis:
                    break
            else:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "Please use probe tools or submit_diagnosis."})
                print()

        except Exception as e:
            print(f"Error: {e}")
            break

    # Check result
    correct = False
    if diagnosis:
        d_lower = diagnosis.lower()
        correct = any(kw in d_lower for kw in fault['keywords'])

    # Print results
    print()
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  R1 Diagnosis: {diagnosis}")
    print(f"  Actual Fault: {fault['component']}")
    print(f"  Correct: {'YES' if correct else 'NO'}")
    print()

    # Save report
    report_dir = Path(__file__).parent / 'reports' / 'r1_fair'
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = report_dir / f"r1_fair_{fault['id']}_{timestamp}.md"

    md = f"""# DeepSeek R1 Fair Test Report

## Result: {'CORRECT' if correct else 'INCORRECT'}

| Field | Value |
|-------|-------|
| Model | `{MODEL}` |
| Date | {datetime.now().strftime('%Y-%m-%d %H:%M')} |
| Fault | {fault['name']} |
| Component | {fault['component']} |
| R1 Diagnosis | {diagnosis} |
| Correct | {'Yes' if correct else 'No'} |
| Measurements | {len([m for m in measurements_log if m['tool'] != 'submit_diagnosis'])} |
| Turns | {turn} |

## Test Conditions

This test used the **FULL documentation** that Claude had access to, including:
- Complete circuit schematic
- Component list
- Expected healthy values
- Detailed fault signatures with specific thresholds
- Diagnostic strategy

## Measurements Taken

| # | Tool | Result |
|---|------|--------|
"""

    for i, m in enumerate(measurements_log, 1):
        md += f"| {i} | {m['tool']} | {m['result']} |\n"

    md += "\n## R1 Reasoning Process\n\n"

    for r in reasoning_log:
        md += f"### Turn {r['turn']}\n\n"
        md += f"```\n{r['content']}\n```\n\n"

    md += """
---
*Generated by R1 Fair Test - Same documentation as Claude*
"""

    report_path.write_text(md)
    print(f"  Report saved: {report_path}")

    return {
        "fault": fault,
        "diagnosis": diagnosis,
        "correct": correct,
        "measurements": measurements_log,
        "reasoning": reasoning_log
    }


if __name__ == "__main__":
    fault_num = None
    if len(sys.argv) > 1:
        try:
            fault_num = int(sys.argv[1])
            if fault_num < 1 or fault_num > 5:
                print("Fault number must be 1-5")
                sys.exit(1)
        except ValueError:
            print("Usage: python r1_single_fair_test.py [fault_number 1-5]")
            sys.exit(1)

    run_single_test(fault_num)
