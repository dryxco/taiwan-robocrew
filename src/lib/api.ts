import { useCallback, useEffect, useRef, useState } from 'react';
export type Robot = {id:string;name:string;status:string;owner:string|null;active:boolean;stage:string;position:number[];hold_reason?:string|null; [key:string]:any};
export type State = {robots:Robot[];orders:any[];ledger:any[];server_time:number;[key:string]:any};
export function useNightShift(){
 const [state,setState]=useState<State>({robots:[],orders:[],ledger:[],server_time:0});
 const [connected,setConnected]=useState(false),[error,setError]=useState('');
 const [workerId]=useState(()=>`worker-${crypto.randomUUID().slice(0,6)}`);
 const socket=useRef<WebSocket|null>(null),sequence=useRef(0),received=useRef(0),serverOffset=useRef<number|null>(null);
 const [age,setAge]=useState(0);
 useEffect(()=>{
  let stopped=false,timer:ReturnType<typeof setTimeout>;
  const connect=()=>{const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/${workerId}`);socket.current=ws;
   ws.onopen=()=>{if(stopped){ws.close();return;}setConnected(true);setError('');};
   ws.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){setState(m.state);received.current=Date.now();const sample=(m.state.server_time||Date.now())-Date.now();serverOffset.current=serverOffset.current===null?sample:Math.max(serverOffset.current,sample);}if(m.type==='ack'&&!m.ok)setError(m.error||'Command rejected.');}catch{setError('Could not read the server message.');}};
   ws.onclose=()=>{setConnected(false);if(!stopped)timer=setTimeout(connect,1800);};
   ws.onerror=()=>ws.close();
  };connect();const clock=setInterval(()=>setAge(received.current?Date.now()-received.current:0),200);
  return()=>{stopped=true;clearTimeout(timer);clearInterval(clock);socket.current?.close();};
 },[workerId]);
 const send=useCallback((type:string,robot_id:string,extra:Record<string,unknown>={})=>{if(socket.current?.readyState!==WebSocket.OPEN)return false;socket.current.send(JSON.stringify({type,robot_id,seq:++sequence.current,sent_at:Date.now()+(serverOffset.current||0),...extra}));return true;},[]);
 return {state,connected,workerId,send,error,setError,age};
}
