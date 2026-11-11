import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

export type MarketStallId = 'jipai' | 'pepper-bun' | 'bubble-tea';
export interface MarketEnvironment {
  group: THREE.Group;
  stalls: Record<MarketStallId, { position: THREE.Vector3; approach: THREE.Vector3; counter: THREE.Vector3 }>;
  update: (elapsedSeconds: number) => void;
  dispose: () => void;
}

/** Original procedural art. Metres, Y-up; stall fronts face +Z. Call once per scene. */
export function buildMarketEnvironment(scene: THREE.Scene): MarketEnvironment {
  const group = new THREE.Group();
  group.name = 'taiwan-night-market';
  scene.add(group);
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  const cache = new Map<string, THREE.MeshStandardMaterial>();
  const steam: THREE.Mesh[] = [];
  const lamps: THREE.Group[] = [];
  const material = (color: string, glow = 0, metalness = 0) => {
    const key = `${color}:${glow}:${metalness}`;
    let mat = cache.get(key);
    if (!mat) {
      mat = new THREE.MeshStandardMaterial({ color, roughness: metalness ? 0.33 : 0.8, metalness, emissive: color, emissiveIntensity: glow, flatShading: true });
      cache.set(key, mat); materials.add(mat);
    }
    return mat;
  };
  const mesh = (parent: THREE.Object3D, geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number) => {
    geometries.add(geo); materials.add(mat);
    const obj = new THREE.Mesh(geo, mat); obj.position.set(x, y, z);
    obj.castShadow = true; obj.receiveShadow = true; parent.add(obj); return obj;
  };
  const box = (p: THREE.Object3D, x: number, y: number, z: number, w: number, h: number, d: number, c: string, glow = 0, metal = 0) => mesh(p, new THREE.BoxGeometry(w, h, d), material(c, glow, metal), x, y, z);
  const cyl = (p: THREE.Object3D, x: number, y: number, z: number, top: number, bottom: number, h: number, c: string, glow = 0, n = 16) => mesh(p, new THREE.CylinderGeometry(top, bottom, h, n), material(c, glow), x, y, z);
  const ball = (p: THREE.Object3D, x: number, y: number, z: number, r: number, c: string, glow = 0) => mesh(p, new THREE.SphereGeometry(r, 10, 7), material(c, glow), x, y, z);
  const rod = (p: THREE.Object3D, a: THREE.Vector3, b: THREE.Vector3, radius: number, color: string) => {
    const delta = b.clone().sub(a);
    const obj = cyl(p, ...a.clone().add(b).multiplyScalar(0.5).toArray() as [number, number, number], radius, radius, delta.length(), color, 0, 6);
    obj.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), delta.normalize()); return obj;
  };
  const sign = (p: THREE.Object3D, title: string, subtitle: string, x: number, y: number, z: number, w: number, h: number, bg: string, fg = '#fff1cb') => {
    box(p, x, y, z - 0.035, w + 0.08, h + 0.08, 0.09, '#28262e');
    // Canvas keeps CJK legible without bundling a font; OS CJK fallbacks are listed explicitly.
    const canvas = document.createElement('canvas'); canvas.width = 1024; canvas.height = Math.max(128, Math.round(1024 * h / w));
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = bg; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = fg; ctx.lineWidth = 5; ctx.strokeRect(13, 13, canvas.width - 26, canvas.height - 26);
    ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `900 ${Math.floor(canvas.height * (subtitle ? 0.49 : 0.62))}px "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif`;
    ctx.fillText(title, 512, canvas.height * (subtitle ? 0.39 : 0.51), 950);
    if (subtitle) { ctx.font = `600 ${Math.floor(canvas.height * 0.15)}px sans-serif`; ctx.fillText(subtitle, 512, canvas.height * 0.79, 920); }
    const tex = new THREE.CanvasTexture(canvas); tex.colorSpace = THREE.SRGBColorSpace; textures.add(tex);
    const mat = new THREE.MeshBasicMaterial({ map: tex, toneMapped: false });
    mesh(p, new THREE.PlaneGeometry(w, h), mat, x, y, z + 0.018).castShadow = false;
  };
  const lantern = (x: number, y: number, z: number, color = '#ee5640') => {
    const p = new THREE.Group(); p.position.set(x, y, z); group.add(p); lamps.push(p);
    const body = ball(p, 0, -0.2, 0, 0.24, color, 0.85); body.scale.set(1, 1.25, 1);
    for (let i = 0; i < 5; i++) cyl(p, 0, -0.4 + i * 0.1, 0, 0.22 * Math.sin((i + 1) * Math.PI / 6), 0.22 * Math.sin((i + 1) * Math.PI / 6), 0.012, '#ffb763', 0.3);
    cyl(p, 0, 0.08, 0, 0.1, 0.1, 0.06, '#65352e'); cyl(p, 0, -0.5, 0, 0.09, 0.09, 0.06, '#65352e');
    rod(p, new THREE.Vector3(0, 0.1, 0), new THREE.Vector3(0, 0.3, 0), 0.009, '#302c36');
    rod(p, new THREE.Vector3(0, -0.53, 0), new THREE.Vector3(0, -0.72, 0), 0.025, '#df9e41');
  };
  const stool = (x: number, z: number, color: string) => {
    cyl(group, x, 0.46, z, 0.23, 0.25, 0.09, color);
    for (const dx of [-0.14, 0.14]) for (const dz of [-0.14, 0.14]) rod(group, new THREE.Vector3(x + dx, 0.43, z + dz), new THREE.Vector3(x + dx * 1.4, 0.04, z + dz * 1.4), 0.028, color);
  };
  const tray = (p: THREE.Object3D, x: number, z: number, w = 0.7) => {
    box(p, x, 1.11, z, w, 0.035, 0.5, '#9dadae', 0, 0.7);
    for (const dz of [-0.24, 0.24]) box(p, x, 1.15, z + dz, w, 0.08, 0.025, '#c3cdca', 0, 0.7);
  };
  const bottle = (p: THREE.Object3D, x: number, y: number, z: number, c: string) => {
    cyl(p, x, y + 0.12, z, 0.065, 0.07, 0.24, c);
    cyl(p, x, y + 0.27, z, 0.025, 0.04, 0.07, '#efdfb3');
  };
  const vapor = (p: THREE.Object3D, x: number, y: number, z: number) => {
    for (let i = 0; i < 5; i++) {
      const m = new THREE.MeshBasicMaterial({ color: '#ffe8c8', transparent: true, opacity: 0.1, depthWrite: false });
      const puff = mesh(p, new THREE.IcosahedronGeometry(0.075, 0), m, x, y + i * 0.12, z);
      puff.userData.origin = new THREE.Vector3(x, y, z); puff.userData.phase = i / 5; puff.castShadow = false; steam.push(puff);
    }
  };

  // Broad, uninterrupted walking alley, wet-looking patches, gutters and tile aprons.
  box(group, 0, -0.12, 0, 24, 0.22, 19, '#222936');
  box(group, 0, -0.002, -2.8, 14.8, 0.05, 4.1, '#44444b');
  for (let x = -7; x <= 7; x += 0.5) box(group, x, 0.03, -0.78, 0.47, 0.035, 0.34, '#66636a');
  for (let x = -8; x <= 8; x += 1) {
    box(group, x, 0.006, -0.44, 0.8, 0.015, 0.17, '#121b25');
    for (let i = 0; i < 5; i++) box(group, x - 0.32 + i * 0.16, 0.018, -0.44, 0.025, 0.015, 0.16, '#555864');
  }
  const puddleMat = new THREE.MeshStandardMaterial({ color: '#596071', metalness: 0.65, roughness: 0.16, transparent: true, opacity: 0.35 });
  for (let i = 0; i < 12; i++) { const o = mesh(group, new THREE.CircleGeometry(0.4 + (i % 3) * 0.24, 12), puddleMat, -7 + i * 1.27, 0.003, 0.3 + (i % 4) * 1.1); o.rotation.x = -Math.PI / 2; o.scale.y = 0.35; }

  // Mixed-use shophouses: tiled faces, shutters, balconies, AC condensers and roof tanks.
  for (let i = 0; i < 7; i++) {
    const x = -9 + i * 3; const height = 6.4 + (i % 3) * 0.9;
    box(group, x, height / 2, -6, 2.92, height, 3.1, ['#535969', '#6f6264', '#525e61'][i % 3]);
    box(group, x, 2, -4.43, 2.7, 3.6, 0.08, '#333b46');
    for (let j = 0; j < 13; j++) box(group, x, 0.45 + j * 0.22, -4.35, 2.7, 0.035, 0.08, '#53555c');
    for (let floor = 0; floor < 2; floor++) for (const dx of [-0.67, 0.67]) {
      const y = 4.4 + floor * 1.7;
      box(group, x + dx, y, -4.42, 0.94, 1.16, 0.12, '#242e3d');
      box(group, x + dx, y, -4.34, 0.74, 0.95, 0.04, (i + floor) % 3 ? '#c69b67' : '#253747', (i + floor) % 3 ? 0.3 : 0);
      box(group, x + dx, y, -4.29, 0.045, 1.0, 0.04, '#434954');
      box(group, x + dx, y - 0.57, -4.05, 1.1, 0.11, 0.65, '#77727a');
      for (let j = 0; j < 5; j++) box(group, x + dx - 0.44 + j * 0.22, y - 0.35, -3.77, 0.025, 0.43, 0.025, '#303946');
    }
    box(group, x + 0.8, 3.3, -4.1, 0.6, 0.42, 0.4, '#b0aba0');
    const fan = cyl(group, x + 0.8, 3.3, -3.88, 0.15, 0.15, 0.04, '#4b5460'); fan.rotation.x = Math.PI / 2;
    box(group, x - 1.33, 3, -4.31, 0.07, 6, 0.08, '#858083');
    cyl(group, x, height + 0.55, -5.8, 0.55, 0.55, 1, '#929497');
  }

  const stalls = {} as MarketEnvironment['stalls'];
  const specs: { id: MarketStallId; x: number; title: string; sub: string; color: string; menu: string }[] = [
    { id: 'jipai', x: -4, title: '艋舺大雞排', sub: 'CRISPY CHICKEN  ·  FRESHLY FRIED', color: '#bd4a3a', menu: '招牌雞排  90 元' },
    { id: 'pepper-bun', x: 0, title: '炭烤胡椒餅', sub: 'PEPPER BUNS  ·  CHARCOAL OVEN', color: '#ca8839', menu: '現烤胡椒餅  60 元' },
    { id: 'bubble-tea', x: 4, title: '島嶼珍珠奶茶', sub: 'BUBBLE TEA  ·  HAND-SHAKEN', color: '#418a80', menu: '黑糖珍珠鮮奶  65 元' },
  ];
  for (const s of specs) {
    const p = new THREE.Group(); p.name = `stall-${s.id}`; p.userData.stallId = s.id; p.position.set(s.x, 0, -3); group.add(p);
    stalls[s.id] = { position: p.position.clone(), approach: new THREE.Vector3(s.x, 1.65, 0.6), counter: new THREE.Vector3(s.x, 1.1, -1.85) };
    box(p, 0, 0.54, 0.8, 3.35, 1.02, 0.82, s.color);
    box(p, 0, 1.07, 0.8, 3.5, 0.1, 1.02, '#b7b7ac', 0, 0.65);
    for (const x of [-1.65, 1.65]) for (const z of [-0.9, 1.35]) box(p, x, 1.42, z, 0.075, 2.84, 0.075, '#a5a19a', 0, 0.5);
    box(p, 0, 1.1, -0.85, 3.3, 0.08, 0.5, '#8a8c88', 0, 0.6);
    for (let i = 0; i < 12; i++) {
      const c = i % 2 ? '#f4d8a0' : s.color;
      const awning = box(p, -1.65 + i * 0.3, 2.79, 0.3, 0.3, 0.055, 2.65, c); awning.rotation.x = 0.10;
      box(p, -1.65 + i * 0.3, 2.49, 1.62, 0.3, 0.32, 0.045, c);
    }
    sign(p, s.title, s.sub, 0, 3.12, 1.15, 3.5, 0.76, s.color);
    sign(p, s.menu, '手作 · 現點現做', 0.65, 0.57, 1.225, 1.75, 0.53, '#f1d8a6', '#513a36');
    sign(p, '營業中', 'OPEN', -1.13, 0.55, 1.225, 0.62, 0.43, '#273b3c', '#ffe0a3');
    box(p, 0, 2.35, 0.1, 2.5, 0.045, 0.08, '#fff1c2', 2);
    const light = new THREE.PointLight('#ffcb87', 12, 6, 2); light.position.set(0, 2.25, 0.6); p.add(light);
    for (let j = 0; j < 3; j++) bottle(p, -1.3 + j * 0.18, 1.12, 0.58, ['#ad4433', '#d8af62', '#6b7451'][j]);
    box(p, 1.16, 1.24, 0.65, 0.32, 0.26, 0.26, '#e6d8b5');
    for (let j = 0; j < 6; j++) rod(p, new THREE.Vector3(1.08 + j * 0.03, 1.28, 0.65), new THREE.Vector3(1.08 + j * 0.03, 1.65, 0.62), 0.008, '#b78c57');
    lantern(s.x - 1.4, 2.32, -1.3); lantern(s.x + 1.4, 2.32, -1.3);
    // Rear shelving and crates establish usable workspace behind each counter.
    for (let j = 0; j < 4; j++) { box(p, -1.1 + j * 0.7, 0.23, -0.6, 0.58, 0.42, 0.45, j % 2 ? '#44685f' : '#976444'); for (let k = 0; k < 3; k++) box(p, -1.1 + j * 0.7, 0.12 + k * 0.1, -0.365, 0.5, 0.025, 0.02, '#2d3c39'); }
    if (s.id === 'jipai') {
      box(p, -0.52, 1.22, 0.45, 0.92, 0.25, 0.7, '#5d6467', 0, 0.6);
      box(p, -0.52, 1.355, 0.45, 0.76, 0.02, 0.55, '#9d591c', 0.25);
      for (let j = 0; j < 8; j++) box(p, -0.85 + j * 0.095, 1.38, 0.44, 0.013, 0.02, 0.52, '#c3bca7', 0, 0.65);
      rod(p, new THREE.Vector3(-0.52, 1.4, 0.75), new THREE.Vector3(-0.52, 1.52, 1.03), 0.035, '#353c3f');
      tray(p, 0.5, 0.8);
      for (let j = 0; j < 3; j++) { const chicken = mesh(p, new THREE.IcosahedronGeometry(0.19, 1), material('#d89137'), 0.3 + j * 0.2, 1.18 + j * 0.035, 0.8); chicken.scale.set(0.8, 0.25, 1.25); }
      box(p, -0.5, 2.05, -0.32, 1.4, 0.22, 0.9, '#767d7f', 0, 0.7); box(p, -0.5, 2.4, -0.5, 0.38, 0.6, 0.38, '#666f76', 0, 0.7);
      vapor(p, -0.5, 1.43, 0.45);
    } else if (s.id === 'pepper-bun') {
      // Open cylindrical tandoor-style charcoal oven: dark cavity, brick rim and coals.
      const oven = new THREE.Group(); oven.position.set(-0.6, 0, 1.68); p.add(oven);
      cyl(oven, 0, 0.62, 0, 0.5, 0.46, 1.15, '#925641');
      cyl(oven, 0, 1.205, 0, 0.42, 0.42, 0.025, '#261e22');
      const rim = mesh(oven, new THREE.TorusGeometry(0.45, 0.075, 6, 24), material('#c79469'), 0, 1.21, 0); rim.rotation.x = Math.PI / 2;
      for (let j = 0; j < 12; j++) { const a = j * Math.PI / 6; const bun = ball(oven, Math.cos(a) * 0.31, 1.2, Math.sin(a) * 0.31, 0.075, '#e9b76d'); bun.scale.y = 0.55; }
      for (let j = 0; j < 8; j++) ball(oven, Math.cos(j * 2.4) * 0.19, 1.225, Math.sin(j * 2.4) * 0.19, 0.045, '#ec6b29', 1.2);
      for (const y of [0.3, 0.74, 1.05]) cyl(oven, 0, y, 0, 0.49, 0.49, 0.04, '#343d40');
      vapor(oven, 0, 1.3, 0); tray(p, 0.5, 0.8);
      for (let j = 0; j < 6; j++) { const bun = ball(p, 0.28 + (j % 3) * 0.2, 1.2, 0.65 + Math.floor(j / 3) * 0.22, 0.1, '#e0ab60'); bun.scale.y = 0.65; for (let k = 0; k < 3; k++) box(p, bun.position.x - 0.04 + k * 0.04, 1.263, bun.position.z, 0.01, 0.006, 0.025, '#fff0b6'); }
      rod(p, new THREE.Vector3(1.25, 0.1, -0.3), new THREE.Vector3(0.85, 2.2, -0.3), 0.025, '#c29b65');
    } else {
      for (let j = 0; j < 3; j++) { cyl(p, -0.8 + j * 0.55, 1.45, -0.6, 0.2, 0.2, 0.64, '#9aa9a6'); cyl(p, -0.8 + j * 0.55, 1.79, -0.6, 0.22, 0.22, 0.06, '#333e43'); box(p, -0.8 + j * 0.55, 1.24, -0.36, 0.055, 0.1, 0.1, '#253d3e'); }
      for (let j = 0; j < 4; j++) {
        const x = -0.55 + j * 0.38; cyl(p, x, 1.3, 0.82, 0.105, 0.078, 0.34, j % 2 ? '#bc8c62' : '#dbc19b');
        cyl(p, x, 1.48, 0.82, 0.112, 0.112, 0.035, '#f2e9d0');
        for (let k = 0; k < 5; k++) ball(p, x + Math.cos(k * 1.3) * 0.066, 1.18 + (k % 2) * 0.03, 0.82 + Math.sin(k * 1.3) * 0.066, 0.022, '#392c31');
        rod(p, new THREE.Vector3(x, 1.45, 0.82), new THREE.Vector3(x + 0.04, 1.73, 0.82), 0.015, '#c74e43');
      }
      box(p, 0.9, 1.4, -0.4, 0.54, 0.56, 0.54, '#a6c4ba'); box(p, 0.9, 1.63, -0.1, 0.35, 0.12, 0.04, '#293e46');
    }
  }

  // Warm festoon canopy leads the eye along the market, with cables visible against sky.
  for (const z of [0.1, 3.5]) {
    const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(-8, 4.4, z), new THREE.Vector3(0, 3.5, z), new THREE.Vector3(8, 4.4, z)]);
    mesh(group, new THREE.TubeGeometry(curve, 32, 0.012, 4, false), material('#252532'), 0, 0, 0);
    for (let i = 0; i < 17; i++) { const v = curve.getPoint(i / 16); if (i % 2 === 0) lantern(v.x, v.y - 0.15, v.z, z > 1 ? '#eab258' : '#e65c49'); else ball(group, v.x, v.y - 0.09, v.z, 0.055, '#ffe8ad', 2); }
  }
  // Side seating keeps the central walking and interaction area clear.
  for (const x of [-7.1, 7.1]) {
    cyl(group, x, 0.75, 1.6, 0.53, 0.53, 0.06, '#b4b6b1'); cyl(group, x, 0.38, 1.6, 0.06, 0.08, 0.7, '#62686a');
    stool(x - 0.65, 1.7, '#b4473b'); stool(x + 0.4, 2.2, '#40877f'); stool(x + 0.1, 0.8, '#c29141');
    bottle(group, x, 0.79, 1.6, '#9c4034');
  }
  // Entry posts, lantern gate and small pavement sandwich boards.
  for (const x of [-8.2, 8.2]) { box(group, x, 2.2, 3.5, 0.13, 4.4, 0.13, '#576365'); cyl(group, x, 0.1, 3.5, 0.3, 0.33, 0.2, '#454956'); }
  sign(group, '夜市', 'NIGHT SHIFT · TAIWAN', -7.1, 3.2, -0.8, 1.05, 1.65, '#29494c', '#f9d794');
  for (const x of [-2, 2]) { const board = box(group, x, 0.52, -0.1, 0.55, 0.95, 0.07, '#8b6349'); board.rotation.x = -0.12; sign(group, x < 0 ? '現炸' : '手作', '歡迎光臨', x, 0.58, 0.0, 0.46, 0.65, '#283e3c', '#e8d49d'); }

  // Batch static geometry by material; retain steam and swinging lantern roots.
  // Geometry is baked in world space because this factory is attached at the origin.
  group.updateMatrixWorld(true);
  const animated = new Set<THREE.Object3D>([...steam, ...lamps]);
  const batches = new Map<string, { material: THREE.Material; shadow: boolean; stallId?: MarketStallId; meshes: THREE.Mesh[] }>();
  group.traverse(object => {
    if (!(object instanceof THREE.Mesh) || Array.isArray(object.material)) return;
    let parent: THREE.Object3D | null = object;
    let stallId: MarketStallId | undefined;
    while (parent && parent !== group) {
      if (animated.has(parent)) return;
      if (parent.userData.stallId) stallId = parent.userData.stallId as MarketStallId;
      parent = parent.parent;
    }
    const key = `${object.material.uuid}:${object.castShadow}:${stallId ?? 'street'}`;
    if (!batches.has(key)) batches.set(key, { material: object.material, shadow: object.castShadow, stallId, meshes: [] });
    batches.get(key)!.meshes.push(object);
  });
  for (const batch of batches.values()) {
    if (batch.meshes.length < 2) continue;
    const parts = batch.meshes.map(object => {
      const part = object.geometry.index ? object.geometry.toNonIndexed() : object.geometry.clone();
      return part.applyMatrix4(object.matrixWorld);
    });
    const merged = mergeGeometries(parts);
    parts.forEach(part => part.dispose());
    if (!merged) continue;
    const combined = mesh(group, merged, batch.material, 0, 0, 0);
    combined.castShadow = batch.shadow;
    if (batch.stallId) combined.userData.stallId = batch.stallId;
    batch.meshes.forEach(object => { object.removeFromParent(); object.geometry.dispose(); geometries.delete(object.geometry); });
  }

  let disposed = false;
  return {
    group, stalls,
    update(elapsedSeconds) {
      if (disposed) return;
      for (let i = 0; i < steam.length; i++) {
        const puff = steam[i]; const phase = (elapsedSeconds * 0.24 + Number(puff.userData.phase)) % 1;
        const origin = puff.userData.origin as THREE.Vector3;
        puff.position.set(origin.x + Math.sin(elapsedSeconds + i) * phase * 0.12, origin.y + phase * 0.8, origin.z);
        puff.scale.setScalar(0.5 + phase * 1.6); (puff.material as THREE.MeshBasicMaterial).opacity = Math.sin(phase * Math.PI) * 0.13;
      }
      for (let i = 0; i < lamps.length; i++) lamps[i].rotation.z = Math.sin(elapsedSeconds * 0.8 + i * 0.7) * 0.025;
    },
    dispose() { if (disposed) return; disposed = true; group.removeFromParent(); geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); textures.forEach(t => t.dispose()); },
  };
}

export default buildMarketEnvironment;
