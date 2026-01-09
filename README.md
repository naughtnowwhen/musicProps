# AeroTone Model 12

An adversarial multi-agent benchmark for LLM reasoning, built on a SPICE-level circuit simulation.

## Overview

This project is an **adversarial evaluation system** where one agent injects faults into a circuit, and another agent must diagnose them *blind* - without access to the source code, only through probe measurements and reasoning.

```
┌────────────────────────────┐
│  AUTHOR (Hidden Side)      │  Injects faults, encrypts answers
├────────────────────────────┤
│  ████  FIREWALL  ████      │  "DO NOT READ ANY FILES"
├────────────────────────────┤
│  TROUBLESHOOTER (Blind)    │  Can ONLY probe measurements, must reason
└────────────────────────────┘
```

**The key insight:** By preventing the troubleshooting agent from seeing the fault injection code, we test *genuine reasoning ability* - not pattern matching. The agent must understand circuit theory, interpret measurements, and systematically diagnose failures.

### The Test Bed: AeroTone Model 12

The circuit being diagnosed is a complete physics simulation of a fictional 1979 electromechanical musical instrument - a 12-voice synthesizer where sound is produced by motor-driven propellers. This provides:

- **Rich failure modes** - capacitors, transistors, op-amps, diodes can all fail differently
- **Measurable symptoms** - voltage, current, frequency, waveform shape all change
- **Ambiguous signatures** - multiple faults can produce similar symptoms (testing differential diagnosis)
- **Domain complexity** - requires understanding PLL control, motor physics, signal conditioning

### What This Project Demonstrates

1. **Adversarial agent evaluation** - Author vs Troubleshooter across a firewall
2. **Circuit-level simulation** of 1979-era analog electronics
3. **Unified SPICE-Python pipeline** where physics generates audio directly
4. **Validated fault signatures** from ngspice as ground truth

## The Core Concept

The instrument produces sound through periodic pressure pulses of spinning propeller blades. The fundamental frequency (Blade Passage Frequency) is:

```
BPF = (RPM × Number of Blades) / 60
```

For the 12-blade propeller configuration:
- **A2 (110 Hz)** requires 550 RPM
- **A3 (220 Hz)** requires 1,100 RPM
- **A4 (440 Hz)** requires 2,200 RPM

**Simple formula: RPM = Frequency × 5**

A phase-locked loop (PLL) control system locks the motor speed to a target frequency, enabling precise pitch control.

## Quick Start

```bash
# Install dependencies
pip install numpy scipy sounddevice matplotlib

# Play a single propeller tone
python demo_simple.py

# Play a specific note
python demo_simple.py A3

# Real-time visualization with RPM gauge and spectrum
python demo_visual.py

# Interactive keyboard (macOS/Linux)
python demo_interactive.py

# Beat frequency demonstration (two propellers)
python demo_beats.py
```

## System Architecture

Each voice follows this signal path:

```
                                    ┌─────────────────┐
                                    │  Weather System │
                                    │  (Perlin noise) │
                                    └────────┬────────┘
                                             │ air density
                                             ▼
┌──────────┐    ┌─────────┐    ┌─────────┐    ┌───────────┐    ┌─────────┐
│ Reference│───▶│ CD4046  │───▶│  Loop   │───▶│  H-Bridge │───▶│   DC    │
│   Freq   │    │   PLL   │    │ Filter  │    │  Driver   │    │  Motor  │
└──────────┘    └────┬────┘    └─────────┘    └───────────┘    └────┬────┘
                     │                                               │
                     │ feedback                                      │ ω
                     │                                               ▼
              ┌──────┴──────┐                               ┌───────────────┐
              │   Signal    │◀──────────────────────────────│   Propeller   │
              │ Conditioner │        magnetic pickup        │  (12 blade)   │
              └─────────────┘                               └───────┬───────┘
                                                                    │ BPF, thrust
                                                                    ▼
┌──────────────┐    ┌─────────────┐    ┌──────────┐    ┌────────────────────┐
│  Expression  │───▶│   Envelope  │───▶│   Iris   │───▶│  Acoustic Synth    │
│    Pedal     │    │  Generator  │    │ Aperture │    │  (blade + Doppler  │
└──────────────┘    └─────────────┘    └──────────┘    │   + chamber)       │
                                                        └─────────┬──────────┘
                                                                  │
                                                                  ▼
                                                            AUDIO OUTPUT
```

### Key Subsystems

| Module | Purpose | Key Features |
|--------|---------|--------------|
| `cd4046.py` | PLL control | Phase comparator, VCO behavioral model, lock detection |
| `motor.py` | DC motor physics | Electrical + mechanical equations, back-EMF, thermal |
| `propeller.py` | Aerodynamics | Drag ∝ ρn²D⁵, thrust, blade passage frequency |
| `driver.py` | H-bridge driver | Transistor saturation, flyback protection, current limiting |
| `acoustics_v2.py` | Sound synthesis | Blade waveform, Doppler, chamber resonance, turbulence |
| `iris_circuit.py` | Volume control | 555 timer PWM, servo control, envelope generator |
| `spice_voice.py` | Integration | Complete voice with all subsystems (782 lines) |

## Technical Details

### Control System

The AeroTone uses a CD4046 phase-locked loop where the motor itself serves as the "voltage-controlled oscillator":

1. Reference frequency (target pitch) compared to tachometer feedback
2. Phase comparator outputs error signal
3. Loop filter (100kΩ/10µF, τ=1s) smooths to DC control voltage
4. H-bridge converts control voltage to motor drive
5. Motor accelerates/decelerates until phase lock achieved

**Control Law:**
```
V_control = V_mid + Kp×error + Ki×∫error·dt
Where: V_mid=7.5V, Kp=0.15 V/Hz, Ki=0.5 V/(Hz·s)
```

### H-Bridge Motor Driver

Four-transistor topology (TIP31/TIP32) with:
- **Saturation drop:** 1.4V total (2 transistors in series)
- **Maximum motor voltage:** 10.6V
- **Current limiting:** 2A via sense resistors
- **Flyback protection:** 1N4001 diodes

### Motor Equations

**Electrical:**
```
V = I×R + L×(dI/dt) + Ke×ω
```

**Mechanical:**
```
J×(dω/dt) = Kt×I - B×ω - T_load
```

Where:
- R = 2.0Ω (armature resistance)
- L = 0.5mH (inductance)
- Ke = Kt = 0.05 (back-EMF/torque constant)
- J = 30 µkg·m² (combined inertia)

### Acoustic Synthesis (v2)

Advanced propeller acoustics based on actual aeroacoustic research:

1. **Blade Passage Waveform** - Asymmetric pressure pulse (fast rise, slower decay)
2. **Doppler Modulation** - Blade tip velocity creates ±2-3% pitch swirl
3. **Chamber Resonance** - Helmholtz resonator at ~280Hz
4. **Turbulence Noise** - Tip vortex + trailing edge components
5. **Imbalance Modulation** - Realistic wobble from imperfect balance

## SPICE Integration

A key innovation is the **unified SPICE-Python pipeline** where:

- SPICE circuits simulate actual component transient responses
- Python behavioral models replicate SPICE behavior exactly
- Audio is generated directly from motor voltage/current trajectories
- No separate "synthesizer model" - **physics is the audio generator**

### Validated Fault Signatures

Fault signatures derived from ngspice simulations serve as ground truth:

| Fault | Component | Signature |
|-------|-----------|-----------|
| F001 | Leaky capacitor C2 | Ripple >200mV (288× normal), DC drifts to VDD/2 |
| F002 | Burned transistor Q1 | Low voltage AND **low current** (resistance blocks flow) |
| F003 | Noisy op-amp U2 | High-frequency oscillation, output exceeds rails |
| F004 | Open resistor R9 | Saturated square wave, Vpp=24V (rail-to-rail) |
| F005 | Shorted diode D2 | Low voltage AND **high current** (parallel path) |

## LLM Fault Diagnosis Challenge

The project includes an **adversarial multi-agent evaluation system** for testing LLM reasoning on blind circuit troubleshooting.

### The Architecture: Author vs Troubleshooter

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HIDDEN SIDE (Author)                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  Fault Pool     │───▶│  Challenge      │───▶│  Encrypted      │     │
│  │  (6 fault types)│    │  Generator      │    │  Answer File    │     │
│  └─────────────────┘    └────────┬────────┘    └─────────────────┘     │
│                                  │                                      │
│                                  │ inject fault                         │
│                                  ▼                                      │
│                         ┌─────────────────┐                            │
│                         │  Faulty Circuit │                            │
│                         │  (running)      │                            │
│                         └────────┬────────┘                            │
├──────────────────────────────────┼──────────────────────────────────────┤
│           ████████  FIREWALL  ████████                                  │
│           "DO NOT READ ANY FILES"                                       │
│           Only probe measurements allowed                               │
├──────────────────────────────────┼──────────────────────────────────────┤
│                                  │ probe interface only                 │
│                                  ▼                                      │
│                        BLIND SIDE (Troubleshooter)                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐     │
│  │  99 Probe       │───▶│  LLM Agent      │───▶│  Diagnosis      │     │
│  │  Points         │    │  (reasoning)    │    │  Submission     │     │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘     │
│                                                                         │
│  Available: VDC, VAC, frequency, waveform capture                      │
│  NOT available: Source code, fault type, answer file                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### How It Works

**1. Challenge Generator (Hidden Side)**
- Randomly selects a fault from a pool of 6 failure modes
- Injects the fault into a running circuit simulation
- Encrypts and hides the answer (base64 obfuscation)
- Exposes ONLY a probe measurement interface

**2. The Firewall**
- Strict rule: **"DO NOT READ ANY FILES IN THIS DIRECTORY"**
- The troubleshooter agent is intentionally blind
- Reading source files is "cheating" and invalidates results
- Only interaction is through measurement API

**3. Troubleshooter (Blind Side)**
- Receives circuit documentation and healthy reference values
- Can probe 99 test points (IC pins, component terminals)
- Must reason systematically from measurements alone
- Submits diagnosis without ever seeing the fault injection code

### Why This Matters

This architecture tests **genuine reasoning ability**:
- The agent can't pattern-match on fault injection code
- Must understand circuit theory to interpret measurements
- Must differentiate similar symptoms (F002 vs F005 both show low voltage)
- Success requires systematic diagnostic methodology

### Results (December 2025)

| Model | Accuracy | Notes |
|-------|----------|-------|
| **Claude Opus 4.5** | 100% (5/5) | Full documentation provided |
| **DeepSeek R1** | 100% (5/5) | Full documentation (fair test) |
| **Llama 3.3 70B** | 20% (1/5) | Condensed prompt only (unfair test) |

**Key Finding:** When given equivalent documentation, open-source reasoning models match proprietary model performance. Initial poor results were due to insufficient context, not model capability.

### Running a Challenge

```bash
# Generate a new challenge (hidden side)
python .hidden_answers/challenge_generator.py --difficulty medium

# Troubleshoot (blind side) - agent uses ONLY this interface
python .hidden_answers/troubleshoot.py <challenge_id>

# Or via API
curl -X POST http://localhost:5001/challenge/new
curl http://localhost:5001/challenge/{id}/healthy
curl http://localhost:5001/challenge/{id}/faulty
curl -X POST http://localhost:5001/challenge/{id}/diagnose \
  -d '{"component": "C2"}'
```

## Available Notes

| Note | Frequency | Target RPM |
|------|-----------|------------|
| A2   | 110.00 Hz | 550 |
| B2   | 123.47 Hz | 617 |
| C3   | 130.81 Hz | 654 |
| D3   | 146.83 Hz | 734 |
| E3   | 164.81 Hz | 824 |
| F3   | 174.61 Hz | 873 |
| G3   | 196.00 Hz | 980 |
| A3   | 220.00 Hz | 1,100 |
| B3   | 246.94 Hz | 1,235 |
| C4   | 261.63 Hz | 1,308 |
| D4   | 293.66 Hz | 1,468 |
| E4   | 329.63 Hz | 1,648 |
| A4   | 440.00 Hz | 2,200 |

**Operating range:** A2 to A4 (two octaves, 550-2200 RPM)

## Component Count (Per Voice)

**Electronic:**
- 3 ICs (CD4046 PLL, LM358 op-amp, Schmitt trigger)
- 4 power transistors (TIP31/TIP32)
- 4 flyback diodes (1N4001)
- ~40 resistors, ~25 capacitors

**Mechanical:**
- 1 DC motor (12V, 2000 RPM max)
- 1 12-blade propeller (100mm aluminum)
- 1 magnetic pickup sensor
- 1 high-speed servo motor
- 1 9-blade iris aperture

**Full 12-voice instrument: 700+ discrete components, ~96 ICs**

## Project Structure

```
musicProps/
├── aerotone/                    # Core simulation modules
│   ├── motor.py                 # DC motor physics
│   ├── propeller.py             # Aerodynamics
│   ├── cd4046.py                # PLL control
│   ├── driver.py                # H-bridge motor driver
│   ├── acoustics_v2.py          # Advanced sound synthesis
│   ├── iris_circuit.py          # Volume/expression control
│   ├── spice_voice.py           # Integrated voice channel
│   └── weather.py               # Environmental simulation
├── docs/                        # Technical documentation
│   ├── publication.md           # Theory of operation
│   ├── schematics.md            # ASCII circuit diagrams
│   └── AEROTONE_REPORT.md       # Architecture summary
├── fault_challenge/             # LLM diagnosis benchmark
│   ├── challenge_*.md           # Individual test cases
│   └── AGENT_INSTRUCTIONS.md    # Challenge protocol
├── demo_simple.py               # Basic audio demo
├── demo_visual.py               # Real-time visualization
├── demo_interactive.py          # Keyboard playable
├── demo_beats.py                # Beat frequency demo
└── spice_to_audio.py            # Direct SPICE→WAV pipeline
```

## The Notation Problem

Standard musical notation fails for the AeroTone because:

- **Glissando is the default** - motor inertia means every note transition slides
- **Pitch bend is the natural state** - not an ornament
- **Motor dynamics are musical** - acceleration curves define timbre

The `docs/publication.md` proposes five notation systems, with a recommended two-tier approach:
1. **Human composition** using simplified note+duration marks
2. **Machine execution** with precise timestamps and curve parameters

The beauty is that we don't need to calculate glissando curves - the motor physics does it naturally. We just set targets and let the PLL, motor inertia, and propeller drag create realistic transitions.

## What You Should Hear

- **Pitched tone** - Clear musical note at the target frequency
- **Rich harmonics** - Blade passage creates sawtooth-like overtones
- **Organic texture** - Subtle broadband noise like real propeller air
- **Doppler swirl** - Pitch modulation from blade tip motion
- **Beat frequencies** - Wobble when two props are slightly mistuned
- **Glissando transitions** - Natural slides between notes

## Dependencies

```
numpy>=1.20
scipy>=1.7
sounddevice>=0.4
matplotlib>=3.4
```

Optional for SPICE validation:
```
ngspice (brew install ngspice)
```

## Related Work

- Farassat's formulation for propeller thickness and loading noise
- Helmholtz resonator theory for chamber acoustics
- Classical PLL control theory (Gardner, "Phaselock Techniques")
- Motor control systems (Krause, "Analysis of Electric Machinery")

---

*AeroTone Model 12 - A SPICE-level simulation demonstrating that physics can be the synthesizer.*

*© 1979 Precision Propeller Instruments (fictional)*
