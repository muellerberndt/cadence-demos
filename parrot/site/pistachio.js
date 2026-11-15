// The pistachio: modelled by the page (a beige shell split along its seam, the green kernel showing),
// thrown from the visitor's side on a short arc, caught in the beak, nibbled and eaten. The page
// animates the throw and the catch; the reward reaches the brain when the nut is in the beak.
import * as THREE from 'three';

function nutModel() {
  const g = new THREE.Group();
  const shellMat = new THREE.MeshPhysicalMaterial({ color: '#d9c49b', roughness: 0.55, clearcoat: 0.3, clearcoatRoughness: 0.5, sheen: 0.3, sheenColor: new THREE.Color('#f1e3c4') });
  const kernelMat = new THREE.MeshPhysicalMaterial({ color: '#7f9a3a', roughness: 0.6, sheen: 0.4, sheenColor: new THREE.Color('#c7d98a') });
  // two half shells, a little apart along the seam
  for (const s of [1, -1]) {
    const half = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 18, 0, Math.PI), shellMat);
    half.scale.set(0.0085, 0.0062, 0.0115);
    half.rotation.y = s > 0 ? 0 : Math.PI;
    half.rotation.z = s * 0.12;
    half.position.x = s * 0.0006;
    half.castShadow = true;
    g.add(half);
  }
  const kernel = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), kernelMat);
  kernel.scale.set(0.0062, 0.0048, 0.0095); kernel.castShadow = true;
  g.add(kernel);
  return g;
}

export class Pistachio {
  constructor(scene) {
    this.scene = scene;
    this.nut = nutModel();
    this.nut.visible = false;
    scene.add(this.nut);
    this.phase = 'idle';
  }

  /** Throw it from `from` (world) to the parrot's beak; `onCatch` fires when it is in the beak. */
  throw(from, parrot, onCatch, onDone) {
    if (this.phase !== 'idle') return false;
    this.parrot = parrot; this.onCatch = onCatch; this.onDone = onDone;
    this.from = from.clone();
    this.phase = 'flying'; this.t = 0;
    this.flight = 0.75;
    this.nut.visible = true;
    this.scene.attach(this.nut);
    this.spin = new THREE.Vector3(Math.random() * 8 + 6, Math.random() * 6, Math.random() * 4);
    return true;
  }

  beakPoint(out = new THREE.Vector3()) {
    const s = this.parrot.sockets.mouth || this.parrot.bones.lower_mandible || this.parrot.bones.head;
    s.getWorldPosition(out);
    const head = this.parrot.bones.head, q = new THREE.Quaternion();
    head.getWorldQuaternion(q);
    return out.add(new THREE.Vector3(0, -0.004, 0.012).applyQuaternion(q));
  }

  /** Each frame; returns the beak opening it asks for (degrees), or null. */
  update(dt) {
    if (this.phase === 'idle') return null;
    this.t += dt;
    if (this.phase === 'flying') {
      const u = Math.min(1, this.t / this.flight), to = this.beakPoint();
      const p = this.from.clone().lerp(to, u);
      p.y += Math.sin(Math.PI * u) * 0.22; // the arc
      this.nut.position.copy(p);
      this.nut.rotation.x += this.spin.x * dt; this.nut.rotation.y += this.spin.y * dt; this.nut.rotation.z += this.spin.z * dt;
      if (u >= 1) { // caught: it sits in the beak and moves with the head
        this.phase = 'caught'; this.t = 0;
        const holder = this.parrot.sockets.mouth || this.parrot.bones.head;
        holder.attach(this.nut);
        this.onCatch?.();
      }
      // the beak opens as the nut comes near
      return u > 0.55 ? 22 * Math.min(1, (u - 0.55) / 0.3) : null;
    }
    if (this.phase === 'caught') { // a short nibble: the beak works on it twice, then it is eaten
      const n = this.t;
      if (n > 1.6) { this.phase = 'idle'; this.nut.visible = false; this.scene.attach(this.nut); this.onDone?.(); return 0; }
      if (n > 1.2) this.nut.scale.setScalar(Math.max(0.01, 1 - (n - 1.2) / 0.4));
      else this.nut.scale.setScalar(1);
      return 6 + 9 * Math.max(0, Math.sin(n * Math.PI * 2.6));
    }
    return null;
  }
}
