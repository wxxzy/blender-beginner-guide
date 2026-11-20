# -*- coding: utf-8 -*-
"""验证 advanced/05-几何节点入门.md：几何节点 API 实测。"""
import bpy, sys, os, math

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# ---------- 建一个网格物体作为分布面 ----------
bpy.ops.mesh.primitive_grid_add(x_subdivisions=12, y_subdivisions=12, size=8)
plane = bpy.context.active_object
plane.name = "Ground"

# ---------- 建几何节点组 ----------
ng = bpy.data.node_groups.new("ScatterTest", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

gin  = ng.nodes.new("NodeGroupInput")
gout = ng.nodes.new("NodeGroupOutput")
gin.location  = (-600, 0)
gout.location = (600, 0)

# 分布式节点
dist = ng.nodes.new("GeometryNodeDistributePointsOnFaces")
dist.location = (-300, 0)
try:
    dist.distribute_method = "RANDOM"
except Exception as e:
    print("distribute_method err:", repr(e))
for name, val in [("Density", 3.0), ("Seed", 7.0)]:
    try:
        dist.inputs[name].default_value = val
    except Exception as e:
        print("input", name, "err:", repr(e))

# 实例化节点
inst = ng.nodes.new("GeometryNodeInstanceOnPoints")
inst.location = (0, 0)
try:
    inst.inputs["Pick Instance"].default_value = True
except Exception as e:
    print("pick instance err:", repr(e))

# 缩放实例节点
scl = ng.nodes.new("GeometryNodeScaleInstances")
scl.location = (300, 0)
try:
    scl.inputs["Scale"].default_value = (0.12, 0.12, 0.12)
except Exception as e:
    print("scale err:", repr(e))

# 网格线（做一个小实例）
line = ng.nodes.new("GeometryNodeMeshLine")
line.location = (-300, -300)
try:
    line.inputs["Count"].default_value = 8
    line.mode = "OFFSET"
    line.inputs["Offset"].default_value = (0.09, 0.0, 0.0)
except Exception as e:
    print("line err:", repr(e))

# 连接
ng.links.new(gin.outputs["Geometry"], dist.inputs["Mesh"])
ng.links.new(dist.outputs["Points"], inst.inputs["Points"])
ng.links.new(line.outputs["Mesh"], inst.inputs["Instance"])
ng.links.new(inst.outputs["Instances"], scl.inputs["Instances"])
ng.links.new(scl.outputs["Instances"], gout.inputs["Geometry"])

# ---------- 挂到物体上 ----------
mod = plane.modifiers.new("Scatter", "NODES")
mod.node_group = ng

print("GN built, nodes =", len(ng.nodes))

# ---------- 渲染验证 ----------
bpy.ops.object.light_add(type="SUN", location=(6, -6, 10))
sun = bpy.context.active_object; sun.data.energy = 3.0
bpy.ops.object.camera_add(location=(10, -12, 8))
cam = bpy.context.active_object
cam.rotation_euler = (1.05, 0, 0.72)
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1200; sc.render.resolution_y = 700
sc.render.filepath = os.path.join(OUT, "geonodes_verify.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
