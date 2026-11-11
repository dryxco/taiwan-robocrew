import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {buildMarketEnvironment} from '../scene/marketEnvironment';
import {createMarketHumanoids} from '../scene/humanoidVisual';

const placements=[{robotId:'jipai',x:-3.8,z:-2.8,yaw:0,scale:1.4},{robotId:'pepper',x:.2,z:-2.8,yaw:0,scale:1.4},{robotId:'tea',x:4.2,z:-2.8,yaw:0,scale:1.4}];
export default function WorkstationView({robotId,view='first_person',robots=[],orders=[],onFrame}:{robotId:string;view?:string;robots?:any[];orders?:any[];onFrame?:(at:number,stamp:number)=>void}){
 const host=useRef<HTMLDivElement>(null),latest=useRef({robots,orders,onFrame}),[error,setError]=useState('');latest.current={robots,orders,onFrame};
 useEffect(()=>{
  const element=host.current;if(!element)return;
  let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setError('Could not initialize the 3D camera.');return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,view==='first_person'?1.5:1));renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.82;element.appendChild(renderer.domElement);
  const scene=new THREE.Scene();scene.background=new THREE.Color('#142022');scene.fog=new THREE.FogExp2('#142022',.025);
  scene.add(new THREE.HemisphereLight('#d2d9e6','#6d5940',.85));const light=new THREE.DirectionalLight('#c8d5e6',.7);light.position.set(4,12,8);scene.add(light);
  const environment=buildMarketEnvironment(scene,robotId==='pepper'?'pepper-bun':robotId==='tea'?'bubble-tea':'jipai'),humanoids=createMarketHumanoids(scene,placements.filter(p=>p.robotId===robotId));
  environment.group.traverse(o=>{if(o instanceof THREE.PointLight)o.intensity*=.45;});
  const selected=placements.find(p=>p.robotId===robotId)!;
  const camera=new THREE.PerspectiveCamera(view==='first_person'?72:55,1,.04,120);
  const convert=(p:number[])=>new THREE.Vector3(selected.x+(p[0]+.04)*1.4,p[2]*1.4,selected.z-(p[1]-.25)*1.4);
  if(view==='first_person'){camera.position.set(selected.x+.056,2.05,selected.z+.40);camera.lookAt(selected.x+.056,1.10,-2.12);}
  else if(view==='operator'){camera.position.set(selected.x+1.8,2.15,.7);camera.lookAt(selected.x,1.35,-2.65);}
  else if(view==='top'){camera.position.set(selected.x,2.30,-2.15);camera.up.set(0,0,-1);camera.lookAt(selected.x,1,-2.2);}
  const foodGeometry=robotId==='tea'?new THREE.CylinderGeometry(.035,.029,.14,20):new THREE.SphereGeometry(1,16,10);
  const foodMaterial=new THREE.MeshStandardMaterial({color:robotId==='tea'?'#b58046':'#e8ac55',roughness:.8});const food=new THREE.Mesh(foodGeometry,foodMaterial);
  if(robotId==='jipai')food.scale.set(.075,.025,.055);if(robotId==='pepper')food.scale.set(.055,.035,.055);// Food is rendered from the simulator geometry endpoint.
  const resize=()=>{const r=element.getBoundingClientRect();renderer.setSize(r.width,r.height);camera.aspect=r.width/Math.max(r.height,1);camera.updateProjectionMatrix();};const observer=new ResizeObserver(resize);observer.observe(element);resize();
  let visible=true;const visibility=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting});visibility.observe(element);
  let frame=0,last=0,lastStamp=0;const clock=new THREE.Clock();
  const animate=(now:number)=>{frame=requestAnimationFrame(animate);if(!visible||now-last<(view==='first_person'?33:100))return;last=now;
   humanoids.update();
   const robot=latest.current.robots.find(r=>r.id===robotId);environment.update(clock.getElapsedTime());environment.setOrders?.(latest.current.orders);
   if(robot?.food_position){const p=robot.food_position;food.position.copy(convert([p[0]*.55,p[1]*.55,p[2]]));food.visible=true;}else food.visible=false;
   if(view==='wrist'&&robot?.embodiment?.arms?.left?.tcp){const tcp=convert(robot.embodiment.arms.left.tcp);camera.position.copy(tcp).add(new THREE.Vector3(.12,.20,.15));camera.lookAt(food.position);}
   if(view==='first_person'){const own=humanoids.group.children.find(c=>c.userData.robotId===robotId);own?.traverse(o=>{if(o.userData.isHead)o.visible=false;});}
   renderer.render(scene,camera);
   element.dataset.drawCalls=String(renderer.info.render.calls);
   element.dataset.triangles=String(renderer.info.render.triangles);
   const root=humanoids.group.children.find(c=>c.userData.robotId===robotId);const stamp=Number(root?.userData.frameTimestamp||0);
   element.dataset.frameStamp=String(stamp);element.dataset.renderAt=String(Date.now());
   element.dataset.receivedStamp=String(root?.userData.receivedStamp);element.dataset.visualError=String(root?.userData.visualError||'');
   if(stamp>lastStamp){lastStamp=stamp;latest.current.onFrame?.(Date.now(),stamp);}
  };frame=requestAnimationFrame(animate);
  return()=>{cancelAnimationFrame(frame);observer.disconnect();visibility.disconnect();humanoids.dispose();environment.dispose();foodGeometry.dispose();foodMaterial.dispose();renderer.dispose();renderer.domElement.remove();};
 },[robotId,view]);
 return <div className="robot-camera shared-market-camera" ref={host} aria-label={`${robotId} ${view} market camera`}>{error&&<div className="camera-message">{error}</div>}</div>;
}
