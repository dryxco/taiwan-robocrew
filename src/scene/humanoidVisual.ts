import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import {addFoodDetail} from './foodDetail';

type Vec3 = readonly [number, number, number];
// All camera views share the immutable source meshes. A camera owns its clone.
const sourceMeshes=new Map<string,Promise<THREE.BufferGeometry>>();
export interface HumanoidGeom {
  role?: string;
  name: string;
  type: string | number;
  mesh_url?: string;
  texture_url?: string;
  vertices?: number[];
  faces?: number[];
  position: Vec3;
  /** MuJoCo world rotation, nine row-major entries. */
  rotation: readonly number[];
  size: Vec3;
  rgba: readonly [number, number, number, number];
}
export interface HumanoidPlacement {
  robotId: string;
  x: number;
  z?: number;
  y?: number;
  scale?: number;
  /** Three Y-axis rotation after the Z-up conversion; default faces +Z. */
  yaw?: number;
}
export interface MarketHumanoids {
  group: THREE.Group;
  /** Optional caller metadata is ignored: poses always come from /visual. */
  update(robots?: unknown): void;
  dispose(): void;
}

/**
 * Render the official G1 mesh subtree, including endpoint-provided hat/fingers.
 * Example: createMarketHumanoids(scene, [{ robotId: 'jipai', x: -4.1 },
 * { robotId: 'pepper', x: 0 }, { robotId: 'tea', x: 4.1 }]).
 * Returns immediately; fetches each robot on creation and then at <=5 Hz.
 * Call dispose on unmount. update() may be called each frame but is optional.
 * Placement is the ground point under the reference pelvis [-.04,.25,.793];
 * vertical world coordinates are preserved, not recentered at the pelvis.
 * STL vertices must be in MuJoCo geom-local coordinates (no extra size scale).
 * Failures retain the last pose and expose a message in each root's
 * userData.visualError, with a console warning only when the error changes.
 */
export function createMarketHumanoids(
  scene: THREE.Scene,
  placements: readonly HumanoidPlacement[],
): MarketHumanoids {
  const group = new THREE.Group();
  group.name = 'market-g1-chefs';
  scene.add(group);
  const abort = new AbortController();
  const loader = new STLLoader();
  const geometryCache = new Map<string, Promise<THREE.BufferGeometry>>();
  const geometries = new Set<THREE.BufferGeometry>();
  const textures = new Map<string, THREE.Texture>();
  const textureLoader = new THREE.TextureLoader();
  const materials = new Map<string, THREE.MeshStandardMaterial>();
  const foodDetails: ReturnType<typeof addFoodDetail>[]=[];
  const rotation = new THREE.Matrix4();
  let disposed = false;
  let busy = false;
  let nextPoll = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const robots = placements.map(placement => {
    const root = new THREE.Group();
    root.name = `g1-${placement.robotId}`;
    root.userData.robotId = placement.robotId;
    root.position.set(placement.x, placement.y ?? 0, placement.z ?? -3.25);
    root.rotation.y = placement.yaw ?? -Math.PI / 2;
    root.scale.setScalar(placement.scale ?? 1.1);
    const basis = new THREE.Group();
    // C maps MuJoCo (x,y,z) to Three (x,z,-y); child rotations stay local.
    basis.rotation.x = -Math.PI / 2;
    const world = new THREE.Group();
    world.position.set(0.04, -0.25, 0);
    basis.add(world); root.add(basis); group.add(root);
    return { placement, root, world, meshes: new Map<string, THREE.Mesh>() };
  });

  async function geometry(geom: HumanoidGeom): Promise<THREE.BufferGeometry> {
    const type = typeof geom.type === 'number'
      ? ['plane', 'hfield', 'sphere', 'capsule', 'ellipsoid', 'cylinder', 'box', 'mesh'][geom.type]
      : geom.type.replace(/^mjGEOM_/i, '').toLowerCase();
    const key = geom.vertices ? 'procedural:'+geom.name : geom.mesh_url ? `mesh:${geom.mesh_url}` : `${type}:${geom.size.join(',')}`;
    const cached = geometryCache.get(key);
    if (cached) return cached;
    const pending = (async () => {
      let result: THREE.BufferGeometry;
      if(geom.vertices&&geom.faces){
        result=new THREE.BufferGeometry();result.setAttribute('position',new THREE.Float32BufferAttribute(geom.vertices,3));result.setIndex(geom.faces);result.computeVertexNormals();
        const uv:number[]=[];for(let i=0;i<geom.vertices.length;i+=3)uv.push(geom.vertices[i]/.13+.5,geom.vertices[i+1]/.09+.5);result.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));
      } else if (geom.mesh_url) {
        const url=geom.mesh_url;
        let source=sourceMeshes.get(url);
        if(!source){source=fetch(url).then(async response=>{
          if(!response.ok)throw new Error(`STL ${response.status}: ${url}`);
          return loader.parse(await response.arrayBuffer());
        });sourceMeshes.set(url,source);source.catch(()=>sourceMeshes.delete(url));}
        result=(await source).clone();
      } else {
        // These are actual MJCF geoms (e.g. hat), never substitute robot parts.
        const [x, y, z] = geom.size;
        switch (type) {
          case 'box': result = new THREE.BoxGeometry(2 * x, 2 * y, 2 * z); break;
          case 'sphere': result = new THREE.SphereGeometry(x, 20, 12); break;
          case 'ellipsoid': result = new THREE.SphereGeometry(1, 20, 12).scale(x, y, z); break;
          case 'cylinder': result = new THREE.CylinderGeometry(x, x, 2 * y, 24).rotateX(Math.PI / 2); break;
          case 'capsule': result = new THREE.CapsuleGeometry(x, 2 * y, 6, 16).rotateX(Math.PI / 2); break;
          default: throw new Error(`Unsupported G1 geom ${geom.name}: ${String(geom.type)}`);
        }
      }
      geometries.add(result);
      return result;
    })();
    geometryCache.set(key, pending);
    try { return await pending; }
    catch (error) { geometryCache.delete(key); throw error; }
  }

  function material(rgba: HumanoidGeom['rgba'], textureUrl?:string) {
    const key = rgba.join(',')+(textureUrl||'');
    let result = materials.get(key);
    if (!result) {
      result = new THREE.MeshStandardMaterial({
        // MuJoCo rgba values are linear; preserve the original grey/white palette.
        color: new THREE.Color().setRGB(rgba[0], rgba[1], rgba[2], THREE.LinearSRGBColorSpace),
        opacity: rgba[3], transparent: rgba[3] < 1, depthWrite: rgba[3] >= 1,
        roughness: 0.65, metalness: 0.12,
      });
      if(textureUrl){let tex=textures.get(textureUrl);if(!tex){tex=textureLoader.load(textureUrl);tex.colorSpace=THREE.SRGBColorSpace;textures.set(textureUrl,tex);}result.map=tex;result.color.set('#ffffff');result.metalness=0;result.roughness=.85;}
      materials.set(key, result);
    }
    return result;
  }

  async function refresh(robot: typeof robots[number]) {
    try {
      const response = await fetch(`/api/robots/${encodeURIComponent(robot.placement.robotId)}/visual`, {
        signal: abort.signal, cache: 'no-store',
      });
      if (!response.ok) throw new Error(`Visual endpoint returned ${response.status}`);
      const data = await response.json() as { geoms: HumanoidGeom[]; frame_timestamp?: number };
      robot.root.userData.receivedStamp=data.frame_timestamp;
      if (disposed) return;
      if (!Array.isArray(data.geoms)) throw new Error('Visual endpoint missing geoms');
      // Load together so fingers and hat do not serialize dozens of STL requests.
      const loaded = await Promise.all(data.geoms.map(async geom => ({ geom, geometry: await geometry(geom) })));
      if (disposed) return;
      const present = new Set<string>();
      loaded.forEach(({ geom, geometry: geo }, index) => {
        const key = `${index}:${geom.name}`; // Unnamed MJCF geoms are valid.
        present.add(key);
        let mesh = robot.meshes.get(key);
        if (!mesh) {
          mesh = new THREE.Mesh(geo, material(geom.rgba,geom.texture_url));
          mesh.name = geom.name;
          mesh.userData.isHead = /head_link|chef_hat/.test((geom.mesh_url || "") + geom.name);
          mesh.castShadow = true; mesh.receiveShadow = true;
          robot.meshes.set(key, mesh); robot.world.add(mesh);
          if(geom.role==='food'){
            const detail=addFoodDetail(mesh,robot.placement.robotId,!!geom.texture_url);
            foodDetails.push(detail);mesh.userData.foodMaterial=detail.material;
          }
        }
        mesh.geometry = geo; mesh.material = mesh.userData.foodMaterial || material(geom.rgba,geom.texture_url);
        if(geom.role==='food'&&robot.placement.robotId==='pepper')
          mesh.userData.foodMaterial.color.set(geom.rgba[0]<.5?'#985825':'#ca914b');
        mesh.visible = geom.rgba[3] > 0;
        mesh.position.set(...geom.position);
        const r = geom.rotation;
        rotation.set(r[0], r[1], r[2], 0, r[3], r[4], r[5], 0, r[6], r[7], r[8], 0, 0, 0, 0, 1);
        mesh.quaternion.setFromRotationMatrix(rotation);
      });
      for (const [key, mesh] of robot.meshes) {
        if (!present.has(key)) { mesh.removeFromParent(); robot.meshes.delete(key); }
      }
      robot.root.userData.frameTimestamp = data.frame_timestamp || 0;
      delete robot.root.userData.visualError;
    } catch (error) {
      if (disposed) return;
      const message = error instanceof Error ? error.message : String(error);
      if (robot.root.userData.visualError !== message) console.warn(`[G1 ${robot.placement.robotId}] ${message}`);
      robot.root.userData.visualError = message;
    }
  }

  function update(_robots?: unknown) {
    if (disposed || busy) return;
    if(performance.now()<nextPoll){
      if(timer!==undefined)clearTimeout(timer);
      timer=setTimeout(update,Math.ceil(nextPoll-performance.now())+1);
      return;
    }
    if (timer !== undefined) clearTimeout(timer);
    busy = true;
    nextPoll = performance.now() + 200;
    void Promise.all(robots.map(refresh)).finally(() => {
      busy = false;
      if (!disposed) timer = setTimeout(update, Math.max(1, Math.ceil(nextPoll - performance.now())));
    });
  }
  update();
  return {
    group, update,
    dispose() {
      if (disposed) return;
      disposed = true;
      abort.abort();
      if (timer !== undefined) clearTimeout(timer);
      group.removeFromParent();
      robots.forEach(robot => { robot.meshes.clear(); robot.world.clear(); });
      geometries.forEach(geo => geo.dispose()); geometries.clear();
      foodDetails.forEach(detail=>detail.dispose());
      materials.forEach(mat => mat.dispose()); materials.clear(); textures.forEach(t=>t.dispose());textures.clear(); geometryCache.clear();
    },
  };
}
