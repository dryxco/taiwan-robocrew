"""Original, collision-free workstation dressing for the rigid-body simulator.

Call after robot-specific physics and backdrop composition. No rendering context,
Pillow, or file writes are required at runtime; packaged PNGs are resolved locally.
"""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET

_TEXTURES = Path(__file__).resolve().parent / 'assets' / 'textures'
_PREFIX = 'workstation_'


def decorate_scene(xml: str, robot_id: str) -> str:
    """Return decorated MJCF without changing any physical geometry or cameras."""
    if robot_id not in ('jipai', 'pepper', 'tea'):
        raise ValueError(f'Unknown workstation: {robot_id}')
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('Workstation MJCF requires worldbody')
    if world.find("body[@name='workstation_decor']") is not None:
        return xml
    asset = root.find('asset')
    if asset is None:
        asset = ET.SubElement(root, 'asset')
    decor = ET.SubElement(world, 'body', name='workstation_decor')

    def material(name, **attrs):
        ET.SubElement(asset, 'material', name=_PREFIX+name, **attrs)
        return _PREFIX+name

    for name in (robot_id, 'bag', 'pickup', 'season', 'cup', 'crust', 'bread', 'steel'):
        ET.SubElement(asset, 'texture', name=_PREFIX+name, type='2d', file=str(_TEXTURES / (name+'.png')))
        material(name, texture=_PREFIX+name, texuniform='false', specular='.12', shininess='.1', emission=('.25' if name == robot_id else '0'))
    material('kraft', rgba='.68 .46 .24 1', specular='0')
    material('metal', rgba='.30 .36 .36 1', specular='.65', shininess='.6')
    material('gold', rgba='.88 .60 .24 1', specular='.4')
    material('lantern', rgba='.95 .18 .07 1', emission='.35')

    def geom(name, kind, pos, size, parent=decor, **attrs):
        return ET.SubElement(parent, 'geom', name=_PREFIX+name, type=kind,
                             pos=pos, size=size, contype='0', conaffinity='0',
                             group='2', mass='0', **attrs)

    def panel(name, texture, pos, width, height, horizontal=False, parent=decor):
        # Explicit UVs keep bilingual artwork upright on the facing side.
        w, h = width/2, height/2
        vertices = f'{-w} 0 {-h} {w} 0 {-h} {w} 0 {h} {-w} 0 {h}'
        if horizontal:
            vertices = f'{-w} {-h} 0 {w} {-h} 0 {w} {h} 0 {-w} {h} 0'
        ET.SubElement(asset, 'mesh', name=_PREFIX+name, vertex=vertices, inertia='shell',
                      face='0 1 2 0 2 3', texcoord='0 1 1 1 1 0 0 0')
        ET.SubElement(parent, 'geom', name=_PREFIX+name, type='mesh', mesh=_PREFIX+name,
                      pos=pos, material=_PREFIX+texture, contype='0', conaffinity='0', group='2', mass='0')

    for name, mat in [('counter', 'steel'), ('bag_base', 'kraft'), ('bag_back', 'kraft'),
                      ('bag_left', 'kraft'), ('bag_right', 'kraft')]:
        original = world.find(f"geom[@name='{name}']")
        if original is not None:
            original.set('material', _PREFIX+mat)
            original.set('rgba', '.68 .46 .24 1' if mat == 'kraft' else '1 1 1 1')
    food = world.find("body[@name='food']")
    if food is not None:
        food_geom = food.find('geom')
        if food_geom is not None:
            food_geom.set('material', _PREFIX+{'jipai':'crust', 'pepper':'bread', 'tea':'cup'}[robot_id])
            food_geom.set('rgba', '1 1 1 1')
        if robot_id == 'tea':
            geom('lid_seal', 'cylinder', '0 0 .081', '.042 .001', parent=food, rgba='.97 .88 .66 1')
            geom('straw_port', 'cylinder', '0 0 .083', '.008 .001', parent=food, rgba='.27 .18 .12 1')
            panel('cup_mark', 'cup', '0 -.045 0', .067, .065, parent=food)

    # Compact rear sign stays within the unchanged first-person field of view.
    geom('sign_frame', 'box', '0 .61 1.29', '.66 .025 .15', material=_PREFIX+'gold')
    panel('sign', robot_id, '0 .583 1.29', 1.29, .28)
    for x in (-.76, .76):
        geom(f'post_{x}', 'cylinder', f'{x} .54 1.04', '.018 .34', material=_PREFIX+'metal')
        geom(f'lantern_{x}', 'ellipsoid', f'{x} .49 1.32', '.065 .065 .09', material=_PREFIX+'lantern')
        for z in (1.235, 1.405):
            geom(f'cap_{x}_{z}', 'cylinder', f'{x} .49 {z}', '.037 .008', material=_PREFIX+'gold')
        ET.SubElement(decor, 'light', name=f'workstation_light_{x}', pos=f'{x} .35 1.42',
                      dir='0 0 -1', diffuse='.32 .20 .10', specular='.1 .07 .03',
                      directional='false', castshadow='false')

    panel('pickup_mark', 'pickup', '.43 -.34 .731', .32, .22, horizontal=True)
    panel('season_mark', 'season', '0 .24 .721', .28, .23, horizontal=True)
    panel('bag_mark', 'bag', '.38 .318 .82', .21, .12)
    for x in (-.16, .16):
        geom(f'tray_edge_{x}', 'box', f'{-.42+x} -.15 .741', '.005 .17 .01', material=_PREFIX+'metal')
    for y in (-.32, .02):
        geom(f'tray_end_{y}', 'box', f'-.42 {y} .741', '.16 .005 .01', material=_PREFIX+'metal')
    for i in range(3):
        x = -.57+i*.095
        geom(f'shaker_{i}', 'cylinder', f'{x} .43 .77', '.031 .07', rgba=('.72 .33 .12 1' if i == 0 else '.80 .69 .45 1'))
        geom(f'shaker_cap_{i}', 'cylinder', f'{x} .43 .844', '.033 .009', material=_PREFIX+'metal')
        for j in range(5):
            angle = j*math.tau/5
            geom(f'shaker_hole_{i}_{j}', 'cylinder', f'{x+.018*math.cos(angle)} {.43+.018*math.sin(angle)} .854', '.0025 .0005', rgba='.08 .08 .07 1')

    if robot_id == 'jipai':
        geom('fryer', 'box', '-.66 .18 .765', '.115 .15 .06', material=_PREFIX+'metal')
        geom('fryer_inset', 'box', '-.66 .18 .827', '.096 .13 .002', rgba='.12 .085 .035 1')
        for i in range(7):
            geom(f'fryer_basket_{i}', 'box', f'{-.75+i*.03} .18 .833', '.002 .125 .002', material=_PREFIX+'gold')
        geom('fryer_handle', 'box', '-.66 -.005 .84', '.018 .07 .012', rgba='.12 .13 .13 1')
    if robot_id == 'pepper':
        # Preserve the solid collision cylinder; dark center and segmented rim
        # suggest an oven mouth without claiming a hollow collision vessel.
        oven = world.find("geom[@name='oven']")
        if oven is not None:
            oven.set('rgba', '.17 .09 .045 1')
        geom('oven_dark_mouth', 'cylinder', '0 .27 1.041', '.165 .001', rgba='.035 .022 .014 1')
        for row in range(3):
            for i in range(16):
                a = (i + .5*(row % 2))*math.tau/16
                geom(f'brick_{row}_{i}', 'box', f'{.197*math.cos(a)} {.27+.197*math.sin(a)} {.77+row*.095}',
                     '.037 .018 .044', euler=f'0 0 {math.degrees(a)+90}', rgba=('.48 .24 .12 1' if i%3 else '.59 .32 .17 1'))
        for i in range(20):
            a = i*math.tau/20
            geom(f'oven_rim_{i}', 'box', f'{.19*math.cos(a)} {.27+.19*math.sin(a)} 1.055', '.029 .026 .018',
                 euler=f'0 0 {math.degrees(a)+90}', rgba='.67 .41 .22 1')
    if robot_id == 'tea':
        for i in range(2):
            x = -.64 + .15*i
            geom(f'tea_tin_{i}', 'cylinder', f'{x} .22 .84', '.06 .14', rgba='.34 .48 .40 1')
            geom(f'tea_tin_lid_{i}', 'cylinder', f'{x} .22 .985', '.063 .01', material=_PREFIX+'gold')
    return ET.tostring(root, encoding='unicode')
