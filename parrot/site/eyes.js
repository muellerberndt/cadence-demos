// The parrot's two eyes: each renders what it sees across its wide field into a small image, the
// image its brain receives (INTERFACES P2).
//
// Each eye sits on the side of the head and looks out sideways, 75 degrees from the beak. Its field
// spans `field` degrees to either side of its axis (87.5: a 175 degree field), so the two fields
// overlap 25 degrees in front of the beak and leave a 35 degree blind spot behind the head; it sees
// `vfield` degrees up and down. A wide field does not fit a camera's flat picture, so each eye
// renders the six faces of a small cube around itself and then reads its image off the cube: one
// column per azimuth, one row per elevation, spaced finely at the eye's axis (its fovea) and
// coarsely toward the field's edges, each pixel the mean of a few rays across its patch.
//
// Layout of an image: row 0 is the top; column 0 is the eye's rear edge and the last column its
// edge beside the beak, in both eyes, so the two images mirror each other. RGB, 8 bits a channel.
// No depth and no labels: the brain learns where things are and how far.
import * as THREE from 'three';

export const EYE = { w: 64, h: 32, field: 87.5, vfield: 60, fovea: 0.4, rays: 2, face: 96, axis: 75 };

const VERT = `varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;
const FRAG = `
precision highp float;
uniform samplerCube cube;
uniform mat3 eyeToWorld;
uniform vec2 size;      // image width, height in pixels
uniform vec2 field;     // half fields in radians: azimuth, elevation
uniform float fovea;
uniform float side;     // -1: the left eye (the beak lies toward its -x), +1: the right eye
uniform float flipX;    // the cube target's x convention
uniform int rays;
uniform float exposure;
// the page's tone curve (ACES, as the main view's), since a render target gets none of its own
vec3 aces(vec3 x) { x *= exposure; return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
float spread(float t) { return t * (fovea + (1.0 - fovea) * abs(t)); } // the eye's foveated spacing
void main() {
  vec2 px = floor(gl_FragCoord.xy);
  vec3 sum = vec3(0.0);
  for (int i = 0; i < 4; i++) {
    if (i >= rays) break;
    for (int j = 0; j < 4; j++) {
      if (j >= rays) break;
      vec2 f = (px + (vec2(float(i), float(j)) + 0.5) / float(rays)) / size; // 0..1 across the image
      float az = field.x * spread(2.0 * f.x - 1.0);   // toward the beak as the column grows
      float el = field.y * spread(2.0 * f.y - 1.0);   // gl rows grow upward
      vec3 d = vec3(side * sin(az) * cos(el), sin(el), cos(az) * cos(el));
      vec3 w = eyeToWorld * d;
      sum += textureCube(cube, vec3(flipX * w.x, w.y, w.z)).rgb;
    }
  }
  gl_FragColor = vec4(aces(sum / float(rays * rays)), 1.0);
  #include <colorspace_fragment>
}`;

class Eye {
  constructor(name, opts) {
    this.name = name;
    this.opts = opts;
    this.cubeTarget = new THREE.WebGLCubeRenderTarget(opts.face, { type: THREE.HalfFloatType, generateMipmaps: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    this.cube = new THREE.CubeCamera(0.008, 30, this.cubeTarget);
    this.target = new THREE.WebGLRenderTarget(opts.w, opts.h, { minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false });
    this.target.texture.colorSpace = THREE.SRGBColorSpace;
    this.material = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG, depthTest: false, depthWrite: false,
      uniforms: { cube: { value: this.cubeTarget.texture }, eyeToWorld: { value: new THREE.Matrix3() }, size: { value: new THREE.Vector2(opts.w, opts.h) },
        field: { value: new THREE.Vector2(opts.field * Math.PI / 180, opts.vfield * Math.PI / 180) }, fovea: { value: opts.fovea },
        side: { value: name === 'left' ? -1 : 1 }, flipX: { value: 1 }, rays: { value: opts.rays }, exposure: { value: 0.95 / 0.6 } },
    });
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.material);
    this.quad.frustumCulled = false;
    this.scene = new THREE.Scene(); this.scene.add(this.quad);
    this.cam = new THREE.Camera();
    this.rgba = new Uint8Array(opts.w * opts.h * 4);
    this.rgb = new Uint8Array(opts.w * opts.h * 3);
    this.pos = new THREE.Vector3(); this.quat = new THREE.Quaternion();
  }
}

export class Eyes {
  constructor(renderer, scene, parrot, opts = {}) {
    this.renderer = renderer; this.scene = scene; this.parrot = parrot;
    this.opts = { ...EYE, ...opts };
    this.left = new Eye('left', this.opts);
    this.right = new Eye('right', this.opts);
    this.ms = 0;
  }

  /** Render both eyes from where they are now; fills each eye's `rgb` (row 0 at the top). */
  render() {
    const t0 = performance.now();
    const r = this.renderer, prevTarget = r.getRenderTarget();
    const prevXr = r.xr.enabled; r.xr.enabled = false;
    for (const [eye, socket] of [[this.left, 'eye_l'], [this.right, 'eye_r']]) {
      this.parrot.eyePose(socket, eye.pos, eye.quat);
      // the camera sits just outside the eyeball, on its axis
      const axis = new THREE.Vector3(0, 0, 1).applyQuaternion(eye.quat);
      eye.cube.position.copy(eye.pos).addScaledVector(axis, 0.004);
      eye.cube.updateMatrixWorld(true);
      eye.cube.update(r, this.scene);
      eye.material.uniforms.eyeToWorld.value.setFromMatrix4(new THREE.Matrix4().makeRotationFromQuaternion(eye.quat));
      r.setRenderTarget(eye.target);
      r.render(eye.scene, eye.cam);
      r.readRenderTargetPixels(eye.target, 0, 0, this.opts.w, this.opts.h, eye.rgba);
      const { w, h } = this.opts;
      for (let y = 0; y < h; y++) { // gl rows run bottom-up; the brain's run top-down
        const src = (h - 1 - y) * w * 4, dst = y * w * 3;
        for (let x = 0; x < w; x++) { eye.rgb[dst + 3 * x] = eye.rgba[src + 4 * x]; eye.rgb[dst + 3 * x + 1] = eye.rgba[src + 4 * x + 1]; eye.rgb[dst + 3 * x + 2] = eye.rgba[src + 4 * x + 2]; }
      }
    }
    r.setRenderTarget(prevTarget);
    r.xr.enabled = prevXr;
    this.ms = performance.now() - t0;
  }

  /** Where in the world a column and row of an eye's image looks: a unit direction. */
  direction(name, col, row) {
    const eye = name === 'left' ? this.left : this.right, o = this.opts;
    const spread = (t) => t * (o.fovea + (1 - o.fovea) * Math.abs(t));
    const az = o.field * Math.PI / 180 * spread(2 * (col + 0.5) / o.w - 1);
    const el = o.vfield * Math.PI / 180 * spread(1 - 2 * (row + 0.5) / o.h);
    const side = name === 'left' ? -1 : 1;
    return new THREE.Vector3(side * Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)).applyQuaternion(eye.quat);
  }

  /** Draw an eye's image into a canvas as the eye would show it: the left eye as it is, the right
   *  eye mirrored, so the two side by side read from the left rear round the front to the right rear. */
  draw(name, canvas) {
    const eye = name === 'left' ? this.left : this.right, { w, h } = this.opts;
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    const g = canvas.getContext('2d'), img = g.createImageData(w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const sx = name === 'left' ? x : w - 1 - x, s = 3 * (y * w + sx), d = 4 * (y * w + x);
      img.data[d] = eye.rgb[s]; img.data[d + 1] = eye.rgb[s + 1]; img.data[d + 2] = eye.rgb[s + 2]; img.data[d + 3] = 255;
    }
    g.putImageData(img, 0, 0);
  }
}
