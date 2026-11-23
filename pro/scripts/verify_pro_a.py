"""高级功能实测 · 批次 A
雕刻重拓扑 / 骨骼绑定+IK / UV 展开 / 资产标记 / 插件开发
运行：blender -b --factory-startup -noaudio -P verify_pro_a.py -- <outdir>
"""
import bpy, bmesh, math, os, sys, importlib

argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else os.path.expanduser("~/out")
os.makedirs(OUT, exist_ok=True)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup(res=(1000, 620), samples=24):
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
    bg.inputs[0].default_value = (0.045, 0.05, 0.065, 1)
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


def render(name):
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(OUT, name)
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("RENDER_OK", name)


def mat(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def ground(z=0.0, size=30, color=(0.09, 0.1, 0.12)):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    g = bpy.context.active_object
    g.data.materials.append(mat("M_Ground", color, 0.85))


# ---------------------------------------------------------------- A1 雕刻
def a1_sculpt():
    clear()
    setup((1100, 620), 32)
    from mathutils import Vector

    # 左：未处理的低模球
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0, location=(-1.6, 0, 1.05))
    left = bpy.context.active_object
    left.name = "Raw"
    left.data.materials.append(mat("M_Raw", (0.32, 0.35, 0.42), 0.35))

    # 右：重拓扑 + 位移 → 岩石质感
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0, location=(1.6, 0, 1.05))
    rock = bpy.context.active_object
    rock.name = "Rock"
    rock.data.materials.append(mat("M_Rock", (0.5, 0.42, 0.35), 0.85))

    rm = rock.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = 0.028
    rm.use_smooth_shade = True

    tex = bpy.data.textures.new("RockNoise", "CLOUDS")
    tex.noise_scale = 0.32
    tex.noise_depth = 3
    dsp = rock.modifiers.new("Displace", "DISPLACE")
    dsp.texture = tex
    dsp.strength = 0.22
    dsp.mid_level = 0.5

    sub = rock.modifiers.new("Sub", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 1

    # 加一点平面反光
    ground(-0.02, 20)
    cam((0, -8.6, 3.1), (0, 0, 1.05), 45)
    light((-3.5, -4.0, 5.0), 900, 5)
    light((4.0, -2.0, 3.0), 400, 4)
    light((0, 4.0, 3.0), 300, 5, (0, 0, 1))

    # 评估后的顶点数
    dg = bpy.context.evaluated_depsgraph_get()
    ev = rock.evaluated_get(dg)
    print("SCULPT raw_verts=%d sculpt_verts=%d" % (len(left.data.vertices), len(ev.data.vertices)))
    render("a1_sculpt.png")


# ---------------------------------------------------------------- A2 绑定
def a2_rig():
    clear()
    setup((1100, 660), 32)
    from mathutils import Vector

    # 建一段可弯曲的柱体（12 段环 × 10 边）
    me = bpy.data.meshes.new("Tentacle")
    bm = bmesh.new()
    rings, seg = 14, 10
    ring_verts = []
    for i in range(rings + 1):
        z = 3.6 * i / rings
        r = 0.34 * (1 - 0.45 * i / rings)
        row = []
        for s in range(seg):
            a = 2 * math.pi * s / seg
            row.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r, z)))
        ring_verts.append(row)
    for i in range(rings):
        for s in range(seg):
            s2 = (s + 1) % seg
            bm.faces.new((ring_verts[i][s], ring_verts[i][s2], ring_verts[i + 1][s2], ring_verts[i + 1][s]))
    bm.faces.new(list(reversed(ring_verts[0])))
    bm.faces.new(ring_verts[-1])
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Tentacle", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat("M_Skin", (0.10, 0.40, 0.33), 0.42))
    for p in ob.data.polygons:
        p.use_smooth = True

    # 骨骼链 3 根
    ad = bpy.data.armatures.new("RigData")
    rig = bpy.data.objects.new("Rig", ad)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i in range(3):
        b = ad.edit_bones.new("B%d" % i)
        b.head = (0, 0, i * 1.2)
        b.tail = (0, 0, (i + 1) * 1.2)
        if prev:
            b.parent = prev
            b.use_connect = True
        prev = b
    bpy.ops.object.mode_set(mode='OBJECT')

    # 自动权重（失败则回退到按高度手动权重）
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    auto_ok = True
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except Exception as e:
        auto_ok = False
        print("AUTO_WEIGHT_FAIL", e)

    if not auto_ok or not ob.vertex_groups:
        ob.parent = rig
        md = ob.modifiers.new("Armature", "ARMATURE")
        md.object = rig
        for i in range(3):
            vg = ob.vertex_groups.new(name="B%d" % i)
            idx = []
            for v in ob.data.vertices:
                z = v.co.z
                lo, hi = i * 1.2, (i + 1) * 1.2
                if lo <= z <= hi:
                    idx.append(v.index)
            if idx:
                vg.add(idx, 1.0, 'REPLACE')

    # IK：末端骨骼拉向一个目标空物体
    tgt = bpy.data.objects.new("IKTarget", None)
    bpy.context.scene.collection.objects.link(tgt)
    tgt.location = (1.35, 0, 2.9)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    pb = rig.pose.bones["B2"]
    ik = pb.constraints.new("IK")
    ik.target = tgt
    ik.chain_count = 2
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()

    print("RIG auto=%s vgroups=%d bones=%d" % (auto_ok, len(ob.vertex_groups), len(ad.bones)))

    ground(-0.02, 20)
    cam((4.8, -8.2, 3.7), (0.55, 0, 1.55), 45)
    light((-4, -4, 6), 900, 5)
    light((4, -1, 3), 350, 4)
    render("a2_rig.png")


# ---------------------------------------------------------------- A3 UV
def make_checker(size=128, squares=8):
    img = bpy.data.images.new("Checker", size, size)
    px = []
    for y in range(size):
        for x in range(size):
            c = ((x * squares) // size + (y * squares) // size) % 2
            v = 0.82 if c else 0.22
            px += [v, v, v, 1.0]
    img.pixels = px
    return img


def a3_uv():
    clear()
    setup((1000, 560), 24)
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1.0))
    ob = bpy.context.active_object
    ob.name = "UVBox"

    # Smart UV Project
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')

    uv = ob.data.uv_layers.active
    im = make_checker()
    m = bpy.data.materials.new("M_UV")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = im
    tx.interpolation = "Closest"
    nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    ob.data.materials.append(m)

    ground(0.0, 20)
    cam((3.8, -5.2, 3.6), (0, 0, 1.0), 55)
    light((-4, -3, 6), 800, 5)
    light((3, -2, 4), 300, 3)
    print("UV layer=%s loops=%d" % (uv.name if uv else "NONE", len(ob.data.loops)))
    render("a3_uv.png")


# ---------------------------------------------------------------- A4 资产
def a4_asset():
    clear()
    lib = os.path.join(OUT, "assetlib")
    os.makedirs(lib, exist_ok=True)
    m = mat("M_AssetStone", (0.42, 0.44, 0.5), 0.7)
    m.asset_mark()
    m.asset_data.description = "示例：可复用的石材材质"
    m.asset_data.tags.new("stone")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(lib, "stone_lib.blend"))
    print("ASSET ok marked=%s tags=%s" % (m.asset_data is not None, [t.name for t in m.asset_data.tags]))


# ---------------------------------------------------------------- A5 插件
ADDON_SRC = '''bl_info = {"name": "Pro Ring Stacker", "blender": (4, 2, 0),
           "category": "Object", "version": (1, 0)}
import bpy, math

class PRO_OT_ring_stack(bpy.types.Operator):
    bl_idname = "pro.ring_stack"
    bl_label = "生成圆环塔"
    bl_options = {"REGISTER", "UNDO"}

    count: bpy.props.IntProperty(name="层数", default=6, min=1, max=30)
    radius: bpy.props.FloatProperty(name="半径", default=1.0)

    def execute(self, context):
        for i in range(self.count):
            bpy.ops.mesh.primitive_torus_add(
                major_radius=self.radius, minor_radius=0.07,
                location=(0, 0, 0.28 * i + 0.2),
                rotation=(math.radians(12 * i), 0, math.radians(8 * i)))
        return {"FINISHED"}

class PRO_PT_panel(bpy.types.Panel):
    bl_label = "Pro 工具"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pro"

    def draw(self, context):
        self.layout.operator("pro.ring_stack", icon="MESH_TORUS")

CLASSES = (PRO_OT_ring_stack, PRO_PT_panel)

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
'''


def a5_addon():
    clear()
    setup((1000, 640), 24)
    path = os.path.join(OUT, "pro_ring_addon.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ADDON_SRC)
    sys.path.insert(0, OUT)
    mod = importlib.import_module("pro_ring_addon")
    importlib.reload(mod)
    mod.register()
    bpy.ops.pro.ring_stack(count=7, radius=1.05)
    print("ADDON registered, objects=%d" % len(bpy.context.scene.objects))

    # 给圆环上色 + 地面
    m = mat("M_Ring", (0.90, 0.34, 0.05), 0.30, 0.20)
    for o in list(bpy.context.scene.objects):
        if o.type == "MESH":
            o.data.materials.append(m)
            for p in o.data.polygons:
                p.use_smooth = True
    ground(-0.02, 20)
    cam((5.6, -7.8, 4.4), (0, 0, 1.25), 50)
    light((-4, -4, 6), 900, 5)
    light((4, -2, 4), 350, 4)
    render("a5_addon.png")
    mod.unregister()
    print("ADDON unregistered")


for fn, tag in [(a1_sculpt, "A1"), (a2_rig, "A2"), (a3_uv, "A3"), (a4_asset, "A4"), (a5_addon, "A5")]:
    try:
        fn()
    except Exception as e:
        import traceback
        print("FAIL", tag, type(e).__name__, e)
        traceback.print_exc()
print("BATCH_A_DONE")
