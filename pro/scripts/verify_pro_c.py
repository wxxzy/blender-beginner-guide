"""高级功能实测 · 批次 C
MPM 流体 / 毛发粒子
运行：blender -b --factory-startup -noaudio -P verify_pro_c.py -- <outdir>
"""
import bpy, bmesh, math, os, sys, random

argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else os.path.expanduser("~/out")
os.makedirs(OUT, exist_ok=True)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup(res=(1100, 620), samples=24):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.05, 0.055, 0.07, 1)
    bg.inputs[1].default_value = 1.0


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


def light(loc, energy=600, size=4, target=(0, 0, 0)):
    from mathutils import Vector
    ld = bpy.data.lights.new("L", "AREA")
    ld.energy = energy
    ld.size = size
    o = bpy.data.objects.new("L", ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o


def mat(name, color, rough=0.5, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            try:
                m.blend_method = "BLEND"
            except Exception:
                pass
    return m


def render(name):
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(OUT, name)
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK", name)


def simulate(end, start=1):
    sc = bpy.context.scene
    for f in range(start, end + 1):
        sc.frame_set(f)
    print("SIMULATED %d..%d" % (start, end))


# ------------------------------------------------------------ 流体
def c1_fluid():
    clear()
    setup((1100, 660), 24)

    # 玻璃容器 = 流体域
    bpy.ops.mesh.primitive_cube_add(size=3.0, location=(0, 0, 1.5))
    dom = bpy.context.active_object
    dom.name = "FluidDomain"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    dom.data.materials.append(None)  # 占位，稍后填液体材质

    fm = dom.modifiers.new("Fluid", "FLUID")
    fm.fluid_type = "DOMAIN"
    ds = fm.domain_settings
    ds.domain_type = "LIQUID"
    ds.resolution_max = 96
    ds.cache_frame_start = 1
    ds.cache_frame_end = 80
    ds.use_mesh = True
    ds.mesh_scale = 1

    # 注入源
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.24, location=(0.15, 0.0, 2.65))
    flow = bpy.context.active_object
    flow.name = "Inflow"
    fmod = flow.modifiers.new("Fluid", "FLUID")
    fmod.fluid_type = "FLOW"
    fs = fmod.flow_settings
    fs.flow_type = "LIQUID"
    fs.flow_behavior = "INFLOW"
    fs.use_inflow = True
    fs.use_initial_velocity = True
    fs.velocity_coord = (0, 0, -1.5)

    # 水面材质（给域，液体网格继承）
    water = bpy.data.materials.new("M_Water")
    water.use_nodes = True
    wb = water.node_tree.nodes["Principled BSDF"]
    wb.inputs["Base Color"].default_value = (0.07, 0.26, 0.40, 1)
    wb.inputs["Roughness"].default_value = 0.08
    wb.inputs["Metallic"].default_value = 0.0
    wb.inputs["Transmission Weight"].default_value = 0.55
    wb.inputs["IOR"].default_value = 1.33
    # 实测结论：流体域只认第一个材质槽，液体与域边界共用同一材质
    dom.data.materials[0] = water

    # 地面 + 光
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(mat("M_G", (0.09, 0.1, 0.12), 0.9))

    cam((5.6, -6.4, 4.0), (0, 0, 1.5), 50)
    light((-4.0, -4.5, 6.5), 700, 5, (0, 0, 1.6))
    light((4.5, -2.0, 4.0), 320, 4, (0, 0, 1.6))
    light((0, 4.5, 4.5), 300, 5, (0, 0, 1.5))

    try:
        sc_eevee = bpy.context.scene.eevee
        sc_eevee.use_raytracing = True
        print("RAYTRACING_ON")
    except Exception as e:
        print("RAYTRACING_NA", e)

    simulate(80)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = dom.evaluated_get(dg)
    try:
        print("FLUID liquid_mesh_verts=%d" % len(ev.data.vertices))
    except Exception as e:
        print("FLUID probe skipped", e)
    render("c1_fluid.png")


# ------------------------------------------------------------ 毛发粒子
def c2_hair():
    clear()
    setup((1100, 660), 32)
    random.seed(3)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=64, ring_count=40, location=(0, 0, 1.05))
    ball = bpy.context.active_object
    ball.name = "Hairy"
    for p in ball.data.polygons:
        p.use_smooth = True
    ball.data.materials.append(mat("M_Body", (0.20, 0.11, 0.08), 0.7))

    pm = ball.modifiers.new("Hair", "PARTICLE_SYSTEM")
    psys = ball.particle_systems[0]
    psys.seed = 11
    st = psys.settings
    st.name = "Fur"
    st.type = "HAIR"
    st.count = 6000
    st.hair_length = 0.26
    st.emit_from = "FACE"
    st.use_even_distribution = True
    st.root_radius = 1.0
    st.tip_radius = 0.15
    st.child_type = "INTERPOLATED"
    st.child_percent = 3
    st.rendered_child_count = 6
    st.child_radius = 0.030
    st.child_length_threshold = 0.4
    st.clump_factor = 0.15
    st.roughness_1 = 0.004
    st.hair_step = 5
    st.display_step = 3
    st.render_step = 4

    # 地面
    bpy.ops.mesh.primitive_plane_add(size=24, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(mat("M_G", (0.10, 0.11, 0.13), 0.85))

    cam((4.4, -6.0, 3.2), (0, 0, 1.02), 52)
    light((-3.0, -3.5, 5.0), 700, 4, (0, 0, 1.1))
    light((3.2, -1.0, 2.8), 260, 3, (0, 0, 1.1))
    light((0, 3.5, 3.5), 260, 4, (0, 0, 1.1))

    dg = bpy.context.evaluated_depsgraph_get()
    ev = ball.evaluated_get(dg)
    print("HAIR particles=%d children=%d" % (len(psys.particles), st.rendered_child_count))
    render("c2_hair.png")


for fn, tag in [(c1_fluid, "C1"), (c2_hair, "C2")]:
    try:
        fn()
    except Exception as e:
        import traceback
        print("FAIL", tag, type(e).__name__, e)
        traceback.print_exc()
print("BATCH_C_DONE")
