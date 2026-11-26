# -*- coding: utf-8 -*-
"""角色绑定与表情系统：半身角色骨架 + 手动蒙皮 + 形态键表情。
Blender 5.2 内置功能。运行： blender -b -P build_rigging.py
产出：六阶段快照 + 三张表情渲染。
"""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))
HEAD_Z = 2.30
RX, RY, RZ = 0.70, 0.76, 0.88


def log(msg):
    print("[RIG] " + str(msg), flush=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def save(name):
    p = os.path.join(OUT, name)
    bpy.ops.wm.save_as_mainfile(filepath=p)
    log("saved " + p)


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def assign_mat(obj, mat):
    if mat is None:
        return
    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ---------------------------------------------------------------------------
# Stage 1 : reference
# ---------------------------------------------------------------------------

def make_reference_image():
    w, h = 640, 420
    px = np.zeros((h, w, 4), dtype=np.float32)
    px[..., :3] = (0.93, 0.93, 0.91)
    px[..., 3] = 1.0
    yy, xx = np.mgrid[0:h, 0:w]
    dark, guide = (0.26, 0.26, 0.25), (0.74, 0.28, 0.24)
    d = ((xx - 320) / 95) ** 2 + ((yy - 160) / 120) ** 2
    px[(d > 0.94) & (d < 1.06), :3] = dark
    px[305:325, 220:420, :3] = dark
    px[320:380, 175:465, :3] = dark
    for gy in (120, 200, 275):
        px[gy:gy + 2, 200:440, :3] = guide
    px[80:360, 318:321, :3] = guide
    for ex in (280, 360):
        px[(xx - ex) ** 2 + (yy - 170) ** 2 < 12 * 12, :3] = (0.18, 0.20, 0.22)
    px[190:200, 312:328, :3] = (0.42, 0.30, 0.26)
    px[248:260, 296:344, :3] = (0.48, 0.29, 0.27)
    img = bpy.data.images.new("RigRef", width=w, height=h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_rig.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
    emp = bpy.context.object
    emp.data = img
    emp.empty_display_size = 4.0
    emp.empty_image_depth = "FRONT"
    emp.name = "REF_Character_Profile"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sphere(name, radius, loc, scale=(1, 1, 1), seg=24, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings,
                                         radius=radius, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def cube(name, dims, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def cylinder(name, radius, depth, loc, verts=24, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius,
                                        depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    return obj


def tube(name, points, depth):
    cu = bpy.data.curves.new(name + "Curve", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 2
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, co in zip(sp.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(obj)
    return obj


def gauss(hx, hz, cx, cz, sx, sz):
    return math.exp(-((hx - cx) / sx) ** 2 - ((hz - cz) / sz) ** 2)


def skull_point(theta, phi):
    st, ct = math.sin(theta), math.cos(theta)
    dx, dy, dz = st * math.cos(phi), st * math.sin(phi), ct
    temporal = 1.0 - 0.08 * gauss(dx, dz, 0.85, 0.35, 0.5, 0.4)
    jaw = 1.0 + 0.12 * gauss(dx, dz, 0.72, -0.45, 0.35, 0.3)
    x = RX * dx * temporal * jaw
    z = RZ * dz
    y = RY * dy
    front = max(0.0, -dy) ** 2
    hx, hz = dx, dz
    brow = 0.026 * (gauss(hx, hz, 0.30, 0.28, 0.16, 0.09)
                    + gauss(hx, hz, -0.30, 0.28, 0.16, 0.09))
    socket = -0.070 * (gauss(hx, hz, 0.28, 0.10, 0.15, 0.12)
                       + gauss(hx, hz, -0.28, 0.10, 0.15, 0.12))
    cheek = 0.040 * (gauss(hx, hz, 0.42, -0.12, 0.17, 0.18)
                     + gauss(hx, hz, -0.42, -0.12, 0.17, 0.18))
    bridge = 0.060 * gauss(hx, hz, 0.0, 0.12, 0.10, 0.30)
    nose = 0.140 * gauss(hx, hz, 0.0, -0.10, 0.13, 0.18)
    alae = 0.050 * (gauss(hx, hz, 0.13, -0.16, 0.08, 0.09)
                    + gauss(hx, hz, -0.13, -0.16, 0.08, 0.09))
    upper_lip = 0.045 * gauss(hx, hz, 0.0, -0.37, 0.20, 0.06)
    lower_lip = 0.050 * gauss(hx, hz, 0.0, -0.45, 0.19, 0.07)
    chin_crease = -0.022 * gauss(hx, hz, 0.0, -0.53, 0.13, 0.05)
    chin = 0.050 * gauss(hx, hz, 0.0, -0.65, 0.18, 0.13)
    disp = (brow + socket + cheek + bridge + nose + alae
            + upper_lip + lower_lip + chin_crease + chin) * front
    y -= disp
    if dy > 0.7:
        y -= 0.04 * (dy - 0.7)
    return (x, y, z + HEAD_Z)


def build_head(name="Character_Head", segments=64, rings=48):
    verts = [skull_point(0.0, 0.0)]
    faces = []
    rows = []
    for i in range(1, rings):
        theta = math.pi * i / rings
        row = []
        for j in range(segments):
            phi = 2.0 * math.pi * j / segments
            row.append(len(verts))
            verts.append(skull_point(theta, phi))
        rows.append(row)
    bottom = len(verts)
    verts.append(skull_point(math.pi, 0.0))
    for j in range(segments):
        faces.append((0, rows[0][j], rows[0][(j + 1) % segments]))
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((a[j], b[j], b[k], a[k]))
    for j in range(segments):
        faces.append((bottom, rows[-1][(j + 1) % segments], rows[-1][j]))
    mesh = bpy.data.meshes.new(name + "Data")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


def build_hair_cap(name="Hair_Mass", segments=48, rings=14):
    verts = [(0, 0.02, HEAD_Z + RZ * 1.02)]
    faces = []
    rows = []
    for i in range(1, rings):
        t = i / rings
        row = []
        for j in range(segments):
            phi = 2.0 * math.pi * j / segments
            dy = math.sin(phi)
            theta_max = 1.16 + 0.52 * max(0.0, dy)
            theta = t * theta_max
            st, ct = math.sin(theta), math.cos(theta)
            x = RX * 1.045 * st * math.cos(phi)
            y = RY * 1.055 * st * math.sin(phi) + 0.02
            z = RZ * 1.03 * ct + HEAD_Z
            row.append(len(verts))
            verts.append((x, y, z))
        rows.append(row)
    for j in range(segments):
        faces.append((0, rows[0][j], rows[0][(j + 1) % segments]))
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((a[j], b[j], b[k], a[k]))
    mesh = bpy.data.meshes.new(name + "Data")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def skin_material():
    mat = bpy.data.materials.new("Skin_Rig")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-760, 0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-560, 120)
    noise.inputs["Scale"].default_value = 3.2
    nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-360, 120)
    cr = ramp.color_ramp
    cr.elements[0].color = (0.56, 0.38, 0.30, 1.0)
    cr.elements[1].color = (0.68, 0.48, 0.38, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    pores = nt.nodes.new("ShaderNodeTexNoise")
    pores.location = (-560, -160)
    pores.inputs["Scale"].default_value = 200.0
    nt.links.new(tc.outputs["Generated"], pores.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-180, -120)
    bump.inputs["Strength"].default_value = 0.06
    bump.inputs["Distance"].default_value = 0.003
    nt.links.new(pores.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.48
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.20
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.32)
    return mat


def simple_mat(name, base, rough, metal=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return mat


# ---------------------------------------------------------------------------
# Stage 2 : blockout
# ---------------------------------------------------------------------------

def build_blockout():
    cube("BLK_Head", (1.35, 1.45, 1.7), (0, 0, HEAD_Z))
    cube("BLK_Neck", (0.46, 0.46, 0.8), (0, 0, HEAD_Z - 1.05))
    cube("BLK_Shoulders", (2.2, 0.9, 0.9), (0, 0, HEAD_Z - 1.65))


# ---------------------------------------------------------------------------
# Stage 3 : rigging
# ---------------------------------------------------------------------------

def build_armature():
    data = bpy.data.armatures.new("CharacterRig")
    rig = bpy.data.objects.new("Character_Rig", data)
    bpy.context.collection.objects.link(rig)
    activate(rig)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    specs = [
        ("Root", (0, 0, 0.3), (0, 0, 1.2), None),
        ("Spine", (0, 0, 1.2), (0, 0, 1.5), "Root"),
        ("Neck", (0, 0, 1.5), (0, 0, 1.9), "Spine"),
        ("Head", (0, 0, 1.9), (0, 0, HEAD_Z + 0.7), "Neck"),
        ("Jaw", (0, -0.15, HEAD_Z - 0.55), (0, -0.75, HEAD_Z - 0.75), "Head"),
        ("Eyelid.L", (0.26, -0.68, HEAD_Z + 0.13), (0.26, -0.68, HEAD_Z + 0.28), "Head"),
        ("Eyelid.R", (-0.26, -0.68, HEAD_Z + 0.13), (-0.26, -0.68, HEAD_Z + 0.28), "Head"),
    ]
    for name, h, t, parent in specs:
        b = eb.new(name)
        b.head = h
        b.tail = t
        if parent:
            b.parent = eb[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def bind_object(obj, rig, group, per_vertex=None):
    """group: default group for all verts; per_vertex: fn(co)->dict."""
    if obj.type != "MESH":
        activate(obj)
        bpy.ops.object.convert(target="MESH")
        obj = bpy.context.object
    if per_vertex is None:
        vg = obj.vertex_groups.new(name=group)
        vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    else:
        groups = {}
        for name in ("Root", "Spine", "Neck", "Head", "Jaw"):
            groups[name] = obj.vertex_groups.new(name=name)
        for v in obj.data.vertices:
            weights = per_vertex(v.co)
            for name, w in weights.items():
                if w > 0.001:
                    groups[name].add([v.index], w, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    mod.use_vertex_groups = True


def skin_weights(co):
    z, x, y = co.z, co.x, co.y
    t1 = max(0.0, min(1.0, (z - 1.30) / 0.35))
    t2 = max(0.0, min(1.0, (z - 1.70) / 0.35))
    w_spine = 1.0 - t1
    w_neck = t1 * (1.0 - t2)
    w_head = t1 * t2
    front = max(0.0, min(1.0, (-y - 0.45) / 0.25))
    jaw = math.exp(-((z - (HEAD_Z - 0.42)) / 0.16) ** 2) * math.exp(-(x / 0.28) ** 2) * front
    jaw = min(0.85, jaw)
    w_head *= (1.0 - jaw)
    total = w_spine + w_neck + w_head + jaw
    if total < 1e-6:
        return {"Spine": 1.0}
    return {"Spine": w_spine / total, "Neck": w_neck / total,
            "Head": w_head / total, "Jaw": jaw / total}


def build_character(rig):
    parts = {}
    head = build_head()
    parts["head"] = head

    neck = cylinder("Neck_Mesh", 0.28, 0.82, (0, 0.02, HEAD_Z - 1.02), verts=24)
    parts["neck"] = neck
    shoulders = sphere("Shoulders", 1.0, (0, 0.02, HEAD_Z - 1.72),
                       (1.12, 0.45, 0.50), seg=32, rings=16)
    parts["shoulders"] = shoulders
    chest = sphere("Chest", 1.0, (0, 0.05, HEAD_Z - 2.05),
                   (0.82, 0.40, 0.42), seg=32, rings=16)
    parts["chest"] = chest
    pedestal = cylinder("Pedestal", 0.60, 0.24, (0, 0, 0.12), verts=32)
    parts["pedestal"] = pedestal

    for side, gname in ((-1, "Eyelid.L"), (1, "Eyelid.R")):
        ex = side * 0.26
        ez = HEAD_Z + RZ * 0.10
        parts["eye_%d" % side] = sphere("Eye_%d" % side, 0.095,
                                        (ex, -0.590, ez), (1, 0.8, 1))
        parts["iris_%d" % side] = sphere("Iris_%d" % side, 0.044,
                                         (ex, -0.675, ez), (1, 0.4, 1))
        parts["pupil_%d" % side] = sphere("Pupil_%d" % side, 0.021,
                                          (ex, -0.692, ez), (1, 0.35, 1))
        parts["upper_lid_%d" % side] = tube("Upper_Lid_%d" % side, [
            (ex - side * 0.13, -0.645, ez + 0.012),
            (ex - side * 0.05, -0.685, ez + 0.066),
            (ex + side * 0.03, -0.690, ez + 0.062),
            (ex + side * 0.13, -0.645, ez + 0.010),
        ], 0.025)
        parts["lower_lid_%d" % side] = tube("Lower_Lid_%d" % side, [
            (ex - side * 0.13, -0.645, ez + 0.006),
            (ex, -0.680, ez - 0.055),
            (ex + side * 0.13, -0.645, ez + 0.006),
        ], 0.017)
        parts["brow_%d" % side] = tube("Brow_%d" % side, [
            (ex - side * 0.16, -0.68, ez + 0.19),
            (ex - side * 0.04, -0.735, ez + 0.235),
            (ex + side * 0.08, -0.745, ez + 0.225),
            (ex + side * 0.16, -0.69, ez + 0.17),
        ], 0.018)
        parts["lid_group_%d" % side] = gname

    mouth_z = HEAD_Z - RZ * 0.41
    parts["upper_lip"] = sphere("Upper_Lip", 0.135,
                                (0, -0.765, mouth_z + 0.014),
                                (1.05, 0.30, 0.20))
    parts["lower_lip"] = sphere("Lower_Lip", 0.140,
                                (0, -0.762, mouth_z - 0.036),
                                (1.0, 0.30, 0.22))

    for side in (-1, 1):
        parts["ear_%d" % side] = sphere("Ear_%d" % side, 0.17,
                                        (side * 0.68, 0.02, HEAD_Z - 0.06),
                                        (0.30, 0.72, 1.10))
    hair = build_hair_cap()
    parts["hair"] = hair

    # bind everything
    bind_object(head, rig, "Head", per_vertex=skin_weights)
    bind_object(neck, rig, "Neck", per_vertex=skin_weights)
    bind_object(shoulders, rig, "Spine")
    bind_object(chest, rig, "Spine")
    for key, obj in parts.items():
        if key.startswith("eye_") or key.startswith("iris_") or key.startswith("pupil_"):
            bind_object(obj, rig, "Head")
        elif key.startswith("upper_lid_") or key.startswith("lower_lid_"):
            side = key.split("_")[-1]
            bind_object(obj, rig, "Eyelid.L" if side == "-1" else "Eyelid.R")
        elif key.startswith("brow_") or key.startswith("ear") or key == "hair":
            bind_object(obj, rig, "Head")
        elif key in ("upper_lip", "lower_lip"):
            bind_object(obj, rig, "Jaw")

    # subdivision after armature for head
    sub = head.modifiers.new("SmoothAfterRig", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2

    # smile shape key on head mesh (before armature in stack order is fine)
    head.shape_key_add(name="Basis")
    smile = head.shape_key_add(name="Smile")
    for v in smile.data:
        z, x, y = v.co.z, v.co.x, v.co.y
        front = max(0.0, min(1.0, (-y - 0.45) / 0.25))
        w = math.exp(-((z - (HEAD_Z - 0.42)) / 0.16) ** 2) * math.exp(-(x / 0.28) ** 2) * front
        if w > 0.01:
            v.co.z += 0.10 * w
            v.co.x += 0.10 * w * (1 if x >= 0 else -1)
            v.co.y += 0.03 * w
    parts["smile_key"] = smile

    # lip meshes occlude the head mesh: give them their own smile keys
    lip_keys = []
    for key in ("upper_lip", "lower_lip"):
        obj = parts[key]
        obj.shape_key_add(name="Basis")
        lip = obj.shape_key_add(name="Smile")
        side_sign = -1 if key == "upper_lip" else 1
        for v in lip.data:
            x = v.co.x
            w = min(1.0, abs(x) / 0.12)
            v.co.z += 0.022 * w
            v.co.x += 0.012 * w * (1 if x >= 0 else -1)
            v.co.y += 0.004 * side_sign * w
        lip_keys.append(lip)
    parts["lip_smile_keys"] = lip_keys

    # blink: squash eyeballs and drive lids down via shape keys
    blink_keys = []
    for key in ("eye_-1", "eye_1", "iris_-1", "iris_1", "pupil_-1", "pupil_1",
                "upper_lid_-1", "upper_lid_1"):
        obj = parts[key]
        obj.shape_key_add(name="Basis")
        sh = obj.shape_key_add(name="Blink")
        for v in sh.data:
            if key.startswith("eye") or key.startswith("iris") or key.startswith("pupil"):
                v.co.z *= 0.10
            else:
                v.co.z -= 0.018
        blink_keys.append(sh)
    parts["blink_keys"] = blink_keys
    return parts


def setup_controls(rig, head, parts):
    ctrl = bpy.data.objects.new("CTRL_Expressions", None)
    bpy.context.collection.objects.link(ctrl)
    ctrl.location = (1.6, 0, HEAD_Z)
    ctrl.empty_display_type = "CIRCLE"
    ctrl.empty_display_size = 0.2
    ctrl["mouth_open"] = 0.0
    ctrl["blink"] = 0.0
    ctrl["smile"] = 0.0

    def driver(target, path, index, prop, expr):
        fc = target.driver_add(path, index) if index is not None else target.driver_add(path)
        d = fc.driver
        d.type = "SCRIPTED"
        v = d.variables.new()
        v.name = "v"
        v.type = "SINGLE_PROP"
        v.targets[0].id = ctrl
        v.targets[0].data_path = '["%s"]' % prop
        d.expression = expr

    jaw = rig.pose.bones["Jaw"]
    jaw.rotation_mode = "XYZ"
    driver(jaw, "rotation_euler", 0, "mouth_open", "v * 0.35")
    for name in ("Eyelid.L", "Eyelid.R"):
        bone = rig.pose.bones[name]
        bone.rotation_mode = "XYZ"
        driver(bone, "rotation_euler", 0, "blink", "v * -1.1")
    driver(parts["smile_key"], "value", None, "smile", "v")
    for key in parts["lip_smile_keys"]:
        driver(key, "value", None, "smile", "v")
    for key in parts["blink_keys"]:
        driver(key, "value", None, "blink", "v")
    return ctrl


# ---------------------------------------------------------------------------
# Lighting / render
# ---------------------------------------------------------------------------

def add_area(name, loc, energy, size, color, target=(0, 0, HEAD_Z)):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    direction = Vector(target) - Vector(loc)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj


def setup_world():
    world = bpy.data.worlds.new("StudioWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.12, 0.13, 0.15, 1.0)
    bg.inputs["Strength"].default_value = 0.6


def add_camera():
    data = bpy.data.cameras.new("CameraLens")
    data.lens = 58.0
    obj = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(obj)
    obj.location = (0.5, -6.5, 2.85)
    direction = Vector((0, 0, HEAD_Z - 0.65)) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = obj
    return obj


def setup_render(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    ev = scene.eevee
    ev.taa_render_samples = 64
    ev.taa_samples = 16
    ev.use_raytracing = True
    ev.ray_tracing_method = "SCREEN"
    opts = ev.ray_tracing_options
    opts.resolution_scale = "1"
    opts.screen_trace_quality = 0.7
    opts.screen_trace_thickness = 0.2
    opts.trace_max_roughness = 0.5
    opts.use_denoise = True
    opts.denoise_spatial = True
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "None"
    except Exception:
        scene.view_settings.look = "NONE"
    scene.view_settings.exposure = 0.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False


def render_pose(scene, ctrl, mouth, blink, smile, filename):
    ctrl["mouth_open"] = mouth
    ctrl["blink"] = blink
    ctrl["smile"] = smile
    ctrl.update_tag(refresh={"OBJECT"})
    bpy.context.view_layer.update()
    scene.frame_set(scene.frame_current)
    scene.render.filepath = os.path.join(OUT, filename)
    bpy.ops.render.render(write_still=True)


def main():
    reset()
    scene = bpy.context.scene
    ref = make_reference_image()
    add_reference(ref)
    save("01_reference.blend")

    build_blockout()
    save("02_blockout.blend")

    for obj in list(bpy.data.objects):
        if obj.name.startswith("BLK_"):
            bpy.data.objects.remove(obj, do_unlink=True)
    rig = build_armature()
    parts = build_character(rig)
    ctrl = setup_controls(rig, parts["head"], parts)
    save("03_rigging.blend")

    skin = skin_material()
    hair_mat = simple_mat("Hair_DarkBrown", (0.055, 0.032, 0.020, 1.0), 0.44)
    sclera = simple_mat("Eye_Sclera", (0.90, 0.89, 0.86, 1.0), 0.16)
    iris_mat = simple_mat("Eye_Iris", (0.10, 0.19, 0.26, 1.0), 0.22)
    pupil_mat = simple_mat("Eye_Pupil", (0.008, 0.008, 0.012, 1.0), 0.10)
    lip_mat = simple_mat("Lips", (0.50, 0.25, 0.23, 1.0), 0.42)
    brow_mat = simple_mat("Brows", (0.09, 0.055, 0.035, 1.0), 0.72)
    bust_mat = simple_mat("Bust_Stone", (0.28, 0.29, 0.31, 1.0), 0.64)
    pedestal_mat = simple_mat("Pedestal_Dark", (0.09, 0.10, 0.11, 1.0),
                              0.48, metal=0.25)

    assign_mat(parts["head"], skin)
    assign_mat(parts["neck"], skin)
    assign_mat(parts["shoulders"], bust_mat)
    assign_mat(parts["chest"], bust_mat)
    assign_mat(parts["pedestal"], pedestal_mat)
    for key, obj in parts.items():
        if key.startswith("eye_"):
            assign_mat(obj, sclera)
        elif key.startswith("iris_"):
            assign_mat(obj, iris_mat)
        elif key.startswith("pupil_"):
            assign_mat(obj, pupil_mat)
        elif key.startswith("upper_lid_") or key.startswith("lower_lid_"):
            assign_mat(obj, skin)
        elif key.startswith("brow_"):
            assign_mat(obj, brow_mat)
        elif key in ("upper_lip", "lower_lip"):
            assign_mat(obj, lip_mat)
        elif key.startswith("ear"):
            assign_mat(obj, skin)
        elif key == "hair":
            assign_mat(obj, hair_mat)
    save("04_material.blend")

    setup_world()
    add_area("Key_Light", (-2.4, -3.4, 5.0), 460.0, 3.5, (1.0, 0.94, 0.88))
    add_area("Fill_Light", (3.4, -1.8, 2.6), 190.0, 4.5, (0.82, 0.89, 1.0))
    add_area("Rim_Light", (1.0, 3.4, 4.0), 400.0, 3.0, (1.0, 0.94, 0.88))
    add_camera()
    save("05_lighting.blend")

    setup_render(scene)
    render_pose(scene, ctrl, 0.0, 0.0, 0.0, "pose_neutral.png")
    render_pose(scene, ctrl, 0.45, 0.0, 1.0, "pose_smile.png")
    render_pose(scene, ctrl, 0.0, 1.0, 0.2, "pose_blink.png")
    ctrl["mouth_open"] = 0.0
    ctrl["blink"] = 0.0
    ctrl["smile"] = 0.0
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
