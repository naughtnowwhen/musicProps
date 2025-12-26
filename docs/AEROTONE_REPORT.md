# AeroTone Model 12: Technical Report & Notation Proposal

## Executive Summary

The AeroTone Model 12 is a SPICE-level emulation of a fictional 1979 electromechanical musical instrument that generates tones via spinning propellers. Unlike conventional synthesizers, pitch is determined by propeller RPM (blade passage frequency), creating an instrument where **glissando is the natural state** and discrete notes require active control system intervention.

This document summarizes the implementation and proposes notation systems for composing music for this novel instrument.

---

## Part 1: Instrument Architecture

### 1.1 Physical Concept

The AeroTone produces sound through the periodic pressure pulses of spinning propeller blades. The fundamental frequency (Blade Passage Frequency) is:

```
BPF = (RPM × num_blades) / 60
```

For a 12-blade propeller:
- 110 Hz (A2) requires 550 RPM
- 220 Hz (A3) requires 1,100 RPM
- 440 Hz (A4) requires 2,200 RPM

Formula: **RPM = Frequency × 5** (for 12 blades)

The propeller is driven by a DC motor controlled by a phase-locked loop (PLL), creating a servo system that locks to a reference frequency.

### 1.2 Module Summary

| Module | Purpose | Key Components |
|--------|---------|----------------|
| `motor.py` | DC motor physics | R, L, Ke, Kt, inertia, thermal |
| `propeller.py` | Aerodynamics | Drag ∝ ρn²D⁵, thrust, BPF |
| `cd4046.py` | PLL control | Phase detector, VCO, loop filter |
| `driver.py` | Motor driver | H-bridge, magnetic pickup, signal conditioning |
| `acoustics_v2.py` | Sound synthesis | Blade waveform, Doppler, chamber resonance |
| `iris_circuit.py` | Volume control | 555 timer, servo, envelope generator |
| `weather.py` | Environmental | Perlin noise air density variation |
| `spice_voice.py` | Integration | Complete voice with all subsystems |

### 1.3 Component Count

**Electronic (per voice):**
- Resistors: ~40
- Capacitors: ~25
- Transistors: 12-16 (BJT + MOSFET)
- ICs: CD4046, LM358, 555, LM339
- Inductors: 2-3

**Mechanical (per voice):**
- DC motor with bearings
- 12-blade propeller (100mm desktop / 400mm concert)
- Magnetic pickup sensor
- 9-blade iris aperture
- Servo actuator

### 1.4 Signal Flow

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

---

## Part 2: The Notation Problem

### 2.1 Why Standard Notation Fails

**Sheet Music:**
- Assumes discrete pitches (notes on staff)
- Glissando is an ornament, not the default
- No representation for motor acceleration curves
- Expression marks (p, f, crescendo) don't map to iris servo dynamics

**MIDI:**
- Note-on/note-off events assume instant pitch changes
- Pitch bend is limited (±2 semitones typical) and treated as modulation
- CC messages for expression don't capture attack/release envelopes
- No concept of "target frequency with transition time"

**The Fundamental Mismatch:**
```
Standard:  Note A ──────────────── Note B ────────────────
           (instant pitch change)

AeroTone:  Note A ───╲         ╱─── Note B ───╲         ╱───
                      ╲  gliss╱                ╲  gliss╱
                       ╲────╱                   ╲────╱
           (motor accelerates through intermediate frequencies)
```

### 2.2 What We Need to Represent

1. **Target Pitch** - Where we want to go (Hz or note name)
2. **Arrival Time** - When we should reach the target
3. **Transition Curve** - How we get there (linear, exponential, S-curve)
4. **Expression Level** - Iris aperture (0-100%)
5. **Duck Behavior** - Auto-duck during transitions (on/off, depth)
6. **Timing Framework** - Tempo, measures, beats

---

## Part 3: Proposed Notation Systems

### 3.1 Proposal A: Timeline Notation (TAB-like)

A text-based format inspired by guitar tablature, read left-to-right with fixed time columns.

```
BPM: 72
DUCK: 45%

TIME:  |0.0    |0.5    |1.0    |1.5    |2.0    |2.5    |3.0    |3.5    |
PITCH: |A2     |~      |B2     |~      |C#3    |~      |D3     |~      |
EXPR:  |100    |100    |100    |100    |80     |~~70   |100    |100    |
CURVE: |       |lin    |       |lin    |       |exp    |       |lin    |

Legend:
  ~     = sustain previous pitch
  ~~70  = glide to 70 over this interval
  lin   = linear transition
  exp   = exponential curve
  s     = S-curve (smooth acceleration/deceleration)
```

**Pros:** Human-readable, easy to type, shows time relationships
**Cons:** Fixed time grid, verbose for long pieces

---

### 3.2 Proposal B: Event Notation (Score-like)

Events listed with timestamps and parameters:

```
# AeroTone Score Format v1
tempo: 72 bpm
duck: {depth: 0.45, attack: 60ms, release: 140ms}

@0.00  pitch:A2   expr:100%  curve:instant
@0.65  pitch:B2   expr:100%  curve:linear
@1.30  pitch:C#3  expr:100%  curve:linear
@1.95  pitch:D3   expr:80%   curve:exp
@2.60  pitch:E3   expr:100%  curve:s-curve
@3.25  pitch:F#3  hold:0.8s
@4.05  pitch:G#3
@4.70  pitch:A3   expr:90%

# Descending
@5.50  pitch:A3   hold:0.4s
@5.90  pitch:G#3  curve:linear
...
```

**Pros:** Precise timing, clear parameters, extensible
**Cons:** Less visual, harder to see overall shape

---

### 3.3 Proposal C: Curve Notation (Graphical)

ASCII representation of pitch and expression curves:

```
BPM: 72  |  DUCK: auto

PITCH (Hz)                                    EXPRESSION (%)
220─┤                            ╭────       100─┤────╮  ╭────╮  ╭────
    │                        ╭───╯                │    ╰──╯    ╰──╯
185─┤                    ╭───╯                 80─┤
    │                ╭───╯                        │
147─┤            ╭───╯                         60─┤
    │        ╭───╯                                │
110─┤────────╯                                 40─┤
    └────────────────────────────────────         └─────────────────────
     0   1   2   3   4   5   6   7   8 sec         0   1   2   3   4   5

Notes: A2──B2──C#3──D3──E3──F#3──G#3──A3
```

**Pros:** Intuitive visual representation, shows curves clearly
**Cons:** Low resolution, hard to edit precisely, not machine-readable

---

### 3.4 Proposal D: Hybrid DSL (Domain-Specific Language)

A compact language designed for the instrument:

```aerotone
voice Main {
  tempo 72
  duck auto(45%, 60ms, 140ms)

  // Ascending scale
  phrase ascending {
    A2  -> B2  : 0.65s linear
    B2  -> C#3 : 0.65s linear
    C#3 -> D3  : 0.65s linear @ expr(80%)
    D3  -> E3  : 0.65s exp @ expr(100%)
    E3  -> F#3 : 0.65s s-curve
    F#3 -> G#3 : 0.65s linear
    G#3 -> A3  : 0.65s linear
    A3  hold 0.4s
  }

  // Descending
  phrase descending {
    A3  -> G#3 : 0.65s linear
    G#3 -> F#3 : 0.65s linear
    // ... etc
  }

  // Play structure
  play {
    ascending
    rest 0.3s
    descending
    A2 hold 0.5s fade
  }
}
```

**Pros:** Expressive, reusable phrases, clear structure
**Cons:** Requires parser, learning curve

---

### 3.5 Proposal E: Minimal Notation (Human-Optimized)

The simplest possible notation for quick composition:

```
# Silent Night - AeroTone arrangement
# Format: NOTE DURATION [expression%] [curve]

tempo 60

G3. A3' G3_ E3...          # "Si-lent night"
G3. A3' G3_ E3...          # "Ho-ly night"
--                          # pause

D3_ D3 B2...               # "All is calm"
C3_ C3 G2...               # "All is bright"
--

A2 A2. C3' B2 A2           # "Round yon Virgin"
G3. A3' G3 E3_             # "Mother and Child"

# Duration symbols:
#   plain = quarter note
#   .     = dotted (1.5x)
#   _     = half note
#   ...   = whole note
#   '     = eighth note
#   --    = rest

# Expression: append @80 for 80%
# Curve: append ~lin or ~exp or ~s
```

**Pros:** Very compact, quick to write, human-friendly
**Cons:** Less precise, limited expression control

---

## Part 4: Recommended Approach

### 4.1 Two-Tier System

**Tier 1: Human Composition (Proposal E)**
- Simple, musical notation
- Note names with duration marks
- Optional expression and curve modifiers
- Easy to write by hand

**Tier 2: Machine Execution (Proposal B)**
- Precise timestamps
- All parameters explicit
- Generated from Tier 1 or hand-crafted for precision

**Compiler:** Tier 1 → Tier 2 conversion handles:
- Tempo to timestamp conversion
- Default curve selection based on interval
- Auto-duck envelope insertion
- Expression interpolation

### 4.2 Key Design Principles

1. **Glissando is default** - Don't require marking every slide
2. **Expression is separate** - Volume track independent of pitch
3. **Curves have sensible defaults** - Linear for small intervals, S-curve for large
4. **Duck is automatic** - Unless explicitly disabled
5. **Timing is musical** - Beats and measures, not just milliseconds

### 4.3 Example: Complete Score

```aerotone
# Silent Night for AeroTone Model 12
# Arranged for single voice with expression

config {
  tempo: 60
  time: 6/8
  duck: auto(45%)
  default_curve: s-curve
  voice: spice_v2
}

# Verse 1
|: G3. A3' G3 | E3... |
|  G3. A3' G3 | E3... |
|  D3_  D3    | B2... |
|  C3_  C3    | G2... @70% :|

# Expression contour for verse
expr |: 100 100 100 | 100 |
     |  100 100 100 | 100 |
     |  90  85      | 80  |
     |  85  90      | 100 :|
```

---

## Part 5: Implementation Notes

### 5.1 Parser Requirements

A notation parser would need to:
1. Tokenize note names, durations, modifiers
2. Resolve tempo to absolute timestamps
3. Calculate transition times between notes
4. Generate expression envelopes
5. Insert duck triggers at note changes
6. Output event list for SpiceVoice

### 5.2 Playback Engine

```python
def play_score(voice: SpiceVoice, events: List[Event]):
    for event in events:
        voice.set_target_frequency(event.frequency)
        voice.set_expression(event.expression)
        # Let physics simulation handle the transition
        generate_audio_until(event.end_time)
```

The beauty of the SPICE simulation is that we don't need to calculate glissando curves - **the motor physics does it naturally**. We just set targets and let the PLL, motor inertia, and propeller drag create realistic transitions.

### 5.3 Notation-to-Circuit Mapping

| Notation Concept | Circuit Reality |
|-----------------|-----------------|
| Note pitch | Reference frequency to CD4046 |
| Transition curve | PLL loop filter response + motor inertia |
| Expression level | Expression pedal pot position |
| Duck envelope | RC envelope generator (τ = R×C) |
| Tempo | Event timing in control system |

---

## Part 6: Open Questions for Research

1. **Curve vocabulary** - What transition shapes do musicians actually want? Linear, exponential, S-curve sufficient? Or need Bezier control points?

2. **Expression granularity** - Per-note expression? Continuous envelope? Both?

3. **Multi-voice notation** - How to represent 12-voice arrangements? Orchestral score style?

4. **Real-time input** - How would a performer notate while playing? Ribbon controller capture?

5. **Microtonal support** - Frequencies between standard notes? Cents deviation?

6. **Weather as composition element** - Can weather patterns be "composed"? Atmospheric dynamics as musical structure?

7. **Fault injection** - Notation for intentional "broken" sounds? Component aging as timbral control?

---

## Appendix A: Note Frequency Reference (12-Blade Configuration)

**Formula:** RPM = Frequency × 5

### Two-Octave Reference (A2 to A4)

| Note | Frequency (Hz) | RPM | Tip Speed (m/s)* |
|------|----------------|-----|------------------|
| **A2** | 110.00 | 550 | 2.88 |
| A#2/Bb2 | 116.54 | 583 | 3.05 |
| B2 | 123.47 | 617 | 3.23 |
| **C3** | 130.81 | 654 | 3.42 |
| C#3/Db3 | 138.59 | 693 | 3.63 |
| D3 | 146.83 | 734 | 3.84 |
| D#3/Eb3 | 155.56 | 778 | 4.07 |
| **E3** | 164.81 | 824 | 4.31 |
| F3 | 174.61 | 873 | 4.57 |
| F#3/Gb3 | 185.00 | 925 | 4.84 |
| **G3** | 196.00 | 980 | 5.13 |
| G#3/Ab3 | 207.65 | 1,038 | 5.44 |
| **A3** | 220.00 | 1,100 | 5.76 |
| A#3/Bb3 | 233.08 | 1,165 | 6.10 |
| B3 | 246.94 | 1,235 | 6.46 |
| **C4** (Middle C) | 261.63 | 1,308 | 6.85 |
| C#4/Db4 | 277.18 | 1,386 | 7.25 |
| D4 | 293.66 | 1,468 | 7.69 |
| D#4/Eb4 | 311.13 | 1,556 | 8.14 |
| **E4** | 329.63 | 1,648 | 8.63 |
| F4 | 349.23 | 1,746 | 9.14 |
| F#4/Gb4 | 369.99 | 1,850 | 9.69 |
| **G4** | 392.00 | 1,960 | 10.26 |
| G#4/Ab4 | 415.30 | 2,077 | 10.87 |
| **A4** (Concert A) | 440.00 | 2,200 | 11.52 |

*Tip speed based on 100mm diameter propeller

### Quick Reference

| Octave | Lowest Note | Highest Note | RPM Range |
|--------|-------------|--------------|-----------|
| Low (2) | A2 (110 Hz) | G#2 (104 Hz) | 520-550 |
| Mid (3) | A3 (220 Hz) | G#3 (208 Hz) | 1,038-1,100 |
| High (4) | A4 (440 Hz) | G#4 (415 Hz) | 2,077-2,200 |

### Why 12 Blades?

The 12-blade configuration provides the optimal balance:
- **Lower RPM** for given frequency (vs fewer blades)
- **Richer harmonics** from more blade passages per revolution
- **Moderate mechanical stress** (vs 16-20 blades)
- **Practical motor sizing** - standard DC motors can achieve 550-2200 RPM easily

## Appendix B: Component Value Reference

| Component | Value | Purpose |
|-----------|-------|---------|
| C_envelope | 4.7µF | Duck timing |
| R_attack | ~12.7kΩ | 60ms attack (τ=RC) |
| R_release | ~29.8kΩ | 140ms release |
| C_555 | 220nF | PWM carrier timing |
| R_555_A | 10kΩ | 555 frequency set |
| R_555_B | 68kΩ | 555 duty cycle |
| R_loop | 100kΩ | PLL loop filter |
| C_loop | 10µF | PLL stability |

---

*Report generated for Deep Research consultation on musical notation systems for electromechanical glissando instruments.*
