# -*- coding: utf-8 -*-
"""生成"修改器效果对比"配图：阵列砖墙 / 倒角 / 细分。"""
import bpy, sys, os, math

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# 材质
def mat(name, col, rough=0.6):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    return m

M_BRICK = mat("M_Brick", (0.42, 0.20, 0.14, 1), 0.75)
M_BEVEL = mat("M_Bevel", (0.85, 0.45, 0.12, 1), 0.45)
M_SUB   = mat("M_Sub",   (0.30, 0.52, 0.80, 1), 0.35)

# ① 阵列砖墙
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-6.2, 0, 0))
brick = bpy.context.active_object
brick.name = "ArrayBricks"
brick.dimensions = (0.9, 0.4, 0.28)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

arr = brick.modifiers.new("Array", "ARRAY")
arr.count = 5
arr.use_relative_offset = False
arr.use_constant_offset = True
arr.constant_offset_displace = (1.0, 0, 0)

arr2 = brick.modifiers.new("ArrayY", "ARRAY")
arr2.count = 3
arr2.use_relative_offset = False
arr2.use_constant_offset = True
arr2.constant_offset_displace = (0.5, 0.45, 0.33)

bev = brick.modifiers.new("Bevel", "BEVEL")
bev.width = 0.02
bev.segments = 2
bev.limit_method = "ANGLE"
bev.angle_limit = math.radians(30)

brick.data.materials.append(M_BRICK)

# ② 倒角立方体
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(-0.4, 0, 0.75))
bc = bpy.context.active_object
bc.name = "BevelCube"
b = bc.modifiers.new("Bevel", "BEVEL")
b.width = 0.18
b.segments = 6
b.limit_method = "ANGLE"
bc.data.materials.append(M_BEVEL)

# ③ 细分立方体
bpy.ops.mesh.primitive_cube_add(size=1.4, location=(4.6, 0, 0.7))
sc_o = bpy.context.active_object
sc_o.name = "SubdivCube"
s = sc_o.modifiers.new("Subdiv", "SUBSURF")
s.subdivision_type = "CATMULL_CLARK"
s.levels = 3
s.render_levels = 3
sc_o.data.materials.append(M_SUB)

# 地面
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -0.16))
g = bpy.context.active_object
g.data.materials.append(mat("M_Ground", (0.55, 0.56, 0.58, 1), 0.85))

# 灯光
bpy.ops.object.light_add(type="AREA", location=(-6, -9, 11))
key = bpy.context.active_object
key.data.energy = 900
key.data.size = 10
d = (bpy.data.objects["ArrayBricks"].location * 0) - key.location
key.rotation_euler = (math.radians(40), 0, math.radians(-28))

bpy.ops.object.light_add(type="SUN", location=(8, -4, 8))
sun = bpy.context.active_object
sun.data.energy = 2.2
sun.rotation_euler = (math.radians(52), 0, math.radians(140))

# 世界
w = bpy.context.scene.world
if w is None:
    w = bpy.data.worlds.new("W"); bpy.context.scene.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.62, 0.66, 0.72, 1.0)
bg.inputs[1].default_value = 0.9

# 相机：正对三个物体
bpy.ops.object.camera_add(location=(0, -13.5, 4.2))
cam = bpy.context.active_object
from mathutils import Vector
target = Vector((0, 0, 0.9))
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = 42
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1600
sc.render.resolution_y = 800
sc.view_settings.view_transform = "Standard"
sc.render.filepath = os.path.join(OUT, "modifiers.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
