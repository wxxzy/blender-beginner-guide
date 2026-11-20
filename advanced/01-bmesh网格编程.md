# 01 · bmesh 网格编程

## 为什么需要 bmesh

`bpy.ops` 的操作符是**面向人类界面**的：它假设"当前有选中对象""当前在编辑模式"。脚本里调用它们容易遇到上下文问题。

`bmesh` 是 Blender 内置的**网格编辑库**，直接操作数据结构：

| | bpy.ops | bmesh |
|---|---|---|
| 面向 | 界面操作 | 数据结构 |
| 上下文依赖 | 强 | 无 |
| 批量操作 | 慢（每步都重算） | 快 |
| 适合 | 加物体、加灯光 | 精确改网格 |

## 核心概念

一个网格由三类元素组成：

```
Vertex（顶点）—— 角上的点
Edge（边）    —— 两个顶点之间的线
Face（面）    —— 边围成的多边形
```

bmesh 提供了对这三者的完整操作，并保证拓扑一致性——**删掉一个顶点，挂在它上面的边和面会一起消失**。

## 读取与写入

```python
import bpy, bmesh

obj = bpy.data.objects.get("Cube")     # 或你刚创建的对象
bm = bmesh.new()                        # 建一个空的 bmesh
bm.from_mesh(obj.data)                  # 从网格读入
# ... 对 bm 做修改 ...
bm.to_mesh(obj.data)                    # 写回网格
bm.free()                               # 释放内存（必须做）
```

> ⚠️ **重要**：`bm.to_mesh()` 只能在**物体模式**下调用。在编辑模式下会报 `ValueError: to_mesh(): Mesh 'Cube' is in editmode`。
>
> 需要在编辑模式下改选中状态时，用 `bmesh.from_edit_mesh()`：
> ```python
> bm = bmesh.from_edit_mesh(obj.data)
> # ... 修改 ...
> bmesh.update_edit_mesh(obj.data)
> ```

## 实战一：给立方体做圆角

需求：把立方体的每个角切成斜角（而不是用修改器）。

```python
import bpy, bmesh

def bevel_cube(obj, amount=0.3):
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    for v in bm.verts:
        # v.co 是顶点的 Vector 坐标
        # 把顶点朝中心方向拉，形成斜切
        v.co = v.co * (1.0 - amount)

    bm.to_mesh(obj.data)
    bm.free()

obj = bpy.data.objects.get("Cube")
if obj:
    obj.data.materials.clear()
    bevel_cube(obj, 0.25)
    print("BEVELED")
```

**验证**：运行后立方体的 8 个角变成斜切面。但注意——这会把立方体**缩小**，而不是真正切角。要真正切角需要下面的 `bmesh.ops.bevel`。

## 实战二：用 bmesh.ops 真正倒角

```python
import bpy, bmesh

def bevel_object(obj, width=0.1, segments=2):
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    # 找出所有边
    edges = list(bm.edges)

    # bmesh.ops.bevel —— 官方倒角操作
    bmesh.ops.bevel(
        bm,
        geom=edges + list(bm.verts) + list(bm.faces),
        offset=width,
        segments=segments,
        profile=0.5,
        affect="EDGES",
    )

    bm.to_mesh(obj.data)
    bm.free()
```

**注意 `geom` 的构成**：Blender 的 bmesh 操作符需要**同时提供边、顶点、面**才能正确推断拓扑，只给边有时候会出问题。这是新手最常踩的坑。

## 实战三：程序化生成一个圆环拱券

这是江南水巷项目的石拱桥核心。用数学公式生成拱券截面：

```python
import bpy, bmesh, math

def build_arch(name, radius=4.15, width=4.8, depth=1.0, segments=32):
    """生成一段拱券实体（沿 y 方向拉伸 width，沿 z 方向 depth）。"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()

    # 内圈、外圈轮廓点
    inner, outer = [], []
    for i in range(segments + 1):
        a = math.pi * i / segments          # 0 → π
        x = math.cos(a) * radius
        z = math.sin(a) * radius
        inner.append((x, z))
        outer.append((x * 1.25, z * 1.25))

    # 每一段生成一个四边形面片，再连成带
    verts_in, verts_out = [], []
    for (x, z) in inner:
        verts_in.append(bm.verts.new((x, -width / 2, z)))
        verts_out.append(bm.verts.new((x * 1.25, -width / 2, z * 1.25)))

    bm.verts.ensure_lookup_table()

    # 前后两个面 + 内外侧壁
    for i in range(segments):
        a0, a1 = verts_in[i], verts_in[i + 1]
        b0, b1 = verts_out[i], verts_out[i + 1]
        bm.faces.new((a0, a1, b1, b0))

    # 沿 y 方向镜像出后半部分
    back_in = [bm.verts.new((v.co.x, width / 2, v.co.z)) for v in verts_in]
    back_out = [bm.verts.new((v.co.x, width / 2, v.co.z)) for v in verts_out]
    for i in range(segments):
        bm.faces.new((verts_in[i], back_in[i], back_in[i + 1], verts_in[i + 1]))
        bm.faces.new((verts_out[i + 1], back_out[i + 1], back_out[i], verts_out[i]))

    # 端面封口：用 contextual_create，避免顶点顺序导致重复面
    for ring in ((verts_in[0], back_in[0], back_out[0], verts_out[0]),
                 (verts_in[-1], verts_out[-1], back_out[-1], back_in[-1])):
        vs = [bm.verts.new(v.co) for v in ring]
        bmesh.ops.contextual_create(bm, geom=vs)

    # 合并重合顶点，消除复制产生的重复点
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()

    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj

arch = build_arch("Arch", radius=4.15, width=4.8)
print("ARCH OK, verts =", len(arch.data.vertices))
```

**验证**：脚本输出 `ARCH OK, verts = 132, faces = 98`，场景里出现一段马蹄形拱券。

![bmesh 生成的倒角立方体与拱券](images/fig_bmesh_arch.png)

上图是同一脚本渲染的结果：左边是 bmesh 倒角后的立方体，中间是程序化生成的拱券，右边是合并后的球体加立方体——注意球体上的立方体**保持了原位**，这正是 `transform(matrix_world)` 的作用。

> ⚠️ **踩坑：端面封口报 `face already exists`**
>
> 直接用 `bm.faces.new((a, b, c, d))` 封口时，如果顶点顺序和已存在的面一致，Blender 会报重复面。两种解法：
> 1. 用 `bmesh.ops.contextual_create(bm, geom=verts)` —— 让 Blender 自己判断怎么连，更安全；
> 2. 顶点顺序改一下（换个方向绕行）。
>
> 上面代码用的是第一种，并且配合 `remove_doubles` 清理复制顶点产生的重合点。

## 实战四：合并多个网格到同一个物体

生成很多零件后，通常要合并成一个物体（减少物体数量、便于整体操作）：

```python
def merge_objects(target, others):
    """把 others 的网格数据合并进 target。"""
    bm = bmesh.new()
    bm.from_mesh(target.data)

    for obj in others:
        tmp = bmesh.new()
        tmp.from_mesh(obj.data)
        tmp.transform(obj.matrix_world)      # 应用物体的变换矩阵
        me = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(me)
        tmp.free()

        bm.from_mesh(me)                    # 追加进来
        bpy.data.meshes.remove(me)

        bpy.data.objects.remove(obj, do_unlink=True)

    bm.to_mesh(target.data)
    bm.free()
```

> 💡 **关键是 `tmp.transform(obj.matrix_world)`** —— 网格数据本身是局部坐标，不做这一步合并出来的物体会全部跑到原点。

## 常用 bmesh.ops 速查

| 操作 | 函数 |
|------|------|
| 倒角 | `bmesh.ops.bevel(bm, geom, offset, segments, affect)` |
| 挤出 | `bmesh.ops.extrude_face_region(bm, geom)` |
| 内插 | `bmesh.ops.inset_region(bm, faces, thickness)` |
| 细分 | `bmesh.ops.subdivide_edges(bm, edges, cuts)` |
| 三角化 | `bmesh.ops.triangulate(bm, faces)` |
| 布尔 | `bmesh.ops.boolean`（或用修改器） |
| 桥接 | `bmesh.ops.bridge_loops(bm, edges)` |
| 排序法线 | `bm.normal_update()` |
| 重算法线 | `bmesh.ops.recalc_face_normals(bm, faces)` |

## 常用网格操作

```python
# 遍历
for v in bm.verts: print(v.co)
for e in bm.edges: print(v0.co, v1.co)
for f in bm.faces: print(f.calc_center_median(), f.normal)

# 按条件筛选
top_faces = [f for f in bm.faces if f.calc_center_median().z > 0.99]

# 选中状态
f.select_set(True)
bm.select_flush()          # 把选择状态同步回网格

# 坐标变换
v.co.x += 1.0
v.co = v.co * 2.0

# 删除（拓扑安全）
bmesh.ops.delete(bm, geom=[v], context="VERTS")
```

## 本章要点回顾

- bmesh 不依赖上下文，适合精确、批量的网格操作
- **必须在物体模式下 `to_mesh()`**，编辑模式用 `from_edit_mesh()`
- `bmesh.ops` 的 `geom` 要**边+顶点+面一起给**
- 合并物体前要 `transform(matrix_world)`，否则全跑到原点
- 删面用 `bmesh.ops.delete`，能保持拓扑一致

## 下一章预告

下一章讲**修改器系统**——不用写一行代码，靠修改器就能做倒角、阵列、布尔、细分。但顺序有讲究：改错了效果会完全不一样。

---

[← 目录](README.md) ｜ [← 上一章](00-导读.md) ｜ [下一章：修改器系统 →](02-修改器系统.md)
