"""Render the committed official G1 as the entrance asset's identity reference.

Run with a Python environment containing requirements.txt:
  python scripts/render_entrance_reference.py
This offline art script never imports or changes the live robot controller.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/entrance-art'


def main():
    root = ET.parse(ROOT / 'server/assets/g1/g1.xml').getroot()
    root.find('compiler').set('meshdir', str(ROOT / 'server/assets/g1/assets'))
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1024', offheight='1024')
    ET.SubElement(visual, 'headlight', ambient='.5 .5 .5', diffuse='.7 .7 .7', specular='.3 .3 .3')
    world = root.find('worldbody')
    ET.SubElement(world, 'light', pos='2 -2 3', dir='-1 1 -1', diffuse='.9 .85 .8')
    ET.SubElement(world, 'light', pos='0 2 2', dir='0 -1 -1', diffuse='.5 .6 .8')
    torso = world.find(".//body[@name='torso_link']")
    # Match the white chef hat in server/humanoid.py, without its work lean.
    hat = ET.SubElement(torso, 'body', name='chef_hat', pos='.004 0 .49')
    ET.SubElement(hat, 'geom', type='cylinder', size='.075 .025', rgba='.97 .97 .94 1', mass='0', contype='0', conaffinity='0')
    ET.SubElement(hat, 'geom', type='ellipsoid', pos='0 0 .075', size='.09 .085 .085', rgba='1 1 .98 1', mass='0', contype='0', conaffinity='0')
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
    data = mujoco.MjData(model)
    # Static photo pose only; official mesh hands remain unmodified here.
    for side, sign in [('left', 1), ('right', -1)]:
        for joint, value in [('shoulder_pitch', -.25), ('shoulder_roll', sign * .2), ('elbow', .35)]:
            data.qpos[model.joint(f'{side}_{joint}_joint').qposadr[0]] = value
    mujoco.mj_forward(model, data)
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [0, 0, .77]
    camera.distance = 2.65
    camera.azimuth = 5
    camera.elevation = -3
    option = mujoco.MjvOption()
    option.geomgroup[3] = 0  # Hide collision proxies, keep official visual meshes.
    OUT.mkdir(parents=True, exist_ok=True)
    with mujoco.Renderer(model, height=1024, width=1024) as renderer:
        renderer.update_scene(data, camera=camera, scene_option=option)
        Image.fromarray(renderer.render()).save(OUT / 'g1-chef-reference.png')


if __name__ == '__main__':
    main()
