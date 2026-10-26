// Deterministic numeric sampling of Blockbench/GeckoLib keyframe channels.
import {INTERPOLATIONS} from './geckolib.mjs';
const clamp=x=>Math.min(1,Math.max(0,x));
function ease(name,t) {
  t=clamp(t);
  if (name==='linear'||name==='catmullrom') return t;
  const match=/^(easeInOut|easeIn|easeOut)(Sine|Quad|Cubic|Quart|Quint|Expo|Circ|Back|Bounce|Elastic)$/.exec(name);
  if(!match)throw Error('Unsupported interpolation: '+name+'; valid: '+INTERPOLATIONS.join(', '));
  const [,direction,kind]=match;
  const f={
    Sine:x=>1-Math.cos(x*Math.PI/2), Quad:x=>x*x,Cubic:x=>x*x*x,Quart:x=>x**4,Quint:x=>x**5,
    Expo:x=>x===0?0:2**(10*x-10), Circ:x=>1-Math.sqrt(1-x*x),
    Back:x=>2.70158*x**3-1.70158*x*x,
    Bounce:x=>{const y=1-x; const n=7.5625,d=2.75; if(y<1/d)return 1-n*y*y;if(y<2/d)return 1-(n*(y-1.5/d)**2+.75);if(y<2.5/d)return 1-(n*(y-2.25/d)**2+.9375);return 1-(n*(y-2.625/d)**2+.984375);},
    Elastic:x=>x===0||x===1?x:-(2**(10*x-10))*Math.sin((x*10-10.75)*(2*Math.PI/3))
  }[kind];
  if(direction==='easeIn')return f(t);
  if(direction==='easeOut')return 1-f(1-t);
  return t<.5?f(2*t)/2:1-f(2-2*t)/2;
}
function vector(k){const p=k.data_points[0];return [p.x,p.y,p.z];}
function sampleKeys(keys,time) {
  const ordered=[...keys].sort((a,b)=>a.time-b.time);
  if(!ordered.length)return null;
  if(time<=ordered[0].time)return vector(ordered[0]);
  if(time>=ordered.at(-1).time)return vector(ordered.at(-1));
  const index=ordered.findIndex(k=>k.time>time);
  const a=ordered[index-1],b=ordered[index];
  const v=vector(a),w=vector(b),t=(time-a.time)/(b.time-a.time);
  const mode=a.interpolation??'linear';
  if(mode==='catmullrom'){
    const previous=vector(ordered[Math.max(0,index-2)]),next=vector(ordered[Math.min(ordered.length-1,index+1)]);
    // Hermite interpolation, with time-weighted tangents so irregular keyframe spacing behaves smoothly.
    const prevTime=ordered[Math.max(0,index-2)].time, nextTime=ordered[Math.min(ordered.length-1,index+1)].time;
    const span=b.time-a.time;
    return v.map((x,i)=>{
      const m0=(w[i]-previous[i])/(b.time-prevTime||span)*span;
      const m1=(next[i]-x)/(nextTime-a.time||span)*span;
      return (2*t**3-3*t*t+1)*x+(t**3-2*t*t+t)*m0+(-2*t**3+3*t*t)*w[i]+(t**3-t*t)*m1;
    });
  }
  const s=ease(mode,t);
  return v.map((x,i)=>x+(w[i]-x)*s);
}
export function samplePose(model,{animation,time,wrap=true}) {
  if(typeof animation!=='string'||animation.length===0||!Number.isFinite(time)||time<0||time>600000||typeof wrap!=='boolean') throw Error('animation required; time must be finite >=0 and wrap boolean');
  if(model.meta?.model_format!=='geckolib_model')throw Error('sample_pose requires geckolib_model');
  const anim=(model.animations||[]).find(a=>a.name===animation);
  if(!anim)throw Error('Animation not found; valid names: '+(model.animations||[]).map(a=>a.name).join(', '));
  if(!Number.isFinite(anim.length)||anim.length<=0)throw Error('Animation length is invalid');
  const sampled=(anim.loop==='loop'&&wrap) ? time%anim.length:Math.min(time,anim.length);
  const bones=(model.groups||[]).map(g=>{
    const kfs=anim.animators?.[g.uuid]?.keyframes||[];
    const channels={};
    for(const channel of ['position','rotation','scale']){
      const keys=kfs.filter(k=>k.channel===channel);
      channels[channel]=sampleKeys(keys,sampled) ?? (channel==='scale'?[1,1,1]:[0,0,0]);
    }
    return {uuid:g.uuid,name:g.name,pivot:g.origin,rest_rotation:g.rotation, ...channels, animated_channels:[...new Set(kfs.map(k=>k.channel))]};
  });
  return {animation,requested_time:time,sampled_time:sampled,length:anim.length,loop:anim.loop,bones,coordinate_system:'Blockbench local channels, degrees for rotation; no world-space transforms'};
}
