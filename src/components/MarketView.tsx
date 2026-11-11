import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { buildMarketEnvironment } from '../scene/marketEnvironment';
import { createMarketHumanoids } from '../scene/humanoidVisual';
export default function MarketView({onSelect,orders=[]}:{onSelect:(id:string)=>void;orders?:any[]}){
 const host=useRef<HTMLDivElement>(null),[error,setError]=useState(''),[street,setStreet]=useState(false);
 const pickRef=useRef(onSelect),ordersRef=useRef(orders),changeView=useRef<(street:boolean)=>void>(()=>{});pickRef.current=onSelect;ordersRef.current=orders;
 useEffect(()=>{const el=host.current;if(!el)return;let renderer:THREE.WebGLRenderer;
 try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}catch{setError('This browser could not open the 3D environment. Use the stall cards below.');return;}
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.2;el.appendChild(renderer.domElement);
 const scene=new THREE.Scene();scene.background=new THREE.Color('#142022');scene.fog=new THREE.FogExp2('#142022',0.025);
 const camera=new THREE.PerspectiveCamera(48,1,0.1,120);camera.position.set(9,7.5,12);
 scene.add(new THREE.HemisphereLight('#d2d9e6','#6d5940',1.7));const moon=new THREE.DirectionalLight('#c8d5e6',1.4);moon.position.set(4,12,8);scene.add(moon);
 const environment=buildMarketEnvironment(scene);
 const humanoids=createMarketHumanoids(scene,[{robotId:'jipai',x:-3.8,z:-2.8,yaw:0,scale:1.4},{robotId:'pepper',x:.2,z:-2.8,yaw:0,scale:1.4},{robotId:'tea',x:4.2,z:-2.8,yaw:0,scale:1.4}]);
 const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,1,-2);controls.maxPolarAngle=Math.PI*.49;controls.minDistance=3;controls.maxDistance=24;controls.enableDamping=true;controls.enablePan=false;
 changeView.current=(walk:boolean)=>{camera.position.set(walk?0:9,walk?1.7:7.5,walk?4.8:12);controls.target.set(0,walk?1.5:1,-2);controls.update();};
 const resize=()=>{const {width,height}=el.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();};const observer=new ResizeObserver(resize);observer.observe(el);resize();
 let frame=0;const clock=new THREE.Clock();const animate=()=>{frame=requestAnimationFrame(animate);controls.update();environment.update(clock.getElapsedTime());if('setOrders' in environment)(environment as any).setOrders(ordersRef.current);renderer.render(scene,camera);};animate();
 const raycaster=new THREE.Raycaster();let downX=0,downY=0;const down=(e:PointerEvent)=>{downX=e.clientX;downY=e.clientY;};const click=(e:PointerEvent)=>{if(Math.hypot(e.clientX-downX,e.clientY-downY)>5)return;const b=el.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-b.left)/b.width*2-1,-(e.clientY-b.top)/b.height*2+1),camera);for(const hit of raycaster.intersectObjects(scene.children,true)){let o:THREE.Object3D|null=hit.object;while(o){if(o.userData.stallId){pickRef.current(o.userData.stallId);return;}o=o.parent;}}};renderer.domElement.addEventListener('pointerdown',down);renderer.domElement.addEventListener('pointerup',click);
 return()=>{cancelAnimationFrame(frame);observer.disconnect();controls.dispose();humanoids.dispose();environment.dispose();renderer.dispose();renderer.domElement.remove();};
 },[]);
 return <div className="market-canvas" ref={host}>{error&&<div className="camera-message">{error}</div>}<div className="scene-navigation"><button className={!street?'active':''} onClick={()=>{setStreet(false);changeView.current(false);}}>Market overview</button><button className={street?'active':''} onClick={()=>{setStreet(true);changeView.current(true);}}>Enter the alley</button></div></div>;
}
