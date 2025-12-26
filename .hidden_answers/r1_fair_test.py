#!/usr/bin/env python3
"""
DEEPSEEK R1 FAIR TEST - WITH FULL DOCUMENTATION

This test gives R1 the SAME documentation that Claude had access to,
making it a fair comparison.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
import numpy as np
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench

MODEL = "deepseek/deepseek-r1-0528"

# ============================================================================
# FULL DOCUMENTATION - Same as Claude had access to
# ============================================================================

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
│               │                      │  CONTROL VOLTAGE (loop_filter_out)  │
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
│               │   │  pickup → GAIN STAGE (×100) → OUTPUT│          │     │
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

## Component List - Voice Card

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

## Expected Healthy Values (220 Hz Target)

| Probe Point | Expected Value | Notes |
|-------------|----------------|-------|
| v_supply | 12.0V DC | Motor supply |
| v_logic | 15.0V DC | CD4046 supply |
| loop_filter_out | ~7.5V DC | VCO control voltage, stable |
| loop_filter (AC) | <50mV RMS | Minimal ripple when healthy |
| motor_voltage | ~6.0V DC | Depends on load |
| motor_current | ~0.03A | Normal running current |
| motor_rpm | ~1100 RPM | For 220 Hz target |
| cond_opamp_out | ±12V square wave | Clean edges, ~220 Hz |

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
- motor_voltage REDUCED by 2-4V (reads ~3V instead of ~6V)
- Motor runs SLOW despite PLL trying to compensate
- Asymmetric H-bridge drive (one half weaker)
- Q1 collector-emitter may show partial short or high resistance
**Key Test:** Measure motor_voltage - if significantly LOW with normal v_supply, suspect Q1

### F003: Noisy Op-Amp U2 (Signal Conditioner)
**Component:** LM358 Dual Op-Amp U2
**Root Cause:** Internal noise, oscillation, or degradation
**Symptoms:**
- cond_opamp_out shows EXCESSIVE NOISE or random spikes
- Output may have HIGH FREQUENCY oscillation superimposed
- Feedback signal to PLL is corrupted
- PLL may have difficulty locking (loop filter voltage unstable)
**Key Test:** Capture cond_opamp_out waveform - if noisy/spiky instead of clean square wave, suspect U2

### F004: Open Feedback Resistor R9 (Signal Conditioner)
**Component:** 100kΩ Feedback Resistor R9
**Root Cause:** Resistor open (broken lead, burned)
**Symptoms:**
- cond_opamp_out SATURATED at +12V or -12V constantly
- Op-amp has infinite gain (no feedback)
- No linear amplification - just rail-to-rail output
- May oscillate rapidly between rails
**Key Test:** If cond_opamp_out is stuck at ±12V with no signal, suspect R9

### F005: Shorted Flyback Diode D2
**Component:** 1N4001 Flyback Diode D2
**Root Cause:** Diode shorted internally
**Symptoms:**
- motor_voltage REDUCED (60-70% of normal)
- motor_current INCREASED (1.5× normal, ~0.045A vs 0.03A)
- H-bridge partially bypassed through shorted diode
- Motor runs slow, may overheat
**Key Test:** If motor_voltage low AND motor_current high, suspect shorted diode

## Diagnostic Strategy

1. **ALWAYS check power supplies first** (v_supply, v_logic)
2. **Check loop filter output** - this is central to PLL operation
   - Low voltage + drift = Leaky capacitor C2
3. **Check motor parameters** - motor_voltage, motor_current
   - Low voltage, normal current = Burned transistor Q1
   - Low voltage, HIGH current = Shorted diode D2
4. **Check signal conditioner output** - cond_opamp_out
   - Noisy/spiky = Noisy op-amp U2
   - Saturated ±12V = Open resistor R9

## Key Probe Points by Category

**Power:** v_supply, v_logic
**Loop Filter:** loop_filter_out, loop_filter_cap_voltage
**Motor:** motor_voltage, motor_current, motor_rpm
**Conditioner:** cond_opamp_out, pickup_raw
'''

# ============================================================================

SYSTEM_PROMPT = f"""You are an expert electronics technician diagnosing a fault in an AeroTone Model 12 circuit.

{FULL_DOCUMENTATION}

YOUR TASK:
1. Systematically probe the circuit using the available tools
2. Compare measurements to the expected healthy values
3. Match symptoms to the fault signatures above
4. Submit your diagnosis with the COMPONENT NAME (e.g., "Loop Filter Capacitor C2", "H-Bridge Transistor Q1", "Signal Conditioner Op-Amp U2", "Feedback Resistor R9", "Flyback Diode D2")

Think carefully about which fault signature matches your measurements before diagnosing."""


PROBE_TOOLS = [
    {"type": "function", "function": {
        "name": "measure_vdc",
        "description": "Measure DC voltage at a probe point",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point: v_supply, v_logic, loop_filter_out, motor_voltage, cond_opamp_out, etc."}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "measure_vac",
        "description": "Measure AC voltage (RMS) - useful for detecting ripple/noise",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "measure_current",
        "description": "Measure DC current at motor_current probe point",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Use 'motor_current' to measure motor current"}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "capture_waveform",
        "description": "Capture waveform: returns Vpp, Vavg, Vac_rms, frequency",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"},
            "duration": {"type": "number", "default": 0.1}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Get circuit status: target frequency and motor RPM",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "submit_diagnosis",
        "description": "Submit your final diagnosis. Use component name like 'Loop Filter Capacitor C2' or 'H-Bridge Transistor Q1'",
        "parameters": {"type": "object", "properties": {
            "diagnosis": {"type": "string", "description": "The faulty component name"}
        }, "required": ["diagnosis"]}
    }}
]


# Fault definitions
FAULTS = [
    {'id': 'F001', 'name': 'Leaky Electrolytic Capacitor C2',
     'component': 'Loop Filter Capacitor C2', 'keywords': ['capacitor', 'c2', 'loop filter', 'electrolytic']},
    {'id': 'F002', 'name': 'Burned Power Transistor Q1',
     'component': 'H-Bridge Transistor Q1', 'keywords': ['transistor', 'q1', 'h-bridge', 'burned', '2n3055']},
    {'id': 'F003', 'name': 'Noisy Op-Amp U2',
     'component': 'Signal Conditioner Op-Amp U2', 'keywords': ['op-amp', 'opamp', 'u2', 'lm358', 'conditioner', 'noisy']},
    {'id': 'F004', 'name': 'Open Feedback Resistor R9',
     'component': 'Feedback Resistor R9', 'keywords': ['resistor', 'r9', 'feedback', 'open']},
    {'id': 'F005', 'name': 'Shorted Flyback Diode D2',
     'component': 'Flyback Diode D2', 'keywords': ['diode', 'd2', 'flyback', 'shorted', '1n4001']},
]


def inject_fault(voice, fault_id):
    """Inject a specific fault into the circuit"""
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
                voice.driver.motor_voltage = max(0, voice.driver.motor_voltage - 3.0)
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
            m = bench.measure_vdc(args["point"])  # Current is read as voltage across sense resistor
            return f"{args['point']}: {m.value:.4f} A"
        elif name == "capture_waveform":
            w = bench.capture_waveform(args["point"], args.get("duration", 0.1))
            return f"{args['point']}: Vpp={w.v_pp:.3f}V, Vavg={w.v_avg:.3f}V, Vac_rms={w.v_ac_rms:.4f}V, freq={w.frequency:.1f}Hz"
        elif name == "get_status":
            rpm = voice.motor.omega * 60 / (2 * np.pi)
            return f"Target: {voice.target_frequency:.0f}Hz, Motor RPM: {rpm:.0f}, Expected RPM: {voice.target_frequency * 5:.0f}"
        elif name == "submit_diagnosis":
            return args.get("diagnosis", "")
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


def check_diagnosis(diagnosis: str, fault: dict) -> bool:
    """Check if diagnosis matches the fault"""
    diagnosis_lower = diagnosis.lower()
    # Check for any keyword match
    for keyword in fault['keywords']:
        if keyword in diagnosis_lower:
            return True
    return False


@dataclass
class TestResult:
    fault_id: str
    fault_name: str
    component: str
    r1_diagnosis: str
    correct: bool
    measurements: int
    turns: int
    reasoning_summary: str


def test_single_fault(client, fault: dict) -> TestResult:
    """Test R1 on a single fault with full documentation"""

    print(f"\n{'='*70}")
    print(f"  TESTING: {fault['name']}")
    print(f"  Expected Component: {fault['component']}")
    print(f"{'='*70}")

    # Create circuit
    params = SpiceVoiceParams(enable_thermal=False)
    voice = SpiceVoice(params=params, sample_rate=44100)
    inject_fault(voice, fault['id'])

    # Warm up
    voice.set_target_frequency(220.0)
    for _ in range(int(44100 * 0.5)):
        voice.update_physics(1/44100)

    bench = TestBench(voice)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "A fault has been injected. Use the probe tools to diagnose it, then submit_diagnosis with the component name."}
    ]

    measurements = 0
    diagnosis = None
    reasoning_parts = []
    max_turns = 15

    for turn in range(1, max_turns + 1):
        print(f"  Turn {turn}...", end=" ", flush=True)

        try:
            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=PROBE_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
                stream=True,
                extra_headers={
                    "HTTP-Referer": "https://github.com/aerotone-project",
                    "X-Title": "AeroTone R1 Fair Test"
                }
            )

            content = ""
            tool_calls = {}
            current_id = None

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                if delta.content:
                    content += delta.content
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.id:
                            current_id = tc.id
                            tool_calls[current_id] = {"name": "", "args": ""}
                        if tc.function and current_id:
                            if tc.function.name:
                                tool_calls[current_id]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[current_id]["args"] += tc.function.arguments

            if content:
                reasoning_parts.append(content[:200])

            if tool_calls:
                tc_list = [{"id": tid, "type": "function",
                           "function": {"name": t["name"], "arguments": t["args"]}}
                          for tid, t in tool_calls.items() if t["name"]]

                if tc_list:
                    messages.append({"role": "assistant", "content": content, "tool_calls": tc_list})

                    for tid, tdata in tool_calls.items():
                        if not tdata["name"]:
                            continue
                        try:
                            args = json.loads(tdata["args"]) if tdata["args"] else {}
                        except:
                            args = {}

                        result = execute_tool(bench, voice, tdata["name"], args)
                        print(f"{tdata['name'][:10]}", end=" ", flush=True)

                        if tdata["name"] == "submit_diagnosis":
                            diagnosis = result
                            messages.append({"role": "tool", "tool_call_id": tid, "content": result})
                            break
                        else:
                            measurements += 1
                            messages.append({"role": "tool", "tool_call_id": tid, "content": result})

                    if diagnosis:
                        break
                else:
                    messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "Please use probe tools or submit_diagnosis."})

        except Exception as e:
            print(f"Error: {e}")
            break

    # Check result
    correct = check_diagnosis(diagnosis, fault) if diagnosis else False
    status = "✅ CORRECT" if correct else "❌ WRONG"

    print(f"\n  R1 Diagnosis: {diagnosis}")
    print(f"  Actual: {fault['component']}")
    print(f"  Result: {status}")

    return TestResult(
        fault_id=fault['id'],
        fault_name=fault['name'],
        component=fault['component'],
        r1_diagnosis=diagnosis or "No diagnosis",
        correct=correct,
        measurements=measurements,
        turns=turn,
        reasoning_summary=" | ".join(reasoning_parts[:3])
    )


def run_fair_test():
    """Run fair test with full documentation"""

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY")
        return

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    print("\n" + "="*70)
    print("  DEEPSEEK R1 FAIR TEST")
    print("  (With FULL documentation - same as Claude)")
    print("  Model:", MODEL)
    print("="*70)

    results = []

    for fault in FAULTS:
        try:
            result = test_single_fault(client, fault)
            results.append(result)
        except Exception as e:
            print(f"  FAILED: {e}")

    # Summary
    correct = sum(1 for r in results if r.correct)
    total = len(results)

    print("\n" + "="*70)
    print("  FINAL RESULTS")
    print("="*70)
    print(f"\n  ACCURACY: {correct}/{total} ({correct/total*100:.0f}%)")
    print()
    print(f"  {'Fault':<40} {'R1 Said':<25} {'Result'}")
    print("  " + "-"*75)

    for r in results:
        status = "✅" if r.correct else "❌"
        diag = r.r1_diagnosis[:25] if r.r1_diagnosis else "None"
        print(f"  {r.fault_name:<40} {diag:<25} {status}")

    # Save report
    report_dir = Path(__file__).parent / 'reports'
    report_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = report_dir / f"R1_FAIR_TEST_{timestamp}.md"

    md = f"""# DeepSeek R1 Fair Test Results

**Model:** `{MODEL}`
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Accuracy:** {correct}/{total} ({correct/total*100:.0f}%)

## Test Conditions
- R1 received the SAME full documentation that Claude had access to
- Including: circuit schematics, component list, fault signatures, diagnostic strategy

## Results

| Fault | Component | R1 Diagnosis | Correct |
|-------|-----------|--------------|---------|
"""

    for r in results:
        status = "✅" if r.correct else "❌"
        md += f"| {r.fault_name} | {r.component} | {r.r1_diagnosis[:40]} | {status} |\n"

    md += f"""

## Comparison

| Model | Accuracy | Notes |
|-------|----------|-------|
| **Claude Opus 4.5** | High | "Excelled" |
| **Claude Haiku** | Good | "Very well" |
| **DeepSeek R1** | {correct/total*100:.0f}% | This test (fair conditions) |

---
*Generated by AeroTone Fair Test*
"""

    report_path.write_text(md)
    print(f"\n  Report: {report_path}")

    return results


if __name__ == "__main__":
    run_fair_test()
