#!/usr/bin/env python3
"""
DEEPSEEK R1 STREAMING TROUBLESHOOTER

Watch DeepSeek R1 think through a fault diagnosis challenge in real-time.
Shows the model's chain-of-thought reasoning as it streams.

Usage:
    python fault_challenge/r1_streaming.py
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

# Load .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from fault_challenge.blind_probe_api import BlindProbeInterface

# Use the latest DeepSeek R1
MODEL = "deepseek/deepseek-r1-0528"

PROBE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "measure_vdc",
            "description": "Measure DC voltage at a probe point (averaged over time)",
            "parameters": {
                "type": "object",
                "properties": {
                    "point": {
                        "type": "string",
                        "description": "The probe point name (e.g., 'v_supply', 'loop_filter_out', 'motor_voltage')"
                    }
                },
                "required": ["point"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "measure_vac",
            "description": "Measure AC voltage (RMS) at a probe point - useful for detecting noise/ripple",
            "parameters": {
                "type": "object",
                "properties": {
                    "point": {"type": "string", "description": "The probe point name"}
                },
                "required": ["point"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_waveform",
            "description": "Capture waveform for detailed analysis. Returns Vpp, Vavg, frequency, duty cycle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "point": {"type": "string", "description": "The probe point name"},
                    "duration": {"type": "number", "description": "Capture duration in seconds", "default": 0.1}
                },
                "required": ["point"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "Get circuit status: target frequency, motor RPM, blade passage frequency",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_diagnosis",
            "description": "Submit your final diagnosis of the faulty component",
            "parameters": {
                "type": "object",
                "properties": {
                    "diagnosis": {
                        "type": "string",
                        "description": "The faulty component (e.g., 'Loop filter capacitor C1', 'H-bridge transistor Q1')"
                    }
                },
                "required": ["diagnosis"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are an expert electronics technician diagnosing a fault in an AeroTone Model 12 circuit.

## Circuit Overview
The AeroTone uses a PLL (Phase-Locked Loop) to control motor speed for generating musical tones:
- Power: V_supply=12V, V_logic=15V
- CD4046 PLL controls VCO frequency
- Loop filter smooths phase comparator output
- H-Bridge drives DC motor
- Propeller spins, pickup senses blade passage
- Signal conditioner (op-amp) amplifies feedback

## Expected Healthy Values (at 220Hz target)
- V_supply: 12.0V, V_logic: 15.0V
- Loop filter output: ~7.5V (stable, low ripple)
- Motor voltage: ~6V, Motor RPM: ~1100
- Conditioner output: within ±12V rails

## Common Faults
- Leaky capacitor: voltage drift, excessive ripple on loop filter
- Burned transistor: reduced motor voltage
- Noisy op-amp: noise/clipping on conditioner output
- Shorted diode: reduced voltage, high current

## Key Probe Points
- Power: v_supply, v_logic
- Loop filter: loop_filter_out, loop_filter_cap_voltage
- Motor: motor_voltage, motor_current
- Conditioner: cond_opamp_out

Take systematic measurements, reason about the results, and submit your diagnosis when confident."""


def execute_tool(probe, name, args):
    """Execute a probe tool"""
    try:
        if name == "measure_vdc":
            result = probe.measure_vdc(args["point"])
            return f"{result.point}: {result.value:.4f} VDC"
        elif name == "measure_vac":
            result = probe.measure_vac(args["point"])
            return f"{result.point}: {result.value:.4f} VAC (RMS)"
        elif name == "capture_waveform":
            duration = args.get("duration", 0.1)
            result = probe.capture_waveform(args["point"], duration)
            return (f"{result.point}: Vpp={result.v_pp:.3f}V, Vavg={result.v_avg:.3f}V, "
                    f"freq={result.frequency:.1f}Hz, Vac_rms={result.v_ac_rms:.4f}V")
        elif name == "get_status":
            status = probe.get_circuit_status()
            return f"Target: {status['target_frequency']:.0f}Hz, RPM: {status['motor_rpm']:.0f}"
        elif name == "submit_diagnosis":
            return args["diagnosis"]
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"


def run_streaming_diagnosis():
    """Run a single challenge with streaming output"""

    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY in .env file")
        return

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )

    # Create challenge
    print("\n" + "="*70)
    print("  DEEPSEEK R1 STREAMING FAULT DIAGNOSIS")
    print("  Model:", MODEL)
    print("="*70)

    probe = BlindProbeInterface.create_random_challenge(difficulty='easy')
    challenge_id = probe.get_challenge_id()
    print(f"\n  Challenge ID: {challenge_id}")
    print("  Difficulty: easy")
    print("  Waiting for R1 to think... (this may take 1-3 minutes)\n")
    print("-"*70)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            "A fault has been injected into this AeroTone circuit. "
            "Use the probe tools to systematically diagnose the problem. "
            "Think step by step. When confident, use submit_diagnosis."
        )}
    ]

    all_thinking = []
    all_measurements = []
    diagnosis_result = None
    max_turns = 15
    turn = 0

    while turn < max_turns and not diagnosis_result:
        turn += 1
        print(f"\n{'='*70}")
        print(f"  TURN {turn}")
        print("="*70)

        try:
            # Use streaming
            print("\n[Streaming response...]\n")

            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=PROBE_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
                stream=True,
                extra_headers={
                    "HTTP-Referer": "https://github.com/aerotone-project",
                    "X-Title": "AeroTone R1 Diagnosis"
                }
            )

            # Collect streamed content
            full_content = ""
            full_reasoning = ""
            tool_calls_data = {}
            current_tool_id = None

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Check for reasoning content (R1 thinking)
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    text = delta.reasoning_content
                    full_reasoning += text
                    print(f"\033[90m{text}\033[0m", end="", flush=True)  # Gray for thinking

                # Regular content
                if delta.content:
                    full_content += delta.content
                    print(delta.content, end="", flush=True)

                # Tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.id:
                            current_tool_id = tc.id
                            tool_calls_data[current_tool_id] = {
                                "id": tc.id,
                                "name": tc.function.name if tc.function else "",
                                "arguments": ""
                            }
                        if tc.function:
                            if tc.function.name and current_tool_id:
                                tool_calls_data[current_tool_id]["name"] = tc.function.name
                            if tc.function.arguments and current_tool_id:
                                tool_calls_data[current_tool_id]["arguments"] += tc.function.arguments

            print()  # Newline after streaming

            # Save thinking
            if full_reasoning:
                all_thinking.append(f"[Turn {turn}]\n{full_reasoning}")
                print(f"\n  [Thinking: {len(full_reasoning)} chars]")

            # Process tool calls
            if tool_calls_data:
                # Build message with tool calls
                tool_calls_list = []
                for tid, tdata in tool_calls_data.items():
                    tool_calls_list.append({
                        "id": tid,
                        "type": "function",
                        "function": {
                            "name": tdata["name"],
                            "arguments": tdata["arguments"]
                        }
                    })

                messages.append({
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": tool_calls_list
                })

                # Execute each tool
                for tid, tdata in tool_calls_data.items():
                    func_name = tdata["name"]
                    try:
                        func_args = json.loads(tdata["arguments"]) if tdata["arguments"] else {}
                    except:
                        func_args = {}

                    print(f"\n  >> Tool: {func_name}({func_args})")

                    if func_name == "submit_diagnosis":
                        diagnosis = func_args.get("diagnosis", "Unknown")
                        diagnosis_result = probe.submit_diagnosis(diagnosis)
                        result_str = f"Submitted: {diagnosis}"

                        print(f"\n{'='*70}")
                        print("  DIAGNOSIS SUBMITTED")
                        print("="*70)
                        print(f"  Your answer: {diagnosis_result.submitted}")
                        print(f"  Correct: {'✅ YES' if diagnosis_result.is_correct else '❌ NO'}")
                        print(f"  Actual fault: {diagnosis_result.actual_fault}")
                        print(f"  Component: {diagnosis_result.actual_component}")
                        print("="*70)
                    else:
                        result_str = execute_tool(probe, func_name, func_args)
                        all_measurements.append(f"{func_name}: {result_str}")
                        print(f"     Result: {result_str}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": result_str
                    })
            else:
                # No tool calls
                messages.append({"role": "assistant", "content": full_content})
                if not full_content and not full_reasoning:
                    print("  [No response - prompting to continue]")
                    messages.append({
                        "role": "user",
                        "content": "Please use the probe tools to take measurements, or submit_diagnosis if ready."
                    })

        except Exception as e:
            print(f"\n  ERROR: {e}")
            break

    # Summary
    print(f"\n{'='*70}")
    print("  SESSION SUMMARY")
    print("="*70)
    print(f"  Turns: {turn}")
    print(f"  Measurements: {len(all_measurements)}")
    print(f"  Thinking blocks: {len(all_thinking)}")
    if diagnosis_result:
        print(f"  Result: {'CORRECT' if diagnosis_result.is_correct else 'INCORRECT'}")
    print("="*70)

    # Save report
    if diagnosis_result:
        report_dir = Path(__file__).parent / 'reports' / 'r1_streaming'
        report_dir.mkdir(parents=True, exist_ok=True)

        report_path = report_dir / f"r1_{challenge_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        md = f"""# DeepSeek R1 Fault Diagnosis Report

## Result: {'✅ CORRECT' if diagnosis_result.is_correct else '❌ INCORRECT'}

| Field | Value |
|-------|-------|
| Challenge ID | `{challenge_id}` |
| Model | `{MODEL}` |
| Diagnosis | {diagnosis_result.submitted} |
| Actual Fault | {diagnosis_result.actual_fault} |
| Measurements | {len(all_measurements)} |
| Turns | {turn} |

## Measurements

"""
        for m in all_measurements:
            md += f"- {m}\n"

        md += "\n## R1 Thinking Process\n\n"
        for i, thought in enumerate(all_thinking, 1):
            md += f"### Turn {i}\n\n```\n{thought}\n```\n\n"

        report_path.write_text(md)
        print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    run_streaming_diagnosis()
