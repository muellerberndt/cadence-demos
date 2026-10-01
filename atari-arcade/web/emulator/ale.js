// The Arcade Learning Environment's view of an Atari 2600, on the 6502.ts core: minimal action sets, four-frame
// action repeats, the games' reward and terminal rules read from RAM, the 60 idle frames and four RESET frames of
// an ALE reset, and the 108,000-frame episode cap. Rewards and terminals for Freeway and Atlantis follow ALE's
// games/supported/Freeway.cpp and Atlantis.cpp.
import Board from '6502.ts/lib/machine/stella/Board';
import Config from '6502.ts/lib/machine/stella/Config';
import Cartridge2k from '6502.ts/lib/machine/stella/cartridge/Cartridge2k';
import Cartridge4k from '6502.ts/lib/machine/stella/cartridge/Cartridge4k';
import ArrayBufferSurface from '6502.ts/lib/video/surface/ArrayBufferSurface';

export const WIDTH = 160, HEIGHT = 210, SURFACE_HEIGHT = 212;
const CLOCKS_PER_LINE = 228, LINES_PER_FRAME = 262;

const ACTION_SWITCHES = {
  NOOP: [], FIRE: ['fire'], UP: ['up'], RIGHT: ['right'], LEFT: ['left'], DOWN: ['down'],
  UPRIGHT: ['up', 'right'], UPLEFT: ['up', 'left'], DOWNRIGHT: ['down', 'right'], DOWNLEFT: ['down', 'left'],
  UPFIRE: ['up', 'fire'], RIGHTFIRE: ['right', 'fire'], LEFTFIRE: ['left', 'fire'], DOWNFIRE: ['down', 'fire'],
};

// ALE's readRam: offset & 0x7F indexes the 128 bytes of RIOT RAM.
const ram = (bytes, offset) => bytes[offset & 0x7f];
const bcd = v => 10 * (v >> 4) + (v & 15);
const decimal2 = (bytes, lower, higher) => bcd(ram(bytes, lower)) + (higher < 0 ? 0 : 100 * bcd(ram(bytes, higher)));
const decimal3 = (bytes, lower, middle, higher) => decimal2(bytes, lower, middle) + 10000 * bcd(ram(bytes, higher));

export const GAMES = {
  Freeway: {
    rom: 'roms/freeway.bin', md5: '8e0ab801b1705a740b476b7f588c6d16',
    actions: ['NOOP', 'UP', 'DOWN'],
    // ALE presses RESET once for the reset and once more when it applies game mode 0.
    resetPresses: 2,
    reset: () => ({ score: 0 }),
    step(bytes, s) {
      const score = decimal2(bytes, 103, -1);
      const reward = Math.min(1, Math.max(0, score - s.score));
      s.score = score;
      return { reward, terminal: ram(bytes, 22) === 1 };
    },
  },
  Atlantis: {
    rom: 'roms/atlantis.bin', md5: '9ad36e699ef6f45d9eb6c4cf90475c9f',
    actions: ['NOOP', 'FIRE', 'RIGHTFIRE', 'LEFTFIRE'],
    resetPresses: 1,
    reset: () => ({ score: 0, lives: 6 }),
    step(bytes, s) {
      const score = decimal3(bytes, 0xa2, 0xa3, 0xa1) * 100;
      let reward = score - s.score;
      const old = s.score;
      s.score = score;
      s.lives = ram(bytes, 0xf1);
      const terminal = s.lives === 0xff;
      if (terminal) { reward = 0; s.score = old; }
      return { reward, terminal };
    },
  },
};

export class Environment {
  constructor(game, romBytes, { seed = 0, frameskip = 4, maxFrames = 108000 } = {}) {
    if (!GAMES[game]) throw new Error(`no game ${game}`);
    this.game = game;
    this.settings = GAMES[game];
    this.actions = this.settings.actions;
    this.frameskip = frameskip;
    this.maxFrames = maxFrames;
    const bytes = romBytes instanceof Uint8Array ? romBytes : new Uint8Array(romBytes);
    const cartridge = bytes.length <= 0x800 ? new Cartridge2k(bytes) : new Cartridge4k(bytes);
    const config = Config.create({ tvMode: 0, enableAudio: false, randomSeed: seed, emulatePaddles: false });
    this.board = new Board(config, cartridge);
    this.surface = ArrayBufferSurface.createFromArrayBuffer(WIDTH, SURFACE_HEIGHT, new ArrayBuffer(WIDTH * SURFACE_HEIGHT * 4));
    this.pixels = new Uint8Array(this.surface.getUnderlyingBuffer());
    this.frameReady = false;
    const video = this.board.getVideoOutput();
    video.setSurfaceFactory(() => this.surface);
    video.newFrame.addHandler(() => { this.frameReady = true; });
    this.bus = this.board.getBus();
    this.joystick = this.board.getJoystick0();
    this.panel = this.board.getControlPanel();
    this.ramBytes = new Uint8Array(128);
    this.episodeFrames = 0;
    this.frames = 0;
    this.state = this.settings.reset();
    this.terminal = false;
    this.booted = false;
  }

  _frame() {
    this.frameReady = false;
    let guard = 0;
    while (!this.frameReady && guard++ < 2 * LINES_PER_FRAME) this.board.tick(CLOCKS_PER_LINE);
    if (!this.frameReady) throw new Error('the emulator produced no frame');
    this.frames++;
  }

  _apply(action) {
    const names = ACTION_SWITCHES[this.actions[action]];
    for (const name of ['up', 'down', 'left', 'right', 'fire']) {
      const sw = name === 'fire' ? this.joystick.getFire() : this.joystick[`get${name[0].toUpperCase()}${name.slice(1)}`]();
      sw.toggle(names.includes(name));
    }
  }

  readRam() {
    for (let i = 0; i < 128; i++) this.ramBytes[i] = this.bus.peek(0x80 + i);
    return this.ramBytes;
  }

  // ALE's reset: a console reset, 60 idle frames, RESET held for four frames (per press), then the game's own reset.
  reset() {
    if (this.booted) this.board.reset(); else { this.board.boot(); this.booted = true; }
    // ALE difficulty 0 means both difficulty switches at B (the switch reads true in 6502.ts).
    this.panel.getDifficultySwitchP0().toggle(true);
    this.panel.getDifficultySwitchP1().toggle(true);
    this.panel.getColorSwitch().toggle(false);
    this.panel.getSelectSwitch().toggle(false);
    this.panel.getResetButton().toggle(false);
    this._apply(0);
    for (let i = 0; i < 60; i++) this._frame();
    for (let press = 0; press < this.settings.resetPresses; press++) {
      this.panel.getResetButton().toggle(true);
      for (let i = 0; i < 4; i++) this._frame();
      this.panel.getResetButton().toggle(false);
    }
    this.state = this.settings.reset();
    this.terminal = false;
    this.episodeFrames = 0;
    this.settings.step(this.readRam(), this.state);
    return this.screen();
  }

  // One agent step: the action held for `frameskip` frames, rewards summed, the game rules read after every frame.
  step(action) {
    if (!Number.isInteger(action) || action < 0 || action >= this.actions.length) throw new Error(`invalid action ${action}`);
    this._apply(action);
    let reward = 0;
    for (let i = 0; i < this.frameskip; i++) {
      if (this.terminal || this.episodeFrames >= this.maxFrames) break;
      this._frame();
      this.episodeFrames++;
      const r = this.settings.step(this.readRam(), this.state);
      reward += r.reward;
      this.terminal = r.terminal;
    }
    const truncated = !this.terminal && this.episodeFrames >= this.maxFrames;
    return { reward, terminal: this.terminal, truncated, score: this.state.score };
  }

  // The last frame as RGBA bytes, 160 x 210 (the ALE screen); the core renders 212 lines.
  screen() {
    return this.pixels.subarray(0, WIDTH * HEIGHT * 4);
  }
}
