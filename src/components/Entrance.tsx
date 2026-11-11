import {ArrowRight} from 'lucide-react';

export default function Entrance(){
 return <section className="entrance">
  <div className="entrance-sign"><small>台北・今晚也營業中</small><h2>夜班夜市</h2><span>NIGHT SHIFT</span></div>
  <div className="entrance-copy"><span className="entrance-stamp">歡迎光臨</span><h1>Tonight, let us<br/>open the night market.</h1><p>Crispy chicken, warm pepper buns, and chilled bubble tea.<br/>Lend a hand to Taipei from your room.</p><button onClick={()=>document.querySelector('.market-panel')?.scrollIntoView({behavior:'smooth'})}>Enter the night market <ArrowRight size={16}/></button><small>Live simulation · three stalls await</small></div>
  <img className="entrance-chef" src="/assets/entrance-scene.png" alt="Simulation rendering of a G1 chef and a market customer with arms around each other"/>
  <span className="entrance-note">一起開工！<small>Glad to share a shift with you</small></span>
 </section>;
}
