"""高级功能实测 · 批次 F
几何节点 Repeat Zone：8 次迭代堆叠出螺旋塔
运行：blender -b --factory-startup -noaudio -P verify_pro_f.py -- <outdir>
"""
import bpy, math, os, sys

argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else os.path.expanduser("~/out")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---------------- 节点组 ----------------
ng = bpy.data.node_groups.new("RepeatTower", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

gi = ng.nodes.new("NodeGroupInput");   gi.location = (-900, 0)
go = ng.nodes.new("NodeGroupOutput");  go.location = (760, 0)

rin = ng.nodes.new("GeometryNodeRepeatInput");   rin.location = (-620, 0)
rout = ng.nodes.new("GeometryNodeRepeatOutput"); rout.location = (480, 0)

# 关键：必须手动配对（新建节点不会自动配对）
rin.pair_with_output(rout)
print("PAIRED:", rin.paired_output is not None)

# 迭代次数
iters = None
for inp in rin.inputs:
    if inp.name == "Iterations":
        inp.default_value = 12
        iters = inp
print("ITER_SOCKET:", iters is not None)

# 基础方块
cube = ng.nodes.new("GeometryNodeMeshCube")
cube.location = (-320, -260)
cube.inputs["Size"].default_value = (0.32, 0.32, 0.10)

# 每层抬高：Iteration * 0.28
mul = ng.nodes.new("ShaderNodeMath")
mul.operation = "MULTIPLY"
mul.location = (-320, 60)
mul.inputs[1].default_value = 0.28

comb = ng.nodes.new("ShaderNodeCombineXYZ")
comb.location = (-140, 60)

# 每层旋转：用 iteration 做角度
ang = ng.nodes.new("ShaderNodeMath")
ang.operation = "MULTIPLY"
ang.location = (-320, -80)
ang.inputs[1].default_value = math.radians(7)

tr = ng.nodes.new("GeometryNodeTransform")
tr.location = (60, -140)

# 累加
join = ng.nodes.new("GeometryNodeJoinGeometry")
join.location = (280, -40)

ng.links.new(rin.outputs["Iteration"], mul.inputs[0])
ng.links.new(mul.outputs["Value"], comb.inputs["Z"])
ng.links.new(rin.outputs["Iteration"], ang.inputs[0])
ng.links.new(ang.outputs["Value"], tr.inputs["Rotation"])

ng.links.new(cube.outputs["Mesh"], tr.inputs["Geometry"])
ng.links.new(comb.outputs["Vector"], tr.inputs["Translation"])

ng.links.new(rin.outputs["Geometry"], join.inputs[0])
ng.links.new(tr.outputs["Geometry"], join.inputs[0])

ng.links.new(join.outputs["Geometry"], rout.inputs["Geometry"])
ng.links.new(rout.outputs["Geometry"], go.inputs["Geometry"])

print("NODES:", len(ng.nodes))

# ---------------- 物体 ----------------
bpy.ops.object.empty_add(location=(0, 0, 0))
ob = bpy.context.active_object
ob.name = "RepeatTower"
mod = ob.modifiers.new("GN", "NODES")
mod.node_group = ng

dg = bpy.context.evaluated_depsgraph_get()
ev = ob.evaluated_get(dg)
try:
    print("RESULT_VERTS:", len(ev.data.vertices), "FACES:", len(ev.data.polygons))
except Exception as e:
    print("RESULT_NA:", e)

# ---------------- 渲染 ----------------
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 1000, 700
try:
    sc.eevee.taa_render_samples = 32
except Exception:
    pass

w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.045, 0.06, 1)


def mat(name, color, rough=0.45, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


bpy.ops.mesh.primitive_plane_add(size=24, location=(0, 0, -0.02))
g = bpy.context.active_object
g.data.materials.append(mat("M_G", (0.08, 0.085, 0.10), 0.9))

# 给塔上材质：GN 输出的几何没有材质，用物体材质槽 + GN 的 Set Material 更稳
setmat = ng.nodes.new("GeometryNodeSetMaterial")
setmat.location = (600, -140)
setmat.inputs["Material"].default_value = mat("M_Tower", (0.80, 0.42, 0.14), 0.35, 0.15)
# 插在 join 与 output 之间
ng.links.new(join.outputs["Geometry"], setmat.inputs["Geometry"])
ng.links.new(setmat.outputs["Geometry"], rout.inputs["Geometry"])

from mathutils import Vector
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam)
cam.location = (4.6, -6.2, 4.1)
cam.rotation_euler = (Vector((0, 0, 1.68)) - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
cd.lens = 50
sc.camera = cam

for loc, en in [((-3.0, -3.4, 5.4), 900), ((3.4, -1.2, 2.6), 320), ((0, 3.6, 3.4), 280)]:
    ld = bpy.data.lights.new("L", "AREA"); ld.energy = en; ld.size = 4
    lo = bpy.data.objects.new("L", ld); sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector((0, 0, 1.4)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()

sc.render.filepath = os.path.join(OUT, "f1_repeat_zone.png")
sc.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
print("RENDER_OK f1_repeat_zone.png")
print("BATCH_F_DONE")
