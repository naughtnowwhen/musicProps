# SPICE-Validated Fault Signatures

## Gold Standard Reference

All fault signatures derived from ngspice simulations.
This is the SINGLE SOURCE OF TRUTH for the AeroTone fault diagnosis challenge.

---

## F001: Leaky Electrolytic Capacitor C2 (Loop Filter)

**Component**: 10µF electrolytic capacitor in PLL loop filter
**Fault Model**: 30kΩ parallel leakage resistance

| Measurement | Healthy | Faulty | Ratio |
|-------------|---------|--------|-------|
| DC Voltage | 7.5V | 6.5V | 0.87x |
| Ripple (Vpp) | 1.6mV | 461mV | **288x** |

**Diagnostic Signature**:
- Ripple > 20mV indicates fault
- DC level drops due to leakage current

**SPICE Model**: `compare_f001_ac.cir`

---

## F002: Burned Power Transistor Q1 (H-Bridge)

**Component**: NPN transistor Q1 in high-side H-bridge
**Fault Model**: 100Ω series resistance (damaged collector-emitter junction)

| Measurement | Healthy | Faulty |
|-------------|---------|--------|
| Motor Voltage | ~6V | ~3V |
| Motor Current | ~0.44A | **~0.03A** |

**Diagnostic Signature**:
- LOW voltage AND **LOW current**
- Damaged transistor restricts current flow

**SPICE Model**: `hbridge_simple.cir`

---

## F003: Noisy Op-Amp U2 (Signal Conditioner)

**Component**: LM358 op-amp in non-inverting amplifier configuration
**Fault Model**: Internal oscillation at 15kHz

| Measurement | Healthy | Faulty |
|-------------|---------|--------|
| Output Vpp | ~10V | ~16V+ |
| Noise Content | Clean | High-frequency |
| Rail Behavior | No overshoot | May overshoot |

**Diagnostic Signature**:
- Output has high-frequency noise superimposed
- Vpp may exceed normal range due to instability
- Distinct from F004: signal still responds to input

**SPICE Model**: `opamp_simple.cir`

---

## F004: Open Feedback Resistor R9 (Signal Conditioner)

**Component**: 100kΩ feedback resistor in op-amp circuit
**Fault Model**: Open circuit (infinite resistance)

| Measurement | Healthy | Faulty |
|-------------|---------|--------|
| Output Vpp | ~10V | **24V exactly** |
| Output Waveform | Sine wave | Square wave |
| Gain | 101x | Infinite |

**Diagnostic Signature**:
- Output SATURATED at rails constantly
- Square wave (not sinusoidal)
- Vpp = 24V (rail-to-rail)

**SPICE Model**: `opamp_simple.cir`

---

## F005: Shorted Flyback Diode D2 (H-Bridge)

**Component**: Flyback diode D2 in H-bridge
**Fault Model**: 5Ω parallel resistance (shorted junction)

| Measurement | Healthy | Faulty |
|-------------|---------|--------|
| Motor Voltage | ~6V | ~3V |
| Motor Current | ~0.44A | **~0.75A** |

**Diagnostic Signature**:
- LOW voltage AND **HIGH current**
- Short creates parallel path, increasing total current

**SPICE Model**: `hbridge_simple.cir`

---

## Key Differential Diagnosis

### F002 vs F005 (Both show low motor voltage):
| Fault | Motor Voltage | Motor Current | Cause |
|-------|---------------|---------------|-------|
| F002 | LOW | **LOW** | High series resistance |
| F005 | LOW | **HIGH** | Parallel short circuit |

### F003 vs F004 (Both affect conditioner output):
| Fault | Vpp | Waveform | Key Feature |
|-------|-----|----------|-------------|
| F003 | Variable | Noisy sine | High-frequency content |
| F004 | 24V exactly | Square wave | Saturated at rails |

---

## Running SPICE Validation

```bash
# Install ngspice
brew install ngspice

# Run individual models
cd fault_challenge/spice_models
ngspice -b compare_f001_ac.cir  # Loop filter validation
ngspice -b hbridge_simple.cir    # H-bridge validation
ngspice -b opamp_simple.cir      # Op-amp validation
```
