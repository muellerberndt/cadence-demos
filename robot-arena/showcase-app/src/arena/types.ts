export type Part = { kind: string; mount: number; weapon?: string | null };
export type Spec = {
  name: string;
  policy: string;
  chassis: string;
  radius: number;
  hp: number;
  parts: Part[];
  inputs: string[];
  slots: number[];
  motors: { kind: string; label: string }[];
  lineage?: string | null;
  elo?: number;
};
// [x, y, heading, hp, mode, strides, planted, angles, spins, brain, commands]
export type BrainRow = [number[], number[], number[], number, number, number, number, number] | null;
export type RobotRow = [number, number, number, number, number, number[], number[], number[], number[], BrainRow, number[] | null];
export type Frame = { t: number; zone: number; robots: RobotRow[]; hits: [number, number, number, number][] };
export type Result = {
  name: string; place: number; score: number; alive: boolean; hp: number; died_at: number | null; moments: number;
  dealt: number; taken: number; burn: number; hits: number; moments_outside: number; travelled_m: number;
  aroused_share: number; sweeps_per_moment: number; learning_sweeps: number; refused: number;
};

export const PALETTE = ["#4fd1c5", "#f6ad55", "#f687b3", "#63b3ed", "#b794f4", "#68d391", "#fc8181", "#f6e05e"];
export const MODE_NAME: Record<number, string> = { 0: "calm", 1: "aroused", 2: "random", 3: "frozen", 4: "refused", 9: "out" };
export const THEME = {
  panel: "#141924", floor: "#1d2430", floorGrid: "#26303f", burn: "rgba(255, 92, 42, 0.22)", ring: "#ff7a45",
  calm: "#4fa3ff", aroused: "#ffb347", random: "#9aa3b5", frozen: "#c58bff", dead: "#4a5160",
  hp: "#5ad37a", hpLow: "#ff5d5d", ink: "#e8ebf2", muted: "#8f98a9", line: "#273040",
};
export const modeColor = (mode: number) =>
  mode === 0 ? THEME.calm : mode === 1 ? THEME.aroused : mode === 3 ? THEME.frozen : mode === 9 ? THEME.dead : THEME.random;
