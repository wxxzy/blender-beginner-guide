# -*- coding: utf-8 -*-
"""验证 advanced/09-渲染与后期合成.md 的合成器链路（5.2 API）。"""
import bpy, sys, os, math

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# 简单场景：几个发光球 + 地面
gm = bpy.data.materials.new("M_G"); gm.use_nodes = True
gb = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
gb.inputs["Base Color"].default_value = (0.25, 0.25, 0.28, 1.0)
bpy.ops.mesh.primitive_plane_add(size=20)
bpy.context.active_object.data.materials.append(gm)

for i, (x, e) in enumerate([(-3, 60), (0, 90), (3, 45)]):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(x, 0, 1.5))
    s = bpy.context.active_object
    m = bpy.data.materials.new(f"M_Emit{i}"); m.use_nodes=True
    b = next(n for n in m.node_tree.nodes if n.type=="BSDF_PRINCIPLED")
    b.inputs["Emission Color"].default_value = (1.0, 0.55, 0.2, 1.0)
    b.inputs["Emission Strength"].default_value = e
    s.data.materials.append(m)
    ld = bpy.data.lights.new(f"L{i}", "POINT"); ld.energy = e
    ob = bpy.data.objects.new(f"L{i}", ld); ob.location = (x,0,1.5)
    bpy.context.scene.collection.objects.link(ob)

bpy.ops.object.camera_add(location=(0, -8, 3))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(80), 0, 0)
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1000; sc.render.resolution_y = 600

# ---------- 合成器（5.2 节点组） ----------
ng = bpy.data.node_groups.new("TestComp", "CompositorNodeTree")
sc.compositing_node_group = ng
ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")

rl = ng.nodes.new("CompositorNodeRLayers"); rl.location = (-1000, 0)

glare = ng.nodes.new("CompositorNodeGlare"); glare.location = (-780, 120)
glare.inputs["Type"].default_value = "Bloom"
glare.inputs["Quality"].default_value = "High"
glare.inputs["Threshold"].default_value = 0.9
glare.inputs["Smoothness"].default_value = 0.5
glare.inputs["Strength"].default_value = 0.55
glare.inputs["Size"].default_value = 0.55
ng.links.new(rl.outputs["Image"], glare.inputs["Image"])

hs = ng.nodes.new("CompositorNodeHueSat"); hs.location = (-560, 120)
hs.inputs["Saturation"].default_value = 1.12
ng.links.new(glare.outputs["Image"], hs.inputs["Image"])

cb = ng.nodes.new("CompositorNodeColorBalance"); cb.location = (-360, 120)
cb.inputs["Type"].default_value = "Lift/Gamma/Gain"
# 注意：同名 socket 有 VALUE(float) 与 RGBA(color) 两个，必须按 type 匹配
lifts = [i for i in cb.inputs if i.name == "Lift" and i.type == "RGBA"]
gains = [i for i in cb.inputs if i.name == "Gain" and i.type == "RGBA"]
if lifts: lifts[0].default_value = (0.002,0.007,0.015,1.0)
if gains: gains[0].default_value = (1.05,1.00,0.94,1.0)
ng.links.new(hs.outputs["Image"], cb.inputs["Image"])

cur = ng.nodes.new("CompositorNodeCurveRGB"); cur.location = (-160, 120)
c = cur.mapping.curves[3]
while len(c.points) > 2: c.points.remove(c.points[1])
c.points[0].location = (0.0,0.0); c.points[1].location = (1.0,1.0)
c.points.new(0.26,0.20); c.points.new(0.74,0.80)
cur.mapping.update()
ng.links.new(cb.outputs["Image"], cur.inputs["Image"])

mix = ng.nodes.new("ShaderNodeMix"); mix.data_type="RGBA"; mix.blend_type="MIX"
mix.location = (140, 60)
mix.inputs[7].default_value = (0.010,0.016,0.030,1.0)
ng.links.new(cur.outputs["Image"], mix.inputs[6])

ell = ng.nodes.new("CompositorNodeEllipseMask"); ell.location = (-300,-260)
ell.inputs["Operation"].default_value = "Add"
ell.inputs["Value"].default_value = 1.0
ell.inputs["Position"].default_value = (0.5,0.5)
ell.inputs["Size"].default_value = (0.95,0.95)
blur = ng.nodes.new("CompositorNodeBlur"); blur.location = (-100,-260)
blur.inputs["Size"].default_value = (0.22, 0.22)   # VECTOR 两分量 (X, Y)
blur.inputs["Type"].default_value = "Gaussian"
ng.links.new(ell.outputs["Mask"], blur.inputs["Image"])

vig = ng.nodes.new("ShaderNodeMath"); vig.operation="MULTIPLY"; vig.location=(20,-260)
vig.inputs[1].default_value = 0.22
ng.links.new(blur.outputs["Image"], vig.inputs[0])
ng.links.new(vig.outputs[0], mix.inputs[0])

lens = ng.nodes.new("CompositorNodeLensdist"); lens.location=(340,60)
lens.inputs["Distortion"].default_value = -0.012
lens.inputs["Dispersion"].default_value = 0.006
ng.links.new(mix.outputs[2], lens.inputs["Image"])

gout = ng.nodes.new("NodeGroupOutput"); gout.location = (560,60)
ng.links.new(lens.outputs["Image"], gout.inputs["Image"])
sc.render.use_compositing = True

print("COMP nodes =", len(ng.nodes))

sc.render.filepath = os.path.join(OUT, "comp_verify.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
