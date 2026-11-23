"""高级功能实测 · 批次 B
刚体堆叠 / 布料垂坠
运行：blender -b --factory-startup -noaudio -P verify_pro_b.py -- <outdir>
"""
import bpy, math, os, sys, random

argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else os.path.expanduser("~/out")
os.makedirs(OUT, exist_ok=True)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup(res=(1200, 640), samples=24):
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


def light(loc, energy=600, size=4, target=(0, 0, 0)):
    from mathutils import Vector
    ld = bpy.data.lights.new("L", "AREA")
    ld.energy = energy
    ld.size = size
    o = bpy.data.objects.new("L", ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def mat(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def ground(size=40):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "Ground"
    g.data.materials.append(mat("M_G", (0.08, 0.09, 0.11), 0.9))
    return g


def simulate(end=90, start=1):
    """后台模式下必须逐帧推进，物理缓存才会真正求解。"""
    sc = bpy.context.scene
    for f in range(start, end + 1):
        sc.frame_set(f)
    print("SIMULATED frames=%d..%d" % (start, end))


def render(name):
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(OUT, name)
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK", name)


# ------------------------------------------------------------ 刚体
def b1_rigid():
    clear()
    setup((1240, 660), 24)
    sc = bpy.context.scene
    g = ground()
    # 地面 = 被动刚体
    bpy.context.view_layer.objects.active = g
    bpy.ops.rigidbody.object_add(type='PASSIVE')
    g.rigid_body.friction = 0.9
    g.rigid_body.restitution = 0.02

    random.seed(7)
    palette = [(0.26, 0.16, 0.12), (0.32, 0.21, 0.15), (0.20, 0.13, 0.10), (0.38, 0.27, 0.19)]
    n = 14
    for i in range(n):
        w = random.uniform(0.42, 0.62)
        d = random.uniform(0.26, 0.36)
        h = random.uniform(0.16, 0.24)
        x = -2.6 + random.uniform(-0.18, 0.18)
        y = random.uniform(-0.22, 0.22)
        z = 0.30 + i * 0.46
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
        b = bpy.context.active_object
        b.name = "Brick%02d" % i
        b.scale = (w, d, h)          # 尺寸走 scale，物理包围盒才对
        b.rotation_euler = (0, 0, math.radians(random.uniform(-9, 9)))
        b.data.materials.append(mat("M_B%d" % i, random.choice(palette), 0.82))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.ops.rigidbody.object_add(type='ACTIVE')
        b.rigid_body.mass = 1.6
        b.rigid_body.friction = 0.85
        b.rigid_body.restitution = 0.03
        b.rigid_body.linear_damping = 0.12

    # 物理世界参数
    rbw = sc.rigidbody_world
    rbw.time_scale = 1.0
    rbw.substeps_per_frame = 12
    rbw.solver_iterations = 20
    rbw.point_cache.frame_start = 1
    rbw.point_cache.frame_end = 90

    cam((-5.2, -5.8, 3.1), (-2.55, 0, 0.7), 55)
    light((-5.5, -5.0, 7.0), 480, 5, (-2.6, 0, 1))
    light((-0.5, -2.0, 3.0), 200, 4, (-2.6, 0, 1))
    light((-4.0, 4.0, 4.0), 180, 5, (-2.6, 0, 1))

    print("RIGID bricks=%d" % n)
    simulate(90)
    render("b1_rigid.png")


# ------------------------------------------------------------ 布料
def b2_cloth():
    clear()
    setup((1240, 660), 24)
    sc = bpy.context.scene
    ground()

    # 被覆盖的球
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.85, segments=48, ring_count=24, location=(2.5, 0, 0.85))
    ball = bpy.context.active_object
    ball.data.materials.append(mat("M_Ball", (0.32, 0.36, 0.44), 0.35))
    for p in ball.data.polygons:
        p.use_smooth = True
    col = ball.modifiers.new("Collision", "COLLISION")
    col.settings.thickness_outer = 0.012

    # 布料平面：直接用 bmesh 生成 40x40 网格，物理求解就在这个密度上
    import bmesh
    me = bpy.data.meshes.new("ClothMesh")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=1.5)
    bm.to_mesh(me)
    bm.free()
    cloth = bpy.data.objects.new("Cloth", me)
    bpy.context.scene.collection.objects.link(cloth)
    cloth.location = (2.5, 0, 2.15)

    cm = cloth.modifiers.new("Cloth", "CLOTH")
    st = cm.settings
    st.quality = 7
    st.mass = 0.25
    st.tension_stiffness = 25
    st.compression_stiffness = 25
    st.shear_stiffness = 8
    st.bending_stiffness = 0.55
    st.air_damping = 2.0
    st.vertex_group_mass = ""
    cm.point_cache.frame_start = 1
    cm.point_cache.frame_end = 90

    cloth.data.materials.append(mat("M_Cloth", (0.40, 0.08, 0.10), 0.62))

    cam((5.2, -6.2, 3.7), (2.5, 0, 0.95), 55)
    light((1.0, -5.0, 6.5), 620, 5, (2.5, 0, 1))
    light((6.0, -1.5, 3.2), 200, 4, (2.5, 0, 1))
    light((4.0, 4.0, 4.0), 180, 5, (2.5, 0, 1))

    for poly in me.polygons:
        poly.use_smooth = True
    sol = cloth.modifiers.new("Solid", "SOLIDIFY")
    sol.thickness = 0.007
    sol.offset = 0.0

    bpy.context.view_layer.objects.active = cloth
    simulate(1, 1)
    simulate(90, 2)
    print("CLOTH verts=%d" % len(cloth.data.vertices))
    render("b2_cloth.png")


for fn, tag in [(b1_rigid, "B1"), (b2_cloth, "B2")]:
    try:
        fn()
    except Exception as e:
        import traceback
        print("FAIL", tag, type(e).__name__, e)
        traceback.print_exc()
print("BATCH_B_DONE")
