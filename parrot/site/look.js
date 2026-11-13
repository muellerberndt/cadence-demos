// The look check: one parrot body on the perch in the page's own room and light, seen from a named
// view, for comparing candidate bodies. look.html?src=<glb>&height=0.29&grip=0.2&view=front|side|head|back
// `grip` is where the feet grip, as a fraction of the body's height from its lowest point.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/three/jsm/loaders/GLTFLoader.js';
import { makeRenderer, Room, BAR_Y } from './scene.js';
import { Parrot, loadRig } from './parrot.js';

const q = new URLSearchParams(location.search);
const canvas = document.getElementById('scene');
const renderer = makeRenderer(canvas);
renderer.setPixelRatio(1);
const room = await new Room(renderer).build();
const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 30);
const VIEWS = {
  front: [[0.05, BAR_Y + 0.13, 0.78], [0, BAR_Y + 0.08, 0]],
  side: [[0.78, BAR_Y + 0.13, 0.08], [0, BAR_Y + 0.08, 0]],
  back: [[-0.25, BAR_Y + 0.16, -0.72], [0, BAR_Y + 0.08, 0]],
  head: [[0.22, BAR_Y + 0.25, 0.36], [0.0, BAR_Y + 0.205, 0.02]],
  room: [[0.95, BAR_Y + 0.45, 1.25], [0, BAR_Y - 0.02, 0]],
};
const [pos, at] = VIEWS[q.get('view') || 'front'];
const lift = q.get('view') === 'head' ? Number(q.get('hy') || 0) : 0; // a body whose head sits higher or lower
camera.position.set(pos[0], pos[1] + lift, pos[2]); camera.lookAt(at[0], at[1] + lift, at[2]);
if (q.get('view') === 'head') { camera.fov = 20; camera.updateProjectionMatrix(); }

let body;
if (q.get('src')) {
  const gltf = await new GLTFLoader().loadAsync(q.get('src'));
  body = gltf.scene;
  body.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(body), size = box.getSize(new THREE.Vector3());
  const k = Number(q.get('height') || 0.29) / size.y;
  body.scale.setScalar(k);
  const grip = Number(q.get('grip') || 0.2);
  body.rotation.y = Number(q.get('yaw') || 0) * Math.PI / 180;
  body.position.set(-(box.min.x + box.max.x) / 2 * k + Number(q.get('dx') || 0), BAR_Y - (box.min.y + grip * size.y) * k, -(box.min.z + box.max.z) / 2 * k + Number(q.get('dz') || 0));
  body.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  if (q.get('toon')) {
    const { toonize } = await import('./looks.js');
    toonize(body);
  }
  room.scene.add(body);
} else {
  const parrot = new Parrot(await loadRig());
  parrot.group.position.set(0, BAR_Y, 0);
  room.scene.add(parrot.group);
  parrot.update(0);
}
function size() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
}
size();
renderer.shadowMap.needsUpdate = true;
let frames = 0;
function frame() {
  renderer.shadowMap.needsUpdate = true;
  renderer.render(room.scene, camera);
  if (++frames === 8) document.body.dataset.ready = '1';
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
