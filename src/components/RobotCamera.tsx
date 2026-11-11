import { useEffect, useRef, useState } from 'react';
import { CameraOff } from 'lucide-react';
export default function RobotCamera({robotId,view='first_person',onFrame,className=''}:{robotId:string;view?:string;onFrame?:(at:number,stamp:number)=>void;className?:string}){
 const stampRef=useRef(0),previousStamp=useRef(0);
 const [src,setSrc]=useState(''),[error,setError]=useState(''),onFrameRef=useRef(onFrame);
 onFrameRef.current=onFrame;
 useEffect(()=>{let stopped=false,url='',timer:ReturnType<typeof setTimeout>;const abort=new AbortController();setSrc('');setError('Connecting camera');previousStamp.current=0;
  const next=async()=>{try{const r=await fetch(`/api/robots/${robotId}/frame?view=${view}&t=${Date.now()}`,{signal:abort.signal});if(!r.ok)throw new Error(r.status===503?'Preparing renderer':'Waiting for camera');const blob=await r.blob();if(stopped)return;const fresh=URL.createObjectURL(blob);if(url)URL.revokeObjectURL(url);url=fresh;stampRef.current=Number(r.headers.get('X-Frame-Timestamp'))||Date.now();setSrc(fresh);setError('');}catch(e){if(!stopped)setError(e instanceof Error?e.message:'Waiting for video');}if(!stopped)timer=setTimeout(next,view==='first_person'?90:240);};next();
  return()=>{stopped=true;abort.abort();clearTimeout(timer);if(url)URL.revokeObjectURL(url);};
 },[robotId,view]);
 return <div className={`robot-camera ${className}`}>{src&&<img src={src} onLoad={()=>{if(stampRef.current!==previousStamp.current){previousStamp.current=stampRef.current;onFrameRef.current?.(Date.now(),stampRef.current);}}} alt={`${robotId} ${view} MuJoCo camera`}/>} {error&&<div className="camera-message"><CameraOff size={24}/><span>{error}</span><small>MuJoCo simulation feed</small></div>}</div>;
}
