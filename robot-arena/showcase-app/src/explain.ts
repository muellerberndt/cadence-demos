// The shared explanations of the demos (public/cadence-explain.js, a copy of shared/ in the
// repository, loaded by index.html as a plain script): question marks and cards on every part
// that carries data-explain, and spots over the parts a canvas draws.
export type Explain = {
  scan(scope?: ParentNode): void;
  spot(container: HTMLElement, box: { x: number; y: number; w: number; h: number }, text: string,
       opts?: { title?: string; mark?: string; id?: string }): HTMLElement;
  clearSpots(container: HTMLElement): void;
  close(): void;
};
export const explain = (): Explain | undefined => (window as any).CadenceExplain;
