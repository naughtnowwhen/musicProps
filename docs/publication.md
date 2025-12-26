# AeroTone Model 12 Technical Publication

## Service Manual and Theory of Operation

**Document Version:** 1.0
**Date:** 1979
**Manufacturer:** Precision Propeller Instruments

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Theory of Operation](#2-theory-of-operation)
3. [System Block Diagram](#3-system-block-diagram)
4. [Circuit Sections](#4-circuit-sections)
   - 4.1 Power Supply
   - 4.2 CD4046 Phase-Locked Loop IC
   - 4.3 Loop Filter
   - 4.4 H-Bridge Motor Driver
   - 4.5 DC Motor
   - 4.6 Propeller Assembly
   - 4.7 Magnetic Pickup
   - 4.8 Signal Conditioner
5. [Component Reference](#5-component-reference)
6. [Test Points and Expected Values](#6-test-points-and-expected-values)
7. [Waveform Reference](#7-waveform-reference)
8. [Troubleshooting Guide](#8-troubleshooting-guide)

---

## 1. Introduction

The AeroTone Model 12 is a precision electronic musical instrument that produces tones using a rotating 12-blade propeller. The fundamental frequency is determined by the Blade Passage Frequency (BPF):

```
BPF = (RPM × Number of Blades) / 60
```

For a 12-blade propeller:
- 110 Hz (A2) requires 550 RPM
- 220 Hz (A3) requires 1100 RPM
- 440 Hz (A4) requires 2200 RPM

The instrument uses a closed-loop Phase-Locked Loop (PLL) control system to maintain precise pitch stability regardless of load variations, temperature changes, or air density fluctuations.

### Key Specifications

| Parameter | Value |
|-----------|-------|
| Frequency Range | 110 Hz - 440 Hz (A2 to A4) |
| Motor Supply | 12V DC |
| Logic Supply | 15V DC |
| Motor Type | Brushed DC |
| Propeller | 12-blade, 100mm diameter |
| Control Bandwidth | ~5 Hz |
| Pitch Stability | ±0.5% when locked |

---

## 2. Theory of Operation

### 2.1 Control System Overview

The AeroTone uses the motor as a "voltage-controlled oscillator" in a phase-locked loop. Unlike a conventional PLL where an electronic VCO generates the output frequency, here the motor speed (and thus blade passage frequency) is the controlled output.

**Control Loop:**
1. A reference frequency (target BPF) is generated digitally
2. The CD4046 phase comparator compares reference to feedback
3. Phase error is converted to a control voltage by the loop filter
4. The H-bridge drives the motor proportionally
5. The propeller spins, creating blade passages
6. The magnetic pickup senses blade passage
7. The signal conditioner produces a clean digital feedback signal
8. The loop locks when feedback matches reference

### 2.2 Frequency-to-Motor Relationship

The motor control uses a PID (Proportional-Integral-Derivative) control algorithm:

| Term | Circuit Equivalent | Function |
|------|-------------------|----------|
| P (Proportional) | Resistor divider | Immediate response to error |
| I (Integral) | Capacitor charging | Eliminates static offset |
| D (Derivative) | Differentiator | Anticipatory braking |

**Control Law:**
```
V_control = V_mid + Kp×error + Ki×∫error·dt + Kd×(d_error/dt)
```

Where:
- V_mid = VDD/2 = 7.5V (center point)
- Kp = 0.15 V/Hz
- Ki = 0.5 V/(Hz·s)
- Kd = 0.0 (disabled in authentic 1979 mode)

---

## 3. System Block Diagram

```
                                    AEROTONE MODEL 12 - SYSTEM BLOCK DIAGRAM

    ┌─────────────────────────────────────────────────────────────────────────────────────────┐
    │                                                                                         │
    │   REFERENCE                                                                             │
    │   FREQUENCY      ┌──────────────┐                                                       │
    │   (Target BPF)   │              │                                                       │
    │        ──────────►   CD4046     │                                                       │
    │                  │   Phase      │    ┌────────────┐    ┌────────────┐    ┌──────────┐  │
    │                  │   Comparator ├────►  Loop      ├────►  H-Bridge  ├────►   DC     │  │
    │                  │   (U1)       │    │  Filter    │    │  Driver    │    │  Motor   │  │
    │                  │              │    │  (R1,C1)   │    │  (H1)      │    │          │  │
    │                  └──────▲───────┘    └────────────┘    └────────────┘    └────┬─────┘  │
    │                         │                                                      │        │
    │                         │ FEEDBACK                                             │        │
    │                         │                                                      ▼        │
    │   ┌─────────────┐    ┌──┴──────────┐                                   ┌──────────────┐│
    │   │   Signal    │    │   Signal    │                                   │  12-Blade   ││
    │   │ Conditioner ◄────┤   Pickup    ◄───────────────────────────────────┤  Propeller  ││
    │   │   (U2)      │    │   (TACH)    │                                   │             ││
    │   └─────────────┘    └─────────────┘                                   └──────────────┘│
    │                                                                                         │
    │   POWER SUPPLIES:  +15V (V_logic)    +12V (V_supply)    GND                            │
    └─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Circuit Sections

### 4.1 Power Supply

The AeroTone requires two DC supplies:

| Rail | Voltage | Purpose | Current |
|------|---------|---------|---------|
| V_logic | +15V | CD4046, signal conditioning | 50mA max |
| V_supply | +12V | Motor driver, H-bridge | 2A max |
| GND | 0V | Common ground | - |

**Expected Measurements:**
- V_supply: 12.0V ±5% (11.4V - 12.6V)
- V_logic: 15.0V ±5% (14.25V - 15.75V)

---

### 4.2 CD4046 Phase-Locked Loop IC (U1)

The CD4046B is a CMOS PLL IC used for phase/frequency comparison. In this application, only the phase comparators are used - the motor serves as the "VCO."

#### Pin Configuration

| Pin | Name | Function | Typical Voltage |
|-----|------|----------|-----------------|
| 1 | PHASE OUT | PC1 output (XOR) | Pulsed 0-15V |
| 3 | COMP IN | Feedback input (from conditioner) | 0V or 15V |
| 4 | VCO OUT | VCO output (not used) | - |
| 5 | INH | Inhibit (grounded) | 0V |
| 8 | VSS | Ground | 0V |
| 9 | VCO IN | VCO control (not used) | - |
| 13 | PC2 OUT | PC2 output (edge-triggered) | 0V, 15V, or Hi-Z |
| 14 | SIG IN | Reference input | 0V or 15V |
| 16 | VDD | Positive supply | 15V |

#### Phase Comparator II Operation

PC2 is edge-triggered with three states:
- **HIGH (15V)**: Reference leads feedback → Increase motor speed
- **LOW (0V)**: Feedback leads reference → Decrease motor speed
- **HIGH-Z**: Edges coincide → Loop is locked, hold voltage

**When locked:** PC2 output is high-impedance, and the loop filter capacitor holds the control voltage.

#### Timing Components

| Component | Value | Purpose |
|-----------|-------|---------|
| R1 (VCO) | 10kΩ | Sets f_max (not used, but present) |
| R2 (VCO) | 100kΩ | Sets f_min (not used) |
| C1 (VCO) | 100nF | Timing capacitor |

---

### 4.3 Loop Filter

The loop filter is a passive RC low-pass filter that converts the phase detector output pulses into a smooth DC control voltage.

#### Circuit

```
        Phase Detector Output
               │
               │
              ┌┴┐
              │ │ R1 = 100kΩ
              │ │
              └┬┘
               │
               ├──────────────► Control Voltage Out
               │
             ─────
             ─────  C1 = 10µF
               │
               │
              GND
```

#### Characteristics

| Parameter | Value |
|-----------|-------|
| R1 | 100kΩ |
| C1 | 10µF (electrolytic) |
| Time Constant (τ) | R1 × C1 = 1.0 second |
| Corner Frequency | 1/(2πτ) ≈ 0.16 Hz |

**Expected Measurements:**
- DC Voltage: 5V - 12V depending on target frequency
- At 220Hz target: ~7.5V
- AC Ripple (healthy): < 50mV RMS
- AC Ripple (faulty cap): > 200mV RMS

**IMPORTANT:** C1 is an electrolytic capacitor and is a common failure point. Symptoms of a leaky or dried-out C1:
- Excessive ripple on loop filter output
- Pitch instability / "warbling"
- Control voltage drifts toward VDD/2
- Loop fails to maintain lock

---

### 4.4 H-Bridge Motor Driver (H1)

The H-bridge converts the control voltage (0-15V) to motor drive voltage (0-12V).

#### Topology

```
                    +12V (V_supply)
                       │
            ┌──────────┼──────────┐
            │          │          │
         [Q1 PNP]      │      [Q3 PNP]
         TIP32         │       TIP32
            │          │          │
            ├────[MOTOR]──────────┤
            │          │          │
         [Q2 NPN]      │      [Q4 NPN]
         TIP31         │       TIP31
            │          │          │
            ├────┬─────┴─────┬────┤
            │    │           │    │
          [D1]  [Rs]       [Rs]  [D2]
          1N4001 0.5Ω      0.5Ω 1N4001
            │    │           │    │
           GND  GND         GND  GND
```

#### Components

| Ref | Part | Value/Type | Function |
|-----|------|------------|----------|
| Q1, Q3 | TIP32 | PNP power transistor | High-side drivers |
| Q2, Q4 | TIP31 | NPN power transistor | Low-side drivers |
| D1-D4 | 1N4001 | Flyback diodes | Inductive protection |
| Rs | 0.5Ω | Sense resistor | Current sensing |

#### Operating Parameters

| Parameter | Value |
|-----------|-------|
| V_supply | 12.0V |
| Vce_sat (per transistor) | 0.7V |
| Total saturation drop | 1.4V (2 transistors in series) |
| Maximum motor voltage | 10.6V |
| Current limit | 2.0A |

**Control Voltage to Motor Voltage Relationship:**
```
V_motor = (V_control / V_logic) × (V_supply - 2×Vce_sat)
V_motor = (V_control / 15) × 10.6
```

**Expected Measurements:**
- Motor voltage at 220Hz: ~6V
- Motor current at 220Hz: ~0.3A
- Transistor temperature: 35-50°C (with heatsink)

**IMPORTANT:** Q1-Q4 are power transistors that can fail from:
- Thermal damage (check heatsink mounting)
- Excessive current (sense resistor failure)
- Voltage spikes (flyback diode failure)

Symptom of burned transistor:
- Reduced motor voltage (even at high control voltage)
- Motor runs slow
- Asymmetric drive (one direction only)

---

### 4.5 DC Motor

The motor is a brushed DC motor sized for the required RPM range.

#### Specifications

| Parameter | Symbol | Value |
|-----------|--------|-------|
| Armature Resistance | R | 2.0Ω |
| Armature Inductance | L | 0.5mH |
| Back-EMF Constant | Ke | 0.05 V/(rad/s) |
| Torque Constant | Kt | 0.05 N·m/A |
| Rotor Inertia | J_motor | 10 µkg·m² |
| Damping | B | 5 µN·m/(rad/s) |
| Maximum Voltage | - | 12V |

#### Motor Equations

**Electrical:**
```
V = I×R + L×(dI/dt) + Ke×ω
```

**Mechanical:**
```
J×(dω/dt) = Kt×I - B×ω - T_load
```

Where:
- V = applied voltage
- I = armature current
- ω = angular velocity (rad/s)
- T_load = propeller drag torque

#### Operating Points

| Frequency | RPM | Motor Voltage | Back-EMF | Current |
|-----------|-----|---------------|----------|---------|
| 110 Hz | 550 | ~3.5V | ~2.9V | ~0.15A |
| 220 Hz | 1100 | ~6.0V | ~5.8V | ~0.25A |
| 330 Hz | 1650 | ~8.5V | ~8.6V | ~0.35A |
| 440 Hz | 2200 | ~11.0V | ~11.5V | ~0.45A |

**Note:** At higher frequencies, motor voltage approaches supply limit. Above ~400Hz, the loop filter saturates at VDD (15V) and cannot increase motor speed further.

---

### 4.6 Propeller Assembly

The 12-blade propeller is the acoustic element that produces the musical tone.

#### Specifications

| Parameter | Value |
|-----------|-------|
| Number of Blades | 12 |
| Diameter | 100mm |
| Hub Diameter | 20mm |
| Material | Injection-molded ABS |
| Mass | 20g |
| Moment of Inertia | 20 µkg·m² |

#### Blade Passage Frequency

```
BPF = (RPM × 12) / 60 = RPM / 5
```

| Note | Frequency | Required RPM |
|------|-----------|--------------|
| A2 | 110.0 Hz | 550 RPM |
| C3 | 130.8 Hz | 654 RPM |
| E3 | 164.8 Hz | 824 RPM |
| A3 | 220.0 Hz | 1100 RPM |
| C4 | 261.6 Hz | 1308 RPM |
| E4 | 329.6 Hz | 1648 RPM |
| A4 | 440.0 Hz | 2200 RPM |

#### Aerodynamic Load

The propeller presents a load torque to the motor:

```
T_load = Cq × ρ × n² × D⁵
```

Where:
- Cq = 0.02 (drag coefficient)
- ρ = 1.225 kg/m³ (air density)
- n = revolutions per second
- D = 0.1m (diameter)

---

### 4.7 Magnetic Pickup (TACH)

The magnetic pickup senses propeller blade passage using a permanent magnet and coil assembly.

#### Specifications

| Parameter | Value |
|-----------|-------|
| Coil Resistance | 500Ω |
| Coil Inductance | 100mH |
| Sensitivity | 0.05 V/(rad/s) at blade rate |
| Pole Pieces | 1 |
| Air Gap | 2mm nominal |

#### Operating Principle

The pickup generates a sinusoidal voltage proportional to the rate of change of magnetic flux:

```
V_pickup = Sensitivity × ω_blade = Sensitivity × ω_motor × num_blades
```

**Expected Output:**
- At 220Hz (1100 RPM): ~50-100mV peak
- At 440Hz (2200 RPM): ~100-200mV peak

The output is a low-amplitude AC signal requiring amplification before use.

---

### 4.8 Signal Conditioner (U2)

The signal conditioner amplifies the pickup signal and converts it to a digital pulse train for the CD4046.

#### Block Diagram

```
Pickup ──► [HP Filter] ──► [Amplifier] ──► [Schmitt Trigger] ──► To CD4046
              │               │                  │
           C=100nF         Gain=100           Hysteresis
           fc=16Hz         ±12V rails          ±0.5V
```

#### Stages

**1. High-Pass Filter:**
- Removes DC offset
- τ = 10ms (fc ≈ 16Hz)
- Passes blade passage frequencies

**2. Op-Amp Amplifier:**
- Gain: 100× (40dB)
- Part: 741 or equivalent
- Supply: ±12V
- Output clips at ±12V

**3. Schmitt Trigger Comparator:**
- Threshold: 0V
- Hysteresis: ±0.5V
- Upper threshold: +0.25V
- Lower threshold: -0.25V
- Output: 0V or 15V (CD4046 compatible)

#### Expected Measurements

| Test Point | Healthy Value |
|------------|---------------|
| Amplifier output (Vpp) | 2-8V depending on speed |
| Amplifier output (exceeds rails) | No - should stay within ±12V |
| Digital output frequency | Matches target BPF ±1% |
| Noise on amplified signal | < 100mV RMS |

**IMPORTANT:** The op-amp (U2) is a potential failure point:
- ESD damage causes excessive noise
- Thermal damage causes output saturation
- Symptom: Output exceeds ±12V rails (damaged protection)
- Symptom: High noise even at low speeds
- Symptom: Intermittent oscillation/squealing

---

## 5. Component Reference

### Complete Bill of Materials

| Ref | Description | Value | Package |
|-----|-------------|-------|---------|
| U1 | PLL IC | CD4046B | DIP-16 |
| U2 | Op-amp | µA741 | DIP-8 |
| Q1, Q3 | PNP Power Transistor | TIP32 | TO-220 |
| Q2, Q4 | NPN Power Transistor | TIP31 | TO-220 |
| D1-D4 | Rectifier Diode | 1N4001 | DO-41 |
| R1 (VCO) | Resistor | 10kΩ | 1/4W |
| R2 (VCO) | Resistor | 100kΩ | 1/4W |
| R1 (Loop) | Resistor | 100kΩ | 1/4W |
| Rs (×2) | Sense Resistor | 0.5Ω 2W | Wirewound |
| C1 (VCO) | Capacitor | 100nF | Ceramic |
| C1 (Loop) | Capacitor | 10µF 25V | Electrolytic |
| M1 | DC Motor | See spec | - |
| PROP | Propeller | 12-blade 100mm | ABS |
| TACH | Magnetic Pickup | See spec | - |

---

## 6. Test Points and Expected Values

### Power Rails

| Test Point | Expected Value | Tolerance |
|------------|----------------|-----------|
| v_supply | 12.0V | ±5% |
| v_logic | 15.0V | ±5% |
| gnd | 0V | Reference |

### PLL Section (at 220Hz target)

| Test Point | Type | Expected Value |
|------------|------|----------------|
| cd4046_sig_in | Digital | 0V/15V at 220Hz |
| cd4046_comp_in | Digital | 0V/15V at ~220Hz |
| cd4046_pc2_out | Tri-state | Hi-Z when locked |

### Loop Filter (at 220Hz target)

| Test Point | Type | Expected Value |
|------------|------|----------------|
| loop_filter_out | DC | ~7.5V |
| loop_filter_cap_voltage | DC + ripple | ~7.5V, <50mV ripple |

### Motor Driver (at 220Hz target)

| Test Point | Type | Expected Value |
|------------|------|----------------|
| driver_control_voltage | DC | ~7.5V |
| motor_voltage | DC | ~6.0V |
| motor_current | DC | ~0.25A |
| hbridge_q1_vce | DC | <1.0V (saturated) |

### Motor and Propeller

| Test Point | Type | Expected Value |
|------------|------|----------------|
| motor_rpm | Tach | 1100 RPM |
| motor_back_emf | AC | ~5.8V peak |
| prop_frequency | Frequency | 220Hz ±1% |

### Feedback Path

| Test Point | Type | Expected Value |
|------------|------|----------------|
| pickup_raw | AC | ~75mV peak |
| cond_opamp_out | AC | 2-8Vpp |
| cond_digital_out | Digital | 0V/15V at 220Hz |

---

## 7. Waveform Reference

### Healthy Loop Filter Output

When the loop is locked and operating normally:

```
Voltage
   │
15V├─────────────────────────────────────────────────
   │
   │
 8V├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
   │              ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
7.5V├─────────────█████████████████████████████████── (stable, minimal ripple)
   │              ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
   │
 0V├─────────────────────────────────────────────────
   └─────────────────────────────────────────────────► Time
                  │←──── Ripple < 50mV ────→│
```

### Faulty Capacitor (C1 Leaky)

When C1 has dried out or become leaky:

```
Voltage
   │
15V├─────────────────────────────────────────────────
   │
   │         ╱╲    ╱╲    ╱╲    ╱╲    ╱╲    ╱╲
 9V├────────╱──╲──╱──╲──╱──╲──╱──╲──╱──╲──╱──╲────── (excessive ripple)
   │       ╱    ╲╱    ╲╱    ╲╱    ╲╱    ╲╱    ╲
 6V├──────╱────────────────────────────────────╲─────
   │
 0V├─────────────────────────────────────────────────
   └─────────────────────────────────────────────────► Time
           │←────── Ripple > 200mV ─────→│

   Note: Voltage drifts toward VDD/2 (7.5V) instead of holding
```

### Healthy Conditioner Output

```
Voltage
    │
+12V├─────────────────────────────────────────────────
    │      ╱╲      ╱╲      ╱╲      ╱╲      ╱╲
 +6V├─────╱──╲────╱──╲────╱──╲────╱──╲────╱──╲───────
    │    ╱    ╲  ╱    ╲  ╱    ╲  ╱    ╲  ╱    ╲
  0V├───╱──────╲╱──────╲╱──────╲╱──────╲╱──────╲─────
    │
 -6V├───────────────────────────────────────────────── (clean sine-like wave)
    │
-12V├─────────────────────────────────────────────────
    └─────────────────────────────────────────────────► Time
```

### Faulty Op-Amp (Noisy/Damaged)

```
Voltage
    │
+15V├──────────╱╲────────────────╱╲──────────────────  ← Exceeds +12V rail!
    │     ╱╲  ╱  ╲    ╱╲   ╱╲   ╱  ╲  ╱╲
+12V├────╱╲╱╲╱────╲╱╲╱╲─╲╲╱──╲╲╱╲╱────╲╱╲╲──────────
    │   ╱        ╲       ╲    ╲       ╲
  0V├──╱──────────╲───────╲────╲───────╲─────────────
    │ ╱            ╲       ╲    ╲
-12V├╱──────────────╲───────╲────╲───────────────────
    │                ╲       ╲    ╲
-15V├─────────────────╲───────╲────╲─────────────────  ← Exceeds -12V rail!
    └─────────────────────────────────────────────────► Time

    Note: Noisy, erratic waveform with clipping beyond ±12V rails
    Indicates damaged output protection circuitry
```

---

## 8. Troubleshooting Guide

### Systematic Approach

1. **Verify Power Supplies** - Check V_supply (12V) and V_logic (15V)
2. **Check PLL Reference** - Verify reference signal at CD4046 SIG_IN
3. **Check Loop Filter** - Measure DC level and AC ripple
4. **Check Motor Driver** - Compare control voltage to motor voltage
5. **Check Feedback Path** - Trace signal from pickup to CD4046

### Common Faults and Symptoms

#### Loop Filter Capacitor (C1) Leaky/Dried

| Symptom | Expected | Faulty |
|---------|----------|--------|
| Loop filter AC ripple | < 50mV RMS | > 200mV RMS |
| Pitch stability | Stable | Warbling, drifting |
| Control voltage | Holds steady | Drifts toward VDD/2 |
| Lock time | < 1 second | Never fully locks |

**Diagnosis:** Capture waveform at `loop_filter_cap_voltage`. Excessive ripple (>200mV) indicates capacitor failure.

---

#### H-Bridge Transistor (Q1-Q4) Burned

| Symptom | Expected | Faulty |
|---------|----------|--------|
| Motor voltage | Proportional to control | Reduced, erratic |
| Motor speed | Reaches target | Runs slow |
| Transistor Vce | < 1V (saturated) | > 3V |
| Motor current | Normal | Reduced or zero |

**Diagnosis:** Compare control voltage to motor voltage. If control is high but motor voltage is low, suspect high-side transistor damage.

---

#### Op-Amp (U2) Noisy/Damaged

| Symptom | Expected | Faulty |
|---------|----------|--------|
| Conditioner Vpp | 2-8V | Erratic, noisy |
| Output within rails | Yes (±12V) | Exceeds ±12V |
| Noise at idle | < 100mV RMS | > 500mV RMS |
| Feedback quality | Clean pulses | Jittery, intermittent |

**Diagnosis:** Capture waveform at `cond_opamp_out`. Check if output exceeds ±12V rails (indicates damaged output stage). High noise indicates ESD or thermal damage.

---

#### Flyback Diode (D2) Shorted

| Symptom | Expected | Faulty |
|---------|----------|--------|
| Motor voltage | ~6V at 220Hz | Reduced (~3.5V) |
| Motor current | ~0.25A at 220Hz | Increased (~0.4A) |
| Motor speed | Matches target | Runs slow |
| Voltage/current ratio | ~24Ω effective | ~9Ω effective |

**Diagnosis:** Compare motor voltage to motor current. A shorted flyback diode causes reduced voltage but increased current (power dissipated in short).

---

#### Current Sense Resistor (R5) Open

| Symptom | Expected | Faulty |
|---------|----------|--------|
| Motor current reading | 0.25A at 220Hz | 0A (always) |
| Current limiting | Active at 2A | Not functional |
| Motor operation | Normal | May work but unprotected |

**Diagnosis:** If motor_current always reads 0A regardless of motor activity, the sense resistor is open.

---

### Quick Diagnostic Table

| Symptom | Check First | Then Check |
|---------|-------------|------------|
| Pitch warbles/drifts | Loop filter C1 | Pickup signal |
| Motor runs slow | H-bridge transistors | Flyback diodes |
| Noisy/scratchy sound | Op-amp U2 | Pickup gap |
| Won't start | Power supplies | CD4046 |
| Overheats | Current limit | Transistor heatsinks |
| Limited pitch range | Motor voltage ceiling | CD4046 VCO (if used) |

---

## Appendix A: Schematic Reference Designators

| Ref | Description |
|-----|-------------|
| U1 | CD4046 PLL IC |
| U2 | 741 Op-Amp (Signal Conditioner) |
| Q1 | H-Bridge High-Side PNP (Left) |
| Q2 | H-Bridge Low-Side NPN (Left) |
| Q3 | H-Bridge High-Side PNP (Right) |
| Q4 | H-Bridge Low-Side NPN (Right) |
| D1-D4 | Flyback Diodes |
| R1 | Loop Filter Resistor (100kΩ) |
| R5 | Current Sense Resistor (0.5Ω) |
| C1 | Loop Filter Capacitor (10µF) |
| M1 | DC Motor |
| PROP | 12-Blade Propeller |
| TACH | Magnetic Pickup |

---

**END OF DOCUMENT**

*© 1979 Precision Propeller Instruments. All rights reserved.*
