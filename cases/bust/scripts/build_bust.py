# -*- coding: utf-8 -*-
"""人物胸像：Blender 5.2 内置功能六阶段教学工程。
运行： blender -b -P build_bust.py
全部由参数化网格生成，无外部模型/贴图/AI。
"""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))
HEAD_Z = 2.35
HEAD_RX, HEAD_RY, HEAD_RZ = 0.76, 0.80, 0.88


def log(msg):
    print("[BUST] " + str(msg), flush=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def save(name):
    path = os.path.join(OUT, name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    log("saved " + path)


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
    w, h = 512, 640
    px = np.zeros((h, w, 4), dtype=np.float32)
    px[..., :3] = (0.94, 0.93, 0.91)
    px[..., 3] = 1.0
    yy, xx = np.mgrid[0:h, 0:w]

    dark = (0.32, 0.30, 0.28)
    guide = (0.72, 0.30, 0.26)

    def ellipse(cx, cy, rx, ry, color, width=4):
        d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        m = (d > 0.94) & (d < 1.06)
        px[m, :3] = color

    ellipse(256, 240, 118, 150, dark)
    ellipse(256, 240, 90, 122, (0.55, 0.52, 0.49), 2)
    for gy in (205, 285, 345):
        px[gy:gy + 2, 120:392, :3] = guide
    px[85:400, 255:257, :3] = guide
    for ex in (205, 307):
        m = (xx - ex) ** 2 + (yy - 205) ** 2 < 15 * 15
        px[m, :3] = (0.20, 0.22, 0.25)
    px[238:250, 246:266, :3] = (0.45, 0.33, 0.28)
    px[335:345, 226:286, :3] = (0.48, 0.30, 0.28)
    px[400:560, 190:322, :3] = (0.50, 0.48, 0.45)

    img = bpy.data.images.new("BustRef", width=w, height=h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_bust.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
    emp = bpy.context.object
    emp.data = img
    emp.empty_display_size = 4.0
    emp.empty_image_depth = "FRONT"
    emp.name = "REF_Bust_Front"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def cube(name, dims, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def sphere(name, radius, loc, scale=(1, 1, 1), seg=32, rings=16):
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


def cylinder(name, radius, depth, loc, verts=32, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius,
                                        depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    return obj


def bevel(obj, width, segments=3, angle=0.4):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = angle
    return mod


def weighted_normal(obj):
    try:
        mod = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
    except Exception:
        pass


def tube(name, points, depth, mat=None, cyclic=False):
    cu = bpy.data.curves.new(name + "Curve", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, co in zip(sp.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    sp.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------------------
# Parametric head mesh
# ---------------------------------------------------------------------------

def gauss(hx, hz, cx, cz, sx, sz):
    return math.exp(-((hx - cx) / sx) ** 2 - ((hz - cz) / sz) ** 2)


def head_point(theta, phi):
    """(theta, phi) on unit sphere -> shaped head point (front faces -Y)."""
    st, ct = math.sin(theta), math.cos(theta)
    dx, dy, dz = st * math.cos(phi), st * math.sin(phi), ct

    # jaw taper: narrow lower half
    taper = 1.0 + 0.16 * min(0.0, dz)
    x = HEAD_RX * dx * taper
    z = HEAD_RZ * dz
    y = HEAD_RY * dy

    front = max(0.0, -dy) ** 2
    hz = dz
    hx = dx

    nose = 0.26 * gauss(hx, hz, 0.0, -0.04, 0.13, 0.26)
    bridge = 0.05 * gauss(hx, hz, 0.0, 0.14, 0.08, 0.24)
    brow = 0.035 * (gauss(hx, hz, 0.26, 0.30, 0.13, 0.07)
                    + gauss(hx, hz, -0.26, 0.30, 0.13, 0.07))
    cheek = 0.030 * (gauss(hx, hz, 0.38, -0.08, 0.14, 0.16)
                     + gauss(hx, hz, -0.38, -0.08, 0.14, 0.16))
    mouth = 0.030 * gauss(hx, hz, 0.0, -0.38, 0.16, 0.08)
    chin = 0.035 * gauss(hx, hz, 0.0, -0.60, 0.20, 0.16)
    socket = -0.055 * (gauss(hx, hz, 0.26, 0.13, 0.12, 0.10)
                       + gauss(hx, hz, -0.26, 0.13, 0.12, 0.10))
    disp = (nose + bridge + brow + cheek + mouth + chin + socket) * front
    y -= disp

    # slight skull flatten at back
    if dy > 0.7:
        y -= 0.05 * (dy - 0.7)
    return (x, y, z + HEAD_Z)


def build_head_mesh(name="Head_Mesh", segments=64, rings=40):
    verts = []
    faces = []
    verts.append(head_point(0.0, 0.0))
    rows = []
    for i in range(1, rings):
        theta = math.pi * i / rings
        row = []
        for j in range(segments):
            phi = 2.0 * math.pi * j / segments
            row.append(len(verts))
            verts.append(head_point(theta, phi))
        rows.append(row)
    bottom = len(verts)
    verts.append(head_point(math.pi, 0.0))
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


def build_hair_cap(name="Hair_Cap", segments=48, rings=14):
    verts = []
    faces = []
    verts.append((0, 0.04, HEAD_Z + HEAD_RZ * 1.02))
    rows = []
    for i in range(1, rings):
        t = i / rings
        row = []
        for j in range(segments):
            phi = 2.0 * math.pi * j / segments
            dy = math.sin(phi)
            theta_max = 1.30 + 0.40 * max(0.0, dy)
            theta = t * theta_max
            st, ct = math.sin(theta), math.cos(theta)
            x = HEAD_RX * 1.035 * st * math.cos(phi)
            y = HEAD_RY * 1.045 * st * math.sin(phi) + 0.02
            z = HEAD_RZ * 1.025 * ct + HEAD_Z
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

def simple_mat(name, base, rough, metal=0.0, noise_scale=None, strength=0.1,
               subsurface=None, coat=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if subsurface is not None and "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
        if "Subsurface Radius" in bsdf.inputs:
            bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.42, 0.30)
    if coat is not None and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if noise_scale:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-640, 0)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-440, 0)
        noise.inputs["Scale"].default_value = noise_scale
        nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (-200, -100)
        bump.inputs["Strength"].default_value = strength
        bump.inputs["Distance"].default_value = 0.004
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# ---------------------------------------------------------------------------
# Stage 2 : blockout
# ---------------------------------------------------------------------------

def build_blockout():
    cube("BLK_Head", (1.3, 1.4, 1.6), (0, 0, HEAD_Z))
    cube("BLK_Neck", (0.5, 0.5, 0.8), (0, 0, HEAD_Z - 1.05))
    cube("BLK_Shoulders", (2.4, 0.9, 0.9), (0, 0, HEAD_Z - 1.65))
    cube("BLK_Pedestal", (1.3, 1.3, 0.25), (0, 0, 0.13))


# ---------------------------------------------------------------------------
# Stage 3 : detailed bust
# ---------------------------------------------------------------------------

def build_detailed():
    parts = {}

    head = build_head_mesh()
    sub = head.modifiers.new("HeadSmooth", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2
    parts["head"] = head

    neck = cylinder("Neck", 0.30, 0.85, (0, 0.02, HEAD_Z - 1.02), verts=32)
    bevel(neck, 0.04, 3, 0.4)
    parts["neck"] = neck

    shoulders = sphere("Shoulders", 1.0, (0, 0.02, HEAD_Z - 1.72),
                       (1.16, 0.46, 0.50), seg=48, rings=24)
    parts["shoulders"] = shoulders

    chest = sphere("Chest", 1.0, (0, 0.04, HEAD_Z - 2.05),
                   (0.84, 0.40, 0.42), seg=40, rings=20)
    parts["chest"] = chest

    pedestal = cylinder("Pedestal", 0.62, 0.24, (0, 0, 0.12), verts=48)
    bevel(pedestal, 0.035, 3, 0.4)
    weighted_normal(pedestal)
    parts["pedestal"] = pedestal

    collar = tube("Collar_Guide", [
        (-0.55, -0.34, HEAD_Z - 1.42),
        (0.0, -0.42, HEAD_Z - 1.48),
        (0.55, -0.34, HEAD_Z - 1.42),
    ], 0.018)
    parts["collar"] = collar

    # eyes
    for side in (-1, 1):
        ex = side * 0.26
        ey = -0.66
        ez = HEAD_Z + HEAD_RZ * 0.13
        eye = sphere("Eye_%d" % side, 0.105, (ex, ey, ez),
                     (1, 0.72, 1), seg=24, rings=12)
        parts["eye_%d" % side] = eye
        iris = sphere("Iris_%d" % side, 0.046, (ex, ey - 0.072, ez),
                      (1, 0.4, 1), seg=20, rings=10)
        parts["iris_%d" % side] = iris
        pupil = sphere("Pupil_%d" % side, 0.022, (ex, ey - 0.092, ez),
                       (1, 0.35, 1), seg=16, rings=8)
        parts["pupil_%d" % side] = pupil
        upper = tube("Upper_Lid_%d" % side, [
            (ex - 0.13, -0.735, ez + 0.01),
            (ex, -0.78, ez + 0.075),
            (ex + 0.13, -0.735, ez + 0.01),
        ], 0.014)
        parts["upper_lid_%d" % side] = upper
        lower = tube("Lower_Lid_%d" % side, [
            (ex - 0.13, -0.735, ez + 0.005),
            (ex, -0.765, ez - 0.055),
            (ex + 0.13, -0.735, ez + 0.005),
        ], 0.011)
        parts["lower_lid_%d" % side] = lower
        brow = tube("Brow_%d" % side, [
            (ex - 0.15, -0.70, ez + 0.19),
            (ex, -0.755, ez + 0.245),
            (ex + 0.15, -0.70, ez + 0.19),
        ], 0.018)
        parts["brow_%d" % side] = brow

    # nose tip + wings
    tip = sphere("Nose_Tip", 0.078, (0, -0.91, HEAD_Z - HEAD_RZ * 0.07),
                 (1.0, 0.80, 0.78), seg=20, rings=10)
    parts["nose_tip"] = tip
    for side in (-1, 1):
        wing = sphere("Nose_Wing_%d" % side, 0.048,
                      (side * 0.070, -0.855, HEAD_Z - HEAD_RZ * 0.12),
                      (1.0, 0.70, 0.75), seg=16, rings=8)
        parts["nose_wing_%d" % side] = wing

    # lips
    mouth_z = HEAD_Z - HEAD_RZ * 0.38
    upper_lip = tube("Upper_Lip", [
        (-0.17, -0.755, mouth_z + 0.005),
        (0.0, -0.79, mouth_z + 0.035),
        (0.17, -0.755, mouth_z + 0.005),
    ], 0.016)
    parts["upper_lip"] = upper_lip
    lower_lip = tube("Lower_Lip", [
        (-0.17, -0.755, mouth_z - 0.005),
        (0.0, -0.785, mouth_z - 0.04),
        (0.17, -0.755, mouth_z - 0.005),
    ], 0.018)
    parts["lower_lip"] = lower_lip

    # ears
    for side in (-1, 1):
        ear = sphere("Ear_%d" % side, 0.16,
                     (side * 0.70, 0.02, HEAD_Z - 0.05),
                     (0.32, 0.75, 1.15), seg=20, rings=10)
        parts["ear_%d" % side] = ear
        inner = tube("Ear_Inner_%d" % side, [
            (side * 0.735, -0.02, HEAD_Z + 0.06),
            (side * 0.755, -0.06, HEAD_Z - 0.04),
            (side * 0.735, -0.01, HEAD_Z - 0.13),
        ], 0.012)
        parts["ear_inner_%d" % side] = inner

    # hair cap + a few strand lines
    hair = build_hair_cap()
    parts["hair"] = hair
    # rig placeholder: bone chain for future skinning
    arm_data = bpy.data.armatures.new("BustRigData")
    rig = bpy.data.objects.new("Bust_Rig", arm_data)
    bpy.context.collection.objects.link(rig)
    activate(rig)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    b0 = eb.new("Root")
    b0.head = (0, 0, 0.2)
    b0.tail = (0, 0, 1.2)
    b1 = eb.new("Spine")
    b1.head = (0, 0, 1.2)
    b1.tail = (0, 0, HEAD_Z - 1.0)
    b1.parent = b0
    b2 = eb.new("Neck")
    b2.head = (0, 0, HEAD_Z - 1.0)
    b2.tail = (0, 0, HEAD_Z - 0.55)
    b2.parent = b1
    b3 = eb.new("Head")
    b3.head = (0, 0, HEAD_Z - 0.55)
    b3.tail = (0, 0, HEAD_Z + 0.75)
    b3.parent = b2
    bpy.ops.object.mode_set(mode="OBJECT")
    parts["rig"] = rig

    return parts


# ---------------------------------------------------------------------------
# Lighting / camera / render
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
    bg.inputs["Color"].default_value = (0.13, 0.14, 0.16, 1.0)
    bg.inputs["Strength"].default_value = 0.55


def add_camera():
    data = bpy.data.cameras.new("CameraLens")
    data.lens = 52.0
    obj = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(obj)
    obj.location = (0.4, -7.0, 3.0)
    direction = Vector((0, 0, HEAD_Z - 0.70)) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = obj
    return obj


def setup_render(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 1050
    scene.render.resolution_percentage = 100
    ev = scene.eevee
    ev.taa_render_samples = 96
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
    parts = build_detailed()
    save("03_topology.blend")

    skin = simple_mat("Skin_Warm", (0.66, 0.44, 0.34, 1.0), 0.46,
                      noise_scale=160.0, strength=0.06,
                      subsurface=0.16, coat=0.10)
    hair_mat = simple_mat("Hair_DarkBrown", (0.075, 0.045, 0.028, 1.0), 0.42,
                          noise_scale=90.0, strength=0.10)
    sclera = simple_mat("Eye_Sclera", (0.88, 0.87, 0.84, 1.0), 0.18, coat=0.3)
    iris_mat = simple_mat("Eye_Iris", (0.11, 0.20, 0.28, 1.0), 0.24, coat=0.4)
    pupil_mat = simple_mat("Eye_Pupil", (0.01, 0.01, 0.015, 1.0), 0.12)
    lip_mat = simple_mat("Lips", (0.50, 0.24, 0.22, 1.0), 0.40,
                         subsurface=0.10)
    brow_mat = simple_mat("Brows", (0.10, 0.06, 0.04, 1.0), 0.7)
    bust_mat = simple_mat("Bust_Stone", (0.30, 0.31, 0.33, 1.0), 0.62,
                          noise_scale=70.0, strength=0.08)
    pedestal_mat = simple_mat("Pedestal_Dark", (0.10, 0.11, 0.12, 1.0),
                              0.48, metal=0.25, noise_scale=80.0, strength=0.06)

    assign_mat(parts["head"], skin)
    assign_mat(parts["neck"], skin)
    assign_mat(parts["shoulders"], bust_mat)
    assign_mat(parts["chest"], bust_mat)
    assign_mat(parts["pedestal"], pedestal_mat)
    assign_mat(parts["collar"], bust_mat)
    for key, obj in parts.items():
        if key.startswith("eye_"):
            assign_mat(obj, sclera)
        elif key.startswith("iris_"):
            assign_mat(obj, iris_mat)
        elif key.startswith("pupil_"):
            assign_mat(obj, pupil_mat)
        elif key in ("upper_lid", "lower_lid"):
            assign_mat(obj, skin)
        elif key.startswith("lid") or key.startswith("upper_lid_") or key.startswith("lower_lid_"):
            assign_mat(obj, skin)
        elif key.startswith("brow_"):
            assign_mat(obj, brow_mat)
        elif key.startswith("nostril_") or key.startswith("nose_"):
            assign_mat(obj, skin)
        elif key in ("upper_lip", "lower_lip"):
            assign_mat(obj, lip_mat)
        elif key.startswith("ear"):
            assign_mat(obj, skin)
        elif key == "hair":
            assign_mat(obj, hair_mat)
        elif key.startswith("strand_"):
            assign_mat(obj, hair_mat)
    save("04_material.blend")

    setup_world()
    add_area("Key_Light", (-2.6, -3.6, 5.2), 480.0, 3.5, (1.0, 0.93, 0.86))
    add_area("Fill_Light", (3.6, -1.6, 2.8), 200.0, 4.5, (0.80, 0.88, 1.0))
    add_area("Rim_Light", (1.0, 3.6, 4.2), 420.0, 3.0, (1.0, 0.94, 0.88))
    add_camera()
    save("05_lighting.blend")

    setup_render(scene)
    scene.render.filepath = os.path.join(OUT, "final.png")
    bpy.ops.render.render(write_still=True)
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
