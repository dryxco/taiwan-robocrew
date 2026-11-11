"""Read-only visual transforms of the actual simulated humanoid."""
from pathlib import Path
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
import time

ASSET_ROOT = Path(__file__).parent / 'assets' / 'g1' / 'assets'
MESH_FILES = {(e.get('name') or Path(e.get('file')).stem): e.get('file') for e in ET.parse(ASSET_ROOT.parent / 'g1.xml').getroot().find('asset') if e.tag == 'mesh'}

def visual_snapshot(robot):
    with robot.lock:
        model, data = robot.model, robot.data
        pelvis = model.body('pelvis').id
        geoms = []
        kinds = {int(mujoco.mjtGeom.mjGEOM_MESH): 'mesh', int(mujoco.mjtGeom.mjGEOM_BOX): 'box', int(mujoco.mjtGeom.mjGEOM_CYLINDER): 'cylinder', int(mujoco.mjtGeom.mjGEOM_ELLIPSOID): 'ellipsoid', int(mujoco.mjtGeom.mjGEOM_SPHERE): 'sphere'}
        for index in range(model.ngeom):
            if model.geom_rgba[index, 3] == 0: continue
            ancestor = int(model.geom_bodyid[index])
            while ancestor and ancestor != pelvis:
                ancestor = int(model.body_parentid[ancestor])
            name = mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,index) or f'geom-{index}'
            body_name = mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_BODY,int(model.geom_bodyid[index]))
            task = name in {'counter','tray','season_zone','bag_base','bag_back','bag_left','bag_right','delivery'} or body_name == 'food' or name.startswith(('workstation_brick_', 'workstation_oven_'))
            if ancestor != pelvis and not task: continue
            kind = kinds.get(int(model.geom_type[index]))
            if not kind: continue
            rotation = data.geom_xmat[index].reshape(3, 3).copy()
            position = data.geom_xpos[index].copy()
            item = {'name': mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,index) or f'geom-{index}', 'type':kind, 'size':model.geom_size[index].tolist(), 'rgba':model.geom_rgba[index].tolist()}
            item['role'] = 'food' if body_name == 'food' else ('fixture' if task else 'robot')
            mat = int(model.geom_matid[index])
            if mat >= 0: item['rgba'] = model.mat_rgba[mat].tolist()
            if task:
                if body_name == 'food': item['rgba'] = {'jipai':[.85,.53,.19,1], 'pepper':([.38,.14,.035,1] if robot.cooked else [.85,.65,.32,1]), 'tea':[.70,.49,.28,1]}[robot.id]
                elif name.startswith('bag'): item['rgba'] = [.65,.46,.25,1]
                elif name == 'tray': item['rgba'] = [.55,.59,.62,1]
                elif name == 'counter': item['rgba'] = [.52,.56,.51,1]
            if body_name == 'food' and (name.startswith('geom-') or name == 'food_chicken'):
                item['texture_url'] = '/api/material-assets/' + {'jipai':'crust','pepper':'bread','tea':'cup'}[robot.id] + '.png'
            if kind == 'mesh':
                mesh = int(model.geom_dataid[index]); mesh_name = mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_MESH,mesh)
                filename = MESH_FILES.get(mesh_name)
                if not filename:
                    if body_name != 'food': continue
                    va, vn = int(model.mesh_vertadr[mesh]),int(model.mesh_vertnum[mesh])
                    fa, fn = int(model.mesh_faceadr[mesh]),int(model.mesh_facenum[mesh])
                    item['vertices'] = model.mesh_vert[va:va+vn].ravel().tolist()
                    item['faces'] = model.mesh_face[fa:fa+fn].ravel().tolist()
                    item.update(position=position.tolist(),rotation=rotation.ravel().tolist())
                    geoms.append(item)
                    continue
                mesh_rotation = np.empty(9); mujoco.mju_quat2Mat(mesh_rotation, model.mesh_quat[mesh])
                rotation = rotation @ mesh_rotation.reshape(3,3).T
                position -= rotation @ model.mesh_pos[mesh]
                item['mesh_url'] = '/api/robot-assets/g1/' + filename
            item.update(position=position.tolist(),rotation=rotation.ravel().tolist())
            geoms.append(item)
        stamp = int(time.time()*1000)
        with robot.frame_lock:
            robot.visual_timestamp = stamp
        return {'geoms':geoms,'robot_id':robot.id,'timestamp':float(data.time),'frame_timestamp':stamp}
