/** Camera is the customer: larger palm advances toward -Y; image height controls Z. */
export type HandAnchor = {x:number;y:number;spanDepth:number;robotX:number;robotY:number;robotZ:number};
const clamp=(v:number,lo=-1,hi=1)=>Math.max(lo,Math.min(hi,v));
export function mapCustomerHand(hand:{x:number;y:number;depth?:number;twist?:number},a:HandAnchor){
 return {
  x:clamp(a.robotX-(hand.x-a.x)*2.4),
  y:clamp(a.robotY-((hand.depth??0)-a.spanDepth)*4),
  depth:clamp(.96-a.robotZ+(hand.y-a.y)*.7,-.12,.12),
  twist:-(hand.twist??0),
 };
}
