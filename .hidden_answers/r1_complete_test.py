#!/usr/bin/env python3
"""
COMPLETE R1 FAULT DIAGNOSIS TEST

Tests DeepSeek R1 against each specific fault type to get comprehensive results.
Generates a full report comparing R1 vs Claude performance.
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
import numpy as np
from aerotone.spice_voice import SpiceVoice, SpiceVoiceParams
from aerotone.test_equipment import TestBench

MODEL = "deepseek/deepseek-r1-0528"

# All fault types
FAULTS = [
    {'id': 'F001', 'name': 'Leaky Electrolytic Capacitor C1',
     'component': 'Loop Filter Capacitor (C1)', 'category': 'capacitor'},
    {'id': 'F002', 'name': 'Burned Power Transistor Q1',
     'component': 'H-Bridge High-Side Transistor (Q1)', 'category': 'transistor'},
    {'id': 'F003', 'name': 'Noisy Op-Amp U2',
     'component': 'Signal Conditioner Op-Amp (U2)', 'category': 'opamp'},
    {'id': 'F004', 'name': 'Open Feedback Resistor R3',
     'component': 'Feedback Resistor (R3)', 'category': 'resistor'},
    {'id': 'F005', 'name': 'Shorted Flyback Diode D2',
     'component': 'H-Bridge Flyback Diode (D2)', 'category': 'diode'},
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
        "description": "Measure AC voltage (RMS) - detects noise/ripple",
        "parameters": {"type": "object", "properties": {
            "point": {"type": "string", "description": "Probe point name"}
        }, "required": ["point"]}
    }},
    {"type": "function", "function": {
        "name": "capture_waveform",
        "description": "Capture waveform: Vpp, Vavg, frequency, duty cycle",
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
        "description": "Submit final diagnosis of faulty component",
        "parameters": {"type": "object", "properties": {
            "diagnosis": {"type": "string", "description": "Faulty component name"}
        }, "required": ["diagnosis"]}
    }}
]

SYSTEM_PROMPT = """You are an expert electronics technician diagnosing an AeroTone Model 12 circuit fault.

## Circuit
- Power: V_supply=12V, V_logic=15V
- CD4046 PLL controls motor speed via loop filter
- H-Bridge (Q1-Q4 transistors, D1-D4 flyback diodes) drives motor
- Signal conditioner (op-amp U2) amplifies pickup feedback

## Expected Values (220Hz target)
- V_supply: 12.0V, V_logic: 15.0V
- Loop filter output: ~7.5V stable, low ripple (<50mV)
- Motor voltage: ~6V, Motor current: ~0.03A
- Conditioner output: square wave within ±12V

## Fault Signatures
1. **Leaky Capacitor C1**: Loop filter voltage DRIFTS toward mid-rail, unstable
2. **Burned Transistor Q1**: Motor voltage REDUCED by 2-3V, asymmetric drive
3. **Noisy Op-Amp U2**: Conditioner output has EXCESSIVE NOISE, random spikes
4. **Open Resistor R3**: Conditioner output SATURATED at ±12V constantly
5. **Shorted Diode D2**: Motor voltage REDUCED, current INCREASED (1.5x normal)

## Key Diagnostic Points
- loop_filter_out, loop_filter_cap_voltage (capacitor issues)
- motor_voltage, motor_current (transistor/diode issues)
- cond_opamp_out (op-amp issues)

Measure systematically, then submit_diagnosis with the component name."""


def inject_fault(voice, fault_id):
    """Inject a specific fault"""
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


@dataclass
class TestResult:
    fault_id: str
    fault_name: str
    component: str
    r1_diagnosis: str
    correct: bool
    measurements: int
    turns: int
    reasoning: List[str]


def execute_tool(bench, voice, name, args):
    """Execute probe tool"""
    try:
        if name == "measure_vdc":
            m = bench.measure_vdc(args["point"])
            return f"{args['point']}: {m.value:.4f} VDC"
        elif name == "measure_vac":
            m = bench.measure_vac(args["point"])
            return f"{args['point']}: {m.value:.4f} VAC"
        elif name == "capture_waveform":
            w = bench.capture_waveform(args["point"], args.get("duration", 0.1))
            return f"{args['point']}: Vpp={w.v_pp:.3f}V, Vavg={w.v_avg:.3f}V, freq={w.frequency:.1f}Hz"
        elif name == "get_status":
            rpm = voice.motor.omega * 60 / (2 * np.pi)
            return f"Target: {voice.target_frequency:.0f}Hz, RPM: {rpm:.0f}"
        elif name == "submit_diagnosis":
            return args.get("diagnosis", "")
        return f"Unknown: {name}"
    except Exception as e:
        return f"Error: {e}"


def test_single_fault(client, fault: dict) -> TestResult:
    """Test R1 on a single specific fault"""

    print(f"\n{'='*60}")
    print(f"  Testing: {fault['name']}")
    print(f"  Component: {fault['component']}")
    print(f"{'='*60}")

    # Create circuit with specific fault
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
        {"role": "user", "content": "Diagnose the fault. Use probe tools, then submit_diagnosis."}
    ]

    reasoning = []
    measurements = 0
    diagnosis = None
    max_turns = 12

    for turn in range(1, max_turns + 1):
        print(f"\n  Turn {turn}...", end=" ", flush=True)

        try:
            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=PROBE_TOOLS,
                tool_choice="auto",
                max_tokens=2048,
                stream=True,
                extra_headers={
                    "HTTP-Referer": "https://github.com/aerotone-project",
                    "X-Title": "AeroTone R1 Test"
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
                reasoning.append(content[:500])

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
                        print(f"{tdata['name']}", end=" ", flush=True)

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
                messages.append({"role": "user", "content": "Use probe tools or submit_diagnosis."})

        except Exception as e:
            print(f"Error: {e}")
            break

    # Check correctness
    correct = False
    if diagnosis:
        diagnosis_lower = diagnosis.lower()
        component_lower = fault['component'].lower()
        correct = (
            fault['category'] in diagnosis_lower or
            any(word in diagnosis_lower for word in component_lower.split()) or
            fault['id'].lower() in diagnosis_lower
        )

    status = "✅ CORRECT" if correct else "❌ WRONG"
    print(f"\n\n  R1 said: {diagnosis}")
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
        reasoning=reasoning
    )


def run_complete_test():
    """Run R1 against all fault types"""

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY")
        return

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    print("\n" + "="*70)
    print("  DEEPSEEK R1 COMPLETE FAULT DIAGNOSIS TEST")
    print("  Model:", MODEL)
    print("  Testing all 5 fault types")
    print("="*70)

    results = []

    for fault in FAULTS:
        result = test_single_fault(client, fault)
        results.append(result)

    # Summary
    correct = sum(1 for r in results if r.correct)

    print("\n" + "="*70)
    print("  FINAL RESULTS")
    print("="*70)
    print(f"\n  Accuracy: {correct}/{len(results)} ({correct/len(results)*100:.0f}%)\n")

    print(f"  {'Fault':<35} {'R1 Diagnosis':<25} {'Result'}")
    print("  " + "-"*70)
    for r in results:
        status = "✅" if r.correct else "❌"
        print(f"  {r.fault_name:<35} {r.r1_diagnosis[:25]:<25} {status}")

    # Save report
    report_dir = Path(__file__).parent / 'reports'
    report_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = report_dir / f"R1_COMPLETE_TEST_{timestamp}.md"

    md = f"""# DeepSeek R1 Complete Fault Diagnosis Test

**Model:** `{MODEL}`
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Accuracy:** {correct}/{len(results)} ({correct/len(results)*100:.0f}%)

## Results Summary

| Fault | Component | R1 Diagnosis | Correct |
|-------|-----------|--------------|---------|
"""
    for r in results:
        status = "✅" if r.correct else "❌"
        md += f"| {r.fault_name} | {r.component} | {r.r1_diagnosis} | {status} |\n"

    md += "\n## Detailed Results\n\n"

    for r in results:
        md += f"### {r.fault_name}\n\n"
        md += f"- **Component:** {r.component}\n"
        md += f"- **R1 Diagnosis:** {r.r1_diagnosis}\n"
        md += f"- **Correct:** {'Yes' if r.correct else 'No'}\n"
        md += f"- **Measurements:** {r.measurements}\n"
        md += f"- **Turns:** {r.turns}\n\n"

    md += """
## Comparison with Claude

| Model | Accuracy | Notes |
|-------|----------|-------|
| Claude Opus 4.5 | TBD | "Excelled" per user |
| Claude Haiku | TBD | "Very well" per user |
| DeepSeek R1 | """ + f"{correct/len(results)*100:.0f}%" + """ | This test |

---
*Generated by AeroTone Fault Diagnosis Benchmark*
"""

    report_path.write_text(md)
    print(f"\n  Report saved: {report_path}")

    return results


if __name__ == "__main__":
    run_complete_test()
