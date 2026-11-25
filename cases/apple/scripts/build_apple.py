# -*- coding: utf-8 -*-
"""写实红苹果静物：Blender 5.2 内置功能六阶段教学工程。
运行： blender -b -P build_apple.py
产物： 01~06 阶段 .blend 快照、reference_apple.png、final.png
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

OUT = os.path.dirname(os.path.abspath(__file__))


def log(msg):
    print("[APPLE] " + str(msg), flush=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def save(name):
    path = os.path.join(OUT, name)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    log("saved " + path)


# ----------------------------------------------------------------------------
# Stage 1 : reference analysis
# ----------------------------------------------------------------------------

def make_reference_image():
    """Procedurally draw a proportion sheet, so no external asset is needed."""
    size = 512
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (xx / (size - 1) - 0.5) * 2.0
    v = 0.5 - yy / (size - 1)
    dx = u / 0.70
    dy = (v + 0.03) / 0.80
    d = dx * dx + dy * dy
    notch = np.where(v > 0.42, 0.42 * ((v - 0.42) / 0.58) ** 2, 0.0)
    inside = (d + notch) < 1.0

    px = np.zeros((size, size, 4), dtype=np.float32)
    px[..., :3] = (0.93, 0.93, 0.91)
    px[..., 3] = 1.0
    px[inside, 0] = 0.70
    px[inside, 1] = 0.16
    px[inside, 2] = 0.12
    guide = (
        (np.abs(u) < 0.006)
        | (np.abs(v - 0.45) < 0.006)
        | (np.abs(v) < 0.006)
        | (np.abs(v + 0.45) < 0.006)
    )
    px[guide, 0] = 0.30
    px[guide, 1] = 0.30
    px[guide, 2] = 0.30

    img = bpy.data.images.new("AppleRef", width=size, height=size, alpha=True)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, "reference_apple.png")
    img.file_format = "PNG"
    img.save()
    return img


def add_reference(img):
    try:
        bpy.ops.object.empty_add(type="IMAGE", location=(0, 0, 0))
        emp = bpy.context.object
        emp.data = img
        emp.empty_display_size = 3.0
        emp.empty_image_depth = "FRONT"
        emp.name = "REF_Apple_Proportion"
        log("reference added as image empty")
    except Exception as exc:
        log("image empty fallback: %s" % exc)
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0, 0, 0),
                                         rotation=(math.pi / 2.0, 0, 0))
        plane = bpy.context.object
        plane.name = "REF_Apple_Proportion"
        mat = bpy.data.materials.new("REF_Mat")
        mat.use_nodes = True
        nt = mat.node_tree
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        plane.data.materials.append(mat)
        plane.hide_render = True


# ----------------------------------------------------------------------------
# Stage 2/3 : geometry
# ----------------------------------------------------------------------------

def apple_vert(theta, phi, detail):
    st = math.sin(theta)
    ct = math.cos(theta)
    width = 1.0 + 0.20 * ct
    radius = st * width
    if detail:
        radius *= 1.0 + 0.035 * math.cos(5.0 * phi) * st * st
        radius *= 1.0 + 0.012 * math.sin(3.0 * phi + 0.7) * st
    z = ct * 0.95
    if theta < 0.62:
        t = 1.0 - theta / 0.62
        z -= 0.30 * t * t
        radius *= 1.0 - 0.10 * t
    if theta > math.pi - 0.55:
        t = (theta - (math.pi - 0.55)) / 0.55
        z += 0.18 * t * t
        radius *= 1.0 - 0.08 * t
    if detail:
        wobble = (
            0.010 * math.sin(7.0 * phi + 3.0 * theta)
            + 0.007 * math.sin(11.0 * theta + 2.0 * phi)
            + 0.005 * math.cos(17.0 * phi - 5.0 * theta)
        )
        radius *= 1.0 + wobble
        z += 0.005 * math.sin(9.0 * phi + 4.0 * theta)
    return (radius * math.cos(phi), radius * math.sin(phi), z)


def build_apple(name, segments=72, rings=44, detail=True):
    verts = []
    faces = []
    verts.append(apple_vert(0.0, 0.0, detail))
    row_indices = []
    for i in range(1, rings):
        theta = math.pi * i / rings
        row = []
        for j in range(segments):
            phi = 2.0 * math.pi * j / segments
            row.append(len(verts))
            verts.append(apple_vert(theta, phi, detail))
        row_indices.append(row)
    bottom = len(verts)
    verts.append(apple_vert(math.pi, 0.0, detail))

    for j in range(segments):
        faces.append((0, row_indices[0][j], row_indices[0][(j + 1) % segments]))
    for i in range(len(row_indices) - 1):
        upper = row_indices[i]
        lower = row_indices[i + 1]
        for j in range(segments):
            k = (j + 1) % segments
            faces.append((upper[j], lower[j], lower[k], upper[k]))
    for j in range(segments):
        faces.append((bottom, row_indices[-1][(j + 1) % segments], row_indices[-1][j]))

    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def add_subdivision(obj, render_levels=2):
    mod = obj.modifiers.new("SmoothQuads", "SUBSURF")
    mod.subdivision_type = "CATMULL_CLARK"
    mod.levels = 1
    mod.render_levels = render_levels


def add_skin_displacement(obj):
    tex = bpy.data.textures.new("SkinClouds", type="CLOUDS")
    tex.noise_scale = 0.075
    tex.noise_depth = 2
    mod = obj.modifiers.new("SkinMicro", "DISPLACE")
    mod.texture = tex
    mod.texture_coords = "LOCAL"
    mod.strength = 0.006
    mod.mid_level = 0.5


def add_stem():
    curve = bpy.data.curves.new("StemCurve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 16
    curve.bevel_depth = 0.020
    curve.bevel_resolution = 4
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(2)
    coords = [(0.0, 0.0, 0.60), (0.02, 0.01, 0.80), (0.075, 0.025, 0.98)]
    for point, co in zip(spline.bezier_points, coords):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new("Stem", curve)
    bpy.context.collection.objects.link(obj)
    return obj


def add_leaf():
    steps = 20
    verts = []
    faces = []
    for i in range(steps + 1):
        t = i / steps
        x = 0.055 + 0.46 * t
        y = 0.02 + 0.10 * math.sin(math.pi * t)
        z = 0.92 + 0.055 * t - 0.02 * math.sin(math.pi * t)
        width = 0.155 * (math.sin(math.pi * t) ** 0.8)
        verts.append((x, y - width, z))
        verts.append((x, y + width, z))
    for i in range(steps):
        a = 2 * i
        faces.append((a, a + 1, a + 3, a + 2))
    mesh = bpy.data.meshes.new("LeafMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Leaf", mesh)
    bpy.context.collection.objects.link(obj)
    for poly in mesh.polygons:
        poly.use_smooth = True
    thick = obj.modifiers.new("Thickness", "SOLIDIFY")
    thick.thickness = 0.006
    return obj


# ----------------------------------------------------------------------------
# Stage 4 : materials
# ----------------------------------------------------------------------------

def color_ramp(nt, stops, loc):
    node = nt.nodes.new("ShaderNodeValToRGB")
    node.location = loc
    ramp = node.color_ramp
    while len(ramp.elements) > 1:
        ramp.elements.remove(ramp.elements[-1])
    ramp.elements[0].position = stops[0][0]
    ramp.elements[0].color = stops[0][1]
    for pos, col in stops[1:]:
        element = ramp.elements.new(pos)
        element.color = col
    return node


def apple_material():
    mat = bpy.data.materials.new("Apple_RedWaxy")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-920, 40)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-730, 180)
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-730, -80)
    noise.inputs["Scale"].default_value = 9.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])

    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY"
    m1.location = (-540, 180)
    m1.inputs[1].default_value = 0.78
    nt.links.new(sep.outputs["Z"], m1.inputs[0])

    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    m2.location = (-540, 0)
    m2.inputs[1].default_value = 0.22
    nt.links.new(noise.outputs["Fac"], m2.inputs[0])

    m3 = nt.nodes.new("ShaderNodeMath")
    m3.operation = "ADD"
    m3.location = (-360, 140)
    nt.links.new(m1.outputs[0], m3.inputs[0])
    nt.links.new(m2.outputs[0], m3.inputs[1])

    ramp = color_ramp(nt, [
        (0.00, (0.55, 0.52, 0.10, 1.0)),
        (0.30, (0.72, 0.16, 0.05, 1.0)),
        (0.62, (0.60, 0.035, 0.025, 1.0)),
        (1.00, (0.42, 0.02, 0.02, 1.0)),
    ], (-160, 180))
    nt.links.new(m3.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = 0.40
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.10
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (0.8, 0.25, 0.15)
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.16
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = 0.30

    pores = nt.nodes.new("ShaderNodeTexNoise")
    pores.location = (-720, -360)
    pores.inputs["Scale"].default_value = 160.0
    pores.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Generated"], pores.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-180, -320)
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.006
    nt.links.new(pores.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def simple_material(name, base, rough, noise_scale=None, strength=0.12):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = rough
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
        bump.inputs["Distance"].default_value = 0.01
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def leaf_material():
    mat = simple_material("Leaf_Green", (0.13, 0.28, 0.07, 1.0), 0.52)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-720, 0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = (-520, 0)
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 22.0
    wave.inputs["Distortion"].default_value = 1.2
    wave.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Generated"], wave.inputs["Vector"])
    ramp = color_ramp(nt, [
        (0.0, (0.10, 0.24, 0.05, 1.0)),
        (0.5, (0.16, 0.34, 0.08, 1.0)),
        (1.0, (0.22, 0.40, 0.10, 1.0)),
    ], (-280, 0))
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.18
    return mat


# ----------------------------------------------------------------------------
# Stage 5 : lighting and camera
# ----------------------------------------------------------------------------

def add_area(name, loc, energy, size, color, target=(0, 0, 0)):
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
    data.lens = 72.0
    obj = bpy.data.objects.new("Camera", data)
    bpy.context.collection.objects.link(obj)
    obj.location = (3.2, -5.4, 2.2)
    direction = Vector((0.0, 0.0, 0.10)) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = obj
    return obj


# ----------------------------------------------------------------------------
# Stage 6 : render
# ----------------------------------------------------------------------------

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
    scene.view_settings.gamma = 1.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False


def main():
    reset()
    scene = bpy.context.scene

    # Stage 1: reference analysis
    ref_image = make_reference_image()
    add_reference(ref_image)
    save("01_reference.blend")

    # Stage 2: blockout
    blockout = build_apple("Apple_Blockout", segments=24, rings=12, detail=False)
    log("blockout vertices: %d" % len(blockout.data.vertices))
    save("02_blockout.blend")

    # Stage 3: topology and sculpt detail
    bpy.data.objects.remove(blockout, do_unlink=True)
    apple = build_apple("Apple_Final", segments=72, rings=44, detail=True)
    add_subdivision(apple, 2)
    add_skin_displacement(apple)
    add_stem()
    add_leaf()
    log("final base vertices: %d" % len(apple.data.vertices))
    save("03_topology.blend")

    # Stage 4: materials
    apple.data.materials.append(apple_material())
    bpy.data.objects["Stem"].data.materials.append(
        simple_material("Stem_Brown", (0.20, 0.12, 0.06, 1.0), 0.78, 60.0, 0.2))
    bpy.data.objects["Leaf"].data.materials.append(leaf_material())
    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0, 0, -0.80))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(
        simple_material("Ground_Charcoal", (0.085, 0.085, 0.09, 1.0), 0.72, 35.0, 0.08))
    save("04_material.blend")

    # Stage 5: lighting and camera
    setup_world()
    add_area("Key_Light", (-3.2, -4.0, 5.0), 520.0, 4.0, (1.0, 0.94, 0.86))
    add_area("Fill_Light", (4.2, -2.0, 2.4), 260.0, 5.0, (0.78, 0.86, 1.0))
    add_area("Rim_Light", (1.0, 4.0, 4.2), 420.0, 3.0, (1.0, 0.95, 0.88))
    add_camera()
    save("05_lighting.blend")

    # Stage 6: final render
    setup_render(scene)
    scene.render.filepath = os.path.join(OUT, "final.png")
    bpy.ops.render.render(write_still=True)
    save("06_final.blend")
    log("DONE")


if __name__ == "__main__":
    main()
