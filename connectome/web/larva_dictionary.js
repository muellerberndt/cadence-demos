// The declared dictionary between the Platynereis larva's body and its compiled whole-body
// connectome. Unlike the fish, every input here lands on real sensory cells and every
// output is read from real effector cells; what is declared is only the physics of what a
// cell's activity does to the body.
//
// In: light per eye drives the adult eye photoreceptors of that side (PRC_l*, PRC_r*) and the
// larval eyespots; ultraviolet and pressure drive the four ciliary photoreceptors (cPRC);
// a tap drives the collar receptor neurons (hCR, ventralpygCR).
// Out: the prototroch ciliated cells' activation per side sets that side's ciliary beat; the
// cholinergic ciliomotor neuron MC arrests the cilia (Verasztó et al. 2017), the serotonergic
// Ser-h1 and Loop neurons raise the beat; the longitudinal muscles' activation per side bends
// the body (a turn), the parapodial and chaetal muscles elevate the parapodia (startle).
export const STEP_MS = 40;                // fish time per brain step, as on the fish page
export const LIGHT_LEVEL = 1.0;           // stimulus level on a photoreceptor at saturating light
export const SENSE_SATURATION = 0.1;      // a photoreceptor saturates at this fraction of the sense scale (declared: a larval eye is a light detector, not a light meter)
export const TAP_LEVEL = 1.0;             // a tap saturates the collar receptors (declared)
export const PRESSURE_TO_CPRC = false;    // declared off: the compiled cPRC pathway answers with the arrest (the UV response), and under the sign rule in force the pressure response of Bezares-Calderón et al. 2024, upward swimming, does not emerge; feeding depth into the cPRCs would sink the larva to the floor
export const CPRC_LEVEL = 0.3;            // at full ultraviolet or full pressure
export const BEAT_GAIN = 4.0;             // ciliary beat per unit of prototroch activation (a lit side at 0.057 reads 0.83, the other at 0.048 reads 0.79)
export const ARREST_GAIN = 8.0;           // arrest level per unit of MC activation (a startled larva arrests fully: a tap takes MC to 0.08 at the demo gain)
export const TAP_HOLD = 0.85;             // per brain step: the collar receptors' response outlasts the tap pulse (declared), about 0.4 s
export const SEROTONIN_GAIN = 2.0;        // beat added per unit of Ser-h1 and Loop activation
export const MUSCLE_GAIN = 4.0;           // muscle command per unit of longitudinal muscle activation
export const PARAPODIA_GAIN = 6.0;        // parapodial elevation per unit of parapodial muscle activation
export const BASELINE_BEAT = 0.3;         // the cilia beat on their own without any synaptic input; synaptic drive adds to it

const sat = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
const eye = (level) => sat(level / SENSE_SATURATION);

/** Stimuli for the brain, {population: level}, from the larva's senses (levels in [0,1]). */
export function stimuli(senses) {
  const out = {};
  if (senses.eye_left > 0) out["PRC:left"] = LIGHT_LEVEL * eye(senses.eye_left);
  if (senses.eye_right > 0) out["PRC:right"] = LIGHT_LEVEL * eye(senses.eye_right);
  if (senses.eyespot_left > 0) out["eyespot:left"] = LIGHT_LEVEL * eye(senses.eyespot_left);
  if (senses.eyespot_right > 0) out["eyespot:right"] = LIGHT_LEVEL * eye(senses.eyespot_right);
  const c = PRESSURE_TO_CPRC ? Math.max(senses.cprc || 0, senses.pressure || 0) : (senses.cprc || 0);
  if (c > 0) out["cPRC"] = CPRC_LEVEL * c;
  if (senses.mechanical > 0) out["collar"] = TAP_LEVEL * senses.mechanical;
  return out;
}

/** Body commands from the brain's readouts (means of named populations). */
export function commands(r) {
  const arrest = sat(ARREST_GAIN * (r.MC || 0));
  const sero = SEROTONIN_GAIN * ((r["Ser-h1"] || 0) + (r.Loop || 0));
  const beat = (side) => sat(BASELINE_BEAT + BEAT_GAIN * (r[`prototroch:${side}`] || 0) + sero) * (1 - arrest);
  return {
    ciliaLeft: beat("left"), ciliaRight: beat("right"), arrest,
    muscleLeft: sat(MUSCLE_GAIN * (r["MUSlong:left"] || 0)), muscleRight: sat(MUSCLE_GAIN * (r["MUSlong:right"] || 0)),
    parapodia: sat(PARAPODIA_GAIN * (r.parapodial || 0)),
  };
}

/** The populations the page reads, by name as the payload will carry them. */
export const READOUTS = ["prototroch:left", "prototroch:right", "MC", "Ser-h1", "Loop", "MUSlong:left", "MUSlong:right", "parapodial", "IN1", "INton", "INRGWa", "INNOS", "PRC:left", "PRC:right", "collar", "cPRC"];
