# AeroTone Phase 1 SPICE-Level Simulation Report

**Date:** December 2024
**Author:** Claude (with Peter Murphy)
**Status:** Phase 1 Complete - Phase 2 Research Needed

---

## Executive Summary

Phase 1 successfully created a working SPICE-level simulation of the AeroTone propeller voice with closed-loop motor speed control. The system achieves pitch accuracy within 1.6 cents (0.008% frequency error) and demonstrates realistic electromechanical behavior.

However, the phase-locked loop implementation deviates from the original CD4046-based design. We ended up using a **PI frequency discriminator** rather than a true phase detector, which works but isn't authentic to the 1979 circuit topology.

**Key Achievement:** Motor speed is controlled by a closed-loop system with real component values, and you can hear the pitch glide as the loop relocks between notes.

**Key Gap:** The CD4046 phase comparators (PC1/PC2) didn't work as expected for motor control. Research needed on proper motor-PLL topologies.

---

## What We Built

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPICE-LEVEL VOICE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TARGET FREQ ──┬──────────────────────────────────────────┐    │
│   (110 Hz)     │                                          │    │
│                │    ┌──────────────────┐                  │    │
│                │    │  FREQUENCY       │                  │    │
│                └───>│  DISCRIMINATOR   │<──────────┐      │    │
│                     │  (PI Control)    │           │      │    │
│                     └────────┬─────────┘           │      │    │
│                              │ Error voltage       │      │    │
│                              ▼                     │      │    │
│                     ┌──────────────────┐           │      │    │
│                     │  LOOP FILTER     │           │      │    │
│                     │  R=100kΩ C=10µF  │           │      │    │
│                     │  τ = 1 second    │           │      │    │
│                     └────────┬─────────┘           │      │    │
│                              │ Control voltage     │      │    │
│                              ▼                     │      │    │
│                     ┌──────────────────┐           │      │    │
│                     │  H-BRIDGE        │           │      │    │
│                     │  MOTOR DRIVER    │           │      │    │
│                     │  12V, 2A limit   │           │      │    │
│                     └────────┬─────────┘           │      │    │
│                              │ Motor voltage       │      │    │
│                              ▼                     │      │    │
│                     ┌──────────────────┐           │      │    │
│                     │  DC MOTOR        │           │      │    │
│                     │  R=2Ω, L=0.5mH   │           │      │    │
│                     │  Ke=Kt=0.05      │           │      │    │
│                     └────────┬─────────┘           │      │    │
│                              │ ω (angular vel)     │      │    │
│                              ▼                     │      │    │
│                     ┌──────────────────┐           │      │    │
│                     │  PROPELLER       │──────────────>AUDIO   │
│                     │  12-blade, 100mm │           │      │    │
│                     │  BPF = ω×12/2π   │           │      │    │
│                     └────────┬─────────┘           │      │    │
│                              │ Blade angle         │      │    │
│                              ▼                     │      │    │
│                     ┌──────────────────┐           │      │    │
│                     │  MAGNETIC        │           │      │    │
│                     │  PICKUP          │───────────┘      │    │
│                     └──────────────────┘                  │    │
│                                                           │    │
└───────────────────────────────────────────────────────────────┘
```

### Component Models Created

| Component | File | Fidelity |
|-----------|------|----------|
| DC Motor | `motor.py` | Full electrical + mechanical dynamics |
| Propeller | `propeller.py` | Aerodynamic drag, inertia |
| CD4046 PLL | `cd4046.py` | Behavioral model of PC1, PC2, VCO |
| Loop Filter | `cd4046.py` | RC filter with high-Z hold mode |
| H-Bridge Driver | `driver.py` | Voltage/current with thermal model |
| Magnetic Pickup | `driver.py` | Variable reluctance sensor |
| Signal Conditioner | `driver.py` | Amplifier + Schmitt trigger |
| Op-Amp | `circuit.py` | Gain, bandwidth, slew rate limiting |
| Resistor | `circuit.py` | With tolerance and aging |
| Capacitor | `circuit.py` | With ESR and aging |
| BJT (NPN/PNP) | `circuit.py` | Ebers-Moll simplified |
| Diode | `circuit.py` | Shockley equation |

### Final Performance

| Parameter | Spec | Achieved |
|-----------|------|----------|
| Frequency accuracy | ±0.1% (±1.7 cents) | 0.008% (1.6 cents) ✓ |
| Lock time | <2 seconds | ~4 seconds (needs tuning) |
| Frequency range | 110-208 Hz | 110-208 Hz ✓ |
| Control voltage range | 0-15V | 0-15V ✓ |
| Motor voltage | 0-12V | 0-12V ✓ |

---

## What Went Wrong: The PLL Struggle

### Attempt 1: CD4046 Phase Comparator II (PC2)

**The Plan:**
Use the edge-triggered phase detector (PC2) as designed for frequency synthesis PLLs.

**What Happened:**
```
0.0s: ctrl=0.31V, BPF=0.0Hz, err=-110.0Hz
0.5s: ctrl=3.98V, BPF=199.1Hz, err=+89.1Hz    ← WAY overshoot!
1.0s: ctrl=4.16V, BPF=214.0Hz, err=+104.0Hz   ← Oscillating
...
Final: Actual=209.95Hz, Locked=False           ← Never locked
```

**Why It Failed:**
1. PC2 is designed for **frequency synthesis** where the VCO is inside the IC
2. In our topology, the **motor IS the VCO** - it's external
3. PC2's three-state output (HIGH/LOW/High-Z) doesn't map well to motor drive
4. The edge timing between reference and feedback created unstable dynamics

### Attempt 2: CD4046 Phase Comparator I (PC1 - XOR)

**The Plan:**
Use the simpler XOR phase detector which averages to Vdd/2 when locked.

**What Happened:**
```
0.0s: ctrl=0.01V, BPF=0.0Hz, err=-110.0Hz
1.0s: ctrl=7.38V, BPF=102.02Hz, err=-7.98Hz
2.0s: ctrl=7.51V, BPF=103.6Hz, err=-6.4Hz
...
Final: Actual=101.6Hz, Locked=False            ← Static error!
```

**Why It Failed:**
1. XOR detector has a fundamental DC problem for motor control
2. When locked, PC1 output averages to **exactly Vdd/2** regardless of frequency
3. But different target frequencies need different motor voltages!
4. 110 Hz needs ~7V, 200 Hz needs ~10V - XOR can't distinguish

### Attempt 3: Increased Loop Gain

**The Plan:**
Maybe the gain is too low. Increase it to reduce static error.

**What Happened:**
Got closer (1.9 Hz error instead of 8 Hz) but still had static offset.

**Why It Failed:**
Proportional control alone (Type 1 loop) always has static error when there's a DC load. The motor needs a specific voltage to maintain speed against friction/drag, and the proportional controller can't provide it without error.

### Solution: PI Frequency Discriminator (Type 2 Loop)

**What We Did:**
Abandoned the CD4046 phase comparators and implemented a direct frequency discriminator with PI control:

```python
# Measure frequency error directly
freq_error = target_frequency - actual_frequency

# Proportional term
p_term = freq_error * 0.15  # V/Hz

# Integral term (eliminates static error)
integral += freq_error * dt * 0.5
integral = clip(integral, -5V, +5V)  # Anti-windup

# Control voltage
control = Vdd/2 + p_term + integral
```

**Why It Works:**
1. The **integral term** accumulates error over time
2. Even tiny steady-state error causes integral to grow
3. Integral keeps growing until error reaches zero
4. This is a **Type 2 loop** - zero static error by design

**Result:**
```
5.0s: ctrl=7.92V, BPF=110.00Hz, err=+0.004Hz (0.00%)
Final: Actual=109.9911Hz, Error=-0.0089Hz, Locked=True ✓
```

---

## The Fundamental Problem: PLL vs Motor Control

### Why CD4046 Doesn't Work Here

The CD4046 was designed for **frequency synthesis** where:
- The VCO is inside the chip (or a direct voltage-to-frequency device)
- VCO responds instantly to control voltage
- Phase comparison makes sense because both signals are clean square waves

In our **motor control** application:
- The "VCO" is a motor + propeller (massive inertia!)
- Motor response is slow (hundreds of milliseconds)
- The feedback signal comes through a pickup + conditioner chain
- There's mechanical resonance and aerodynamic effects

This mismatch causes instability because:
1. The phase detector reacts to instantaneous phase
2. But the motor can't respond instantly
3. By the time the motor catches up, the phase has changed again
4. Result: hunting, oscillation, or wrong operating point

### What Real Synchrophasers Do

Real aircraft synchrophaser systems from the 1970s-80s use:

1. **Frequency discrimination** (not just phase)
   - Compare prop frequencies, not just phases
   - Generate error proportional to Δf

2. **Slow integration**
   - Very slow loop filter (seconds of time constant)
   - Prevents hunting and oscillation

3. **Limited authority**
   - Synchrophaser only trims ±2-5% of engine speed
   - Not responsible for setting absolute speed

4. **Often analog computing**
   - Op-amp integrators, not digital PLLs
   - Continuous-time control, not edge-triggered

---

## Ideas for Phase 2

### Option A: Authentic 1979 Analog Design

Build the control loop from discrete op-amps (LM741) without the CD4046:

```
┌─────────────────────────────────────────────────────────────┐
│  AUTHENTIC 1979 MOTOR CONTROL                               │
│                                                             │
│  Reference ──┬──> [Frequency-to-Voltage] ──┐               │
│  (Crystal    │         (F/V converter)     │               │
│   Divider)   │                              │               │
│              │    ┌───────────────┐         │               │
│              │    │  COMPARATOR   │<────────┘               │
│              │    │   (LM741)     │                         │
│              │    └───────┬───────┘                         │
│              │            │                                 │
│  Feedback ───┴──> [F/V]───┘                                │
│  (Pickup)                                                   │
│                           │ Error voltage                   │
│                           ▼                                 │
│                    ┌─────────────┐                         │
│                    │ INTEGRATOR  │ ← Eliminates static     │
│                    │  (LM741)    │   error (Type 2)        │
│                    └──────┬──────┘                         │
│                           │                                 │
│                           ▼                                 │
│                    ┌─────────────┐                         │
│                    │   DRIVER    │                         │
│                    └──────┬──────┘                         │
│                           │                                 │
│                           ▼                                 │
│                       [MOTOR]                               │
└─────────────────────────────────────────────────────────────┘
```

**Components needed:**
- LM2907 or LM331 Frequency-to-Voltage converter
- LM741 op-amps for comparison and integration
- Discrete H-bridge driver

**Pros:** Authentic to era, uses real ICs from 1979
**Cons:** More complex, more components to simulate

### Option B: Use CD4046 Correctly

The CD4046 CAN work if we:

1. **Use it for the reference only**
   - CD4046 VCO generates the reference frequency
   - Not used for motor feedback

2. **Separate frequency discriminator**
   - Use a dedicated F/V converter for the pickup
   - Compare the two DC voltages

3. **Add external integrator**
   - Op-amp integrator after the phase detector
   - Provides Type 2 loop behavior

### Option C: Hybrid Approach (What We Have Now)

Keep the current PI frequency discriminator but:

1. **Add realistic circuit implementation**
   - Model the F/V converter with real components
   - Model the integrator op-amp circuit
   - Add component tolerances and aging

2. **Keep CD4046 for authenticity**
   - Use it as a "lock detector" (it does detect lock)
   - Maybe use VCO output for a status indicator

3. **Document the deviation**
   - Technical manual notes that this is "late production" variant
   - Explains that early units used pure PLL but had hunting issues

---

## Recommended Phase 2 Tasks

### Research Needed

1. **Synchrophaser patents and literature**
   - How did Hamilton Standard, Woodward, etc. actually do it?
   - What control topology worked for propeller speed?

2. **Motor control PLLs**
   - Academic papers on PLL-based motor control
   - What modifications are needed vs frequency synthesis?

3. **1970s F/V converters**
   - LM2907, LM331, NE555-based designs
   - How to integrate with the control loop

### Implementation Tasks

1. **Frequency-to-Voltage converter model**
   - Realistic F/V converter circuit (e.g., LM2907)
   - Includes ripple, response time, linearity

2. **Op-amp integrator circuit**
   - Real component values (R, C)
   - Saturation, slew rate, drift

3. **Improved loop dynamics**
   - Proper loop compensation
   - Stability analysis (phase margin, gain margin)

4. **Fault injection for control loop**
   - Integrator cap dried out (static error returns)
   - F/V converter failed (loss of feedback)
   - Reference divider wrong count (wrong frequency)

---

## Files Created in Phase 1

```
aerotone/
├── __init__.py          # Package init
├── motor.py             # DC motor model (electrical + mechanical)
├── propeller.py         # Propeller aerodynamics
├── acoustics.py         # BPF sound synthesis
├── voice.py             # Simple PID voice (Phase 0)
├── circuit.py           # SPICE component models (R, C, L, BJT, Op-Amp)
├── cd4046.py            # CD4046 PLL model + loop filter
├── driver.py            # H-bridge, magnetic pickup, signal conditioner
└── spice_voice.py       # Integrated SPICE-level voice (Phase 1)

demos/
├── demo_simple.py       # Single note test
├── demo_scale.py        # Major scale with simple voice
├── demo_beats.py        # Beat frequency demonstration
├── demo_spice.py        # SPICE voice single note
└── demo_spice_scale.py  # SPICE voice scale
```

---

## Conclusion

Phase 1 successfully demonstrated that we can simulate a propeller voice with:
- Real motor physics (back-EMF, inertia, friction)
- Real circuit components (R, C, with tolerances)
- Closed-loop speed control with <2 cent accuracy
- Audible output that responds to control inputs

The main compromise is that the control loop uses a PI frequency discriminator instead of a pure CD4046 phase detector. This is arguably more realistic for motor control anyway, but doesn't match the original "CD4046 PLL" concept in the spec.

For Phase 2, we should research authentic motor-PLL topologies from the 1970s-80s era and implement them with full component-level simulation. This will provide the realistic fault injection scenarios needed for the troubleshooting benchmark.

**The good news:** The motor + propeller + pickup feedback loop works. The audio is audible and pitch-accurate. We have a solid foundation to build on.

---

*End of Report*
