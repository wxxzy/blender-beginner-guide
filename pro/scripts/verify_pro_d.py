"""高级功能实测 · 批次 D
体积散射光柱 / 色彩管理 AgX vs Standard
运行：blender -b --factory-startup -noaudio -P verify_pro_d.py -- <outdir>
"""
import bpy, math, os, sys

argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else os.path.expanduser("~/out")
os.makedirs(OUT, exist_ok=True)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cam(loc, target, lens=50):
    from mathutils import Vector
    cd = bpy.data.cameras.new("C")
    o = bpy.data.objects.new("C", cd)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cd.lens = lens
    bpy.context.scene.camera = o
    return o


def mat(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def render(name, res=(1000, 640), samples=48):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    sc.render.filepath = os.path.join(OUT, name)
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK", name, "vt=", sc.view_settings.view_transform)


# ------------------------------------------------------- D1 体积光
def d1_volumetric():
    clear()
    sc = bpy.context.scene
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.008, 0.009, 0.012, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0

    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(mat("M_G", (0.06, 0.06, 0.07), 0.55))

    # 几根柱子，用来承接光斑
    for i, (x, y, h) in enumerate([(-1.9, -1.0, 4.2), (1.5, -0.3, 3.4)]):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.36, depth=h, location=(x, y, h / 2))
        c = bpy.context.active_object
        c.data.materials.append(mat("M_P%d" % i, (0.30, 0.24, 0.18), 0.72))
        for p in c.data.polygons:
            p.use_smooth = True

    # 体积雾盒子
    bpy.ops.mesh.primitive_cube_add(size=22, location=(0, 0, 7))
    fog = bpy.context.active_object
    fog.name = "Fog"
    fm = bpy.data.materials.new("M_Fog")
    fm.use_nodes = True
    nt = fm.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.055
    vol.inputs["Anisotropy"].default_value = 0.35
    vol.inputs["Color"].default_value = (0.85, 0.90, 1.0, 1)
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    fog.data.materials.append(fm)
    fog.visible_shadow = False

    # 顶部聚光灯
    sd = bpy.data.lights.new("Spot", "SPOT")
    sd.energy = 14000
    sd.spot_size = math.radians(30)
    sd.spot_blend = 0.25
    sd.color = (0.75, 0.85, 1.0)
    sp = bpy.data.objects.new("Spot", sd)
    bpy.context.scene.collection.objects.link(sp)
    sp.location = (-3.2, -4.4, 9.0)
    from mathutils import Vector as V
    sp.rotation_euler = (V((0.2, 0.4, 1.0)) - V(sp.location)).to_track_quat('-Z', 'Y').to_euler()

    cam((9.0, -8.6, 4.1), (0, 0, 2.3), 40)

    ee = sc.eevee
    try:
        ee.use_volumetric_shadows = True
        ee.volumetric_end = 40.0
        ee.volumetric_samples = 96
        ee.volumetric_sample_distribution = 0.85
        ee.use_raytracing = True
    except Exception as e:
        print("EEVEE_VOL_NA", e)

    render("d1_volumetric.png", (1000, 660), 64)
    print("VOL fog_density=0.035 spot=9000W")


# ------------------------------------------------------- D2 色彩管理
def d2_colormgmt():
    clear()
    sc = bpy.context.scene
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.03, 0.05, 1)

    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(mat("M_G", (0.10, 0.10, 0.11), 0.7))

    # 高饱和发光球
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(-1.3, 0, 1.0), segments=48, ring_count=32)
    s = bpy.context.active_object
    for p in s.data.polygons:
        p.use_smooth = True
    sm = bpy.data.materials.new("M_Emit")
    sm.use_nodes = True
    nt = sm.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.90, 0.17, 0.01, 1)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.28, 0.02, 1)
    bsdf.inputs["Emission Strength"].default_value = 1.9
    s.data.materials.append(sm)

    # 金属球（检验高光滚降）
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(1.3, 0, 1.0), segments=48, ring_count=32)
    m2 = bpy.context.active_object
    for p in m2.data.polygons:
        p.use_smooth = True
    m2.data.materials.append(mat("M_Metal", (0.85, 0.86, 0.88), 0.14, 1.0))

    ld = bpy.data.lights.new("Key", "AREA")
    ld.energy = 900
    ld.size = 4
    k = bpy.data.objects.new("Key", ld)
    bpy.context.scene.collection.objects.link(k)
    k.location = (-2.5, -3.0, 5.0)
    from mathutils import Vector
    k.rotation_euler = (Vector((0, 0, 1)) - Vector((-2.5, -3, 5))).to_track_quat('-Z', 'Y').to_euler()

    cam((0.2, -7.4, 2.6), (0, 0, 1.0), 50)

    for vt, fname in [("AgX", "d2_agx.png"), ("Standard", "d2_standard.png")]:
        try:
            sc.view_settings.view_transform = vt
        except Exception as e:
            print("VT_FAIL", vt, e)
        render(fname, (760, 620), 48)

    sc.view_settings.view_transform = "AgX"


for fn, tag in [(d1_volumetric, "D1"), (d2_colormgmt, "D2")]:
    try:
        fn()
    except Exception as e:
        import traceback
        print("FAIL", tag, type(e).__name__, e)
        traceback.print_exc()
print("BATCH_D_DONE")
