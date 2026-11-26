# -*- coding: utf-8 -*-
"""数字雕刻流程：头部胸像的体素重建 + 分层雕刻 + 皮肤材质。
Blender 5.2 内置功能。运行： blender -b -P build_sculpt.py
说明：脚本用位移层模拟雕刻笔刷效果，手工笔触需在 Sculpt 模式继续。
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
    print("[SCULPT] " + str(msg), flush=True)


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
    w, h = 512, 640
    px = np.zeros((h, w, 4), dtype=np.float32)
    px[..., :3] = (0.93, 0.92, 0.90)
    px[..., 3] = 1.0
    yy, xx = np.mgrid[0:h, 0:w]
    dark, guide = (0.28, 0.27, 0.26), (0.74, 0.28, 0.24)
    d = ((xx - 256) / 118) ** 2 + ((yy - 250) / 152) ** 2
    px[(d > 0.94) & (d < 1.06), :3] = dark
    for gy in (198, 262, 336):
        px[gy:gy + 2, 125:387, :3] = guide
    px[85:400, 255:257, :3] = guide
    for ex in (206, 306):
        px[(xx - ex) ** 2 + (yy - 216) ** 2 < 15 * 15, :3] = (0.18, 0.20, 0.22)
    px[244:254, 246:266, :3] = (0.42, 0.30, 0.26)
    px[336:349, 224:288, :3] = (0.48, 0.29, 0.27)
    img = bpy.data.images.new("SculptRef", width=w, height=h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_sculpt.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
    emp = bpy.context.object
    emp.data = img
    emp.empty_display_size = 4.0
    emp.empty_image_depth = "FRONT"
    emp.name = "REF_Head_Proportion"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def cube(name, dims, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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


def gaussian(hx, hz, cx, cz, sx, sz):
    return math.exp(-((hx - cx) / sx) ** 2 - ((hz - cz) / sz) ** 2)


# ---------------------------------------------------------------------------
# Base skull mesh (sculpt foundation)
# ---------------------------------------------------------------------------

def skull_point(theta, phi):
    st, ct = math.sin(theta), math.cos(theta)
    dx, dy, dz = st * math.cos(phi), st * math.sin(phi), ct
    temporal = 1.0 - 0.08 * gaussian(dx, dz, 0.85, 0.35, 0.5, 0.4)
    jaw = 1.0 + 0.12 * gaussian(dx, dz, 0.72, -0.45, 0.35, 0.3)
    x = RX * dx * temporal * jaw
    z = RZ * dz
    y = RY * dy
    front = max(0.0, -dy) ** 2
    hx, hz = dx, dz
    brow = 0.026 * (gaussian(hx, hz, 0.30, 0.28, 0.16, 0.09)
                    + gaussian(hx, hz, -0.30, 0.28, 0.16, 0.09))
    socket = -0.070 * (gaussian(hx, hz, 0.28, 0.10, 0.15, 0.12)
                       + gaussian(hx, hz, -0.28, 0.10, 0.15, 0.12))
    cheek = 0.040 * (gaussian(hx, hz, 0.42, -0.12, 0.17, 0.18)
                     + gaussian(hx, hz, -0.42, -0.12, 0.17, 0.18))
    bridge = 0.060 * gaussian(hx, hz, 0.0, 0.12, 0.10, 0.30)
    nose = 0.140 * gaussian(hx, hz, 0.0, -0.10, 0.13, 0.18)
    alae = 0.050 * (gaussian(hx, hz, 0.13, -0.16, 0.08, 0.09)
                    + gaussian(hx, hz, -0.13, -0.16, 0.08, 0.09))
    philtrum = 0.015 * gaussian(hx, hz, 0.0, -0.30, 0.05, 0.07)
    upper_lip = 0.045 * gaussian(hx, hz, 0.0, -0.37, 0.20, 0.06)
    lower_lip = 0.050 * gaussian(hx, hz, 0.0, -0.45, 0.19, 0.07)
    chin_crease = -0.022 * gaussian(hx, hz, 0.0, -0.53, 0.13, 0.05)
    chin = 0.050 * gaussian(hx, hz, 0.0, -0.65, 0.18, 0.13)
    disp = (brow + socket + cheek + bridge + nose + alae + philtrum
            + upper_lip + lower_lip + chin_crease + chin) * front
    y -= disp
    if dy > 0.7:
        y -= 0.04 * (dy - 0.7)
    return (x, y, z + HEAD_Z)


def build_head(name="Sculpt_Base", segments=96, rings=64):
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


def build_hair_cap(name="Hair_Mass", segments=64, rings=16):
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
    mat = bpy.data.materials.new("Skin_Layered")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1000, 0)
    # large-scale skin tone variation
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-780, 160)
    noise.inputs["Scale"].default_value = 3.0
    noise.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-560, 160)
    cr = ramp.color_ramp
    cr.elements[0].position = 0.28
    cr.elements[0].color = (0.55, 0.37, 0.30, 1.0)
    cr.elements[1].position = 0.72
    cr.elements[1].color = (0.69, 0.49, 0.39, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    # medium-scale mottling for realism
    mottle = nt.nodes.new("ShaderNodeTexNoise")
    mottle.location = (-780, -60)
    mottle.inputs["Scale"].default_value = 22.0
    mottle.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Generated"], mottle.inputs["Vector"])
    bump_m = nt.nodes.new("ShaderNodeBump")
    bump_m.location = (-360, -60)
    bump_m.inputs["Strength"].default_value = 0.018
    bump_m.inputs["Distance"].default_value = 0.004
    nt.links.new(mottle.outputs["Fac"], bump_m.inputs["Height"])
    # pore-scale bump
    pores = nt.nodes.new("ShaderNodeTexNoise")
    pores.location = (-780, -280)
    pores.inputs["Scale"].default_value = 210.0
    pores.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Generated"], pores.inputs["Vector"])
    bump_p = nt.nodes.new("ShaderNodeBump")
    bump_p.location = (-140, -160)
    bump_p.inputs["Strength"].default_value = 0.08
    bump_p.inputs["Distance"].default_value = 0.002
    nt.links.new(pores.outputs["Fac"], bump_p.inputs["Height"])
    nt.links.new(bump_m.outputs["Normal"], bump_p.inputs["Normal"])
    nt.links.new(bump_p.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.48
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.20
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.32)
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.08
    return mat


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
    cube("BLK_Head", (1.35, 1.45, 1.7), (0, 0, HEAD_Z))
    cube("BLK_Neck", (0.46, 0.46, 0.8), (0, 0, HEAD_Z - 1.05))
    cube("BLK_Shoulders", (2.2, 0.9, 0.9), (0, 0, HEAD_Z - 1.65))


# ---------------------------------------------------------------------------
# Stage 3 : sculpt layers
# ---------------------------------------------------------------------------

def build_sculpt():
    parts = {}
    head = build_head()
    parts["head"] = head

    # multiresolution: foundation for hand sculpting
    mr = head.modifiers.new("SculptLevels", "SUBSURF")
    mr.subdivision_type = "CATMULL_CLARK"
    mr.levels = 2
    mr.render_levels = 3

    # layer 1: clay-like medium forms via displacement texture
    tex_medium = bpy.data.textures.new("ClayMedium", type="CLOUDS")
    tex_medium.noise_scale = 0.20
    tex_medium.noise_depth = 2
    d1 = head.modifiers.new("ClayPass", "DISPLACE")
    d1.texture = tex_medium
    d1.texture_coords = "LOCAL"
    d1.strength = 0.002
    d1.mid_level = 0.5

    # layer 2: fine skin undulation
    tex_fine = bpy.data.textures.new("SkinFine", type="CLOUDS")
    tex_fine.noise_scale = 0.055
    tex_fine.noise_depth = 2
    d2 = head.modifiers.new("SkinPass", "DISPLACE")
    d2.texture = tex_fine
    d2.texture_coords = "LOCAL"
    d2.strength = 0.003
    d2.mid_level = 0.5

    neck = cylinder("Neck", 0.28, 0.82, (0, 0.02, HEAD_Z - 1.02), verts=32)
    bevel(neck, 0.035, 3, 0.4)
    parts["neck"] = neck
    shoulders = sphere("Shoulders", 1.0, (0, 0.02, HEAD_Z - 1.72),
                       (1.12, 0.45, 0.50), seg=48, rings=24)
    parts["shoulders"] = shoulders
    chest = sphere("Chest", 1.0, (0, 0.05, HEAD_Z - 2.05),
                   (0.82, 0.40, 0.42), seg=40, rings=20)
    parts["chest"] = chest
    pedestal = cylinder("Pedestal", 0.60, 0.24, (0, 0, 0.12), verts=48)
    bevel(pedestal, 0.035, 3, 0.4)
    parts["pedestal"] = pedestal

    # eyes embedded
    for side in (-1, 1):
        ex = side * 0.26
        ez = HEAD_Z + RZ * 0.10
        parts["eye_%d" % side] = sphere("Eye_%d" % side, 0.095,
                                        (ex, -0.590, ez), (1, 0.8, 1),
                                        seg=32, rings=16)
        parts["iris_%d" % side] = sphere("Iris_%d" % side, 0.044,
                                         (ex, -0.675, ez), (1, 0.4, 1),
                                         seg=24, rings=12)
        parts["pupil_%d" % side] = sphere("Pupil_%d" % side, 0.021,
                                          (ex, -0.692, ez), (1, 0.35, 1),
                                          seg=16, rings=8)
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

    mouth_z = HEAD_Z - RZ * 0.41
    parts["upper_lip"] = sphere("Upper_Lip", 0.135,
                                (0, -0.765, mouth_z + 0.014),
                                (1.05, 0.30, 0.20), seg=32, rings=16)
    parts["lower_lip"] = sphere("Lower_Lip", 0.140,
                                (0, -0.762, mouth_z - 0.036),
                                (1.0, 0.30, 0.22), seg=32, rings=16)

    for side in (-1, 1):
        parts["ear_%d" % side] = sphere("Ear_%d" % side, 0.17,
                                        (side * 0.68, 0.02, HEAD_Z - 0.06),
                                        (0.30, 0.72, 1.10), seg=24, rings=12)
        parts["helix_%d" % side] = tube("Helix_%d" % side, [
            (side * 0.72, -0.03, HEAD_Z + 0.10),
            (side * 0.75, -0.10, HEAD_Z - 0.02),
            (side * 0.72, -0.04, HEAD_Z - 0.15),
        ], 0.013)

    hair = build_hair_cap()
    parts["hair"] = hair

    return parts


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
    parts = build_sculpt()
    save("03_topology.blend")

    skin = skin_material()
    hair_mat = simple_mat("Hair_DarkBrown", (0.055, 0.032, 0.020, 1.0),
                          0.44, noise_scale=100.0, strength=0.10)
    sclera = simple_mat("Eye_Sclera", (0.90, 0.89, 0.86, 1.0), 0.16, coat=0.35)
    iris_mat = simple_mat("Eye_Iris", (0.10, 0.19, 0.26, 1.0), 0.22, coat=0.45)
    pupil_mat = simple_mat("Eye_Pupil", (0.008, 0.008, 0.012, 1.0), 0.10)
    lip_mat = simple_mat("Lips_Real", (0.50, 0.25, 0.23, 1.0), 0.42,
                         subsurface=0.12)
    brow_mat = simple_mat("Brows", (0.09, 0.055, 0.035, 1.0), 0.72)
    bust_mat = simple_mat("Bust_Stone", (0.28, 0.29, 0.31, 1.0), 0.64,
                          noise_scale=70.0, strength=0.08)
    pedestal_mat = simple_mat("Pedestal_Dark", (0.09, 0.10, 0.11, 1.0),
                              0.48, metal=0.25, noise_scale=80.0, strength=0.06)

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
        elif key.startswith("ear") or key.startswith("helix"):
            assign_mat(obj, skin)
        elif key == "hair":
            assign_mat(obj, hair_mat)
        elif key.startswith("strand_"):
            assign_mat(obj, hair_mat)
    save("04_material.blend")

    setup_world()
    add_area("Key_Light", (-2.4, -3.4, 5.0), 460.0, 3.5, (1.0, 0.94, 0.88))
    add_area("Fill_Light", (3.4, -1.8, 2.6), 190.0, 4.5, (0.82, 0.89, 1.0))
    add_area("Rim_Light", (1.0, 3.4, 4.0), 400.0, 3.0, (1.0, 0.94, 0.88))
    add_camera()
    save("05_lighting.blend")

    setup_render(scene)
    scene.render.filepath = os.path.join(OUT, "final.png")
    bpy.ops.render.render(write_still=True)
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
