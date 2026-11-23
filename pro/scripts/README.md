# 验证脚本

这里每个脚本都是**实际跑通过**的，对应教程各章的代码。
跑完会在 `--` 指定的目录里生成 `out/` 结果，包含渲染图与材质库。

## 运行方式

```bash
blender -b --factory-startup -noaudio -P verify_pro_a.py -- ./out
```

Windows（Git Bash）：

```bash
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  -b --factory-startup -noaudio -P verify_pro_a.py -- ./out
```

## 脚本清单

| 脚本 | 覆盖章节 | 关键输出 | 耗时 |
|---|---|---|---|
| `verify_pro_a.py` | [01](../01-雕刻与重拓扑.md) [04](../04-角色绑定与蒙皮.md) [05](../05-UV与贴图烘焙.md) [07](../07-资产库与插件开发.md) | `SCULPT raw_verts=162 sculpt_verts=94170`<br>`RIG auto=True vgroups=3`<br>`UV layer=UVMap loops=24`<br>`ASSET ok`<br>`ADDON registered` | ~60 s |
| `verify_pro_b.py` | [02](../02-物理模拟-刚体与布料.md) | `SIMULATED frames=1..90`<br>`RIGID bricks=14`<br>`CLOTH verts=1681` | ~40 s |
| `verify_pro_c.py` | [03](../03-流体与毛发.md) | `FLUID liquid_mesh_verts=70742`<br>`HAIR particles=0`（后台计数为 0 属正常） | ~70 s |
| `verify_pro_d.py` | [06](../06-渲染进阶-体积光与色彩管理.md) | `RAYTRACING_ON`<br>`RENDER_OK d1/d2` | ~90 s |
| `verify_pro_e.py` | [05](../05-UV与贴图烘焙.md) [08](../08-几何节点进阶-循环与仿真.md) | `BAKE size=(1024,1024) saved=True`<br>`PAIRED_BY_INPUT True` | ~30 s |
| `verify_pro_f.py` | [08](../08-几何节点进阶-循环与仿真.md) | `PAIRED: True`<br>`NODES: 10`<br>`RENDER_OK f1_repeat_zone.png` | ~15 s |

总计约 5 分钟。流体那一步（`verify_pro_c.py`）单独占了 70 秒，因为 MPM 要解 80 帧。

## 输出说明

- `out/` 下的 `*.png` 是原始渲染图（教程里的 `images/*.jpg` 由它们压缩而来）
- `out/pro_ring_addon.py` 是 `verify_pro_a.py` 动态生成的插件文件
- `out/assetlib/stone_lib.blend` 是资产库示例

## 说明

- `--factory-startup` 会重置所有偏好，保证结果可复现
- 脚本内部每个功能独立 `try/except`，某一个失败不影响其余
- 每个成功项都打印 `RENDER_OK` 或具体数值，方便外层判断
- 所有物理/仿真都逐帧推进（`frame_set` 循环），这是后台模式的硬性要求
