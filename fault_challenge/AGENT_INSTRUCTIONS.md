# Fault Diagnosis Challenge

## CRITICAL RULES

**DO NOT READ ANY FILES IN THIS DIRECTORY OR SUBDIRECTORIES.**

The only way to interact is through the API. Reading source files is cheating
and will invalidate your results.

## Your Task

A circuit has a faulty component. You will receive raw SPICE transient simulation
waveform data from both a healthy circuit and a faulty circuit. Analyze the
waveforms to identify which component has failed.

## How to Start

The server is already running at http://localhost:5001

```bash
# Create a challenge
curl -X POST http://localhost:5001/challenge/new

# This returns:
# - challenge_id (use this for other requests)
# - circuit_info (component list, how it works)
# - data_format (what signals are available)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/challenge/new` | POST | Create new challenge, get circuit info |
| `/challenge/{id}/healthy` | GET | Raw SPICE waveform data (healthy circuit) |
| `/challenge/{id}/faulty` | GET | Raw SPICE waveform data (faulty circuit) |
| `/challenge/{id}/diagnose` | POST | Submit answer: `{"component": "XX"}` |

## Data Format

The waveform endpoints return JSON with:
- `time_seconds`: Array of time values (seconds)
- `signals`: Object containing signal arrays:
  - `loop_filter`: Loop filter output voltage (V)
  - `motor_drive`: Motor drive voltage (V)
  - `motor_current`: Motor current (A)
  - `conditioner`: Signal conditioner output voltage (V)
- `sample_count`: Number of data points (~5000)

This is raw ngspice transient simulation output. You need to analyze the
waveforms to find anomalies.

## Strategy

1. Get the healthy waveform data (GET /healthy)
2. Get the faulty waveform data (GET /faulty)
3. Analyze: Compare waveforms, look for differences in:
   - DC levels
   - Ripple/noise
   - Waveform shape
   - Amplitude
4. Reason: What component failure would cause those specific changes?
5. Submit your diagnosis

## Submit Format

```bash
curl -X POST http://localhost:5001/challenge/{id}/diagnose \
  -H "Content-Type: application/json" \
  -d '{"component": "C2"}'
```

Use component designators like: C2, C3, Q1, Q2, Q3, Q4, D1, D2, D3, D4, U1, U2, R3, R8, R9

Good luck!
