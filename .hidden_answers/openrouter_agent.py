#!/usr/bin/env python3
"""
OPENROUTER LLM AGENT FOR FAULT DIAGNOSIS

Tests open-source LLMs (Mistral, Llama, Qwen, etc.) on circuit fault diagnosis
using OpenRouter's unified API.

Setup:
    1. Get API key from https://openrouter.ai/settings/keys
    2. Set environment variable: export OPENROUTER_API_KEY="your-key"
    3. Run: python fault_challenge/openrouter_agent.py

Usage:
    # Test with DeepSeek R1 (thinking model)
    python fault_challenge/openrouter_agent.py --model deepseek/deepseek-r1

    # Run batch of 5 challenges with markdown reports
    python fault_challenge/openrouter_agent.py --batch 5 --model deepseek/deepseek-r1

    # Run benchmark across multiple models
    python fault_challenge/openrouter_agent.py --benchmark
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from fault_challenge.blind_probe_api import BlindProbeInterface


# Available open-source models on OpenRouter
MODELS = {
    # === THINKING/REASONING MODELS (show chain-of-thought) ===
    'deepseek-r1': 'deepseek/deepseek-r1',
    'deepseek-r1-0528': 'deepseek/deepseek-r1-0528',  # Latest version
    'magistral-medium': 'mistralai/magistral-medium-2506',  # Mistral's thinking model
    'magistral-small': 'mistralai/magistral-small-2506',  # Smaller Mistral thinking
    'qwen-qwq-32b': 'qwen/qwq-32b',  # Qwen's reasoning model

    # === STANDARD MODELS ===
    # Mistral
    'mistral-large': 'mistralai/mistral-large-2411',
    'mistral-medium': 'mistralai/mistral-medium-3.1',
    'mixtral-8x7b': 'mistralai/mixtral-8x7b-instruct',
    'mistral-7b': 'mistralai/mistral-7b-instruct',

    # Meta Llama
    'llama-3.1-405b': 'meta-llama/llama-3.1-405b-instruct',
    'llama-3.1-70b': 'meta-llama/llama-3.1-70b-instruct',
    'llama-3.1-8b': 'meta-llama/llama-3.1-8b-instruct',
    'llama-3.3-70b': 'meta-llama/llama-3.3-70b-instruct',

    # Qwen (non-reasoning)
    'qwen-2.5-72b': 'qwen/qwen-2.5-72b-instruct',
    'qwen-2.5-32b': 'qwen/qwen-2.5-32b-instruct',

    # DeepSeek (non-reasoning)
    'deepseek-v3': 'deepseek/deepseek-chat',

    # Google (open weights)
    'gemma-2-27b': 'google/gemma-2-27b-it',
}

# Models that output reasoning tokens
THINKING_MODELS = [
    'deepseek/deepseek-r1',
    'deepseek/deepseek-r1-0528',
    'mistralai/magistral-medium-2506',
    'mistralai/magistral-small-2506',
    'qwen/qwq-32b',
]


# Tool definitions for function calling
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
            "description": "Measure AC voltage (RMS of AC component) at a probe point",
            "parameters": {
                "type": "object",
                "properties": {
                    "point": {
                        "type": "string",
                        "description": "The probe point name"
                    }
                },
                "required": ["point"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "measure_frequency",
            "description": "Measure signal frequency at a probe point",
            "parameters": {
                "type": "object",
                "properties": {
                    "point": {
                        "type": "string",
                        "description": "The probe point name"
                    }
                },
                "required": ["point"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_waveform",
            "description": "Capture and analyze a waveform. Returns Vpp, Vavg, Vac RMS, frequency, duty cycle, Vmin, Vmax.",
            "parameters": {
                "type": "object",
                "properties": {
                    "point": {
                        "type": "string",
                        "description": "The probe point name"
                    },
                    "duration": {
                        "type": "number",
                        "description": "Capture duration in seconds (default 0.1)",
                        "default": 0.1
                    }
                },
                "required": ["point"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_probes",
            "description": "List available probe points, optionally filtered by category",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter category: 'power', 'cd4046', 'filter', 'hbridge', 'motor', 'driver', 'pickup', 'conditioner'",
                        "enum": ["power", "cd4046", "filter", "hbridge", "motor", "driver", "pickup", "conditioner"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_frequency",
            "description": "Set the target operating frequency of the circuit",
            "parameters": {
                "type": "object",
                "properties": {
                    "freq": {
                        "type": "number",
                        "description": "Target frequency in Hz (typically 110-220 Hz)"
                    }
                },
                "required": ["freq"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "Get current circuit status (target frequency, motor RPM, blade passage frequency)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_diagnosis",
            "description": "Submit your final diagnosis of the faulty component. Call this when you've identified the fault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "diagnosis": {
                        "type": "string",
                        "description": "Your diagnosis of the faulty component (e.g., 'Loop filter capacitor C1', 'H-bridge transistor Q1')"
                    }
                },
                "required": ["diagnosis"]
            }
        }
    }
]


SYSTEM_PROMPT = """You are an expert electronics technician troubleshooting a faulty AeroTone Model 12 circuit.

## Circuit Overview
The AeroTone is a 1979 electromechanical musical instrument that uses spinning propellers to generate musical tones. The circuit consists of:

1. **Power Supply**: V_supply (12V), V_logic (15V for CD4046)
2. **CD4046 PLL (Phase-Locked Loop)**:
   - VCO (Voltage-Controlled Oscillator) generates reference signal
   - Phase comparator compares VCO output with feedback
   - Controls motor speed to lock onto target frequency
3. **Loop Filter**: RC filter that smooths phase comparator output to create VCO control voltage
4. **H-Bridge Motor Driver**: Drives the DC motor based on control voltage
5. **Propeller & Pickup**: Motor spins propeller, magnetic pickup senses blade passage
6. **Signal Conditioner**: Op-amp circuit that amplifies/shapes pickup signal for PLL feedback

## Expected Healthy Values (at 220Hz target)
- V_supply: 12.0V
- V_logic: 15.0V
- Loop filter output: ~7.5V (stable, minimal ripple)
- Motor voltage: ~6V
- Motor RPM: ~1100
- Conditioner output: clean square wave, within ±12V rails

## Common Faults
- **Leaky capacitor**: Voltage drift, excessive ripple on loop filter
- **Burned transistor**: Reduced motor voltage, asymmetric drive
- **Noisy op-amp**: Excessive noise, output exceeding rails
- **Open resistor**: Saturated outputs, no linear response
- **Shorted diode**: Reduced voltage, excessive current

## Your Task
1. Systematically probe the circuit to gather measurements
2. Compare readings to expected healthy values
3. Identify anomalies that indicate component failure
4. Submit your diagnosis when confident

Start by checking power supply, then work through the signal path. Use capture_waveform for detailed analysis when needed."""


@dataclass
class AgentResult:
    """Result of an agent troubleshooting session"""
    model: str
    challenge_id: str
    diagnosis_correct: bool
    submitted_diagnosis: str
    actual_fault: str
    actual_component: str
    measurements_taken: int
    turns_taken: int
    total_tokens: int
    reasoning_trace: List[str]
    thinking_content: List[str] = field(default_factory=list)  # For thinking models
    measurements_log: List[Dict] = field(default_factory=list)  # Detailed measurement log
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class OpenRouterAgent:
    """LLM Agent that troubleshoots circuit faults via OpenRouter"""

    def __init__(self, model: str = 'mistralai/mistral-large-2411', api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter. Get key at: https://openrouter.ai/settings/keys"
            )

        # Use OpenAI SDK with OpenRouter endpoint
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1"
        )

        self.probe: Optional[BlindProbeInterface] = None
        self.messages: List[Dict] = []
        self.total_tokens = 0
        self.reasoning_trace: List[str] = []
        self.thinking_content: List[str] = []  # For thinking models (DeepSeek R1, Magistral)
        self.measurements_log: List[Dict] = []
        self.is_thinking_model = model in THINKING_MODELS

    def _execute_tool(self, name: str, args: Dict) -> str:
        """Execute a probe tool and return result as string"""
        try:
            if name == "measure_vdc":
                result = self.probe.measure_vdc(args["point"])
                return f"{result.point}: {result.value:.4f} VDC"

            elif name == "measure_vac":
                result = self.probe.measure_vac(args["point"])
                return f"{result.point}: {result.value:.4f} VAC (RMS)"

            elif name == "measure_frequency":
                result = self.probe.measure_frequency(args["point"])
                return f"{result.point}: {result.value:.2f} Hz"

            elif name == "capture_waveform":
                duration = args.get("duration", 0.1)
                result = self.probe.capture_waveform(args["point"], duration)
                return (
                    f"{result.point} waveform:\n"
                    f"  Vmin: {result.v_min:.4f}V, Vmax: {result.v_max:.4f}V\n"
                    f"  Vpp: {result.v_pp:.4f}V, Vavg: {result.v_avg:.4f}V\n"
                    f"  Vac RMS: {result.v_ac_rms:.4f}V\n"
                    f"  Frequency: {result.frequency:.2f} Hz\n"
                    f"  Duty cycle: {result.duty_cycle*100:.1f}%"
                )

            elif name == "list_probes":
                category = args.get("category")
                if category:
                    probes = self.probe.get_probes_by_category(category)
                    return f"Probes in '{category}': {', '.join(probes)}"
                else:
                    probes = self.probe.get_available_probes()
                    return f"Available probes ({len(probes)}): {', '.join(probes[:20])}..."

            elif name == "set_frequency":
                self.probe.set_target_frequency(args["freq"])
                status = self.probe.get_circuit_status()
                return f"Set to {args['freq']}Hz. Motor RPM: {status['motor_rpm']:.0f}"

            elif name == "get_status":
                status = self.probe.get_circuit_status()
                return (
                    f"Target: {status['target_frequency']:.1f} Hz\n"
                    f"Motor RPM: {status['motor_rpm']:.0f}\n"
                    f"Blade passage: {status['blade_passage_frequency']:.1f} Hz"
                )

            elif name == "submit_diagnosis":
                # This is handled specially in the main loop
                return args["diagnosis"]

            else:
                return f"Unknown tool: {name}"

        except Exception as e:
            return f"Error: {str(e)}"

    def run_diagnosis(self, difficulty: str = 'medium', max_turns: int = 20, verbose: bool = True) -> AgentResult:
        """
        Run a complete fault diagnosis session.

        Args:
            difficulty: 'easy', 'medium', or 'hard'
            max_turns: Maximum conversation turns before timeout
            verbose: Print progress to stdout

        Returns:
            AgentResult with diagnosis outcome and metrics
        """
        # Create challenge
        self.probe = BlindProbeInterface.create_random_challenge(difficulty=difficulty)
        challenge_id = self.probe.get_challenge_id()

        if verbose:
            print(f"\n{'='*60}")
            print(f"  FAULT DIAGNOSIS SESSION")
            print(f"  Model: {self.model}")
            print(f"  Challenge: {challenge_id}")
            print(f"{'='*60}\n")

        # Initialize conversation
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "A fault has been injected into this AeroTone circuit. "
                "Use the probe tools to systematically diagnose the problem. "
                "When you've identified the faulty component, use submit_diagnosis."
            )}
        ]
        self.reasoning_trace = []
        self.thinking_content = []
        self.measurements_log = []
        self.total_tokens = 0

        diagnosis_result = None
        turns = 0

        while turns < max_turns:
            turns += 1

            # Call LLM
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=PROBE_TOOLS,
                    tool_choice="auto",
                    max_tokens=1024,
                    extra_headers={
                        "HTTP-Referer": "https://github.com/aerotone-project",
                        "X-Title": "AeroTone Fault Diagnosis"
                    }
                )
            except Exception as e:
                if verbose:
                    print(f"API Error: {e}")
                break

            # Track tokens
            if response.usage:
                self.total_tokens += response.usage.total_tokens

            message = response.choices[0].message

            # Capture thinking tokens from reasoning models (DeepSeek R1, Magistral, QwQ)
            # These appear in the 'reasoning' field or wrapped in <think> tags
            reasoning_content = getattr(message, 'reasoning', None) or getattr(message, 'reasoning_content', None)
            if reasoning_content:
                self.thinking_content.append(f"[Turn {turns}]\n{reasoning_content}")
                if verbose:
                    print(f"  <thinking>{reasoning_content[:300]}...</thinking>")

            # Log assistant reasoning
            if message.content:
                # Some models include thinking in <think> tags
                content = message.content
                if '<think>' in content and '</think>' in content:
                    import re
                    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
                    if think_match:
                        self.thinking_content.append(f"[Turn {turns}]\n{think_match.group(1)}")
                        if verbose:
                            print(f"  <thinking>{think_match.group(1)[:300]}...</thinking>")
                        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

                self.reasoning_trace.append(f"[Turn {turns}] {content}")
                if verbose and content:
                    print(f"Agent: {content[:200]}...")

            # Check for tool calls
            if not message.tool_calls:
                # No tool calls - might be done or stuck
                self.messages.append({"role": "assistant", "content": message.content or ""})
                if verbose:
                    print("  (No tool calls - prompting to continue)")
                self.messages.append({
                    "role": "user",
                    "content": "Please use the probe tools to take measurements, or submit_diagnosis if you've identified the fault."
                })
                continue

            # Process tool calls
            self.messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in message.tool_calls
                ]
            })

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                # Handle cases where arguments might be None or empty
                raw_args = tool_call.function.arguments
                func_args = json.loads(raw_args) if raw_args else {}

                if verbose:
                    print(f"  Tool: {func_name}({func_args})")

                # Check for diagnosis submission
                if func_name == "submit_diagnosis":
                    diagnosis = func_args["diagnosis"]
                    diagnosis_result = self.probe.submit_diagnosis(diagnosis)

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Diagnosis submitted: {diagnosis}"
                    })

                    if verbose:
                        print(f"\n{'='*60}")
                        print(f"  DIAGNOSIS SUBMITTED")
                        print(f"{'='*60}")
                        print(f"  Your diagnosis: {diagnosis_result.submitted}")
                        print(f"  Correct: {'YES' if diagnosis_result.is_correct else 'NO'}")
                        print(f"  Actual fault: {diagnosis_result.actual_fault}")
                        print(f"  Component: {diagnosis_result.actual_component}")
                        print(f"  Measurements: {diagnosis_result.measurements_taken}")
                        print(f"{'='*60}\n")

                    break

                # Execute other tools
                result = self._execute_tool(func_name, func_args)
                self.reasoning_trace.append(f"  {func_name}: {result}")
                self.measurements_log.append({
                    'turn': turns,
                    'tool': func_name,
                    'args': func_args,
                    'result': result
                })

                if verbose:
                    print(f"    -> {result}")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            if diagnosis_result:
                break

        # Build result
        if diagnosis_result:
            return AgentResult(
                model=self.model,
                challenge_id=challenge_id,
                diagnosis_correct=diagnosis_result.is_correct,
                submitted_diagnosis=diagnosis_result.submitted,
                actual_fault=diagnosis_result.actual_fault,
                actual_component=diagnosis_result.actual_component,
                measurements_taken=diagnosis_result.measurements_taken,
                turns_taken=turns,
                total_tokens=self.total_tokens,
                reasoning_trace=self.reasoning_trace,
                thinking_content=self.thinking_content,
                measurements_log=self.measurements_log
            )
        else:
            # Timed out without diagnosis
            return AgentResult(
                model=self.model,
                challenge_id=challenge_id,
                diagnosis_correct=False,
                submitted_diagnosis="TIMEOUT",
                actual_fault="Unknown (timed out)",
                actual_component="Unknown",
                measurements_taken=self.probe.get_measurement_count(),
                turns_taken=turns,
                total_tokens=self.total_tokens,
                reasoning_trace=self.reasoning_trace,
                thinking_content=self.thinking_content,
                measurements_log=self.measurements_log
            )


def generate_markdown_report(result: AgentResult, output_dir: Path) -> Path:
    """Generate a detailed markdown report for a single challenge result."""

    filename = f"challenge_{result.challenge_id}_{result.timestamp[:10]}.md"
    filepath = output_dir / filename

    status = "CORRECT" if result.diagnosis_correct else "INCORRECT"
    status_emoji = "✅" if result.diagnosis_correct else "❌"

    md = f"""# Fault Diagnosis Challenge Report

## Summary

| Field | Value |
|-------|-------|
| **Challenge ID** | `{result.challenge_id}` |
| **Model** | `{result.model}` |
| **Result** | {status_emoji} **{status}** |
| **Submitted Diagnosis** | {result.submitted_diagnosis} |
| **Actual Fault** | {result.actual_fault} |
| **Actual Component** | {result.actual_component} |
| **Measurements Taken** | {result.measurements_taken} |
| **Turns** | {result.turns_taken} |
| **Tokens Used** | {result.total_tokens:,} |
| **Timestamp** | {result.timestamp} |

---

## Measurements Log

"""

    for m in result.measurements_log:
        md += f"### Turn {m['turn']}: `{m['tool']}`\n"
        md += f"**Arguments:** `{m['args']}`\n\n"
        md += f"**Result:**\n```\n{m['result']}\n```\n\n"

    md += """---

## Agent Reasoning Trace

"""
    for trace in result.reasoning_trace:
        md += f"{trace}\n\n"

    # Include thinking content if available (for reasoning models)
    if result.thinking_content:
        md += """---

## Internal Thinking (Chain-of-Thought)

*This section shows the model's internal reasoning process.*

"""
        for i, thought in enumerate(result.thinking_content, 1):
            md += f"### Thinking Block {i}\n\n"
            md += f"```\n{thought}\n```\n\n"

    md += f"""---

## Analysis

### What the model got {"right" if result.diagnosis_correct else "wrong"}:

"""
    if result.diagnosis_correct:
        md += f"The model correctly identified the fault as **{result.actual_component}**.\n\n"
    else:
        md += f"""The model diagnosed: **{result.submitted_diagnosis}**

But the actual fault was: **{result.actual_fault}** ({result.actual_component})

"""

    md += """---

*Generated by AeroTone Fault Diagnosis Benchmark*
"""

    filepath.write_text(md)
    return filepath


def run_batch(model: str, num_challenges: int = 5, difficulty: str = 'medium',
              output_dir: Optional[Path] = None, verbose: bool = True) -> List[AgentResult]:
    """
    Run a batch of challenges and generate markdown reports.

    Args:
        model: Model identifier to use
        num_challenges: Number of challenges to run
        difficulty: 'easy', 'medium', or 'hard'
        output_dir: Directory to save reports (default: fault_challenge/reports/)
        verbose: Print progress

    Returns:
        List of AgentResult objects
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / 'reports'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_dir = output_dir / f"batch_{timestamp}"
    batch_dir.mkdir(exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  BATCH FAULT DIAGNOSIS")
    print(f"  Model: {model}")
    print(f"  Challenges: {num_challenges}")
    print(f"  Difficulty: {difficulty}")
    print(f"  Output: {batch_dir}")
    print(f"{'='*70}\n")

    results = []

    for i in range(num_challenges):
        print(f"\n--- Challenge {i+1}/{num_challenges} ---")

        try:
            agent = OpenRouterAgent(model=model)
            result = agent.run_diagnosis(difficulty=difficulty, verbose=verbose)
            results.append(result)

            # Generate markdown report
            report_path = generate_markdown_report(result, batch_dir)

            status = "CORRECT" if result.diagnosis_correct else "WRONG"
            print(f"\n  Result: {status}")
            print(f"  Report: {report_path.name}")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    # Generate summary report
    correct = sum(1 for r in results if r.diagnosis_correct)
    accuracy = correct / len(results) * 100 if results else 0
    avg_measurements = sum(r.measurements_taken for r in results) / len(results) if results else 0
    avg_tokens = sum(r.total_tokens for r in results) / len(results) if results else 0

    summary_md = f"""# Batch Summary Report

## Overview

| Metric | Value |
|--------|-------|
| **Model** | `{model}` |
| **Total Challenges** | {num_challenges} |
| **Completed** | {len(results)} |
| **Correct** | {correct} |
| **Accuracy** | {accuracy:.1f}% |
| **Avg Measurements** | {avg_measurements:.1f} |
| **Avg Tokens** | {avg_tokens:,.0f} |
| **Difficulty** | {difficulty} |
| **Timestamp** | {timestamp} |

## Individual Results

| # | Challenge ID | Result | Diagnosis | Actual Fault |
|---|--------------|--------|-----------|--------------|
"""

    for i, r in enumerate(results, 1):
        status = "✅" if r.diagnosis_correct else "❌"
        summary_md += f"| {i} | `{r.challenge_id}` | {status} | {r.submitted_diagnosis[:30]}... | {r.actual_fault} |\n"

    summary_md += """
## Reports

"""
    for r in results:
        summary_md += f"- [Challenge {r.challenge_id}](challenge_{r.challenge_id}_{r.timestamp[:10]}.md)\n"

    summary_md += """
---

*Generated by AeroTone Fault Diagnosis Benchmark*
"""

    summary_path = batch_dir / "SUMMARY.md"
    summary_path.write_text(summary_md)

    print(f"\n{'='*70}")
    print(f"  BATCH COMPLETE")
    print(f"{'='*70}")
    print(f"  Accuracy: {accuracy:.1f}% ({correct}/{len(results)})")
    print(f"  Reports saved to: {batch_dir}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*70}\n")

    return results


def run_benchmark(models: List[str], trials_per_model: int = 3, difficulty: str = 'medium'):
    """Run benchmark across multiple models"""

    print(f"\n{'='*70}")
    print(f"  OPENROUTER FAULT DIAGNOSIS BENCHMARK")
    print(f"  Models: {len(models)}, Trials: {trials_per_model}, Difficulty: {difficulty}")
    print(f"{'='*70}\n")

    results = []

    for model in models:
        print(f"\n--- Testing: {model} ---")
        model_results = []

        for trial in range(trials_per_model):
            print(f"  Trial {trial + 1}/{trials_per_model}...", end=" ", flush=True)

            try:
                agent = OpenRouterAgent(model=model)
                result = agent.run_diagnosis(difficulty=difficulty, verbose=False)
                model_results.append(result)

                status = "CORRECT" if result.diagnosis_correct else "WRONG"
                print(f"{status} ({result.measurements_taken} measurements, {result.total_tokens} tokens)")

            except Exception as e:
                print(f"ERROR: {e}")
                continue

        if model_results:
            correct = sum(1 for r in model_results if r.diagnosis_correct)
            avg_measurements = sum(r.measurements_taken for r in model_results) / len(model_results)
            avg_tokens = sum(r.total_tokens for r in model_results) / len(model_results)

            results.append({
                'model': model,
                'accuracy': correct / len(model_results),
                'trials': len(model_results),
                'correct': correct,
                'avg_measurements': avg_measurements,
                'avg_tokens': avg_tokens
            })

    # Print summary
    print(f"\n{'='*70}")
    print(f"  BENCHMARK RESULTS")
    print(f"{'='*70}")
    print(f"{'Model':<40} {'Accuracy':<12} {'Avg Meas':<12} {'Avg Tokens'}")
    print("-" * 70)

    for r in sorted(results, key=lambda x: x['accuracy'], reverse=True):
        print(f"{r['model']:<40} {r['accuracy']*100:>6.1f}%     {r['avg_measurements']:>6.1f}       {r['avg_tokens']:>6.0f}")

    return results


def main():
    parser = argparse.ArgumentParser(description='OpenRouter LLM Fault Diagnosis Agent')
    parser.add_argument('--model', default='deepseek/deepseek-r1',
                       help='Model to use (default: deepseek-r1 thinking model)')
    parser.add_argument('--difficulty', default='medium', choices=['easy', 'medium', 'hard'])
    parser.add_argument('--batch', type=int, metavar='N',
                       help='Run N challenges with markdown reports')
    parser.add_argument('--benchmark', action='store_true', help='Run benchmark across models')
    parser.add_argument('--benchmark-thinking', action='store_true',
                       help='Run benchmark across thinking/reasoning models only')
    parser.add_argument('--max-turns', type=int, default=20, help='Max conversation turns')
    parser.add_argument('--quiet', action='store_true', help='Minimal output')
    parser.add_argument('--list-models', action='store_true', help='List available models')
    args = parser.parse_args()

    if args.list_models:
        print("\n=== THINKING/REASONING MODELS ===")
        for name, model_id in MODELS.items():
            if model_id in THINKING_MODELS:
                print(f"  {name:<20} -> {model_id}")
        print("\n=== STANDARD MODELS ===")
        for name, model_id in MODELS.items():
            if model_id not in THINKING_MODELS:
                print(f"  {name:<20} -> {model_id}")
        return

    if args.benchmark_thinking:
        # Benchmark thinking models only
        thinking_models = [
            'deepseek/deepseek-r1',
            'mistralai/magistral-medium-2506',
            'qwen/qwq-32b',
        ]
        run_benchmark(thinking_models, trials_per_model=3, difficulty=args.difficulty)

    elif args.benchmark:
        # Run benchmark with popular open-source models
        benchmark_models = [
            'deepseek/deepseek-r1',
            'mistralai/mistral-large-2411',
            'meta-llama/llama-3.1-70b-instruct',
            'qwen/qwen-2.5-72b-instruct',
        ]
        run_benchmark(benchmark_models, trials_per_model=3, difficulty=args.difficulty)

    elif args.batch:
        # Run batch of challenges with markdown reports
        run_batch(
            model=args.model,
            num_challenges=args.batch,
            difficulty=args.difficulty,
            verbose=not args.quiet
        )

    else:
        # Single model test
        agent = OpenRouterAgent(model=args.model)
        result = agent.run_diagnosis(
            difficulty=args.difficulty,
            max_turns=args.max_turns,
            verbose=not args.quiet
        )

        print(f"\nResult: {'CORRECT' if result.diagnosis_correct else 'INCORRECT'}")
        print(f"Tokens used: {result.total_tokens}")


if __name__ == '__main__':
    main()
