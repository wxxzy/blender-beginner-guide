"""高级功能实测 · 批次 E
程序化材质烘焙为贴图 / 几何节点 Simulation Zone 结构验证
运行：blender -b --factory-startup -noaudio -P verify_pro_e.py -- <outdir>
"""
import bpy, os, sys, math, addon_utils

argv = sys.argv
OUT = argv[argv.index("--") + 1] if "--" in argv else os.path.expanduser("~/out")
os.makedirs(OUT, exist_ok=True)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ------------------------------------------------------- E1 烘焙
def e1_bake():
    clear()
    addon_utils.enable("cycles", default_set=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 6
    sc.cycles.use_denoising = False

    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = "BakeTarget"

    # UV
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 程序化材质：噪声 → 色带
    m = bpy.data.materials.new("M_Proc")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 6.0
    tex.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.06, 0.14, 0.30, 1)
    ramp.color_ramp.elements[1].color = (0.85, 0.45, 0.12, 1)
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    ob.data.materials.append(m)

    # 目标贴图节点（必须选中且为活动节点）
    img = bpy.data.images.new("BakedColor", 1024, 1024, alpha=False)
    tnode = nt.nodes.new("ShaderNodeTexImage")
    tnode.image = img
    tnode.select = True
    nt.nodes.active = tnode

    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, margin=12, use_clear=True)
    p = os.path.join(OUT, "e1_baked_diffuse.png")
    img.filepath_raw = p
    img.file_format = 'PNG'
    img.save()

    # 检查像素是否真的写进去了（非全黑）
    px = list(img.pixels[0:400])
    print("BAKE size=%s saved=%s sample_nonzero=%d" % (img.size[:], os.path.exists(p), sum(1 for v in px if v > 0.01)))


# ------------------------------------------------------- E2 几何节点仿真结构
def e2_gn_sim():
    clear()
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("SimDemo", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    gin = ng.nodes.new("NodeGroupInput")
    gout = ng.nodes.new("NodeGroupOutput")
    gin.location = (-600, 0)
    gout.location = (400, 0)

    sim_in = ng.nodes.new("GeometryNodeSimulationInput")
    sim_in.location = (-300, 0)
    sim_out = sim_in.paired_output
    sim_out.location = (150, 0)

    print("SIM_PAIRED:", sim_out is not None, "| in_sockets:", [s.name for s in sim_in.outputs])
    print("SIM_OUT_items_before:", [i.name for i in sim_out.state_items])

    # 加状态项：一个累积的几何
    try:
        sim_out.state_items.new("Geometry", "GEOMETRY")
        print("STATE_ITEM_OK:", [i.name for i in sim_out.state_items])
    except Exception as e:
        print("STATE_ITEM_ERR:", e)

    # 场景时间 → 驱动
    st = ng.nodes.new("GeometryNodeInputSceneTime")
    print("SCENE_TIME ok")

    print("SIM_NODES total=%d" % len(ng.nodes))


for fn, tag in [(e1_bake, "E1"), (e2_gn_sim, "E2")]:
    try:
        fn()
    except Exception as e:
        import traceback
        print("FAIL", tag, type(e).__name__, e)
        traceback.print_exc()
print("BATCH_E_DONE")
