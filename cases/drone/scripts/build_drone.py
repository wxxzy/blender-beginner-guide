# -*- coding: utf-8 -*-
"""科幻四轴无人机：Blender 5.2 内置功能六阶段教学工程。
运行： blender -b -P build_drone.py
"""
import bpy
import math
import os
import numpy as np
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))
BODY_Z = 1.55
ARM_ANGLES = (45, 135, 225, 315)


def log(msg):
    print("[DRONE] " + str(msg), flush=True)


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
# Stage 1
# ---------------------------------------------------------------------------

def make_reference_image():
    w, h = 512, 512
    px = np.zeros((h, w, 4), dtype=np.float32)
    px[..., :3] = (0.93, 0.94, 0.95)
    px[..., 3] = 1.0
    yy, xx = np.mgrid[0:h, 0:w]
    cx = cy = 256.0

    def ring(r0, r1, color):
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        m = (d2 > r0 * r0) & (d2 < r1 * r1)
        px[m, :3] = color

    ring(150, 156, (0.20, 0.55, 0.78))
    for a in ARM_ANGLES:
        t = math.radians(a)
        for r0, r1 in ((50, 150), (160, 175)):
            mx = cx + (r0 + r1) / 2 * math.cos(t)
            my = cy - (r0 + r1) / 2 * math.sin(t)
            d2 = (xx - mx) ** 2 + (yy - my) ** 2
            m = d2 < 12 * 12
            px[m, :3] = (0.22, 0.24, 0.27)
        dx, dy = math.cos(t), -math.sin(t)
        nx, ny = -dy, dx
        for r in (45, 205):
            for L in np.linspace(-30, 30, 40):
                bx = cx + dx * r + nx * L
                by = cy + dy * r + ny * L
                m = (xx - bx) ** 2 + (yy - by) ** 2 < 6 * 6
                px[m, :3] = (0.15, 0.17, 0.20)
    m = (xx - cx) ** 2 + (yy - cy) ** 2 < 46 * 46
    px[m, :3] = (0.25, 0.28, 0.33)
    px[250:262, 180:332, :3] = (0.45, 0.48, 0.52)

    img = bpy.data.images.new("DroneRef", width=w, height=h, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_drone.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
    emp = bpy.context.object
    emp.data = img
    emp.empty_display_size = 4.0
    emp.empty_image_depth = "FRONT"
    emp.name = "REF_Drone_TopView"


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


def cylinder(name, radius, depth, loc, verts=32, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius,
                                        depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    return obj


def sphere(name, radius, loc, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16,
                                         radius=radius, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for p in obj.data.polygons:
        p.use_smooth = True
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
        mod.weight = 40
    except Exception as exc:
        log("weighted normal skipped: %s" % exc)


def mirror_x(obj):
    mod = obj.modifiers.new("MirrorX", "MIRROR")
    mod.use_axis[0] = True
    mod.use_axis[1] = False
    return mod


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
    bsdf.inputs["Roughness"].default_value = 0.3
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
    cube("BLK_Body", (1.0, 1.0, 0.35), (0, 0, BODY_Z))
    for i, a in enumerate(ARM_ANGLES):
        t = math.radians(a)
        arm = cube("BLK_Arm_%d" % i, (1.5, 0.2, 0.14),
                   (1.05 * math.cos(t), 1.05 * math.sin(t), BODY_Z),
                   (0, 0, t))
        motor = cylinder("BLK_Motor_%d" % i, 0.17, 0.2,
                         (1.75 * math.cos(t), 1.75 * math.sin(t), BODY_Z + 0.1))


# ---------------------------------------------------------------------------
# Stage 3 : detailed geometry
# ---------------------------------------------------------------------------

def build_detailed():
    parts = {}

    # central hull: beveled hexagonal prism -> sci-fi faceted body
    hull = cylinder("Main_Hull", 0.62, 0.34, (0, 0, BODY_Z), verts=6,
                    rot=(0, 0, math.radians(30)))
    bevel(hull, 0.06, 3, 0.3)
    weighted_normal(hull)
    parts["hull"] = hull

    upper = cylinder("Upper_Shell", 0.48, 0.22, (0, 0, BODY_Z + 0.26), verts=6,
                     rot=(0, 0, math.radians(30)))
    bevel(upper, 0.05, 3, 0.3)
    parts["upper"] = upper

    belly = sphere("Sensor_Dome", 0.30, (0, 0, BODY_Z - 0.24), (1, 1, 0.65))
    parts["belly"] = belly

    top = sphere("Top_Sensor", 0.16, (0, 0, BODY_Z + 0.44), (1, 1, 0.7))
    parts["top"] = top

    # four arms + motors + rotors, radial repeat
    for i, a in enumerate(ARM_ANGLES):
        t = math.radians(a)
        ax, ay = 1.02 * math.cos(t), 1.02 * math.sin(t)
        arm = cube("Arm_%d" % i, (1.45, 0.17, 0.13), (ax, ay, BODY_Z),
                   (0, 0, t))
        bevel(arm, 0.025, 2, 0.4)
        weighted_normal(arm)
        parts["arm_%d" % i] = arm

        mx, my = 1.72 * math.cos(t), 1.72 * math.sin(t)
        motor = cylinder("Motor_%d" % i, 0.16, 0.22,
                         (mx, my, BODY_Z + 0.10), verts=32)
        bevel(motor, 0.02, 2, 0.4)
        parts["motor_%d" % i] = motor

        cap = cylinder("Motor_Cap_%d" % i, 0.115, 0.03,
                       (mx, my, BODY_Z + 0.23), verts=32)
        parts["cap_%d" % i] = cap

        for b in (0, 1):
            blade = cube("Blade_%d_%d" % (i, b), (0.92, 0.11, 0.024),
                         (mx, my, BODY_Z + 0.28),
                         (0, 0, t + b * math.pi / 2 + math.radians(12)))
            parts["blade_%d_%d" % (i, b)] = blade
        hub = cylinder("Rotor_Hub_%d" % i, 0.06, 0.05,
                       (mx, my, BODY_Z + 0.30), verts=24)
        parts["hub_%d" % i] = hub

        # emissive strip on arm top
        led = cube("Arm_LED_%d" % i, (1.15, 0.04, 0.016),
                   (ax, ay, BODY_Z + 0.075), (0, 0, t))
        parts["arm_led_%d" % i] = led

    # emissive ring around hull
    ring_pts = []
    for k in range(48):
        ang = 2 * math.pi * k / 48
        ring_pts.append((0.60 * math.cos(ang), 0.60 * math.sin(ang),
                         BODY_Z - 0.05, 1.0))
    cu = bpy.data.curves.new("HullLEDCurve", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.014
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(ring_pts) - 1)
    for p, co in zip(sp.points, ring_pts):
        p.co = co
    sp.use_cyclic_u = True
    ring = bpy.data.objects.new("Hull_LED_Ring", cu)
    bpy.context.collection.objects.link(ring)
    parts["hull_led"] = ring

    # gimbal camera at front-bottom
    cam_ball = sphere("Gimbal_Ball", 0.17, (0, -0.52, BODY_Z - 0.24))
    parts["gimbal"] = cam_ball
    lens = cylinder("Camera_Lens", 0.10, 0.14,
                    (0, -0.68, BODY_Z - 0.24), verts=32,
                    rot=(math.pi / 2, 0, 0))
    parts["lens"] = lens
    lens_rim = cylinder("Lens_Rim", 0.115, 0.03,
                        (0, -0.75, BODY_Z - 0.24), verts=32,
                        rot=(math.pi / 2, 0, 0))
    parts["lens_rim"] = lens_rim

    # landing skids: two mirrored curved struts
    for side in (-1, 1):
        cu = bpy.data.curves.new("SkidCurve_%d" % side, "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.035
        cu.bevel_resolution = 3
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(3)
        coords = [(side * 0.34, -0.22, BODY_Z - 0.22),
                  (side * 0.48, -0.28, 0.55),
                  (side * 0.48, 0.28, 0.22),
                  (side * 0.34, 0.30, 0.20)]
        for bp, co in zip(sp.bezier_points, coords):
            bp.co = co
            bp.handle_left_type = "AUTO"
            bp.handle_right_type = "AUTO"
        skid = bpy.data.objects.new("Landing_Skid_%d" % side, cu)
        bpy.context.collection.objects.link(skid)
        parts["skid_%d" % side] = skid
        foot = cube("Skid_Foot_%d" % side, (0.10, 0.62, 0.06),
                    (side * 0.36, 0.02, 0.18))
        bevel(foot, 0.02, 2, 0.4)
        parts["foot_%d" % side] = foot

    # antenna
    ant = cylinder("Antenna", 0.012, 0.42,
                   (0.22, 0.18, BODY_Z + 0.52), verts=12)
    parts["antenna"] = ant
    tip = sphere("Antenna_Tip", 0.035, (0.22, 0.18, BODY_Z + 0.74))
    parts["ant_tip"] = tip

    # panel seams on upper shell
    for i in (-1, 1):
        seam = cube("Panel_Seam_%d" % i, (0.30, 0.02, 0.01),
                    (i * 0.18, -0.20, BODY_Z + 0.375))
        parts["seam_%d" % i] = seam

    return parts


# ---------------------------------------------------------------------------
# Lighting / camera / compositor
# ---------------------------------------------------------------------------

def add_area(name, loc, energy, size, color, target=(0, 0, BODY_Z)):
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
    world = bpy.data.worlds.new("NightStudio")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.055, 0.065, 0.085, 1.0)
    bg.inputs["Strength"].default_value = 0.5


def add_camera():
    data = bpy.data.cameras.new("CameraLens")
    data.lens = 55.0
    obj = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(obj)
    obj.location = (5.0, -6.8, 4.8)
    direction = Vector((0, 0, BODY_Z - 0.15)) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = obj
    return obj


def setup_compositor(scene):
    ng = bpy.data.node_groups.new("DroneComp", "CompositorNodeTree")
    scene.compositing_node_group = ng
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.location = (-800, 0)
    glare = ng.nodes.new("CompositorNodeGlare")
    glare.location = (-560, 0)
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 0.85
    glare.inputs["Smoothness"].default_value = 0.5
    glare.inputs["Strength"].default_value = 0.5
    glare.inputs["Size"].default_value = 0.55
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
    parts = build_detailed()
    save("03_topology.blend")

    carbon = simple_mat("Carbon_Composite", (0.055, 0.065, 0.075, 1.0),
                        0.38, metal=0.32, noise_scale=110.0, strength=0.12)
    gunmetal = simple_mat("Gunmetal", (0.22, 0.25, 0.28, 1.0), 0.32,
                          metal=0.82, noise_scale=80.0, strength=0.08)
    dark = simple_mat("Matte_Polymer", (0.035, 0.04, 0.045, 1.0), 0.55,
                      noise_scale=90.0, strength=0.08)
    blade_mat = simple_mat("Rotor_Blade", (0.09, 0.10, 0.11, 1.0), 0.42,
                           metal=0.25)
    lens_mat = simple_mat("Lens_Glass", (0.02, 0.03, 0.045, 1.0), 0.08,
                          metal=0.3)
    rubber = simple_mat("Skid_Rubber", (0.03, 0.03, 0.035, 1.0), 0.85)
    led_cyan = emissive_mat("LED_Cyan", (0.04, 0.62, 1.0, 1.0), 4.5)
    led_amber = emissive_mat("LED_Amber", (1.0, 0.45, 0.05, 1.0), 3.0)

    assign_mat(parts["hull"], carbon)
    assign_mat(parts["upper"], gunmetal)
    assign_mat(parts["belly"], dark)
    assign_mat(parts["top"], gunmetal)
    for key, obj in parts.items():
        if key.startswith("arm_") and not key.startswith("arm_led_"):
            assign_mat(obj, carbon)
        elif key.startswith("motor_") and not key.startswith("motor_cap"):
            assign_mat(obj, gunmetal)
        elif key.startswith("cap_"):
            assign_mat(obj, dark)
        elif key.startswith("blade_"):
            assign_mat(obj, blade_mat)
        elif key.startswith("hub_"):
            assign_mat(obj, gunmetal)
        elif key.startswith("arm_led_"):
            assign_mat(obj, led_cyan)
        elif key.startswith("skid_"):
            assign_mat(obj, gunmetal)
        elif key.startswith("foot_"):
            assign_mat(obj, rubber)
        elif key.startswith("seam_"):
            assign_mat(obj, dark)
    assign_mat(parts["hull_led"], led_cyan)
    assign_mat(parts["gimbal"], gunmetal)
    assign_mat(parts["lens"], lens_mat)
    assign_mat(parts["lens_rim"], gunmetal)
    assign_mat(parts["antenna"], dark)
    assign_mat(parts["ant_tip"], led_amber)

    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    assign_mat(ground, simple_mat("Ground_Charcoal", (0.055, 0.06, 0.07, 1.0),
                                  0.68, noise_scale=35.0, strength=0.08))
    save("04_material.blend")

    setup_world()
    add_area("Key_Light", (-3.6, -4.4, 5.8), 520.0, 4.0, (0.82, 0.90, 1.0))
    add_area("Fill_Light", (4.6, -1.8, 2.8), 200.0, 5.0, (0.60, 0.75, 1.0))
    add_area("Rim_Light", (1.4, 4.4, 4.8), 460.0, 3.0, (0.70, 0.88, 1.0))
    add_camera()
    save("05_lighting.blend")

    setup_render(scene)
    scene.render.filepath = os.path.join(OUT, "final.png")
    bpy.ops.render.render(write_still=True)
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
