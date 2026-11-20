# -*- coding: utf-8 -*-
"""验证 advanced/03-程序化曲面.md 的屋面生成代码。"""
import bpy, bmesh, math, os, sys, random
from mathutils import Matrix

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

def build_roof(name, cx, cy, width=6.0, depth=5.0,
               z_eave=3.2, z_ridge=4.6, curl=0.55):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    half = width / 2 + 0.85
    y0 = cy - depth / 2 - 0.45
    y1 = cy + depth / 2 + 0.45

    for s in (-1, 1):
        rows = []
        for j in range(6):
            y = y0 + (y1 - y0) * j / 5
            row = []
            for i in range(8):
                t = i / 7
                x = cx + s * half * t
                z = z_ridge - (z_ridge - z_eave) * (1 - (1 - t) ** 1.7)
                ey = max(0.0, abs(y - cy) - (depth / 2 + 0.45 - 1.05)) / 1.05
                z += curl * (ey ** 2.2) * (t ** 2.4)
                row.append((x, y, z))
            rows.append(row)

        # 建面片（vs 是当前坡的顶点列表，直接用局部索引）
        vs = [bm.verts.new(v) for row in rows for v in row]
        for j in range(5):
            for i in range(7):
                a = j * 8 + i
                quad = (vs[a], vs[a+1], vs[a+8+1], vs[a+8])
                if s < 0:
                    quad = tuple(reversed(quad))
                bm.faces.new(quad)

    # 檐口瓦当
    y = y0 + 0.12
    while y < y1 - 0.05:
        for s in (-1, 1):
            x = cx + s * half
            bmesh.ops.create_cone(
                bm, cap_ends=True, cap_tris=False, segments=8,
                radius1=0.058, radius2=0.058, depth=0.17,
                matrix=Matrix.Translation((x, y, z_eave - 0.03))
            )
        y += 0.34

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()

    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj

roof = build_roof("Roof", cx=0, cy=0)
print("ROOF verts =", len(roof.data.vertices), "faces =", len(roof.data.polygons))

# 平滑着色
bpy.ops.object.select_all(action="DESELECT")
roof.select_set(True)
bpy.context.view_layer.objects.active = roof
try:
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
    print("SMOOTH_BY_ANGLE ok")
except Exception as e:
    for p in roof.data.polygons:
        p.use_smooth = True
    print("smooth fallback:", repr(e))

# 材质
mat = bpy.data.materials.new("M_Tile")
mat.use_nodes = True
b = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
b.inputs["Base Color"].default_value = (0.16, 0.15, 0.15, 1)
b.inputs["Roughness"].default_value = 0.7
roof.data.materials.append(mat)

# 一排屋顶（参数化生成）
def make_roof_row(n, spacing, seed=0):
    rng = random.Random(seed)
    for i in range(n):
        w = rng.uniform(5.0, 7.5)
        d = rng.uniform(4.5, 6.0)
        ze = rng.uniform(3.0, 3.6)
        zr = ze + rng.uniform(1.2, 1.7)
        build_roof(f"RoofRow_{i:02d}", cx=spacing * i, cy=0,
                   width=w, depth=d, z_eave=ze, z_ridge=zr,
                   curl=rng.uniform(0.4, 0.75))

make_roof_row(5, 9.0, seed=7)
print("ROW built, objects =", len(bpy.data.objects))

# 渲染
bpy.ops.object.light_add(type="SUN", location=(6, -8, 12))
sun = bpy.context.active_object; sun.data.energy = 3.5
bpy.ops.object.camera_add(location=(14, -18, 10))
cam = bpy.context.active_object
cam.rotation_euler = (1.05, 0, 0.66)
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = 1400; sc.render.resolution_y = 700
sc.render.filepath = os.path.join(OUT, "roof_verify.png")
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
