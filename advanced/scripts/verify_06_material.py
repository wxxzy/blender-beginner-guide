# -*- coding: utf-8 -*-
"""验证 advanced/06-节点编辑器思维.md 与 07 的材质代码。"""
import bpy, sys, os, math

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# ---------- 节点模板 ----------
def new_mat(name):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    return m, nt, out

def add_bsdf(nt, out, base=(0.5,0.5,0.5,1), rough=0.6, metal=0.0,
             emit=None, emit_str=0.0, spec=0.5, alpha=1.0, loc=(200,0)):
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = loc
    b.inputs["Base Color"].default_value = base
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    if "Alpha" in b.inputs:
        b.inputs["Alpha"].default_value = alpha
    if emit is not None:
        key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[key].default_value = emit
        b.inputs["Emission Strength"].default_value = emit_str
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return b

def add_texcoord(nt, loc=(-800,0)):
    t = nt.nodes.new("ShaderNodeTexCoord"); t.location = loc; return t

def add_noise(nt, scale=5.0, detail=6.0, rough=0.55, dims="3D", loc=(-550,0)):
    n = nt.nodes.new("ShaderNodeTexNoise"); n.location = loc
    n.noise_dimensions = dims
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    return n

def add_ramp(nt, stops, loc=(-300,0)):
    r = nt.nodes.new("ShaderNodeValToRGB"); r.location = loc
    cr = r.color_ramp
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = stops[0][0]
    cr.elements[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = cr.elements.new(pos); e.color = col
    return r

def add_bump(nt, bsdf, height_out, strength=0.25, distance=0.08, loc=(-100,-320)):
    b = nt.nodes.new("ShaderNodeBump"); b.location = loc
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height_out, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return b

def add_math(nt, operation="MULTIPLY", value2=1.0, loc=(-100,0)):
    m = nt.nodes.new("ShaderNodeMath"); m.operation = operation; m.location = loc
    m.inputs[1].default_value = value2
    return m

def _s2l(c):
    return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def hex_to_linear(h, a=1.0):
    h = h.lstrip("#")
    r,g,b = (int(h[i:i+2],16)/255.0 for i in (0,2,4))
    return (_s2l(r),_s2l(g),_s2l(b),a)

# ---------- 白墙材质 ----------
def mat_plaster():
    m, nt, out = new_mat("M_Plaster")
    b = add_bsdf(nt, out, base=(0.72,0.70,0.66,1), rough=0.85)
    tc = add_texcoord(nt)
    n1 = add_noise(nt, scale=2.2, detail=8, rough=0.6, loc=(-560,100))
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    ramp1 = add_ramp(nt, [(0.35,(0.62,0.60,0.56,1)),(0.62,(0.82,0.80,0.76,1))], loc=(-330,100))
    nt.links.new(n1.outputs["Fac"], ramp1.inputs["Fac"])
    n2 = add_noise(nt, scale=14.0, detail=6, rough=0.7, loc=(-560,-180))
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    ramp2 = add_ramp(nt, [(0.40,(0,0,0,1)),(0.58,(0.55,0.55,0.55,1))], loc=(-330,-180))
    nt.links.new(n2.outputs["Fac"], ramp2.inputs["Fac"])
    mul = add_math(nt, "MULTIPLY", loc=(-80,0))
    nt.links.new(ramp1.outputs["Color"], mul.inputs[0])
    nt.links.new(ramp2.outputs["Color"], mul.inputs[1])
    nt.links.new(mul.outputs[0], b.inputs["Base Color"])
    add_bump(nt, b, n2.outputs["Fac"], strength=0.22, distance=0.05)
    return m

# ---------- 青砖材质 ----------
def mat_brick():
    m, nt, out = new_mat("M_Brick")
    b = add_bsdf(nt, out, rough=0.78)
    tc = add_texcoord(nt)
    # Voronoi 砖块
    vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.location = (-560, 0)
    vor.feature = "F1"; vor.distance = "EUCLIDEAN"
    vor.inputs["Scale"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    # 砖缝颜色
    ramp = add_ramp(nt, [(0.02,(0.05,0.05,0.05,1)),(0.08,(0.30,0.28,0.26,1)),(0.30,(0.36,0.33,0.30,1))], loc=(-330,0))
    nt.links.new(vor.outputs["Distance"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    # 苔痕
    moss = add_noise(nt, scale=4.0, detail=8, rough=0.7, loc=(-560,-260))
    nt.links.new(tc.outputs["Object"], moss.inputs["Vector"])
    mramp = add_ramp(nt, [(0.52,(0,0,0,1)),(0.66,(0.5,0.5,0.5,1))], loc=(-330,-260))
    nt.links.new(moss.outputs["Fac"], mramp.inputs["Fac"])
    mixn = add_math(nt, "MULTIPLY", loc=(-100,-260))
    nt.links.new(ramp.outputs["Color"], mixn.inputs[0])
    nt.links.new(mramp.outputs["Color"], mixn.inputs[1])
    nt.links.new(mixn.outputs[0], b.inputs["Base Color"])
    add_bump(nt, b, vor.outputs["Distance"], strength=0.5, distance=0.06)
    return m

# ---------- 场景：三个球体三种材质 ----------
mats = [mat_plaster(), mat_brick()]
for i, mt in enumerate(mats):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(i*2.6, 0, 1.2))
    s = bpy.context.active_object
    s.data.materials.append(mt)

# 地面
bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,0))
g = bpy.context.active_object
# 地面（用 add_bsdf 而不是空节点）
gm, gnt, gout = new_mat("M_Ground")
gb = add_bsdf(gnt, gout, base=(0.3,0.3,0.32,1), rough=0.8)
g.data.materials.append(gm)

bpy.ops.object.light_add(type="AREA", location=(2, -4, 8))
lamp = bpy.context.active_object
lamp.data.energy = 600; lamp.data.size = 6
lamp.rotation_euler = (math.radians(50), 0, 0)
bpy.ops.object.camera_add(location=(1.2, -7, 3.4))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(76), 0, 0)
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1200; sc.render.resolution_y = 700
sc.render.filepath = os.path.join(OUT, "material_verify.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
