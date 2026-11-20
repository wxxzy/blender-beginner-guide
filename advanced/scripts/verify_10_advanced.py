# -*- coding: utf-8 -*-
"""验证 advanced/02、10、11、12 章的关键代码片段。"""
import bpy, bmesh, math, sys, os, random
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()

# ============ 02 修改器：阵列 + 布尔 ============
bpy.ops.mesh.primitive_cube_add(size=1.0)
brick = bpy.context.active_object
brick.scale = (1.0, 0.4, 0.25)
brick.dimensions = (1.0, 0.4, 0.25)
arr = brick.modifiers.new("Array", "ARRAY")
arr.count = 20
arr.use_relative_offset = False
arr.use_constant_offset = True
arr.constant_offset_displace = (1.0, 0, 0)
empty = bpy.data.objects.new("OffsetRef", None)
empty.location = (0.5, 0, 0)
bpy.context.scene.collection.objects.link(empty)
arr.use_object_offset = True
arr.offset_object = empty
print("ARRAY ok, count =", arr.count)

# 布尔
bpy.ops.mesh.primitive_cube_add(size=0.3, location=(5, 0, 0))
cutter = bpy.context.active_object
bm = target = brick.modifiers.new("Bool", "BOOLEAN")
target.operation = "DIFFERENCE"
target.object = cutter
target.solver = "EXACT"
print("BOOL ok, solver =", target.solver)

# 倒角
bev = brick.modifiers.new("Bevel", "BEVEL")
bev.width = 0.03; bev.segments = 2
bev.limit_method = "ANGLE"; bev.angle_limit = math.radians(30)
print("BEVEL ok")

# 细分
bpy.ops.mesh.primitive_cube_add(size=1, location=(-3, 0, 0))
sub_o = bpy.context.active_object
sub = sub_o.modifiers.new("Subdiv", "SUBSURF")
sub.subdivision_type = "CATMULL_CLARK"
sub.levels = 2; sub.render_levels = 3
print("SUBSURF ok")

# 修改器顺序调整
bpy.context.view_layer.objects.active = brick
brick.select_set(True)
bpy.ops.object.modifier_move_to_index(modifier="Bevel", index=0)
print("MOVE ok, order =", [m.name for m in brick.modifiers])

# ============ 10 关键帧与运镜 ============
def fcurves_of(idblock):
    ad = getattr(idblock, "animation_data", None)
    if not ad or not ad.action: return []
    act = ad.action
    try:
        if hasattr(act, "fcurves") and len(act.fcurves):
            return list(act.fcurves)
    except Exception: pass
    out = []
    for layer in getattr(act, "layers", []):
        for strip in getattr(layer, "strips", []):
            for cb in getattr(strip, "channelbags", []):
                out.extend(getattr(cb, "fcurves", []))
    return out

bpy.ops.object.camera_add(location=(0, -40, 7))
cam = bpy.context.active_object
keys = [
    (1,   (1.35, -40.0, 7.10), (0.7, -10.0, 2.6)),
    (52,  (1.10, -30.0, 5.20), (0.8, -2.0, 3.0)),
    (104, (0.55, -20.0, 3.55), (0.9, 7.0, 3.4)),
    (156, (-0.20, -13.0, 2.60), (1.0, 11.0, 3.8)),
    (204, (-1.15, -7.6, 2.30), (1.30, 15.5, 4.55)),
    (240, (-1.00, -3.4, 2.25), (1.30, 17.0, 4.75)),
]
for f, loc, tgt in keys:
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.keyframe_insert("location", frame=f)
    cam.keyframe_insert("rotation_euler", frame=f)

fcs = fcurves_of(cam)
print("FCURVES ok, count =", len(fcs))
for fc in fcs:
    for kp in fc.keyframe_points:
        kp.interpolation = "BEZIER"
        kp.handle_left_type = "AUTO_CLAMPED"
        kp.handle_right_type = "AUTO_CLAMPED"
    if fc.array_index in (0, 2) and "location" in fc.data_path:
        mod = fc.modifiers.new("NOISE")
        mod.strength = 0.03; mod.scale = 50
        mod.phase = 12 if fc.array_index == 2 else 31
print("INTERP + NOISE ok")

# ============ 11 驱动器 ============
ctrl = bpy.data.objects.new("CTRL_Count", None)
ctrl.empty_display_size = 0.5
bpy.context.scene.collection.objects.link(ctrl)
ctrl["count"] = 20

def add_driver(owner, path, index=-1, expression="v", var_specs=None):
    fcurve = owner.driver_add(path) if index < 0 else owner.driver_add(path, index)
    drv = fcurve.driver
    drv.type = "SCRIPTED"
    for name, id_obj, data_path in (var_specs or []):
        var = drv.variables.new()
        var.name = name; var.type = "SINGLE_PROP"
        var.targets[0].id = id_obj
        var.targets[0].data_path = data_path
    drv.expression = expression
    return drv

add_driver(ctrl, '["count"]', expression="max(1, int(c))",
           var_specs=[("c", ctrl, '["count"]')])
print("DRIVER ok")

# frame 驱动的表达式
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, location=(0, 0, 3))
ball = bpy.context.active_object
add_driver(ball, "location", index=2, expression="2.0 + sin(frame/20.0)*0.5")
print("FRAME DRIVER ok")

# 约束
tgt = bpy.data.objects.new("Target", None)
bpy.context.scene.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO")
c.target = tgt
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"
print("CONSTRAINT ok:", c.type)

# ============ 12 集合与实例 ============
coll = bpy.data.collections.new("TestColl")
bpy.context.scene.collection.children.link(coll)
def link(o, c):
    for x in list(o.users_collection): x.objects.unlink(o)
    c.objects.link(o); return o
link(brick, coll)
print("COLLECTION ok, objects =", len(coll.objects))

# 集合实例
emp = bpy.data.objects.new("CollInst", None)
emp.instance_type = "COLLECTION"
emp.instance_collection = coll
emp.location = (8, 0, 0)
bpy.context.scene.collection.objects.link(emp)
print("COLLECTION INSTANCE ok")

# ============ 渲染验证 ============
bpy.ops.object.light_add(type="SUN", location=(6, -6, 12))
sun = bpy.context.active_object; sun.data.energy = 3.0
sc = bpy.context.scene
sc.camera = cam          # ← 必须设为场景相机
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1280; sc.render.resolution_y = 640
sc.frame_set(150)
sc.render.filepath = os.path.join(OUT, "advanced_verify.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
