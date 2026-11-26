# -*- coding: utf-8 -*-
"""六轴机械臂：Blender 5.2 内置功能六阶段教学工程。
运行： blender -b -P build_arm.py
"""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))


def log(msg):
    print("[ARM] " + str(msg), flush=True)


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
    w, h = 512, 512
    px = np.zeros((h, w, 4), dtype=np.float32)
    px[..., :3] = (0.93, 0.93, 0.92)
    px[..., 3] = 1.0
    yy, xx = np.mgrid[0:h, 0:w]

    def line(p0, p1, color, width=5):
        x0, y0 = p0
        x1, y1 = p1
        for t in np.linspace(0, 1, 300):
            bx = x0 + (x1 - x0) * t
            by = y0 + (y1 - y0) * t
            m = (xx - bx) ** 2 + (yy - by) ** 2 < width * width
            px[m, :3] = color

    def disc(c, r, color):
        m = (xx - c[0]) ** 2 + (yy - c[1]) ** 2 < r * r
        px[m, :3] = color

    dark = (0.18, 0.20, 0.22)
    line((256, 460), (256, 400), dark, 8)
    disc((256, 400), 62, (0.30, 0.32, 0.35))
    disc((256, 400), 22, dark)
    line((256, 380), (150, 240), dark, 16)
    disc((150, 240), 26, (0.85, 0.45, 0.10))
    line((150, 240), (300, 120), dark, 13)
    disc((300, 120), 22, (0.85, 0.45, 0.10))
    line((300, 120), (350, 175), dark, 9)
    line((340, 165), (388, 195), dark, 6)
    line((340, 165), (388, 140), dark, 6)
    for c in ((256, 400), (150, 240), (300, 120)):
        m = (xx - c[0]) ** 2 + (yy - c[1]) ** 2 < 6 * 6
        px[m, :3] = (0.10, 0.55, 0.85)

    img = bpy.data.images.new("ArmRef", width=w, height=h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_arm.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
    emp = bpy.context.object
    emp.data = img
    emp.empty_display_size = 3.2
    emp.empty_image_depth = "FRONT"
    emp.name = "REF_Arm_Profile"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def sphere(name, radius, loc, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12,
                                         radius=radius, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def joint(name, loc, parent=None, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.empty_display_type = "CIRCLE"
    obj.empty_display_size = 0.18
    obj.location = loc
    obj.rotation_euler = rot
    if parent:
        obj.parent = parent
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


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

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
        bump.inputs["Distance"].default_value = 0.006
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def emissive_mat(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.01, 0.01, 0.01, 1.0)
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = strength
    else:
        bsdf.inputs["Emission"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


# ---------------------------------------------------------------------------
# Stage 2 : blockout
# ---------------------------------------------------------------------------

def build_blockout():
    cube("BLK_Base", (1.2, 1.2, 0.3), (0, 0, 0.15))
    cylinder("BLK_Turret", 0.42, 0.4, (0, 0, 0.5))
    cube("BLK_Upper", (0.34, 0.34, 1.4), (0, 0, 1.25), (0, -0.45, 0))
    cube("BLK_Fore", (0.28, 0.28, 1.15), (-0.55, 0, 2.35), (0, 0.35, 0))
    cube("BLK_Gripper", (0.3, 0.3, 0.35), (-0.85, 0, 2.85))


# ---------------------------------------------------------------------------
# Stage 3 : detailed hierarchy
# ---------------------------------------------------------------------------

def build_detailed():
    parts = {}
    joints = {}

    # ---- fixed base ----
    base = cylinder("Base_Plate", 0.62, 0.22, (0, 0, 0.11), verts=48)
    bevel(base, 0.035, 3, 0.35)
    weighted_normal(base)
    parts["base"] = base

    collar = cylinder("Base_Collar", 0.40, 0.14, (0, 0, 0.29), verts=48)
    bevel(collar, 0.025, 2, 0.4)
    parts["collar"] = collar

    for i in range(8):
        a = 2 * math.pi * i / 8
        bolt = cylinder("Base_Bolt_%d" % i, 0.045, 0.05,
                        (0.50 * math.cos(a), 0.50 * math.sin(a), 0.235),
                        verts=16)
        parts["bolt_%d" % i] = bolt

    # ---- J1 : turret yaw around Z ----
    j1 = joint("J1_Turret", (0, 0, 0.36))
    joints["j1"] = j1

    turret = cylinder("Turret", 0.36, 0.38, (0, 0, 0.19))
    bevel(turret, 0.04, 3, 0.35)
    weighted_normal(turret)
    turret.parent = j1
    parts["turret"] = turret

    shoulder_yoke = cube("Shoulder_Yoke", (0.52, 0.44, 0.30), (0, 0, 0.44))
    bevel(shoulder_yoke, 0.04, 3, 0.35)
    shoulder_yoke.parent = j1
    parts["yoke"] = shoulder_yoke

    # ---- J2 : shoulder pitch around X ----
    j2 = joint("J2_Shoulder", (0, 0, 0.52), j1, (math.radians(-38), 0, 0))
    joints["j2"] = j2

    sh = cylinder("Shoulder_Pin", 0.23, 0.50, (0, 0, 0), verts=40,
                  rot=(math.pi / 2, 0, 0))
    sh.parent = j2
    parts["shoulder_pin"] = sh

    upper = cube("Upper_Arm", (0.30, 0.34, 1.35), (0, 0, 0.72))
    bevel(upper, 0.045, 3, 0.35)
    weighted_normal(upper)
    upper.parent = j2
    parts["upper"] = upper

    upper_cap = cylinder("Upper_Cap", 0.17, 0.12, (0, 0, 1.38), verts=32)
    upper_cap.parent = j2
    parts["upper_cap"] = upper_cap

    # hydraulic ram alongside upper arm
    ram = cylinder("Hydraulic_Ram", 0.075, 0.95, (0.22, -0.02, 0.62), verts=24)
    ram.parent = j2
    parts["ram"] = ram
    ram_rod = cylinder("Hydraulic_Rod", 0.038, 0.55, (0.22, -0.02, 1.28),
                       verts=20)
    ram_rod.parent = j2
    parts["ram_rod"] = ram_rod

    # ---- J3 : elbow pitch around X ----
    j3 = joint("J3_Elbow", (0, 0, 1.40), j2, (math.radians(72), 0, 0))
    joints["j3"] = j3

    elbow = cylinder("Elbow_Pin", 0.19, 0.42, (0, 0, 0), verts=40,
                     rot=(math.pi / 2, 0, 0))
    elbow.parent = j3
    parts["elbow_pin"] = elbow

    fore = cube("Forearm", (0.25, 0.28, 1.05), (0, 0, 0.55))
    bevel(fore, 0.035, 3, 0.35)
    weighted_normal(fore)
    fore.parent = j3
    parts["forearm"] = fore

    fore_ram = cylinder("Forearm_Ram", 0.055, 0.70, (0.17, 0, 0.48), verts=20)
    fore_ram.parent = j3
    parts["fore_ram"] = fore_ram

    # ---- J4 : wrist roll around Z ----
    j4 = joint("J4_Wrist_Roll", (0, 0, 1.10), j3)
    joints["j4"] = j4

    wrist = cylinder("Wrist_Housing", 0.15, 0.26, (0, 0, 0.08), verts=32)
    bevel(wrist, 0.02, 2, 0.4)
    wrist.parent = j4
    parts["wrist"] = wrist

    # ---- J5 : wrist pitch ----
    j5 = joint("J5_Wrist_Pitch", (0, 0, 0.22), j4, (math.radians(-34), 0, 0))
    joints["j5"] = j5

    tool = cube("Tool_Flange", (0.24, 0.24, 0.16), (0, 0, 0.08))
    bevel(tool, 0.02, 2, 0.4)
    tool.parent = j5
    parts["tool"] = tool

    # ---- J6 : tool roll + gripper ----
    j6 = joint("J6_Tool_Roll", (0, 0, 0.18), j5)
    joints["j6"] = j6

    grip_base = cylinder("Gripper_Base", 0.14, 0.16, (0, 0, 0.06), verts=24)
    grip_base.parent = j6
    parts["grip_base"] = grip_base

    for side in (-1, 1):
        finger = cube("Finger_%d" % side, (0.07, 0.11, 0.34),
                      (side * 0.13, 0, 0.27))
        bevel(finger, 0.015, 2, 0.4)
        finger.parent = j6
        parts["finger_%d" % side] = finger
        pad = cube("Finger_Pad_%d" % side, (0.025, 0.13, 0.24),
                   (side * 0.085, 0, 0.30))
        pad.parent = j6
        parts["pad_%d" % side] = pad

    # sensor LED at wrist
    led = sphere("Status_LED", 0.045, (0, 0.16, 0.10), (1, 0.5, 1))
    led.parent = j5
    parts["led"] = led

    # cable bundle: build in world space after posing
    bpy.context.view_layer.update()
    world = {k: v.matrix_world.translation.copy() for k, v in joints.items()}
    pts = [Vector((0.18, -0.20, 0.55)),
           world["j1"] + Vector((0.22, -0.22, 0.20)),
           world["j2"] + Vector((0.24, -0.24, 0.0)),
           world["j3"] + Vector((0.22, -0.20, 0.0)),
           world["j5"] + Vector((0.14, -0.12, 0.0))]
    cu = bpy.data.curves.new("CableCurve", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.028
    cu.bevel_resolution = 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    cable = bpy.data.objects.new("Cable_Bundle", cu)
    bpy.context.collection.objects.link(cable)
    parts["cable"] = cable

    return parts, joints


# ---------------------------------------------------------------------------
# Lighting / camera / compositor
# ---------------------------------------------------------------------------

def add_area(name, loc, energy, size, color, target=(0, 0, 1.7)):
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
    bg.inputs["Color"].default_value = (0.14, 0.15, 0.17, 1.0)
    bg.inputs["Strength"].default_value = 0.55


def add_camera():
    data = bpy.data.cameras.new("CameraLens")
    data.lens = 50.0
    obj = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(obj)
    obj.location = (5.6, -7.6, 4.3)
    direction = Vector((0, 0, 1.85)) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = obj
    return obj


def setup_compositor(scene):
    ng = bpy.data.node_groups.new("ArmComp", "CompositorNodeTree")
    scene.compositing_node_group = ng
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.location = (-800, 0)
    glare = ng.nodes.new("CompositorNodeGlare")
    glare.location = (-560, 0)
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 0.9
    glare.inputs["Strength"].default_value = 0.35
    glare.inputs["Size"].default_value = 0.5
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    out = ng.nodes.new("NodeGroupOutput")
    out.location = (-280, 0)
    ng.links.new(glare.outputs["Image"], out.inputs["Image"])


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
    setup_compositor(scene)


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
    parts, joints = build_detailed()
    save("03_topology.blend")

    white = simple_mat("Industrial_White", (0.72, 0.74, 0.75, 1.0), 0.40,
                       noise_scale=90.0, strength=0.06)
    dark = simple_mat("Joint_Dark", (0.07, 0.08, 0.09, 1.0), 0.42,
                      metal=0.35, noise_scale=80.0, strength=0.08)
    steel = simple_mat("Brushed_Steel", (0.48, 0.51, 0.54, 1.0), 0.30,
                       metal=0.88, noise_scale=120.0, strength=0.05)
    orange = simple_mat("Safety_Orange", (0.92, 0.38, 0.06, 1.0), 0.46)
    rubber = simple_mat("Gripper_Rubber", (0.025, 0.025, 0.03, 1.0), 0.88)
    cable_mat = simple_mat("Cable_Jacket", (0.035, 0.04, 0.05, 1.0), 0.65)
    led_mat = emissive_mat("Status_Cyan", (0.05, 0.70, 1.0, 1.0), 3.5)

    assign_mat(parts["base"], dark)
    assign_mat(parts["collar"], steel)
    for key, obj in parts.items():
        if key.startswith("bolt_"):
            assign_mat(obj, steel)
        elif key in ("turret", "yoke", "upper", "forearm", "tool"):
            assign_mat(obj, white)
        elif key in ("elbow_pin", "upper_cap", "wrist",
                     "grip_base", "ram_rod"):
            assign_mat(obj, steel)
        elif key in ("ram", "fore_ram"):
            assign_mat(obj, orange)
        elif key.startswith("finger_") and "pad" not in key:
            assign_mat(obj, steel)
        elif key.startswith("pad_"):
            assign_mat(obj, rubber)
    assign_mat(parts["shoulder_pin"], dark)
    assign_mat(parts["led"], led_mat)
    assign_mat(parts["cable"], cable_mat)

    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    assign_mat(ground, simple_mat("Ground_Charcoal", (0.085, 0.085, 0.09, 1.0),
                                  0.72, noise_scale=35.0, strength=0.08))
    save("04_material.blend")

    setup_world()
    add_area("Key_Light", (-3.6, -4.2, 5.8), 560.0, 4.0, (1.0, 0.95, 0.88))
    add_area("Fill_Light", (4.4, -2.0, 2.6), 220.0, 5.0, (0.78, 0.88, 1.0))
    add_area("Rim_Light", (1.4, 4.4, 4.6), 480.0, 3.0, (1.0, 0.93, 0.86))
    add_camera()
    save("05_lighting.blend")

    setup_render(scene)
    scene.render.filepath = os.path.join(OUT, "final.png")
    bpy.ops.render.render(write_still=True)
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
