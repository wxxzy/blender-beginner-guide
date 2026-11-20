# 配套脚本

本目录下的脚本都是**实际运行验证过的**，可以直接跑。每个脚本对应教程中的某个章节。

## 运行方式

```bash
blender -b --factory-startup -noaudio -P <脚本>.py -- ./out
```

`--` 之后的内容会作为脚本参数传入（脚本里用 `sys.argv` 读取）。

## 脚本清单

| 脚本 | 对应章节 | 内容 | 验证输出 |
|------|---------|------|---------|
| `verify_01_bmesh.py` | [01 bmesh](01-bmesh网格编程.md) | 倒角立方体、程序化拱券、物体合并 | `BEVEL verts=96` / `ARCH verts=132 faces=98` / `MERGE 482→490` |
| `verify_03_roof.py` | [03 程序化曲面](03-程序化曲面.md) | 中式起翘屋面 + 瓦当 + 参数化生成一排屋顶 | `ROOF verts=640 faces=410` |
| `verify_05_geonodes.py` | [05 几何节点](05-几何节点入门.md) | 面上随机分布实例 | `GN built, nodes = 6` |
| `verify_06_material.py` | [06 节点编辑器](06-节点编辑器思维.md)、[07 程序化纹理](07-程序化纹理.md) | 白墙风化 + 青砖苔痕材质 | `RENDER_OK` |
| `verify_09_compositor.py` | [09 渲染与后期](09-渲染与后期合成.md) | 完整后期链路：Bloom→调色→S曲线→暗角→畸变 | `COMP nodes = 11` |
| `verify_10_advanced.py` | [02](02-修改器系统.md)/[10](10-关键帧与运镜.md)/[11](11-约束与驱动器.md)/[12](12-场景工程化.md) | 修改器栈、F曲线、驱动器、约束、集合实例 | `FCURVES count=6` / `DRIVER ok` / `CONSTRAINT ok` |

## 渲染产物

运行后会生成 `out/` 目录，内含各脚本的验证渲染图：

- `bmesh_verify.png` —— 倒角立方体 + 拱券 + 合并效果
- `roof_verify.png` —— 一排程序化生成的起翘屋面
- `geonodes_verify.png` —— 几何节点随机分布
- `material_verify.png` —— 程序化白墙与青砖材质
- `comp_verify.png` —— 后期合成链路效果
- `advanced_verify.png` —— 修改器 + 关键帧 + 约束的综合效果

这些图已被复制到 `../images/` 用作教程配图。

## 关于验证

**这些脚本不是示例代码，是跑通过的代码。** 教程里写的每个 API 调用都在这里实测过，包括那些踩过的坑：

- `bm.faces.new()` 端面重复 → 改用 `contextual_create` + `remove_doubles`
- 多坡共用 bmesh 的索引错位 → 用局部索引
- `ColorBalance` 同名 socket 有 VALUE/RGBA 两个 → 按 `type` 匹配
- `CompositorNodeBlur.Size` 是两分量向量
- `ShaderNodeMix` 在合成器里 A/B 是 6/7 号插槽
- 几何节点 `Seed` 必须是 int
- `primitive_cube_add(size=...)` 只接受 float，尺寸用 `dimensions`
- 材质 `use_nodes` 在 6.0 将废弃
- `view_settings.look` 在 5.2 只有 `NONE`

## 自定义运行

想改参数试试，加命令行参数即可：

```bash
# 改屋面数量与间距（需先改脚本里的常量）
blender -b --factory-startup -noaudio -P verify_03_roof.py -- ./my_out
```

---

[← 返回目录](README.md)
