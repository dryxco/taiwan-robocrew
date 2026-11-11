"""Collision-free Taipei market scenery for MuJoCo robot camera renders.

Compose after robot-specific XML, humanoid.augment_scene and
workstation_visuals.decorate_scene. This module only appends named visual
assets/body/lights; existing task geometry, cameras and constraints stay intact.
Legacy market_decor_root may coexist, but callers should omit that older backdrop
when composing a fresh scene to avoid duplicated distant stalls.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

_PREFIX = 'camera_market_'
_COLORS = ('#bd4a3a', '#ca8839', '#418a80')


def decorate_camera_market(xml: str, robot_id: str) -> str:
    """Add a Z-up night street around the employee facing world -Y.

    The central work volume stays clear: rear facades begin beyond Y=1,
    opposite shops beyond Y=-3, neighboring stalls at X=+/-2, canopy above
    Z=2.5. All additions have zero mass and disabled contact masks.
    """
    if robot_id not in ('jipai', 'pepper', 'tea'):
        raise ValueError(f'Unknown workstation: {robot_id}')
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('Camera market MJCF requires worldbody')
    if world.find("body[@name='camera_market_root']") is not None:
        return xml
    asset = root.find('asset')
    if asset is None:
        asset = ET.SubElement(root, 'asset')
    # Preserve an explicitly supplied sky rather than introduce multiple skyboxes.
    if asset.find("texture[@type='skybox']") is None:
        ET.SubElement(asset, 'texture', name=_PREFIX+'sky', type='skybox',
                      builtin='gradient', rgb1='.025 .075 .095', rgb2='.13 .23 .25',
                      width='256', height='1536')
    decor = ET.SubElement(world, 'body', name=_PREFIX+'root')
    materials = {}

    def material(color, glow=0):
        key = (color, glow)
        if key not in materials:
            name = _PREFIX+f'material_{len(materials)}'
            rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
            ET.SubElement(asset, 'material', name=name,
                          rgba=' '.join(map(str, rgb+[1])), emission=str(glow),
                          specular='.12', shininess='.1')
            materials[key] = name
        return materials[key]

    def geom(name, pos, size, color, kind='box', glow=0, **attrs):
        return ET.SubElement(decor, 'geom', name=_PREFIX+name, type=kind,
                             pos=' '.join(map(str, pos)), size=' '.join(map(str, size)),
                             material=material(color, glow), contype='0', conaffinity='0',
                             mass='0', group='2', **attrs)

    # A thin visual paving overlay avoids coplanar flicker with the physical floor.
    geom('pavement', (0, -2, .002), (11, 9, .001), '#222936')
    for y in (-.95, -3.25):
        for i in range(33):
            geom(f'tile_{y}_{i}', (-8+i*.5, y, .014), (.235, .17, .012), '#66636a')
        geom(f'gutter_{y}', (0, y-.24, .008), (9, .065, .005), '#121b25')
    for i in range(9):
        geom(f'road_mark_{i}', (-7+i*1.8, -2.1, .007), (.35, .025, .003), '#777563')

    # Two continuous rows of mixed-use shophouses enclose both camera directions.
    for row, face, direction in (('rear', 1.7, -1), ('opposite', -4.8, 1)):
        for i in range(7):
            x = (i-3)*2.5
            name = f'{row}_{i}'
            height = 5.8+(i % 3)*.65
            geom(name+'_building', (x, face-direction*.65, height/2),
                 (1.23, .65, height/2), ('#535969', '#6f6264', '#525e61')[i % 3])
            geom(name+'_shutter', (x, face+direction*.025, 1.15), (1.08, .03, 1.05), '#333b46')
            for j in range(9):
                geom(name+f'_slat_{j}', (x, face+direction*.065, .3+j*.22), (1.06, .025, .012), '#67636a')
            for floor in range(2):
                for side in (-1, 1):
                    z, wx = 3.45+floor*1.5, x+side*.57
                    label = name+f'_window_{floor}_{side}'
                    geom(label+'_frame', (wx, face+direction*.03, z), (.43, .045, .56), '#242e3d')
                    lit = (i+floor+side) % 3 != 0
                    geom(label, (wx, face+direction*.085, z), (.34, .015, .46), '#c69b67' if lit else '#253747', glow=.45 if lit else 0)
                    geom(label+'_mullion', (wx, face+direction*.11, z), (.018, .02, .47), '#434954')
                    geom(label+'_balcony', (wx, face+direction*.22, z-.57), (.48, .25, .045), '#77727a')
                    for bar in range(4):
                        geom(label+f'_rail_{bar}', (wx-.36+bar*.24, face+direction*.44, z-.35), (.012, .012, .2), '#303946')
            geom(name+'_ac', (x+.75, face+direction*.23, 2.63), (.26, .19, .16), '#b0aba0')
            geom(name+'_drainpipe', (x-1.13, face+direction*.08, 2.8), (.027, .035, 2.8), '#858083')
            geom(name+'_roof_tank', (x, face-direction*.4, height+.36), (.37, .36), '#929497', kind='cylinder')

    def stall(name, x, y, color, direction, counter=True):
        # Slim side stalls do not intersect the active counter or employee.
        if counter:
            geom(name+'_counter', (x, y, .48), (.84, .32, .48), color)
            geom(name+'_steel_top', (x, y, .98), (.88, .36, .025), '#b7b7ac')
            for j in range(4):
                geom(name+f'_bottle_{j}', (x-.5+j*.2, y, 1.12), (.045, .1), ('#ad4433', '#d8af62')[j % 2], kind='cylinder')
        for side in (-1, 1):
            geom(name+f'_post_{side}', (x+side*.89, y+.22, 1.31), (.023, .023, 1.31), '#a5a19a')
        for stripe in range(10):
            c = color if stripe % 2 == 0 else '#f4d8a0'
            sx = x-.855+stripe*.19
            geom(name+f'_awning_{stripe}', (sx, y, 2.68), (.095, .65, .025), c)
            geom(name+f'_valance_{stripe}', (sx, y+direction*.65, 2.57), (.095, .025, .1), c)
        geom(name+'_sign_frame', (x, y+direction*.48, 2.99), (.92, .055, .22), '#28262e')
        geom(name+'_sign', (x, y+direction*.545, 2.99), (.86, .015, .17), color, glow=.3)
        # Warm sign strokes suggest illuminated shop lettering without font assets.
        for j in range(5):
            sx = x-.6+j*.3
            geom(name+f'_sign_stroke_{j}', (sx, y+direction*.565, 2.99), (.08, .008, .025), '#fff1cb', glow=.5)
        geom(name+'_strip_light', (x, y, 2.49), (.65, .025, .018), '#fff1c2', glow=.7)

    index = ('jipai', 'pepper', 'tea').index(robot_id)
    for i, x in enumerate((-2, 0, 2)):
        stall(f'near_stall_{i}', x, .55, _COLORS[(index+i-1) % 3], -1, counter=x != 0)
        stall(f'far_stall_{i}', x*1.25, -4.0, _COLORS[i], 1)

    for row, y in enumerate((-1.35, -3.15)):
        for i in range(17):
            x = -8+i
            z = 3.35+.012*x*x
            if i < 16:
                nx = x+1
                ET.SubElement(decor, 'geom', name=_PREFIX+f'wire_{row}_{i}', type='capsule',
                              fromto=f'{x} {y} {z} {nx} {y} {3.35+.012*nx*nx}', size='.009',
                              rgba='.12 .12 .15 1', contype='0', conaffinity='0', mass='0', group='2')
            geom(f'lantern_{row}_{i}', (x, y, z-.2), (.15, .15, .2), '#ee5640' if row == 0 else '#eab258', kind='ellipsoid', glow=.6)
            for dz in (-.4, 0):
                geom(f'lantern_cap_{row}_{i}_{dz}', (x, y, z+dz), (.07, .02), '#65352e', kind='cylinder')
            geom(f'tassel_{row}_{i}', (x, y, z-.47), (.018, .07), '#df9e41', kind='cylinder')
    # Keep the source task lights/headlight intact; one fill avoids the GL light cap.
    ET.SubElement(decor, 'light', name=_PREFIX+'ambient', pos='0 -2 6', dir='0 0 -1',
                  directional='true', ambient='.12 .18 .19', diffuse='.28 .30 .28',
                  specular='.05 .05 .05', castshadow='false')
    return ET.tostring(root, encoding='unicode')
