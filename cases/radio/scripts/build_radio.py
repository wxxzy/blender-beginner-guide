# -*- coding: utf-8 -*-
"""复古收音机（硬表面写实）：Blender 5.2 内置功能六阶段教学工程。
运行： blender -b -P build_radio.py
产物： 01~06 阶段 .blend 快照、reference_radio.png、final.png
"""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))

BODY_W, BODY_D, BODY_Z = 3.4, 1.3, 0.12
FRONT_Y = -BODY_D / 2.0


def log(msg):
    print("[RADIO] " + str(msg), flush=True)


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


def apply_mod(obj, mod):
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)



def assign_mat(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

# ---------------------------------------------------------------------------
# Stage 1 : reference
# ---------------------------------------------------------------------------

def make_reference_image():
    w, h = 640, 420
    px = np.zeros((h, w, 4), dtype=np.float32)
    px[..., :3] = (0.94, 0.93, 0.90)
    px[..., 3] = 1.0

    def rect(x0, y0, x1, y1, color):
        px[max(0, y0):min(h, y1), max(0, x0):min(w, x1), :3] = color

    dark = (0.25, 0.22, 0.20)
    rect(70, 60, 570, 350, dark)
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy, r = 235, 205, 100
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
    px[mask, :3] = (0.35, 0.32, 0.29)
    rect(370, 150, 545, 215, (0.40, 0.38, 0.34))
    for kx in (405, 500):
        m = (xx - kx) ** 2 + (yy - 285) ** 2 < 26 * 26
        px[m, :3] = (0.55, 0.45, 0.22)
    for gx in (70 + (570 - 70) // 2,):
        rect(gx, 50, gx + 2, 360, (0.62, 0.20, 0.18))
    rect(60, 205, 580, 207, (0.62, 0.20, 0.18))

    img = bpy.data.images.new("RadioRef", width=w, height=h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_radio.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
    emp = bpy.context.object
    emp.data = img
    emp.empty_display_size = 3.6
    emp.empty_image_depth = "FRONT"
    emp.name = "REF_Radio_Proportion"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def cube(name, dims, loc, mat=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.append(mat)
    return obj


def cylinder(name, radius, depth, loc, rot=(0, 0, 0), verts=48, mat=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius,
                                        depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    return obj


def bevel(obj, width, segments=3, angle=0.35):
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
        mod.weight = 40
    except Exception as exc:
        log("weighted normal skipped: %s" % exc)


def boolean_cut(target, cutter):
    mod = target.modifiers.new("Cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    mod.object = cutter
    apply_mod(target, mod)
    bpy.data.objects.remove(cutter, do_unlink=True)
    while len(target.data.materials) and target.data.materials[0] is None:
        target.data.materials.pop(index=0)


def text_obj(name, body, size, loc, mat, align="CENTER"):
    cu = bpy.data.curves.new(name + "Curve", "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.extrude = 0.002
    obj = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.pi / 2.0, 0, 0)
    obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def color_ramp(nt, stops, loc):
    node = nt.nodes.new("ShaderNodeValToRGB")
    node.location = loc
    ramp = node.color_ramp
    while len(ramp.elements) > 1:
        ramp.elements.remove(ramp.elements[-1])
    ramp.elements[0].position = stops[0][0]
    ramp.elements[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = ramp.elements.new(pos)
        e.color = col
    return node


def simple_mat(name, base, rough, metal=0.0, noise_scale=None, strength=0.1):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
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
        bump.inputs["Distance"].default_value = 0.008
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wood_material():
    mat = bpy.data.materials.new("Walnut_Wood")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, 0)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-720, 0)
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.4)
    nt.links.new(tc.outputs["Generated"], mapping.inputs["Vector"])

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-540, 160)
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 3.0
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])

    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = (-540, -60)
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 7.0
    wave.inputs["Distortion"].default_value = 4.0
    wave.inputs["Detail"].default_value = 2.0
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])

    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.location = (-320, 60)
    mix.inputs[1].default_value = 0.35
    mix.inputs[2].default_value = 0.32
    nt.links.new(wave.outputs["Fac"], mix.inputs[0])

    ramp = color_ramp(nt, [
        (0.0, (0.16, 0.07, 0.035, 1.0)),
        (0.45, (0.30, 0.14, 0.065, 1.0)),
        (0.75, (0.42, 0.22, 0.10, 1.0)),
        (1.0, (0.24, 0.10, 0.045, 1.0)),
    ], (-120, 80))
    nt.links.new(mix.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-120, -160)
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.006
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Roughness"].default_value = 0.42
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.18
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = 0.32
    return mat


def grille_material():
    mat = bpy.data.materials.new("Speaker_Cloth")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.075, 0.065, 0.055, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.92
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-700, 0)
    wave_a = nt.nodes.new("ShaderNodeTexWave")
    wave_a.location = (-500, 100)
    wave_a.wave_type = "BANDS"
    wave_a.bands_direction = "X"
    wave_a.inputs["Scale"].default_value = 70.0
    nt.links.new(tc.outputs["Generated"], wave_a.inputs["Vector"])
    wave_b = nt.nodes.new("ShaderNodeTexWave")
    wave_b.location = (-500, -120)
    wave_b.wave_type = "BANDS"
    wave_b.bands_direction = "Z"
    wave_b.inputs["Scale"].default_value = 70.0
    nt.links.new(tc.outputs["Generated"], wave_b.inputs["Vector"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.location = (-280, 0)
    nt.links.new(wave_a.outputs["Fac"], mul.inputs[0])
    nt.links.new(wave_b.outputs["Fac"], mul.inputs[1])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-80, 0)
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(mul.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def glass_material():
    mat = bpy.data.materials.new("Dial_Glass")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.85, 0.90, 0.92, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["IOR"].default_value = 1.46
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.72
    return mat


# ---------------------------------------------------------------------------
# Stage 2 : blockout
# ---------------------------------------------------------------------------

def build_blockout():
    cube("BLK_Body", (BODY_W, BODY_D, 2.1), (0, 0, BODY_Z + 1.05))
    cube("BLK_FrontPanel", (BODY_W - 0.2, 0.08, 1.9),
         (0, FRONT_Y - 0.04, BODY_Z + 1.05))
    cylinder("BLK_Speaker", 0.62, 0.04,
             (-0.85, FRONT_Y - 0.08, BODY_Z + 1.15), (math.pi / 2, 0, 0), 32)
    cube("BLK_Dial", (1.25, 0.04, 0.5),
         (0.80, FRONT_Y - 0.08, BODY_Z + 1.35))
    for i, x in enumerate((0.42, 1.22)):
        cylinder("BLK_Knob_%d" % i, 0.17, 0.14,
                 (x, FRONT_Y - 0.14, BODY_Z + 0.55), (math.pi / 2, 0, 0), 32)


# ---------------------------------------------------------------------------
# Stage 3 : detailed geometry
# ---------------------------------------------------------------------------

def build_detailed():
    mats = {}

    body = cube("Radio_Body", (BODY_W, BODY_D, 2.1), (0, 0, BODY_Z + 1.05))
    bevel(body, 0.10, 4, 0.3)
    weighted_normal(body)
    mats["body"] = body

    panel = cube("Front_Panel", (BODY_W - 0.16, 0.10, 1.92),
                 (0, FRONT_Y - 0.05, BODY_Z + 1.05))
    # circular speaker hole
    cut_spk = cylinder("TMP_SpeakerCut", 0.60, 0.4,
                       (-0.85, FRONT_Y - 0.05, BODY_Z + 1.15),
                       (math.pi / 2, 0, 0), 64)
    boolean_cut(panel, cut_spk)
    # rectangular dial hole
    cut_dial = cube("TMP_DialCut", (1.20, 0.4, 0.44),
                    (0.80, FRONT_Y - 0.05, BODY_Z + 1.35))
    boolean_cut(panel, cut_dial)
    bevel(panel, 0.02, 2, 0.5)
    weighted_normal(panel)
    mats["panel"] = panel

    # speaker recess + cloth
    cloth = cylinder("Speaker_Cloth", 0.59, 0.03,
                     (-0.85, FRONT_Y - 0.115, BODY_Z + 1.15),
                     (math.pi / 2, 0, 0), 64)
    mats["cloth"] = cloth

    ring = bpy.data.curves.new("GrilleRing", "CURVE")
    ring.dimensions = "3D"
    ring.bevel_depth = 0.022
    ring.bevel_resolution = 3
    spline = ring.splines.new("POLY")
    spline.points.add(63)
    for i, p in enumerate(spline.points):
        a = 2.0 * math.pi * i / 64.0
        p.co = (-0.85 + 0.605 * math.cos(a),
                FRONT_Y - 0.085,
                BODY_Z + 1.15 + 0.605 * math.sin(a), 1.0)
    spline.use_cyclic_u = True
    ring_obj = bpy.data.objects.new("Grille_Ring", ring)
    bpy.context.collection.objects.link(ring_obj)
    mats["ring"] = ring_obj

    # dial face, ticks, numbers, needle, glass
    dial = cube("Dial_Face", (1.16, 0.03, 0.40),
                (0.80, FRONT_Y - 0.055, BODY_Z + 1.35))
    mats["dial"] = dial
    ticks = []
    for i in range(11):
        x = 0.80 - 0.50 + i * 0.10
        t = cube("Dial_Tick_%02d" % i, (0.012, 0.012, 0.07 if i % 5 == 0 else 0.04),
                 (x, FRONT_Y - 0.105, BODY_Z + 1.35))
        ticks.append(t)
    for i, label in enumerate(("88", "94", "100", "106", "118")):
        text_obj("Dial_Num_%d" % i, label, 0.075,
                 (0.33 + i * 0.235, FRONT_Y - 0.11, BODY_Z + 1.20),
                 None, "CENTER")
    needle = cube("Dial_Needle", (0.018, 0.012, 0.30),
                  (0.98, FRONT_Y - 0.112, BODY_Z + 1.35))
    mats["needle"] = needle
    glass = cube("Dial_Glass", (1.18, 0.012, 0.42),
                 (0.80, FRONT_Y - 0.095, BODY_Z + 1.35))
    mats["glass"] = glass

    # knobs with knurling
    for i, x in enumerate((0.42, 1.22)):
        base = cylinder("Knob_Base_%d" % i, 0.20, 0.06,
                        (x, FRONT_Y - 0.10, BODY_Z + 0.55),
                        (math.pi / 2, 0, 0), 48)
        knob = cylinder("Knob_%d" % i, 0.165, 0.16,
                        (x, FRONT_Y - 0.20, BODY_Z + 0.55),
                        (math.pi / 2, 0, 0), 48)
        bevel(knob, 0.02, 3, 0.4)
        weighted_normal(knob)
        mats["knob_%d" % i] = knob
        cap = cylinder("Knob_Cap_%d" % i, 0.07, 0.175,
                       (x, FRONT_Y - 0.205, BODY_Z + 0.55),
                       (math.pi / 2, 0, 0), 32)
        mats["cap_%d" % i] = cap
        for k in range(24):
            a = 2.0 * math.pi * k / 24.0
            tooth = cube("Knurl_%d_%02d" % (i, k), (0.022, 0.14, 0.022),
                         (x + 0.163 * math.cos(a),
                          FRONT_Y - 0.20,
                          BODY_Z + 0.55 + 0.163 * math.sin(a)))
            tooth.rotation_euler[1] = -a

    # carrying handle (bezier curve)
    handle = bpy.data.curves.new("HandleCurve", "CURVE")
    handle.dimensions = "3D"
    handle.bevel_depth = 0.045
    handle.bevel_resolution = 4
    spline = handle.splines.new("BEZIER")
    spline.bezier_points.add(4)
    points = [(-0.75, 0, 2.17), (-0.45, 0, 2.44), (0, 0, 2.52),
              (0.45, 0, 2.44), (0.75, 0, 2.17)]
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    handle_obj = bpy.data.objects.new("Carry_Handle", handle)
    bpy.context.collection.objects.link(handle_obj)
    for x in (-0.75, 0.75):
        mount = cylinder("Handle_Mount_%s" % x, 0.07, 0.06,
                         (x, 0, 2.16), (0, 0, 0), 24)
        mats["mount_%s" % x] = mount

    # feet
    for x in (-1.35, 1.35):
        for y in (-0.45, 0.45):
            foot = cylinder("Foot_%s_%s" % (x, y), 0.10, 0.12,
                            (x, y, 0.06), (0, 0, 0), 24)
            bevel(foot, 0.02, 2, 0.4)
            mats["foot_%s_%s" % (x, y)] = foot

    # brand plate and text
    plate = cube("Brand_Plate", (0.90, 0.02, 0.20),
                 (0.80, FRONT_Y - 0.07, BODY_Z + 0.90))
    mats["plate"] = plate
    text_obj("Brand_Text", "AUREX 1948", 0.11,
             (0.80, FRONT_Y - 0.09, BODY_Z + 0.86), None, "CENTER")

    # four corner screws
    for sx in (-1, 1):
        for sz in (-1, 1):
            screw = cylinder("Screw_%s_%s" % (sx, sz), 0.035, 0.02,
                             (sx * 1.52, FRONT_Y - 0.11,
                              BODY_Z + 1.05 + sz * 0.84),
                             (math.pi / 2, 0, 0), 16)
            mats["screw_%s_%s" % (sx, sz)] = screw

    return mats


# ---------------------------------------------------------------------------
# Lighting and render
# ---------------------------------------------------------------------------

def add_area(name, loc, energy, size, color, target=(0, 0, 0.62)):
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
    bg.inputs["Color"].default_value = (0.16, 0.17, 0.19, 1.0)
    bg.inputs["Strength"].default_value = 0.55


def add_camera():
    data = bpy.data.cameras.new("CameraLens")
    data.lens = 58.0
    obj = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(obj)
    obj.location = (4.6, -7.4, 2.6)
    direction = Vector((0, 0, 0.62)) - obj.location
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
    scene.view_settings.exposure = -0.25
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
    mats = build_detailed()
    save("03_topology.blend")

    wood = wood_material()
    panel_mat = simple_mat("Panel_Bakelite", (0.055, 0.05, 0.045, 1.0),
                           0.40, noise_scale=120.0, strength=0.08)
    cloth = grille_material()
    brass = simple_mat("Aged_Brass", (0.66, 0.48, 0.20, 1.0), 0.32,
                       metal=0.82, noise_scale=90.0, strength=0.08)
    dial_mat = simple_mat("Dial_Cream", (0.86, 0.82, 0.68, 1.0), 0.68)
    ink = simple_mat("Dial_Ink", (0.03, 0.03, 0.03, 1.0), 0.8)
    red = simple_mat("Needle_Red", (0.65, 0.06, 0.04, 1.0), 0.45)
    rubber = simple_mat("Rubber_Foot", (0.035, 0.035, 0.035, 1.0),
                        0.88, noise_scale=60.0, strength=0.2)

    assign_mat(mats["body"], wood)
    assign_mat(mats["panel"], panel_mat)
    assign_mat(mats["cloth"], cloth)
    assign_mat(mats["ring"], brass)
    assign_mat(mats["dial"], dial_mat)
    for obj in bpy.data.objects:
        if obj.name.startswith("Dial_Tick") or obj.name.startswith("Dial_Num"):
            obj.data.materials.append(ink)
    assign_mat(mats["needle"], red)
    mats["glass"].data.materials.append(glass_material())
    for i in (0, 1):
        assign_mat(mats["knob_%d" % i], brass)
        assign_mat(mats["cap_%d" % i], panel_mat)
        for obj in bpy.data.objects:
            if obj.name.startswith("Knurl_%d_" % i):
                obj.data.materials.append(brass)
    for key, obj in mats.items():
        if key.startswith("mount_"):
            obj.data.materials.append(brass)
        elif key.startswith("foot_"):
            obj.data.materials.append(rubber)
        elif key.startswith("screw_"):
            obj.data.materials.append(brass)
    assign_mat(mats["plate"], brass)
    for obj in bpy.data.objects:
        if obj.name == "Brand_Text":
            obj.data.materials.append(ink)
    assign_mat(bpy.data.objects["Carry_Handle"], brass)

    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    assign_mat(ground, simple_mat("Ground_Charcoal", (0.085, 0.085, 0.09, 1.0),
                                  0.72, noise_scale=35.0, strength=0.08))
    save("04_material.blend")

    setup_world()
    add_area("Key_Light", (-3.4, -4.2, 5.6), 460.0, 4.0, (1.0, 0.94, 0.86))
    add_area("Fill_Light", (4.4, -2.0, 2.6), 180.0, 5.0, (0.78, 0.86, 1.0))
    add_area("Rim_Light", (1.2, 4.2, 4.6), 360.0, 3.0, (1.0, 0.95, 0.88))
    add_camera()
    save("05_lighting.blend")

    setup_render(scene)
    scene.render.filepath = os.path.join(OUT, "final.png")
    bpy.ops.render.render(write_still=True)
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
