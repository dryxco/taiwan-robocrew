"""Render an actual G1 and the market's block customer; no image generation."""
from pathlib import Path
import xml.etree.ElementTree as ET
import math
import mujoco,numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
root=ET.parse(ROOT/'server/assets/g1/g1.xml').getroot();root.find('compiler').set('meshdir',str(ROOT/'server/assets/g1/assets'))
visual=ET.SubElement(root,'visual');ET.SubElement(visual,'global',offwidth='1000',offheight='1000');ET.SubElement(visual,'headlight',ambient='.4 .4 .4',diffuse='.5 .5 .5',specular='.15 .15 .15')
world=root.find('worldbody');ET.SubElement(world,'light',pos='3 -2 4',dir='-1 0 -1',diffuse='.65 .62 .54');ET.SubElement(world,'light',pos='1 3 3',dir='-1 -1 -1',diffuse='.3 .35 .4')
torso=world.find(".//body[@name='torso_link']");hat=ET.SubElement(torso,'body',name='chef_hat',pos='.004 0 .49')
ET.SubElement(hat,'geom',type='cylinder',size='.075 .025',rgba='.96 .94 .87 1',contype='0',conaffinity='0')
ET.SubElement(hat,'geom',type='ellipsoid',pos='0 0 .075',size='.09 .085 .085',rgba='1 .98 .91 1',contype='0',conaffinity='0')
# Same proportions and palette as marketEnvironment.drawPerson, at G1 scale.
customer=ET.SubElement(world,'body',name='market_customer',pos='.04 -.56 0')
scale=.82
skin='.839 .627 .475 1';shirt='.318 .557 .541 1';pants='.188 .224 .286 1'
def box(name,pos,size,color,quat=None):
 attrs=dict(name=name,type='box',pos=' '.join(str(v*scale) for v in pos),size=' '.join(str(v*scale/2) for v in size),rgba=color,contype='0',conaffinity='0')
 if quat:attrs['quat']=quat
 return ET.SubElement(customer,'geom',**attrs)
box('shirt',[0,0,1.05],[.23,.37,.5],shirt)
box('left_leg',[0,.1,.45],[.15,.13,.72],pants);box('right_leg',[0,-.1,.45],[.15,.13,.72],pants)
box('cap',[-.01,0,1.62],[.26,.28,.08],'.16 .16 .21 1')
# Faceted head matching the crowd's eight longitude / six latitude sphere.
verts=[]
for j in range(7):
 for i in range(8):
  a=i*math.tau/8;b=j*math.pi/6
  verts.extend([.14*scale*math.sin(b)*math.cos(a),.15*scale*math.sin(b)*math.sin(a),.18*scale*math.cos(b)])
asset=root.find('asset');ET.SubElement(asset,'mesh',name='customer_head',vertex=' '.join(map(str,verts)))
ET.SubElement(customer,'geom',name='customer_face',type='mesh',mesh='customer_head',pos=f'0 0 {1.49*scale}',rgba=skin,contype='0',conaffinity='0')
# Customer's near arm rests across the chef's back; outer arm relaxed.
box('shoulder_arm',[0,.36,1.30],[.12,.53,.12],skin)
box('right_arm',[0,-.25,1.01],[.11,.1,.43],skin)
model=mujoco.MjModel.from_xml_string(ET.tostring(root,encoding='unicode'));data=mujoco.MjData(model)
for joint,value in [('left_shoulder_pitch',.1),('left_shoulder_roll',.1),('left_elbow',.3),('left_wrist_pitch',0),('right_shoulder_pitch',-.35),('right_shoulder_roll',-1.35),('right_elbow',1.2)]:data.qpos[model.joint(joint+'_joint').qposadr[0]]=value
mujoco.mj_forward(model,data)
cam=mujoco.MjvCamera();cam.lookat[:]=[0,-.25,.8];cam.distance=2.6;cam.azimuth=5;cam.elevation=-3
option=mujoco.MjvOption();option.geomgroup[3]=0
with mujoco.Renderer(model,height=1000,width=1000) as r:
 r.update_scene(data,camera=cam,scene_option=option);rgb=r.render().copy();r.enable_segmentation_rendering();r.update_scene(data,camera=cam,scene_option=option);seg=r.render();alpha=np.where(seg[:,:,0]>=0,255,0).astype(np.uint8)
 out=ROOT/'public/assets/entrance-scene.png';Image.fromarray(np.dstack([rgb,alpha])).save(out);print(out)
