import * as THREE from 'three';

/** Render-only surface details follow the physical food mesh, never a second food pose. */
export function addFoodDetail(mesh: THREE.Mesh, kind: string, main: boolean) {
 const resources: {dispose():void}[]=[];
 let seed=47;
 const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 const mat=(color:string,roughness=.8)=>{const m=new THREE.MeshStandardMaterial({color,roughness,metalness:0});resources.push(m);return m;};
 const base=mat(kind==='jipai'?'#c88a35':kind==='pepper'?'#ca914b':main?'#ba8759':'#eee4ce');
 mesh.material=base;
 const add=(geometry:THREE.BufferGeometry, material:THREE.Material, count:number)=>{
  resources.push(geometry);const instances=new THREE.InstancedMesh(geometry,material,count);mesh.add(instances);return instances;
 };
 const dummy=new THREE.Object3D();
 if(kind==='jipai'){
  // Sample the actual triangle surface: compiled MuJoCo mesh axes need not be XYZ.
  const geo=mesh.geometry.index?mesh.geometry.toNonIndexed():mesh.geometry;
  const p=geo.getAttribute('position');const n=geo.getAttribute('normal');
  const crumbs=add(new THREE.IcosahedronGeometry(1,0),mat('#e3aa4c'),460);
  const toast=add(new THREE.IcosahedronGeometry(1,0),mat('#905021'),130);
  for(const batch of [crumbs,toast])for(let i=0;i<batch.count;i++){
   const face=Math.floor(rand()*p.count/3)*3;let u=rand(),v=rand();if(u+v>1){u=1-u;v=1-v;}
   const a=new THREE.Vector3().fromBufferAttribute(p,face),b=new THREE.Vector3().fromBufferAttribute(p,face+1),c=new THREE.Vector3().fromBufferAttribute(p,face+2);
   dummy.position.copy(a.multiplyScalar(1-u-v).addScaledVector(b,u).addScaledVector(c,v));
   const normal=new THREE.Vector3().fromBufferAttribute(n,face);dummy.position.addScaledVector(normal,.0007);
   const size=.0008+rand()*.0017;dummy.scale.set(size,size*(.5+rand()),size);dummy.rotation.set(rand()*3,rand()*3,rand()*3);dummy.updateMatrix();batch.setMatrixAt(i,dummy.matrix);
  }
  if(geo!==mesh.geometry)geo.dispose();
 }else if(kind==='pepper'){
  const seeds=add(new THREE.SphereGeometry(1,6,4),mat('#f2db9b'),120);
  mesh.geometry.computeBoundingBox();const bounds=mesh.geometry.boundingBox!;const sx=bounds.max.x,sy=bounds.max.y,sz=bounds.max.z;
  for(let i=0;i<seeds.count;i++){
   const a=rand()*Math.PI*2,r=Math.sqrt(rand())*.94;
   dummy.position.set(sx*r*Math.cos(a),sy*r*Math.sin(a),sz*Math.sqrt(1-r*r)+.0006);
   dummy.rotation.set(0,0,rand()*Math.PI);dummy.scale.set(.0018,.00065,.00045);dummy.updateMatrix();seeds.setMatrixAt(i,dummy.matrix);
  }
 }else if(main){
  mesh.geometry.computeBoundingBox();const b=mesh.geometry.boundingBox!,height=b.max.z,radius=b.max.x;
  const pearls=add(new THREE.SphereGeometry(.004,8,6),mat('#322019',.3),34);
  for(let i=0;i<pearls.count;i++){const angle=i*2.399;dummy.position.set(Math.cos(angle)*(radius-.001),Math.sin(angle)*(radius-.001),-height+.008+rand()*.026);dummy.scale.setScalar(1);dummy.rotation.set(0,0,0);dummy.updateMatrix();pearls.setMatrixAt(i,dummy.matrix);}
  const strawGeometry=new THREE.CylinderGeometry(.0038,.0038,.095,12).rotateX(Math.PI/2);resources.push(strawGeometry);
  const straw=new THREE.Mesh(strawGeometry,mat('#a94435',.45));straw.position.set(.013,0,height+.043);mesh.add(straw);
  const ringGeometry=new THREE.TorusGeometry(radius+.001,.002,8,40);resources.push(ringGeometry);
  const ring=new THREE.Mesh(ringGeometry,mat('#efe4ce',.4));ring.position.z=height+.005;mesh.add(ring);
 }
 return {material:base,dispose:()=>resources.forEach(r=>r.dispose())};
}
