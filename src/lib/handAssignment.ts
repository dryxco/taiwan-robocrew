import type {HandPoint} from './handIntent';
type Entry={points:HandPoint[];score:number};
type Pair=Partial<Record<'left'|'right',Entry>>;
/** Handedness is a classification, not a unique tracking ID. Keep both detections. */
export function assignHands(points:HandPoint[][],labels:{categoryName:string;score:number}[][],previous:Pair={}):Pair{
 const entries=points.slice(0,2).map((p,i)=>({points:p,score:labels[i]?.[0]?.score??0,side:labels[i]?.[0]?.categoryName==='Left'?'right':'left'}));
 if(entries.length<2)return entries.length?{[entries[0].side]:entries[0]}:{};
 const [a,b]=entries;
 if(a.side!==b.side)return {[a.side]:a,[b.side]:b};
 const distance=(entry:Entry,old:Entry)=>Math.hypot(entry.points[0].x-old.points[0].x,entry.points[0].y-old.points[0].y);
 if(previous.left&&previous.right){
  const straight=distance(a,previous.left)+distance(b,previous.right);
  const crossed=distance(b,previous.left)+distance(a,previous.right);
  return straight<=crossed?{left:a,right:b}:{left:b,right:a};
 }
 return a.points[0].x<b.points[0].x?{left:a,right:b}:{left:b,right:a};
}
