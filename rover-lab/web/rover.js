// Measured differential-drive experience and shared model-based control: the JavaScript edition of rover.py.
//
// The body alone receives wheel gain. Models see executed commands and measured motion. The heading controller's
// coefficients are supplied by hand; nothing here evolves or learns a motor policy.

import { PyRandom } from './cadence.js';
import { makeModel, modelFromSnapshot, pysum } from './models.js';

export const ENGINE = 'JavaScript edition of the cadence-net 0.70.0 population solver';

export const PROTOCOL = {
  schema: 'rover-protocol-v1',
  development_seeds: [17, 29],
  confirmation_seeds: [101, 211, 307],
  weak_gain: 0.35,
  declared_gain_range: [0.25, 0.5],
  dt: 0.1,
  wheel_base: 0.7,
  max_speed: 1.5,
  action_levels: [0.0, 0.4, 0.8],
  bootstrap_epochs: 12,
  bootstrap_experiences: 9,
  online_presentations_per_transition: 2,
  replay_window: 12,
  episode_steps: 80,
  target_radius: 0.22,
  phases: [['normal', 160], ['weakened', 400], ['restored_probe', 160], ['restored_learning', 240]],
  controller: { forward_speed: 0.72, minimum_speed: 0.28, heading_gain: 1.8, turn_weight: 12.0 },
  demonstration_gate: {
    normal_success_rate_min: 0.75,
    weak_distance_integral_ratio_max: 0.9,
    weak_success_rate_min: 0.6,
    control_p95_ms_max: 100,
    deadline_miss_fraction_max: 0.05,
  },
  comparison_boundary: 'Equal information and transition budgets; each controller produces its own executed witnesses. No commercial advantage or useful-depth claim follows from a frozen-control gain.',
  selection_boundary: 'Development seeds may diagnose settings. Protocol and implementation hashes are recorded before reserved runs. All scheduled outcomes are retained.',
};

export const MAX_STEPS = 3600;
export const AUTOMATIC_STEPS = PROTOCOL.phases.reduce((n, [, length]) => n + length, 0);
// itertools.product(levels, repeat=2): the left wheel varies slowest.
export const ACTIONS = PROTOCOL.action_levels.flatMap(left => PROTOCOL.action_levels.map(right => [left, right]));
export const LABELS = { cadence: 'Cadence · learning', frozen: 'Cadence · frozen', adaptive: 'Adaptive estimator',
                        mlp: 'Small MLP', observer: 'Cadence · with observers' };
export const COLORS = { cadence: '#8de0c6', frozen: '#efae85', adaptive: '#9bbdf3', mlp: '#ccb0e9', observer: '#90b6b4' };
const PHASE_NAMES = ['normal', 'weakened', 'restored_probe', 'restored_learning'];
const ARM_ORDER = ['cadence', 'frozen', 'adaptive', 'mlp', 'observer'];

const now = () => performance.now();
const clone = value => JSON.parse(JSON.stringify(value));
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
// Python's float modulo: the result takes the divisor's sign.
const pymod = (a, b) => { const r = a % b; return r !== 0 && (r < 0) !== (b < 0) ? r + b : r; };
export const wrap = angle => pymod(angle + Math.PI, 2 * Math.PI) - Math.PI;

export function bodyMotion(action, rightGain = 1.0) {
  const left = action[0], right = rightGain * action[1];
  return [(left + right) / 2, (right - left) / 2];
}

// Exact constant-wheel-speed integration in metres and radians.
export function advance(pose, motion, dt = PROTOCOL.dt) {
  const v = motion[0] * PROTOCOL.max_speed;
  const w = motion[1] * 2 * PROTOCOL.max_speed / PROTOCOL.wheel_base;
  let [x, y] = pose;
  const theta = pose[2];
  const turn = w * dt;
  if (Math.abs(w) < 1e-10) {
    x = x + v * dt * Math.cos(theta);
    y = y + v * dt * Math.sin(theta);
  } else {
    x += v / w * (Math.sin(theta + turn) - Math.sin(theta));
    y -= v / w * (Math.cos(theta + turn) - Math.cos(theta));
  }
  return [x, y, wrap(theta + turn)];
}

// A heading-aware inverse-dynamics controller shared by every model.
export function selectAction(pose, target, predictions) {
  const dx = target[0] - pose[0], dy = target[1] - pose[1];
  const distance = Math.hypot(dx, dy);
  const angle = wrap(Math.atan2(dy, dx) - pose[2]);
  const config = PROTOCOL.controller;
  const desiredV = Math.max(config.minimum_speed, config.forward_speed * Math.min(1.0, distance)) * Math.max(0.0, Math.cos(angle));
  const desiredW = clamp(config.heading_gain * angle, -2.8, 2.8);
  const desiredTurn = desiredW * PROTOCOL.wheel_base / (2 * PROTOCOL.max_speed);
  let best = 0, bestScore = Infinity;
  ACTIONS.forEach((a, i) => {
    const p = predictions[i];
    const score = (p[0] - desiredV) ** 2 + config.turn_weight * (p[1] - desiredTurn) ** 2 + 0.001 * (a[0] ** 2 + a[1] ** 2);
    if (score < bestScore) { bestScore = score; best = i; }
  });
  return ACTIONS[best].slice();
}

export function route(seed, count = 2048) {
  const rng = new PyRandom(seed + 91000);
  const result = [];
  for (let i = 0; i < count; i++) {
    const radius = rng.uniform(1.8, 2.7), angle = rng.uniform(-0.85, 0.85);
    result.push([radius * Math.cos(angle), radius * Math.sin(angle)]);
  }
  return result;
}

const emptyMetrics = () => ({ steps: 0, targets: 0, attempts: 0, distance_integral: 0.0, squared_prediction_error: 0.0,
                              learning_presentations: 0, latencies_ms: [], command_ages_ms: [], queue_delays_ms: [],
                              deadline_misses: 0 });

export function summarize(metrics) {
  const result = {};
  for (const [phase, row] of Object.entries(metrics)) {
    const value = {};
    for (const [k, v] of Object.entries(row)) if (!Array.isArray(v)) value[k] = v;
    value.success_rate = row.targets / Math.max(1, row.attempts);
    value.prediction_rmse = Math.sqrt(row.squared_prediction_error / Math.max(1, row.steps));
    for (const key of ['latencies_ms', 'command_ages_ms', 'queue_delays_ms']) {
      const data = row[key].slice().sort((a, b) => a - b);
      value[key.replace('_ms', '_p95_ms')] = data.length ? data[Math.min(data.length - 1, Math.ceil(0.95 * data.length) - 1)] : 0;
    }
    result[phase] = value;
  }
  return result;
}

export function demonstrationGate(metrics, auto = true) {
  const live = metrics.cadence || {}, frozen = metrics.frozen || {};
  const complete = auto && PROTOCOL.phases.every(([phase, length]) =>
    phase in live && phase in frozen && Object.values(metrics).every(arm => arm[phase]?.steps === length));
  if (!complete) return { complete: false, passed: false };
  const spec = PROTOCOL.demonstration_gate;
  const weak = live.weakened, control = frozen.weakened;
  const ratio = weak.distance_integral / Math.max(1e-12, control.distance_integral);
  const phases = Object.values(live);
  const checks = {
    normal_targets: live.normal.success_rate >= spec.normal_success_rate_min,
    recovery_distance: ratio <= spec.weak_distance_integral_ratio_max,
    weak_targets: weak.success_rate >= spec.weak_success_rate_min,
    latency: phases.every(v => v.command_ages_p95_ms <= spec.control_p95_ms_max),
    deadlines: phases.reduce((n, v) => n + v.deadline_misses, 0) / Math.max(1, phases.reduce((n, v) => n + v.steps, 0))
      <= spec.deadline_miss_fraction_max,
  };
  return { complete: true, passed: Object.values(checks).every(Boolean), checks, weak_distance_ratio: ratio,
           scope: 'Demonstration versus frozen Cadence only' };
}

// One serial owner for all models, bodies, witnesses and counters.
export class Life {
  constructor(seed = 17, weakGain = null, { observers = false, progress = null } = {}) {
    if (!Number.isInteger(seed) || seed < 0 || seed > 2147483647) throw new Error('Seed must be an integer between 0 and 2147483647');
    this.seed = seed;
    this.weakGain = weakGain === null ? PROTOCOL.weak_gain : Number(weakGain);
    if (!(this.weakGain >= 0.25 && this.weakGain <= 0.5)) throw new Error('Wheel strength must be between 0.25 and 0.50');
    this.step = 0;
    this.phase = 'normal';
    this.auto = true;
    this.phaseStart = 0;
    this.targets = route(this.seed);
    this.events = [];
    this.rows = [];
    this.arms = {};
    this.bootstrap = {};
    this.observers = observers;
    const rng = new PyRandom(this.seed + 20000);
    const experiences = ACTIONS.map(a => [a.slice(), bodyMotion(a)]);
    // Only measured transitions teach: these commands were executed in the body.
    const order = experiences.map((_, i) => i);
    const schedule = [];
    for (let epoch = 0; epoch < PROTOCOL.bootstrap_epochs; epoch++) {
      rng.shuffle(order);
      schedule.push(...order);
    }
    this.bootstrapWitnesses = clone(experiences);
    this.bootstrapSchedule = schedule.slice();
    const kinds = ['cadence', 'adaptive', 'mlp', ...(observers ? ['observer'] : [])];
    const arms = {};
    for (const kind of kinds) {
      if (progress) progress(`Bootstrapping ${LABELS[kind]}`);
      const started = now();
      const model = makeModel(kind === 'cadence' ? 'coupled' : kind, this.seed);
      for (const witness of schedule) {
        if (!model.learn(...experiences[witness])) throw new Error(`${kind} refused a bootstrap motion witness`);
      }
      const predictions = model.query(ACTIONS);
      const rmse = Math.sqrt(pysum(predictions.map((p, i) => {
        const y = experiences[i][1];
        return pysum([0, 1].map(j => (p[j] - y[j]) ** 2)) / 2;
      })) / experiences.length);
      this.bootstrap[kind] = { experiences: experiences.length, presentations: schedule.length,
                               seconds: (now() - started) / 1000, training_grid_rmse: rmse, parameters: model.parameters() };
      arms[kind] = this._arm(kind, model);
    }
    const frozen = modelFromSnapshot(arms.cadence.model.snapshot());
    this.arms = { cadence: arms.cadence, frozen: this._arm('frozen', frozen) };
    for (const kind of kinds) if (kind !== 'cadence') this.arms[kind] = arms[kind];
    this.bootstrap.frozen = { ...this.bootstrap.cadence };
    this.events.push({ step: 0, text: 'Identical Cadence checkpoint. Normal wheels. Shared target schedule.' });
  }

  _arm(kind, model) {
    return { model, pose: [0.0, 0.0, 0.0], target: this.targets[0].slice(), trail: [[0.0, 0.0]], targets: 0, attempts: 0,
             reached: false, prediction_error: 0.0, error_history: [], command: [0.0, 0.0], motion: [0.0, 0.0],
             latency_ms: 0.0, deadline_misses: 0, metrics: {}, replay: [], pending: null, learning: kind !== 'frozen' };
  }

  get wheelGain() {
    return this.phase === 'weakened' ? this.weakGain : 1.0;
  }

  changePhase(phase) {
    if (!PHASE_NAMES.includes(phase)) throw new Error('Unknown phase');
    this.phase = phase;
    this.phaseStart = this.step;
    // Task resets pose at declared phase/episode boundaries; brains and replay persist.
    for (const arm of Object.values(this.arms)) {
      arm.pose = [0.0, 0.0, 0.0]; arm.trail = [[0.0, 0.0]]; arm.reached = false;
    }
    const labels = { normal: 'Normal wheels', weakened: 'Right wheel weakened; learners receive motion only',
                     restored_probe: 'Wheels restored; learning paused for immediate retention probe',
                     restored_learning: 'Original wheels; learning resumed' };
    this.events.push({ step: this.step, text: labels[phase] });
  }

  _automaticPhase() {
    if (!this.auto) return;
    let boundary = 0;
    for (const [phase, length] of PROTOCOL.phases) {
      if (this.step === boundary && this.phase !== phase) this.changePhase(phase);
      boundary += length;
    }
  }

  tick(queueDelayMs = 0.0) {
    const tickStarted = now();
    this._automaticPhase();
    const phaseStep = this.step - this.phaseStart;
    const episodeStart = phaseStep % PROTOCOL.episode_steps === 0;
    const targetIndex = Math.floor(this.step / PROTOCOL.episode_steps) % this.targets.length;
    for (const [kind, arm] of Object.entries(this.arms)) {
      const started = now();
      const armQueueMs = queueDelayMs + (started - tickStarted);
      const model = arm.model;
      const metrics = arm.metrics[this.phase] ??= emptyMetrics();
      const learning = kind !== 'frozen' && this.phase !== 'restored_probe';
      arm.learning = learning;
      // Admit the last consequence before choosing the next command. This work and replay are included in the
      // sensing-to-command timer.
      let presentations = 0;
      if (arm.pending !== null) {
        const [action, motion, admittedPhase] = arm.pending;
        // A restoration probe may not learn even the transition before it.
        if (learning && admittedPhase !== 'restored_probe') {
          if (!model.learn(action, motion)) throw new Error(`${kind} refused an executed motion witness`);
          presentations += 1;
          if (arm.replay.length) {
            const replay = arm.replay[(this.step * 7) % arm.replay.length];
            if (!model.learn(...replay)) throw new Error(`${kind} refused a replay witness`);
            presentations += 1;
          }
        }
        arm.replay.push([action.slice(), motion.slice()]);
        arm.replay = arm.replay.slice(-PROTOCOL.replay_window);
      }
      if (episodeStart) {
        arm.pose = [0.0, 0.0, 0.0]; arm.trail = [[0.0, 0.0]]; arm.reached = false;
        arm.target = this.targets[targetIndex].slice();
        arm.attempts += 1;
        metrics.attempts += 1;
      }
      const before = arm.pose.slice();
      let action;
      if (arm.reached) {
        action = [0.0, 0.0];
      } else {
        const predictions = model.query(ACTIONS);
        action = selectAction(before, arm.target, predictions);
      }
      const predicted = model.activate(action);
      const elapsed = now() - started;
      const actual = bodyMotion(action, this.wheelGain);
      const after = advance(before, actual);
      const distance = Math.hypot(after[0] - arm.target[0], after[1] - arm.target[1]);
      const hit = !arm.reached && distance <= PROTOCOL.target_radius;
      arm.reached = arm.reached || hit;
      arm.targets += hit ? 1 : 0;
      const mse = pysum([0, 1].map(j => (predicted[j] - actual[j]) ** 2)) / 2;
      arm.prediction_error = Math.sqrt(mse);
      arm.error_history = [...arm.error_history, Math.sqrt(mse)].slice(-180);
      arm.pose = after; arm.command = action; arm.motion = actual;
      arm.trail = [...arm.trail, after.slice(0, 2)].slice(-600);
      arm.latency_ms = elapsed;
      const age = elapsed + armQueueMs;
      const missed = age > 1000 * PROTOCOL.dt;
      arm.deadline_misses += missed ? 1 : 0;
      arm.pending = [action.slice(), actual.slice(), this.phase];
      metrics.steps += 1;
      metrics.targets += hit ? 1 : 0;
      metrics.distance_integral += distance * PROTOCOL.dt;
      metrics.squared_prediction_error += mse;
      metrics.learning_presentations += presentations;
      metrics.latencies_ms.push(elapsed);
      metrics.command_ages_ms.push(age);
      metrics.queue_delays_ms.push(armQueueMs);
      metrics.deadline_misses += missed ? 1 : 0;
      this.rows.push({ step: this.step, model: kind, phase: this.phase, phase_step: phaseStep, before, after,
                       target: arm.target.slice(), action, prediction: predicted, motion: actual,
                       right_gain: this.wheelGain, hit, episode_start: episodeStart, learning, presentations,
                       latency_ms: elapsed, queue_delay_ms: armQueueMs, command_age_ms: age });
    }
    this.step += 1;
  }

  // What the page draws: every position, sample and patch state of this instant.
  state() {
    const models = Object.entries(this.arms).map(([kind, arm]) => ({
      pose: arm.pose.slice(), target: arm.target.slice(), trail: arm.trail.map(p => p.slice()), targets: arm.targets,
      attempts: arm.attempts, prediction_error: arm.prediction_error, error_history: arm.error_history.slice(),
      command: arm.command.slice(), motion: arm.motion.slice(), latency_ms: arm.latency_ms,
      deadline_misses: arm.deadline_misses, learning: arm.learning, id: kind, label: LABELS[kind], color: COLORS[kind],
      activity: arm.model.activity(), phase_metrics: summarize(arm.metrics),
    }));
    const labels = { normal: 'Normal wheels', weakened: 'Right wheel weakened', restored_probe: 'Restored · retention probe',
                     restored_learning: 'Restored · relearning' };
    return { ready: true, error: null, step: this.step, sim_time: Math.round(this.step * PROTOCOL.dt * 100) / 100,
             phase: this.phase, phase_label: labels[this.phase], wheel_gain: this.wheelGain, weak_gain: this.weakGain,
             seed: this.seed, auto: this.auto,
             engine: `${ENGINE}, ${this.observers ? 'state-coupled populations and an observer arm' : 'state-coupled populations'}`,
             models, events: this.events.slice(-12), protocol: PROTOCOL };
  }

  snapshot() {
    const arms = {};
    for (const [kind, arm] of Object.entries(this.arms)) {
      const { model, ...rest } = arm;
      arms[kind] = { ...clone(rest), model: model.snapshot() };
    }
    return { schema: 'rover-life-js-v1', engine: ENGINE, protocol: clone(PROTOCOL), seed: this.seed, weak_gain: this.weakGain,
             step: this.step, phase: this.phase, auto: this.auto, phase_start: this.phaseStart, targets: clone(this.targets),
             events: clone(this.events), rows: clone(this.rows), bootstrap: clone(this.bootstrap),
             bootstrap_witnesses: clone(this.bootstrapWitnesses), bootstrap_schedule: this.bootstrapSchedule.slice(),
             observers: this.observers, arms };
  }

  static fromSnapshot(data) {
    if (!data || typeof data !== 'object' || data.schema !== 'rover-life-js-v1') {
      throw new Error('This file is not a checkpoint of the browser edition');
    }
    if (JSON.stringify(data.protocol) !== JSON.stringify(PROTOCOL)) throw new Error('Checkpoint protocol differs from this demo');
    data = clone(data);
    const life = Object.create(Life.prototype);
    if (!Number.isInteger(data.seed) || !Number.isInteger(data.step) || !Number.isInteger(data.phase_start)
        || data.step < 0 || data.step > MAX_STEPS || data.phase_start < 0 || data.phase_start > data.step
        || !PHASE_NAMES.includes(data.phase) || typeof data.auto !== 'boolean' || typeof data.observers !== 'boolean'
        || !(data.weak_gain >= 0.25 && data.weak_gain <= 0.5)) throw new Error('Checkpoint life counters are invalid');
    for (const key of ['targets', 'events', 'rows', 'bootstrap_witnesses', 'bootstrap_schedule']) {
      if (!Array.isArray(data[key])) throw new Error(`Checkpoint ${key} must be a list`);
    }
    Object.assign(life, { seed: data.seed, weakGain: data.weak_gain, step: data.step, phase: data.phase, auto: data.auto,
                          phaseStart: data.phase_start, targets: data.targets, events: data.events, rows: data.rows,
                          bootstrap: data.bootstrap, bootstrapWitnesses: data.bootstrap_witnesses,
                          bootstrapSchedule: data.bootstrap_schedule, observers: data.observers });
    // Member order in a file has no meaning; execution order is part of the runtime.
    const expected = ARM_ORDER.filter(kind => kind !== 'observer' || life.observers);
    if (!data.arms || Object.keys(data.arms).length !== expected.length || !expected.every(kind => kind in data.arms)) {
      throw new Error('Checkpoint model set is incomplete');
    }
    life.arms = {};
    for (const kind of expected) {
      const arm = data.arms[kind];
      const pairOk = v => Array.isArray(v) && v.length === 2 && v.every(Number.isFinite);
      if (!Array.isArray(arm.pose) || arm.pose.length !== 3 || !arm.pose.every(Number.isFinite) || !pairOk(arm.target)
          || !pairOk(arm.command) || !pairOk(arm.motion) || !Array.isArray(arm.trail) || !Array.isArray(arm.replay)
          || !Array.isArray(arm.error_history) || typeof arm.metrics !== 'object') throw new Error(`Checkpoint arm ${kind} is malformed`);
      life.arms[kind] = { ...arm, model: modelFromSnapshot(arm.model) };
    }
    return life;
  }

  receipt() {
    const metrics = {};
    for (const [kind, arm] of Object.entries(this.arms)) metrics[kind] = summarize(arm.metrics);
    return { schema: 'rover-evidence-js-v1', engine: ENGINE, seed: this.seed, weak_gain: this.weakGain, steps: this.step,
             auto: this.auto, protocol: PROTOCOL, bootstrap: this.bootstrap, bootstrap_witnesses: this.bootstrapWitnesses,
             bootstrap_schedule: this.bootstrapSchedule, metrics, events: this.events, transitions: this.rows,
             gate: demonstrationGate(metrics, this.auto),
             boundary: 'Simulated odometry, learned dynamics, supplied heading controller. No superiority, retention, physical-robot or useful-observer claim.' };
  }
}
