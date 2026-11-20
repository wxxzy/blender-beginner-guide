# -*- coding: utf-8 -*-
"""验证 advanced/01-bmesh网格编程.md 中的代码片段可运行。"""
import bpy, bmesh, math, sys

OUT = sys.argv[sys.argv.index("--") + 1]
import os; os.makedirs(OUT, exist_ok=True)

# --- 清空场景 ---
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# ============ 实战一 / 二：倒角 ============
def bevel_object(obj, width=0.1, segments=2):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = list(bm.edges)
    bmesh.ops.bevel(bm, geom=edges + list(bm.verts) + list(bm.faces),
                    offset=width, segments=segments, profile=0.5, affect="EDGES")
    bm.to_mesh(obj.data)
    bm.free()

bpy.ops.mesh.primitive_cube_add(size=2, location=(-4, 0, 1))
cube = bpy.context.active_object
cube.name = "BevelCube"
bevel_object(cube, 0.12, 3)
print("BEVEL verts =", len(cube.data.vertices))

# ============ 实战三：拱券 ============
def build_arch(name, radius=4.15, width=4.8, segments=32):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    inner, outer = [], []
    for i in range(segments + 1):
        a = math.pi * i / segments
        x = math.cos(a) * radius
        z = math.sin(a) * radius
        inner.append((x, z))
        outer.append((x * 1.25, z * 1.25))
    verts_in, verts_out = [], []
    for (x, z) in inner:
        verts_in.append(bm.verts.new((x, -width/2, z)))
        verts_out.append(bm.verts.new((x*1.25, -width/2, z*1.25)))
    for i in range(segments):
        a0, a1 = verts_in[i], verts_in[i+1]
        b0, b1 = verts_out[i], verts_out[i+1]
        bm.faces.new((a0, a1, b1, b0))
    back_in = [bm.verts.new((v.co.x, width/2, v.co.z)) for v in verts_in]
    back_out = [bm.verts.new((v.co.x, width/2, v.co.z)) for v in verts_out]
    for i in range(segments):
        bm.faces.new((verts_in[i], back_in[i], back_in[i+1], verts_in[i+1]))
        bm.faces.new((verts_out[i+1], back_out[i+1], back_out[i], verts_out[i]))
    # 端面封口：用 contextual_create 避免顶点顺序导致的重���面
    for ring in ((verts_in[0], back_in[0], back_out[0], verts_out[0]),
                 (verts_in[-1], verts_out[-1], back_out[-1], back_in[-1])):
        vs = [bm.verts.new(v.co) for v in ring]
        bmesh.ops.contextual_create(bm, geom=vs)
    # 合并重合顶点，消除刚才复制产生的重复点
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj

arch = build_arch("Arch", radius=4.15, width=4.8)
print("ARCH OK, verts =", len(arch.data.vertices), "faces =", len(arch.data.polygons))

# ============ 实战四：合并 ============
def merge_objects(target, others):
    bm = bmesh.new()
    bm.from_mesh(target.data)
    for obj in others:
        tmp = bmesh.new()
        tmp.from_mesh(obj.data)
        tmp.transform(obj.matrix_world)
        me = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(me); tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        bpy.data.objects.remove(obj, do_unlink=True)
    bm.to_mesh(target.data)
    bm.free()

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(3, 2, 1))
s1 = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=1, location=(3, -2, 0.5))
s2 = bpy.context.active_object
before = len(s1.data.vertices)
merge_objects(s1, [s2])
print("MERGE OK, verts", before, "->", len(s1.data.vertices))

# ============ 渲染验证 ============
bpy.ops.object.light_add(type="SUN", location=(6, -8, 12))
sun = bpy.context.active_object; sun.data.energy = 4.0
bpy.ops.object.camera_add(location=(10, -12, 8))
cam = bpy.context.active_object
cam.rotation_euler = (1.05, 0, 0.7)
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1280; sc.render.resolution_y = 720
sc.render.filepath = os.path.join(OUT, "bmesh_verify.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
