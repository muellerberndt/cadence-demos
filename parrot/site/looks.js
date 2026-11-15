// The parrot's looks: bodies made for the same rig, so the page switches between them and the
// brain drives each with the same joints. A prepared look is a .glb whose mesh is in the parrot's
// frame with skin weights on the rig's bones (tools/prepare_look.py), and a rig file with the bones
// and the eye sockets fitted to that body. The drawn look is the page's own placeholder body.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/jsm/loaders/GLTFLoader.js';
import { Parrot } from './parrot.js';

export async function lookList() {
  const r = await fetch('looks/looks.json');
  return r.ok ? (await r.json()).looks : [];
}

// Toon shading for the anime look: light in three soft steps, and a dark outline drawn from an
// inflated copy of the body's back faces.
let gradient = null;
function toonGradient() {
  if (gradient) return gradient;
  const data = new Uint8Array([90, 90, 90, 255, 175, 175, 175, 255, 255, 255, 255, 255]);
  gradient = new THREE.DataTexture(data, 3, 1, THREE.RGBAFormat);
  gradient.minFilter = gradient.magFilter = THREE.NearestFilter; gradient.needsUpdate = true;
  return gradient;
}

export function toonMaterial(src) {
  // toon shading takes no light from the room's probe: a share of the colour lights itself, so the
  // side away from the lamp reads as a flat shade, as in a drawing
  return new THREE.MeshToonMaterial({ map: src.map || null, color: new THREE.Color(0.78, 0.78, 0.78), gradientMap: toonGradient(),
    emissiveMap: src.map || null, emissive: new THREE.Color(1, 1, 1), emissiveIntensity: 0.42 });
}

export function outlineMaterial(thickness = 0.0009) {
  const m = new THREE.MeshBasicMaterial({ color: '#1d1f24', side: THREE.BackSide });
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uOutline = { value: thickness };
    shader.vertexShader = 'uniform float uOutline;\n' + shader.vertexShader.replace('#include <project_vertex>',
      '#ifdef USE_SKINNING\n  transformed += normalize( objectNormal ) * uOutline;\n#else\n  transformed += normalize( normal ) * uOutline;\n#endif\n#include <project_vertex>');
  };
  m.customProgramCacheKey = () => 'parrot-outline';
  return m;
}

/** A body for the plain glTF candidates of look.html: toon-shaded, with an outline. */
export function toonize(root) {
  const meshes = [];
  root.traverse((o) => { if (o.isMesh) meshes.push(o); });
  for (const o of meshes) {
    o.material = toonMaterial(o.material);
    const line = new THREE.Mesh(o.geometry, outlineMaterial(0.0035 / Math.max(1e-6, root.scale.x)));
    o.add(line);
  }
}

/** Make the parrot of a look: its rig (the page's rig with the look's fitted bones and sockets) and
 *  its body bound to the rig's skeleton. */
export async function makeParrot(look, baseRig) {
  if (!look || !look.file) return { parrot: new Parrot(baseRig), info: look };
  const fitted = await (await fetch(look.rig)).json();
  const rig = { ...baseRig, ...fitted, joints: baseRig.joints, toes: { ...baseRig.toes, ...(fitted.toes || {}) } };
  const parrot = new Parrot(rig, { placeholder: false });
  const gltf = await new GLTFLoader().loadAsync(look.file);
  const meshes = [];
  gltf.scene.traverse((o) => { if (o.isMesh) meshes.push(o); });
  for (const m of meshes) {
    const geo = m.geometry;
    if (!geo.attributes.skinIndex) throw new Error(`The ${look.title} body has no skin weights.`);
    let mat = m.material;
    if (look.shading === 'toon') mat = toonMaterial(mat);
    else { mat.envMapIntensity = look.envMapIntensity ?? 1; }
    parrot.attach(geo, mat);
    if (look.shading === 'toon') parrot.attach(geo, outlineMaterial(look.outline ?? 0.0009));
  }
  // the mouth's dark inside, seen when the beak opens (the jaw is cut free of the upper beak)
  const mouth = fitted.sockets?.mouth;
  if (mouth && parrot.sockets.mouth) {
    const plug = new THREE.Mesh(new THREE.SphereGeometry(0.55 * (mouth.radius || 0.006), 20, 14), new THREE.MeshStandardMaterial({ color: '#2a1d1f', roughness: 0.6 }));
    plug.scale.set(0.9, 0.7, 1.2);
    plug.visible = false; // shown only while the beak is open
    parrot.sockets.mouth.add(plug);
    parrot.mouthPlug = plug;
  }
  parrot.update(0);
  return { parrot, info: look };
}
