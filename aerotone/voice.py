"""
PropellerVoice - Integrated motor/propeller/acoustic simulation

This is the main class that ties together:
  - DC motor simulation
  - Propeller aerodynamics
  - PID speed control (placeholder for PLL)
  - Acoustic synthesis

One PropellerVoice = one key on the AeroTone keyboard
"""

import numpy as np
from .motor import DCMotor, MotorParams, SimplePIDController
from .propeller import Propeller, PropellerParams, rpm_for_frequency, NOTES
from .acoustics import PropellerSynth, AcousticParams


class PropellerVoice:
    """
    Complete simulation of one AeroTone voice channel.

    Integrates:
      - Motor electrical/mechanical dynamics
      - Propeller aerodynamic loading
      - Speed control (PID, later PLL)
      - Acoustic synthesis

    Usage:
        voice = PropellerVoice()
        voice.set_target_frequency(110)  # A2

        # In your audio callback or main loop:
        voice.update_physics(dt=0.001)  # Run at 1kHz for physics
        audio = voice.generate_audio(num_samples)
    """

    def __init__(self,
                 motor_params: MotorParams = None,
                 propeller_params: PropellerParams = None,
                 acoustic_params: AcousticParams = None,
                 sample_rate: int = 44100):

        # Create subsystems
        self.motor = DCMotor(motor_params)
        self.propeller = Propeller(propeller_params)
        self.controller = SimplePIDController()
        self.synth = PropellerSynth(sample_rate, acoustic_params)

        self.sample_rate = sample_rate

        # Connect propeller to motor
        self.motor.load_inertia = self.propeller.get_inertia()

        # State
        self.target_frequency = 0.0
        self.target_rpm = 0.0
        self.active = False

        # Physics simulation rate
        self.physics_rate = 1000  # Hz
        self.physics_dt = 1.0 / self.physics_rate
        self.physics_accumulator = 0.0

    def set_target_frequency(self, frequency: float):
        """
        Set the target blade passage frequency.

        Args:
            frequency: Target BPF in Hz (e.g., 110 for A2)
        """
        self.target_frequency = frequency
        self.target_rpm = rpm_for_frequency(frequency, self.propeller.params.num_blades)
        self.controller.set_target(self.target_rpm)
        self.active = frequency > 0

    def set_target_note(self, note: str):
        """
        Set target frequency by note name.

        Args:
            note: Note name (e.g., 'A2', 'C#3')
        """
        freq = NOTES.get(note.upper())
        if freq:
            self.set_target_frequency(freq)
        else:
            raise ValueError(f"Unknown note: {note}")

    def update_physics(self, dt: float):
        """
        Update motor and propeller physics.

        Call this at a fixed rate (e.g., 1kHz) for accurate simulation.

        Args:
            dt: Time step in seconds
        """
        # Accumulate time for physics steps
        self.physics_accumulator += dt

        while self.physics_accumulator >= self.physics_dt:
            # Update controller
            voltage = self.controller.update(self.motor.rpm, self.physics_dt)
            self.motor.set_voltage(voltage if self.active else 0)

            # Update propeller loading based on current speed
            self.propeller.update(self.motor.omega)
            self.motor.load_torque = self.propeller.get_load_torque()

            # Update motor
            self.motor.update(self.physics_dt)

            self.physics_accumulator -= self.physics_dt

        # Update synthesizer operating point
        acoustic_params = self.propeller.get_acoustic_params()
        self.synth.set_operating_point(
            bpf=acoustic_params['bpf'],
            thrust=max(acoustic_params['thrust'], 0.1) if self.active else 0,
            num_blades=acoustic_params['num_blades'],
            has_serrations=acoustic_params['has_serrations']
        )

    def generate_audio(self, num_samples: int) -> np.ndarray:
        """
        Generate audio samples.

        This should be called from the audio thread/callback.

        Args:
            num_samples: Number of samples to generate

        Returns:
            numpy array of audio samples
        """
        # Also update physics for the audio block duration
        audio_duration = num_samples / self.sample_rate
        self.update_physics(audio_duration)

        return self.synth.generate(num_samples)

    @property
    def current_rpm(self) -> float:
        """Current motor RPM"""
        return self.motor.rpm

    @property
    def current_frequency(self) -> float:
        """Current blade passage frequency"""
        return self.propeller.blade_passage_frequency

    @property
    def is_locked(self) -> bool:
        """
        Is the PLL (controller) locked to target frequency?

        For PID, this means we're within 0.5% of target.
        Real PLL will have actual lock detection.
        """
        if self.target_rpm == 0:
            return False
        error_pct = abs(self.motor.rpm - self.target_rpm) / self.target_rpm
        return error_pct < 0.005  # 0.5% = roughly 8 cents

    def get_state(self) -> dict:
        """Return complete state for monitoring/display"""
        return {
            'active': self.active,
            'target_frequency': self.target_frequency,
            'target_rpm': self.target_rpm,
            'current_rpm': self.motor.rpm,
            'current_frequency': self.current_frequency,
            'frequency_error_hz': self.current_frequency - self.target_frequency,
            'frequency_error_cents': self._cents_error(),
            'is_locked': self.is_locked,
            'motor_voltage': self.motor.voltage,
            'motor_current': self.motor.current,
            'motor_temperature': self.motor.temperature,
            'propeller_torque': self.propeller.torque,
            'propeller_thrust': self.propeller.thrust,
        }

    def _cents_error(self) -> float:
        """Frequency error in cents (musical unit)"""
        if self.target_frequency == 0 or self.current_frequency == 0:
            return 0.0
        ratio = self.current_frequency / self.target_frequency
        return 1200 * np.log2(ratio)

    def reset(self):
        """Reset to initial state"""
        self.motor.omega = 0.0
        self.motor.current = 0.0
        self.motor.voltage = 0.0
        self.propeller.omega = 0.0
        self.controller.reset()
        self.synth.reset()
        self.physics_accumulator = 0.0


class AeroTone:
    """
    Complete AeroTone Model 12 - 12-voice propeller organ.

    Each voice is assigned a chromatic note from A2 to G#3.
    """

    # Note assignments for the 12 voices
    VOICE_NOTES = ['A2', 'A#2', 'B2', 'C3', 'C#3', 'D3',
                   'D#3', 'E3', 'F3', 'F#3', 'G3', 'G#3']

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.voices = [PropellerVoice(sample_rate=sample_rate) for _ in range(12)]

        # Pre-assign frequencies
        for i, note in enumerate(self.VOICE_NOTES):
            self.voices[i].target_frequency = NOTES[note]
            self.voices[i].target_rpm = rpm_for_frequency(NOTES[note], 5)

    def key_on(self, voice_idx: int):
        """Press a key (activate a voice)"""
        if 0 <= voice_idx < 12:
            note = self.VOICE_NOTES[voice_idx]
            self.voices[voice_idx].set_target_note(note)

    def key_off(self, voice_idx: int):
        """Release a key (deactivate a voice)"""
        if 0 <= voice_idx < 12:
            self.voices[voice_idx].active = False
            self.voices[voice_idx].controller.set_target(0)

    def generate_audio(self, num_samples: int) -> np.ndarray:
        """Generate mixed audio from all voices"""
        output = np.zeros(num_samples)

        active_voices = [v for v in self.voices if v.active]
        if not active_voices:
            return output

        for voice in active_voices:
            output += voice.generate_audio(num_samples)

        # Normalize
        output /= np.sqrt(max(len(active_voices), 1))

        return np.clip(output, -1.0, 1.0)

    def reset(self):
        """Reset all voices"""
        for voice in self.voices:
            voice.reset()
