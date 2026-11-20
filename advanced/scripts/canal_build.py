# -*- coding: utf-8 -*-
"""
河畔夜话 · Canal Town at Night
================================
从零程序化重建一条江南水巷夜景：
  河道 / 沿河民居 / 石拱桥 / 灯笼 / 中文发光招牌 / 乌篷船
夜晚光照、水面反射、相机运镜、乌篷船行进。

Usage
-----
  blender -b --factory-startup --python build_river_town.py -- --out <dir>
  ... --mode preview                 # 3 张构图预览
  ... --mode hero --frame 210 --res 2400x1350 --samples 96
  ... --mode frames --count 32 --res 1600x900 --samples 64

除系统楷体字库外不依赖任何外部素材；固定随机种子，可重跑出同一场景。
"""

import bpy
import bmesh
import math
import os
import sys
import random
import time
from mathutils import Vector, Matrix

# ----------------------------------------------------------------------------
# 0. CONFIG
# ----------------------------------------------------------------------------

SEED = 20261031
FPS = 24
FRAME_START, FRAME_END = 1, 240

RIVER_HALF = 6.6          # 水面半宽 (m)
QUAY_Z = 1.05             # 河岸地面高度
BANK_X = 6.78             # 建筑临水立面 x

BRIDGE_Y = 16.5           # 石拱桥中心 y
BRIDGE_W = 4.8            # 桥面宽度 (沿 y)
BRIDGE_SPAN = 9.4         # 半跨
BRIDGE_R = 4.15           # 拱券半径

EXPOSURE = 2.35
FONT_PATH = "C:/Windows/Fonts/STKAITI.TTF"

rng = random.Random(SEED)

# 记录场景中所有发光体，用于生成水面反射光柱（x, y, z, 强度, 颜色）
GLOW_POINTS = []


def log(*a):
    print("[canal]", *a)
    sys.stdout.flush()


def fcurves_of(idblock):
    """Blender 5 slotted-action 兼容：取出某个 ID 的全部 fcurve。"""
    ad = getattr(idblock, "animation_data", None)
    if not ad or not ad.action:
        return []
    act = ad.action
    try:
        if hasattr(act, "fcurves") and len(act.fcurves):
            return list(act.fcurves)
    except Exception:
        pass
    out = []
    for layer in getattr(act, "layers", []):
        for strip in getattr(layer, "strips", []):
            for cb in getattr(strip, "channelbags", []):
                out.extend(getattr(cb, "fcurves", []))
    return out


# ----------------------------------------------------------------------------
# 1. COLOR / MATERIAL HELPERS
# ----------------------------------------------------------------------------

def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexc(h, a=1.0):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (_s2l(r), _s2l(g), _s2l(b), a)


def new_mat(name):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    return m, nt, out


def _bsdf(nt, out, base=(0.5, 0.5, 0.5, 1), rough=0.6, metal=0.0,
          emit=None, emit_str=0.0, spec=0.5, ior=1.45, alpha=1.0):
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = (150, 0)
    b.inputs["Base Color"].default_value = base
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["IOR"].default_value = ior
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


def _color_ramp(nt, stops, loc=(-200, 0)):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.location = loc
    cr = r.color_ramp
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = stops[0][0]
    cr.elements[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = cr.elements.new(pos)
        e.color = col
    return r


def _noise(nt, scale=5.0, detail=6.0, rough=0.55, loc=(-500, 0), dims="3D"):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.location = loc
    n.noise_dimensions = dims
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    return n


def _texcoord(nt, loc=(-750, 0)):
    t = nt.nodes.new("ShaderNodeTexCoord")
    t.location = loc
    return t


def _bump(nt, bsdf, height_out, strength=0.25, distance=0.08):
    b = nt.nodes.new("ShaderNodeBump")
    b.location = (-150, -320)
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height_out, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return b


# ---- concrete materials -----------------------------------------------------

def mat_plaster():
    """粉墙：暖灰白，带雨渍与颗粒。"""
    m, nt, out = new_mat("M_Plaster")
    b = _bsdf(nt, out, base=hexc("#948b7b"), rough=0.9, spec=0.2)
    tc = _texcoord(nt)
    n = _noise(nt, scale=3.0, detail=8, rough=0.62, loc=(-520, 60))
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    ramp = _color_ramp(nt, [
        (0.30, hexc("#7f786a")),
        (0.55, hexc("#8f8779")),
        (0.76, hexc("#a2988a")),
    ], loc=(-300, 60))
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])

    n2 = _noise(nt, scale=38.0, detail=4, loc=(-520, -300))
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    _bump(nt, b, n2.outputs["Fac"], strength=0.16, distance=0.03)
    return m


def mat_stone(name="M_Stone", c1="#54524a", c2="#43413b", mortar="#232320", scale=1.0):
    m, nt, out = new_mat(name)
    b = _bsdf(nt, out, base=(0.2, 0.2, 0.19, 1), rough=0.7, spec=0.45)
    tc = _texcoord(nt)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.location = (-360, 60)
    br.inputs["Color1"].default_value = hexc(c1)
    br.inputs["Color2"].default_value = hexc(c2)
    br.inputs["Mortar"].default_value = hexc(mortar)
    br.inputs["Scale"].default_value = scale
    br.inputs["Mortar Size"].default_value = 0.035
    br.inputs["Mortar Smooth"].default_value = 0.4
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Brick Width"].default_value = 0.46
    br.inputs["Row Height"].default_value = 0.22
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    _bump(nt, b, br.outputs["Fac"], strength=0.85, distance=0.05)
    return m


def mat_wood(name="M_Wood", col="#3a281c", rough=0.62):
    m, nt, out = new_mat(name)
    b = _bsdf(nt, out, base=hexc(col), rough=rough, spec=0.35)
    tc = _texcoord(nt)
    n = _noise(nt, scale=14, detail=7, loc=(-500, 40))
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    ramp = _color_ramp(nt, [(0.34, hexc("#211610")), (0.66, hexc(col))], loc=(-300, 40))
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    _bump(nt, b, n.outputs["Fac"], strength=0.2, distance=0.02)
    return m


def mat_roof_tile():
    m, nt, out = new_mat("M_RoofTile")
    b = _bsdf(nt, out, base=hexc("#333a43"), rough=0.5, spec=0.65)
    tc = _texcoord(nt)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = (-420, 60)
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 8.0
    wave.inputs["Distortion"].default_value = 1.2
    wave.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    ramp = _color_ramp(nt, [(0.22, hexc("#1e2329")), (0.62, hexc("#454d58"))], loc=(-220, 60))
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    _bump(nt, b, wave.outputs["Fac"], strength=0.6, distance=0.05)
    return m


def mat_emit(name, col, strength, base=None):
    m, nt, out = new_mat(name)
    _bsdf(nt, out, base=base or hexc(col), rough=0.4, emit=hexc(col), emit_str=strength)
    return m


def mat_water():
    """水面：低粗糙度 + 双层流动噪声凹凸，EEVEE 光追反射。"""
    m, nt, out = new_mat("M_Water")
    b = _bsdf(nt, out, base=hexc("#0e2d36"), rough=0.055, spec=1.0, ior=1.333)
    tc = _texcoord(nt)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.location = (-620, 0)
    mp.inputs["Scale"].default_value = (1.0, 1.5, 1.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    n1 = _noise(nt, scale=5.5, detail=6, rough=0.6, loc=(-400, 130), dims="4D")
    nt.links.new(mp.outputs["Vector"], n1.inputs["Vector"])
    n2 = _noise(nt, scale=26.0, detail=4, rough=0.5, loc=(-400, -230), dims="4D")
    nt.links.new(mp.outputs["Vector"], n2.inputs["Vector"])

    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "FLOAT"
    mix.blend_type = "ADD"
    mix.inputs[0].default_value = 0.3
    nt.links.new(n1.outputs["Fac"], mix.inputs[2])
    nt.links.new(n2.outputs["Fac"], mix.inputs[3])
    _bump(nt, b, mix.outputs[0], strength=0.18, distance=0.05)

    for node, end in ((n1, 2.4), (n2, 4.0)):
        sock = node.inputs["W"]
        sock.default_value = 0.0
        sock.keyframe_insert("default_value", frame=FRAME_START)
        sock.default_value = end
        sock.keyframe_insert("default_value", frame=FRAME_END)
    for fc in fcurves_of(m.node_tree):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    return m


def _metal():
    m, nt, out = new_mat("M_Iron")
    _bsdf(nt, out, base=hexc("#171615"), rough=0.42, metal=0.9)
    return m


def _moss():
    """水线苔痕：潮湿发绿。"""
    m, nt, out = new_mat("M_Moss")
    b = _bsdf(nt, out, base=hexc("#27331f"), rough=0.82, spec=0.35)
    tc = _texcoord(nt)
    n = _noise(nt, scale=12, detail=6, loc=(-420, 0))
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    ramp = _color_ramp(nt, [(0.32, hexc("#1a2416")), (0.7, hexc("#3b4a2c"))], loc=(-220, 0))
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def _foliage():
    m, nt, out = new_mat("M_Foliage")
    b = _bsdf(nt, out, base=hexc("#22301c"), rough=0.85)
    tc = _texcoord(nt)
    n = _noise(nt, scale=22, detail=6, loc=(-420, 0))
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    ramp = _color_ramp(nt, [(0.3, hexc("#182412")), (0.7, hexc("#33452a"))], loc=(-220, 0))
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def build_materials():
    M = {}
    M["plaster"] = mat_plaster()
    M["stone"] = mat_stone("M_Stone", "#3f3c35", "#302d27", "#100f0d", 1.0)
    M["stone_ring"] = mat_stone("M_StoneRing", "#57534a", "#454138", "#151513", 1.0)
    M["stone_dark"] = mat_stone("M_StoneDark", "#3a3833", "#2e2c28", "#181816", 1.0)
    M["paver"] = mat_stone("M_Paver", "#3c3a35", "#302e29", "#171714", 1.0)
    M["wood"] = mat_wood("M_Wood", "#3a281c", 0.62)
    M["wood_warm"] = mat_wood("M_WoodWarm", "#63432c", 0.55)
    M["wood_dark"] = mat_wood("M_WoodDark", "#211610", 0.7)
    M["tile"] = mat_roof_tile()
    M["glow_warm"] = mat_emit("M_WindowGlow", "#ffa050", 3.0, base=hexc("#2c1a09"))
    M["glow_soft"] = mat_emit("M_WindowGlowSoft", "#ffb478", 1.2, base=hexc("#2a1a0e"))
    M["lantern"] = mat_emit("M_LanternPaper", "#f22a0c", 3.4, base=hexc("#8c1b08"))
    M["sign"] = mat_emit("M_SignGlow", "#ffc46a", 9.0, base=hexc("#3a2410"))
    M["sign_cool"] = mat_emit("M_SignGlowCool", "#9fe0ff", 7.0, base=hexc("#12303c"))
    M["canopy"] = mat_wood("M_Canopy", "#241f1b", 0.82)
    M["metal"] = _metal()
    M["foliage"] = _foliage()
    M["moss"] = _moss()
    M["water"] = mat_water()
    return M


# ----------------------------------------------------------------------------
# 2. MESH BUILDER
# ----------------------------------------------------------------------------

class MB:
    """把大量盒子/圆柱/放样累积进一个 mesh，逐面材质与光滑标记。"""

    def __init__(self):
        self.v = []
        self.f = []
        self.fm = []
        self.fs = []

    def _v(self, co):
        self.v.append((float(co[0]), float(co[1]), float(co[2])))
        return len(self.v) - 1

    def face(self, idx, mat=0, smooth=False):
        if len(idx) < 3:
            return
        self.f.append(tuple(idx))
        self.fm.append(mat)
        self.fs.append(smooth)

    def box(self, center, size, mat=0, rot=None, smooth=False):
        cx, cy, cz = center
        hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        pts = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
               (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
        mat_r = Matrix.Identity(3) if rot is None else (
            Matrix.Rotation(rot[2], 3, 'Z') @ Matrix.Rotation(rot[1], 3, 'Y')
            @ Matrix.Rotation(rot[0], 3, 'X'))
        base = len(self.v)
        for p in pts:
            q = mat_r @ Vector(p)
            self._v((q.x + cx, q.y + cy, q.z + cz))
        for q in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                  (2, 3, 7, 6), (3, 0, 4, 7), (1, 2, 6, 5)]:
            self.face([base + i for i in q], mat, smooth)

    def beam(self, p0, p1, w, h, mat=0, smooth=False):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        if d.length < 1e-6:
            return
        z = d.normalized()
        up = Vector((0, 0, 1))
        if abs(z.dot(up)) > 0.98:
            up = Vector((1, 0, 0))
        x = z.cross(up).normalized()
        y = z.cross(x).normalized()
        base = len(self.v)
        for s in ((0, 0), (1, 0), (1, 1), (0, 1)):
            for e in (0.0, 1.0):
                c = p0 + d * e + x * (w * (s[0] - 0.5)) + y * (h * (s[1] - 0.5))
                self._v(c)
        self.face([base + 0, base + 1, base + 2, base + 3], mat)
        self.face([base + 7, base + 6, base + 5, base + 4], mat)
        for i in range(4):
            j = (i + 1) % 4
            self.face([base + i, base + j, base + 4 + j, base + 4 + i], mat, smooth)

    def cyl(self, p0, p1, r, seg=12, mat=0, caps=True, smooth=True, r2=None):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        if d.length < 1e-6:
            return
        z = d.normalized()
        up = Vector((0, 0, 1))
        if abs(z.dot(up)) > 0.98:
            up = Vector((1, 0, 0))
        x = z.cross(up).normalized()
        y = z.cross(x).normalized()
        r2 = r if r2 is None else r2
        base = len(self.v)
        for k in range(seg):
            a = 2 * math.pi * k / seg
            self._v(p0 + (x * math.cos(a) + y * math.sin(a)) * r)
        for k in range(seg):
            a = 2 * math.pi * k / seg
            self._v(p1 + (x * math.cos(a) + y * math.sin(a)) * r2)
        for k in range(seg):
            k2 = (k + 1) % seg
            self.face([base + k, base + k2, base + seg + k2, base + seg + k], mat, smooth)
        if caps:
            self.face([base + k for k in range(seg)][::-1], mat)
            self.face([base + seg + k for k in range(seg)], mat)

    def sphere(self, c, r, seg=16, rings=8, mat=0, scale=(1, 1, 1), smooth=True):
        base = len(self.v)
        for j in range(rings + 1):
            phi = math.pi * j / rings
            for i in range(seg):
                th = 2 * math.pi * i / seg
                self._v((c[0] + math.sin(phi) * math.cos(th) * r * scale[0],
                         c[1] + math.sin(phi) * math.sin(th) * r * scale[1],
                         c[2] + math.cos(phi) * r * scale[2]))
        for j in range(rings):
            for i in range(seg):
                i2 = (i + 1) % seg
                a = base + j * seg + i
                b = base + j * seg + i2
                cc = base + (j + 1) * seg + i2
                d = base + (j + 1) * seg + i
                self.face([a, b, cc, d], mat, smooth)

    def grid(self, rows, mat=0, smooth=False, flip=False, mat_fn=None):
        base = len(self.v)
        n = len(rows[0])
        for row in rows:
            for p in row:
                self._v(p)
        for j in range(len(rows) - 1):
            for i in range(n - 1):
                a = base + j * n + i
                b = a + 1
                c = base + (j + 1) * n + i + 1
                d = base + (j + 1) * n + i
                m = mat_fn(j, i) if mat_fn else mat
                if flip:
                    self.face([d, c, b, a], m, smooth)
                else:
                    self.face([a, b, c, d], m, smooth)

    def prism(self, pts, axis, a, b, mat=0, smooth=False):
        base = len(self.v)
        n = len(pts)

        def mk(u, v, w):
            if axis == "x":
                return (w, u, v)
            if axis == "y":
                return (u, w, v)
            return (u, v, w)

        for w in (a, b):
            for (u, v) in pts:
                self._v(mk(u, v, w))
        for i in range(n):
            j = (i + 1) % n
            self.face([base + i, base + j, base + n + j, base + n + i], mat, smooth)
        self.face([base + i for i in range(n)], mat)
        self.face([base + n + i for i in range(n)][::-1], mat)

    def build(self, name, mats, coll, recalc=True, smooth_all=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.validate(verbose=False)
        for m in mats:
            me.materials.append(m)
        for i, p in enumerate(me.polygons):
            p.material_index = min(self.fm[i], len(mats) - 1) if i < len(self.fm) else 0
            p.use_smooth = self.fs[i] if i < len(self.fs) else smooth_all
        if recalc:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
        me.update()
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


# ----------------------------------------------------------------------------
# 3. FOUNDATIONS: sky, water, quay
# ----------------------------------------------------------------------------

def build_world(sc):
    w = bpy.data.worlds.new("NightSky")
    sc.world = w
    if w.node_tree is None:
        w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    out.location = (400, 0)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.location = (200, 0)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-700, 0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-500, 0)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = _color_ramp(nt, [
        (0.40, hexc("#16202e")),
        (0.55, hexc("#101a28")),
        (0.90, hexc("#06090f")),
    ], loc=(-300, 0))
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.5
    nt.links.new(bg.outputs[0], out.inputs["Surface"])


def build_water(coll, M):
    mb = MB()
    mb.box((0, 0, -0.3), (RIVER_HALF * 2 + 6, 210, 0.6), 0)
    ob = mb.build("Water_Surface", [M["water"]], coll, recalc=False)
    ob.location = (0, -30, 0)
    return ob


def build_quay(coll, M):
    mb = MB()
    length, y0 = 200.0, -100.0
    for side in (1, -1):
        x = side * (RIVER_HALF + 0.14)
        mb.box((x, y0 + length / 2, (QUAY_Z - 1.7) / 2 - 0.45),
               (0.62, length, QUAY_Z + 1.3), 0)
        mb.box((x - side * 0.07, y0 + length / 2, QUAY_Z + 0.07),
               (0.86, length, 0.17), 1)
        # 水线苔痕
        mb.box((x + side * 0.06, y0 + length / 2, 0.12), (0.70, length, 0.30), 3)
        mb.box((side * (RIVER_HALF + 7.0), y0 + length / 2, QUAY_Z - 0.09),
               (13.0, length, 0.2), 2)
    for side in (1, -1):
        for yc in (-30.0, -12.0, 2.0, 24.0, 40.0):
            for k in range(6):
                mb.box((side * (RIVER_HALF - 0.02 - k * 0.27), yc,
                        QUAY_Z - 0.15 - k * 0.17), (0.34, 2.8, 0.17), 1)
    return mb.build("Bank_Quay",
                    [M["stone"], M["stone_dark"], M["paver"], M["moss"]], coll)


# ----------------------------------------------------------------------------
# 4. LANTERNS / SIGNS / PROPS
# ----------------------------------------------------------------------------

def lantern_mesh(M):
    if "LanternMesh" in bpy.data.meshes:
        return bpy.data.meshes["LanternMesh"]
    mb = MB()
    mb.sphere((0, 0, 0), 0.155, seg=18, rings=9, mat=0, scale=(1, 1, 1.14))
    mb.cyl((0, 0, 0.165), (0, 0, 0.205), 0.07, 12, mat=1)
    mb.cyl((0, 0, -0.195), (0, 0, -0.155), 0.07, 12, mat=1)
    mb.cyl((0, 0, 0.2), (0, 0, 0.28), 0.011, 6, mat=1, caps=False)
    mb.cyl((0, 0, -0.275), (0, 0, -0.19), 0.011, 6, mat=1, caps=False)
    mb.sphere((0, 0, -0.30), 0.04, seg=8, rings=5, mat=1, scale=(1, 1, 1.5))
    ob = mb.build("LanternMesh", [M["lantern"], M["wood_dark"]],
                  bpy.context.scene.collection, recalc=True)
    me = ob.data
    me.name = "LanternMesh"
    bpy.data.objects.remove(ob)
    return me


def add_lantern(coll, mesh, pos, scale=1.0, cord=0.0, name="Lantern"):
    GLOW_POINTS.append((pos[0], pos[1], pos[2], 1.0 * scale, "#ff7a30"))
    ob = bpy.data.objects.new(name, mesh)
    coll.objects.link(ob)
    ob.location = pos
    ob.scale = (scale, scale, scale)
    if cord > 0.01:
        mb = MB()
        mb.cyl((0, 0, 0.26), (0, 0, 0.26 + cord), 0.006, 4, 0, caps=False)
        c = mb.build(name + "_Cord", [bpy.data.materials["M_WoodDark"]], coll, recalc=False)
        c.location = pos
    return ob


def orient(ob, loc, normal, up=(0, 0, 1)):
    n = Vector(normal).normalized()
    u = Vector(up).normalized()
    if abs(n.dot(u)) > 0.99:
        u = Vector((0, 1, 0))
    x = u.cross(n).normalized()
    y = n.cross(x).normalized()
    ob.matrix_world = Matrix((
        (x.x, y.x, n.x, loc[0]),
        (x.y, y.y, n.y, loc[1]),
        (x.z, y.z, n.z, loc[2]),
        (0, 0, 0, 1)))


def text_obj(coll, body, font, size, mat, loc, normal=(0, -1, 0),
             extrude=0.012, name="Txt", res=6):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = font
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude
    cu.resolution_u = res
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    orient(ob, loc, normal)
    return ob


SIGN_WORDS = ["茶樓", "酒家", "客棧", "河鮮", "麵館", "燈影", "書院",
              "米行", "藥", "粥", "糖", "渡", "客", "樓", "閣", "酒"]


def add_sign(coll, M, font, anchor, normal, word, size=0.42, cool=False,
             board_w=None, name="Sign"):
    """发光中文招牌：木底板 + 边框 + 逐字发光。"""
    GLOW_POINTS.append((anchor[0], anchor[1], anchor[2], 1.15, "#ffb050"))
    n = Vector(normal).normalized()
    up = n.cross(Vector((0, 0, 1))).normalized()
    nchars = len(word)
    mat = M["sign_cool"] if cool else M["sign"]
    board_w = board_w or (size * 1.85)
    board_h = size * (nchars * 1.24 + 0.55)

    mb = MB()
    mb.box((0, 0, 0), (board_w, 0.07, board_h), 0)
    for sx in (-1, 1):
        mb.box((sx * board_w / 2, -0.015, 0), (0.045, 0.1, board_h + 0.05), 1)
    for sz in (-1, 1):
        mb.box((0, -0.015, sz * board_h / 2), (board_w + 0.05, 0.1, 0.045), 1)
    ob = mb.build(name + "_Board", [M["wood_dark"], M["wood"]], coll, recalc=True)
    ob.location = anchor
    ob.rotation_euler = (0, 0, math.atan2(up.y, up.x))

    for i, ch in enumerate(word):
        zz = (nchars - 1) * 0.5 * size * 1.24 - i * size * 1.24
        p = Vector(anchor) + Vector((0, 0, zz)) + n * 0.052
        text_obj(coll, ch, font, size, mat, p, normal=n,
                 extrude=0.01, name="%s_%s" % (name, ch))
    return ob


def add_potted_plant(coll, M, pos, scale=1.0):
    mb = MB()
    mb.cyl((0, 0, 0), (0, 0, 0.27 * scale), 0.16 * scale, 10, 0, smooth=True)
    mb.cyl((0, 0, 0.27 * scale), (0, 0, 0.29 * scale), 0.18 * scale, 10, 0, smooth=True)
    ob = mb.build("PlantPot", [M["stone_dark"]], coll, recalc=True)
    ob.location = pos
    mb2 = MB()
    for k in range(5):
        a = k / 5 * 2 * math.pi
        mb2.sphere((math.cos(a) * 0.13 * scale, math.sin(a) * 0.13 * scale,
                    0.44 * scale + 0.04 * math.sin(k)), 0.18 * scale,
                   seg=8, rings=5, mat=0, smooth=True)
    ob2 = mb2.build("PlantLeaves", [M["foliage"]], coll, recalc=True)
    ob2.location = pos


def make_streak_mesh():
    """反射光柱单元：局部 y 从 0（光源正下方）延伸到 -1（远处），UV.v 1→0。"""
    me = bpy.data.meshes.new("StreakMesh")
    # 远端收窄成梯形，倒影更像水面上的锥形光带
    me.from_pydata([(-0.5, 0, 0), (0.5, 0, 0), (0.20, -1, 0), (-0.20, -1, 0)],
                   [], [(0, 1, 2, 3)])
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    for i, uv in enumerate([(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]):
        uvl.data[i].uv = uv
    return me


def mat_streak():
    """倒影光柱材质：UV 渐变 × 流动噪声 → 半透明发光带。"""
    m, nt, out = new_mat("M_Streak")
    b = _bsdf(nt, out, base=(0.0, 0.0, 0.0, 1.0), rough=1.0,
              emit=hexc("#ff8034"), emit_str=1.35)
    tc = _texcoord(nt)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-520, 0)
    nt.links.new(tc.outputs["UV"], sep.inputs[0])
    grad = _color_ramp(nt, [(0.0, (0.0, 0.0, 0.0, 1)),
                             (0.45, (0.22, 0.22, 0.22, 1)),
                             (0.80, (0.55, 0.55, 0.55, 1)),
                             (1.0, (1.0, 1.0, 1.0, 1))], loc=(-330, 60))
    nt.links.new(sep.outputs["Y"], grad.inputs["Fac"])

    # 横向软边
    side = _color_ramp(nt, [(0.0, (0.0, 0.0, 0.0, 1)),
                             (0.32, (0.75, 0.75, 0.75, 1)),
                             (0.68, (0.75, 0.75, 0.75, 1)),
                             (1.0, (0.0, 0.0, 0.0, 1))], loc=(-330, -140))
    nt.links.new(sep.outputs["X"], side.inputs["Fac"])

    n = _noise(nt, scale=34.0, detail=8, rough=0.62, loc=(-330, -280), dims="4D")
    nr = _color_ramp(nt, [(0.30, (0.0, 0.0, 0.0, 1)),
                           (0.62, (1.0, 1.0, 1.0, 1))], loc=(-140, -280))
    nt.links.new(n.outputs["Fac"], nr.inputs["Fac"])

    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.location = (60, 40)
    nt.links.new(grad.outputs["Color"], mul.inputs[0])
    nt.links.new(side.outputs["Color"], mul.inputs[1])
    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.operation = "MULTIPLY"
    mul2.location = (200, -60)
    nt.links.new(mul.outputs[0], mul2.inputs[0])
    nt.links.new(nr.outputs["Color"], mul2.inputs[1])
    nt.links.new(mul2.outputs[0], b.inputs["Alpha"])

    sock = n.inputs["W"]
    sock.default_value = 0.0
    sock.keyframe_insert("default_value", frame=FRAME_START)
    sock.default_value = 3.2
    sock.keyframe_insert("default_value", frame=FRAME_END)
    for fc in fcurves_of(m.node_tree):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    m.use_backface_culling = False
    return m


def build_reflection_streaks(coll, M):
    """在每个发光体正下方的水面上铺一条倒影光柱。"""
    mesh = make_streak_mesh()
    mat = mat_streak()
    mesh.materials.append(mat)
    n = 0
    for (x, y, z, k, col) in GLOW_POINTS:
        if z < 0.06:
            continue
        length = z * 1.15 + 0.6 if z > 0.4 else 0.55
        width = (0.18 + z * 0.022) * (k / 0.85)
        ob = bpy.data.objects.new("Streak_%03d" % n, mesh)
        coll.objects.link(ob)
        ob.location = (x, y, 0.014)
        ob.scale = (width, length, 1.0)
        n += 1
    log("reflection streaks:", n)
    return n


# ----------------------------------------------------------------------------
# 5. HOUSES
# ----------------------------------------------------------------------------

def add_window(mb, mbg, cx, cy, cz, w, h, facing, mat_wood=0, lattice=True, lit=0):
    t = 0.065
    mb.box((cx - facing * 0.01, cy, cz + h / 2), (0.11, w, t), mat_wood)
    mb.box((cx - facing * 0.01, cy, cz - h / 2), (0.11, w, t), mat_wood)
    mb.box((cx - facing * 0.01, cy - w / 2, cz), (0.11, t, h), mat_wood)
    mb.box((cx - facing * 0.01, cy + w / 2, cz), (0.11, t, h), mat_wood)
    mbg.box((cx - facing * 0.022, cy, cz), (0.02, w - 0.10, h - 0.10), lit)
    if lattice:
        cols = max(3, int(w / 0.115))
        rows = max(3, int(h / 0.13))
        for i in range(1, cols):
            mb.box((cx - facing * 0.05, cy - w / 2 + i * w / cols, cz),
                   (0.04, 0.028, h - 0.02), mat_wood)
        for j in range(1, rows):
            mb.box((cx - facing * 0.05, cy, cz - h / 2 + j * h / rows),
                   (0.04, w - 0.02, 0.028), mat_wood)


def add_roof_surface(mb, cx, cy, wy, dx, z_eave, z_ridge, ov=0.85, curl=0.55,
                     mat=0, seg_t=7, seg_y=5):
    half = dx / 2 + ov
    y0 = cy - wy / 2 - 0.45
    y1 = cy + wy / 2 + 0.45
    for s in (-1, 1):
        rows = []
        for j in range(seg_y + 1):
            y = y0 + (y1 - y0) * j / seg_y
            row = []
            for i in range(seg_t + 1):
                t = i / seg_t
                x = cx + s * half * t
                z = z_ridge - (z_ridge - z_eave) * (1 - (1 - t) ** 1.7)
                ey = max(0.0, abs(y - cy) - (wy / 2 + 0.45 - 1.05)) / 1.05
                z += curl * (ey ** 2.2) * (t ** 2.4)
                row.append((x, y, z))
            rows.append(row)
        mb.grid(rows, mat=mat, smooth=True, flip=(s < 0))


def add_tile_ends(mb, cx, cy, wy, dx, z_eave, ov=0.85, mat=0, spacing=0.34, r=0.058):
    """檐口一排瓦当（圆头滴水），是中式屋檐剪影的关键细节。"""
    half = dx / 2 + ov
    y0 = cy - wy / 2 - 0.45
    y1 = cy + wy / 2 + 0.45
    y = y0 + 0.12
    while y < y1 - 0.05:
        for s in (-1, 1):
            x = cx + s * half
            mb.cyl((x, y, z_eave + 0.03), (x + s * 0.07, y, z_eave - 0.10),
                   r, 8, mat, smooth=True)
        y += spacing


def add_gua_luo(mbw, x_face, side, yc, width, z, mat=0):
    """檐下挂落：木格牙子，小而密，显著提升立面层次。"""
    x = x_face - side * 0.72
    n = max(4, int(width * 0.62 / 0.26))
    y0 = yc - width * 0.31
    step = width * 0.62 / n
    mbw.box((x, yc, z - 0.04), (0.05, width * 0.64, 0.05), mat)
    for i in range(n + 1):
        y = y0 + i * step
        mbw.box((x, y, z - 0.16), (0.04, 0.04, 0.26), mat)
    for i in range(n):
        y = y0 + i * step + step / 2
        mbw.box((x, y, z - 0.24), (0.035, 0.035, 0.18), mat)


def add_eave_band(mb, mbw, x_face, side, yc, width, z, out=0.55, mat_tile=1):
    """腰檐：楼层之间的小挑檐，打破立面的平板感。"""
    rows = []
    for j in (0, 1):
        row = []
        for i in range(5):
            t = i / 4
            x = x_face - side * (0.02 + out * t)
            row.append((x, yc - width / 2 - 0.15 + (width + 0.3) * j, z - 0.17 * t))
        rows.append(row)
    mb.grid(rows, mat=mat_tile, smooth=True, flip=(side > 0))
    mbw.box((x_face - side * (out * 0.5), yc, z - 0.21),
            (out, width + 0.25, 0.08), 0)


def build_house(coll, M, font, side, yc, width, depth, floors, style, idx,
                lantern_mesh, name_prefix="House", setback=0.0):
    fx = side * (BANK_X + setback)
    zb = QUAY_Z
    fh = 2.95 + rng.uniform(-0.12, 0.18)
    z_top = zb + fh * floors
    x0, x1 = sorted((fx, fx + side * depth))
    xm = (x0 + x1) / 2

    mb = MB()
    mbw = MB()
    mbg = MB()

    mb.box((xm, yc, zb + 0.22), (depth + 0.16, width + 0.08, 0.44), 2)
    mb.box((xm, yc, zb + (z_top - zb) / 2 + 0.3),
           (depth, width, z_top - zb - 0.3), 0)

    ncol = max(2, int(width / 1.55))
    for i in range(ncol + 1):
        y = yc - width / 2 + i * width / ncol
        mbw.box((fx + side * 0.02, y, zb + (z_top - zb) / 2),
                (0.12, 0.14, z_top - zb), 0)
    for f in range(floors + 1):
        mbw.box((fx + side * 0.02, yc, zb + f * fh), (0.15, width, 0.15), 0)

    # 底层木作门面（江南民居最典型的深色木板墙）
    panel_h = fh - 0.35
    mbw.box((fx - side * 0.028, yc, zb + 0.45 + panel_h / 2),
            (0.06, width * 0.94, panel_h), 1)
    # 竖向板缝
    for i in range(int(width * 0.94 / 0.26)):
        yy = yc - width * 0.47 + 0.13 + i * 0.26
        mbw.box((fx - side * 0.062, yy, zb + 0.45 + panel_h / 2),
                (0.02, 0.025, panel_h - 0.05), 0)

    door_w = min(1.75, width * 0.42)
    # 门口雨披
    mbw.box((fx - side * 0.45, yc - width * 0.26, zb + 2.62),
            (1.0, door_w + 0.7, 0.07), 1, rot=(0, side * 0.12, 0))


    mbw.box((fx + side * 0.05, yc - width * 0.26, zb + 1.2), (0.1, door_w, 2.3), 0)
    mbg.box((fx - side * 0.05, yc - width * 0.26, zb + 1.15), (0.02, door_w - 0.28, 1.9), 0)
    # 两扇门板（留一道缝透光）
    for ds in (-1, 1):
        mbw.box((fx - side * 0.075, yc - width * 0.26 + ds * (door_w * 0.28), zb + 1.15),
                (0.05, door_w * 0.42, 2.05), 2)
    for s in (-1, 1):
        yy = yc - width * 0.26 + s * (door_w / 2 + width * 0.11 + 0.04)
        mbw.box((fx + side * 0.045, yy, zb + 1.25), (0.07, width * 0.22, 2.4), 1)

    nwin = max(1, int(width / 2.0))
    for f in range(1, floors):
        z = zb + f * fh + fh / 2 + 0.02
        for k in range(nwin):
            y = yc - width / 2 + width / (nwin + 1) * (k + 1)
            add_window(mb, mbg, fx + side * 0.02, y, z, 0.86, 1.12, side,
                       lit=0 if rng.random() < 0.72 else 1)
            if rng.random() < 0.8:
                GLOW_POINTS.append((fx + side * 0.05, y, z, 0.75, "#ff9440"))

    if style in ("balcony", "shop") and floors >= 2:
        zbal = zb + fh
        mbw.box((fx + side * 0.4, yc, zbal + 0.05), (0.86, width * 0.84, 0.11), 1)
        for i in range(int(width * 0.84 / 0.3) + 1):
            y = yc - width * 0.42 + i * 0.3
            mbw.box((fx + side * 0.78, y, zbal + 0.48), (0.045, 0.045, 0.86), 0)
        mbw.box((fx + side * 0.78, yc, zbal + 0.94), (0.08, width * 0.84, 0.07), 1)
        mbw.box((fx + side * 0.78, yc, zbal + 0.58), (0.06, width * 0.84, 0.045), 1)
        add_eave_band(mb, mbw, fx, side, yc, width, zbal + 1.35, out=0.62)

    if floors >= 2 and style != "shop":
        add_eave_band(mb, mbw, fx, side, yc, width, zb + fh - 0.05, out=0.5)

    z_eave = z_top + 0.16
    z_ridge = z_eave + (depth * 0.5 + 0.85) * 0.5
    add_roof_surface(mb, xm, yc, width, depth, z_eave, z_ridge, ov=0.85, curl=0.55, mat=1)
    add_tile_ends(mb, xm, yc, width, depth, z_eave, ov=0.85, mat=1)
    mb.box((xm, yc, z_ridge + 0.07), (0.28, width + 0.95, 0.2), 2)
    add_gua_luo(mbw, fx, side, yc, width, z_eave - 0.30, mat=0)

    if style in ("gable", "balcony") and rng.random() < 0.8:
        hw = width / 2 + 0.45
        for sy in (-1, 1):
            yy = yc + sy * hw
            for tw, tz in ((1.02, z_eave + 0.5), (0.6, z_eave + 1.2), (0.26, z_ridge + 0.4)):
                mb.box((xm, yy, (z_eave + tz) / 2),
                       (depth + 0.48, 0.6 * tw + 0.34, tz - z_eave), 3)
                mb.box((xm, yy, tz + 0.04),
                       (depth + 0.6, 0.6 * tw + 0.48, 0.1), 2)

    mb.build(name_prefix + "_Body",
             [M["plaster"], M["tile"], M["wood_dark"], M["plaster"]], coll)
    mbw.build(name_prefix + "_Timber", [M["wood_dark"], M["wood"]], coll)
    mbg.build(name_prefix + "_Glow", [M["glow_warm"], M["glow_soft"]], coll, recalc=True)

    nlan = 2 + (idx % 3)
    for k in range(nlan):
        y = yc - width * 0.34 + (width * 0.68) * (k / max(1, nlan - 1))
        add_lantern(coll, lantern_mesh, (fx + side * 0.78, y, z_eave - 0.38),
                    scale=0.9 + 0.18 * rng.random(), cord=0.32,
                    name=name_prefix + "_Lantern_%d" % k)

    if rng.random() < 0.9:
        word = rng.choice(SIGN_WORDS)
        sy = yc + width * (0.3 if rng.random() < 0.5 else -0.32)
        # 挑出式招牌：面朝河道来向，从水路一眼可读
        add_sign(coll, M, font, (fx - side * 0.62, sy, zb + fh * 1.32),
                 normal=(0, -1, 0), word=word, size=0.42,
                 cool=(rng.random() < 0.15), name=name_prefix + "_Sign")
        mbw_s = MB()
        mbw_s.beam((fx, sy, zb + fh * 1.32 + 0.8), (fx - side * 0.75, sy, zb + fh * 1.32 + 0.86),
                   0.05, 0.05, 0)
        mbw_s.build(name_prefix + "_SignArm", [M["wood_dark"]], coll, recalc=False)
    if rng.random() < 0.88:
        word = rng.choice(["酒家", "茶", "麵", "客棧", "河鮮", "燈"])
        add_sign(coll, M, font, (fx + side * 1.05, yc - width * 0.36, zb + 2.55),
                 normal=(-side * 0.22, -1, 0), word=word, size=0.40,
                 name=name_prefix + "_HangSign")
    if rng.random() < 0.3:
        add_potted_plant(coll, M, (fx + side * 0.5, yc + width * 0.34, zb), 0.85)


def build_bank_row(coll, M, font, lantern_mesh, side, y_from, y_to, prefix):
    y = y_from
    i = 0
    while y < y_to:
        width = rng.uniform(4.8, 7.6)
        if abs((y + width / 2) - BRIDGE_Y) < 5.5:
            y += 1.8
            continue
        depth = rng.uniform(5.2, 7.8)
        floors = rng.choice([2, 2, 3, 1, 2, 3, 2])
        style = rng.choice(["balcony", "gable", "shop", "gable", "balcony", "flat"])
        build_house(coll, M, font, side, y + width / 2, width, depth, floors,
                    style, i, lantern_mesh,
                    name_prefix="%s_%02d" % (prefix, i),
                    setback=rng.uniform(0.0, 0.55))
        y += width + rng.uniform(0.3, 0.9)
        i += 1


def build_backdrop(coll, M):
    mb = MB()
    for side in (1, -1):
        y = -50.0
        while y < 50:
            w = rng.uniform(5, 9)
            d = rng.uniform(5, 8)
            f = rng.choice([2, 3, 3, 4])
            h = 2.95 * f
            x = side * (BANK_X + 9.0 + rng.uniform(0, 2.5))
            zt = QUAY_Z + h
            mb.box((x, y + w / 2, QUAY_Z + h / 2), (d, w, h), 0)
            ridge = zt + d * 0.3
            mb.prism([(x - d / 2 - 0.5, zt), (x + d / 2 + 0.5, zt), (x, ridge)],
                     "y", y - 0.3, y + w + 0.3, 1)
            y += w + rng.uniform(0.4, 1.6)
    return mb.build("Backdrop_Rooftops", [M["stone_dark"], M["tile"]], coll)


# ----------------------------------------------------------------------------
# 6. STONE ARCH BRIDGE  (实体：两侧墙 + 桥面 + 拱腹，全部四边形)
# ----------------------------------------------------------------------------

def build_bridge(coll, M, font, lantern_mesh):
    cy = BRIDGE_Y
    hw = BRIDGE_W / 2
    span = BRIDGE_SPAN
    r = BRIDGE_R
    z_spring = QUAY_Z + 0.02
    z_c, z_end = 6.05, 1.55
    N = 72

    def deck_z(x):
        return z_c - (z_c - z_end) * (x / span) ** 2

    def unders_z(x):
        if abs(x) >= r:
            return z_spring
        return z_spring + math.sqrt(max(0.0, r * r - x * x))

    xs = [-span + 2 * span * i / N for i in range(N + 1)]
    mb = MB()

    for y in (cy - hw, cy + hw):
        bot = [(x, y, unders_z(x)) for x in xs]
        top = [(x, y, deck_z(x)) for x in xs]
        mb.grid([bot, top], mat=0)

    mb.grid([[(x, cy - hw, deck_z(x)) for x in xs],
             [(x, cy + hw, deck_z(x)) for x in xs]], mat=1)

    ax = [x for x in xs if abs(x) < r]
    mb.grid([[(x, cy - hw, unders_z(x)) for x in ax],
             [(x, cy + hw, unders_z(x)) for x in ax]], mat=0)

    for x in (-span, span):
        mb.face([mb._v((x, cy - hw, z_spring)), mb._v((x, cy + hw, z_spring)),
                 mb._v((x, cy + hw, deck_z(x))), mb._v((x, cy - hw, deck_z(x)))], 0)
    for seg in ((span, r), (-r, -span)):
        xs_seg = [seg[0] + (seg[1] - seg[0]) * i / 8 for i in range(9)]
        mb.grid([[(x, cy - hw, z_spring) for x in xs_seg],
                 [(x, cy + hw, z_spring) for x in xs_seg]], mat=0)

    mb.build("Bridge_Arch", [M["stone"], M["paver"]], coll, recalc=True)

    # 拱券石环
    mb2 = MB()
    for y, sgn in ((cy - hw - 0.06, -1), (cy + hw + 0.06, 1)):
        rows = []
        for rr in (r - 0.04, r + 0.44):
            row = []
            for i in range(25):
                a = math.pi * i / 24
                row.append((rr * math.cos(a), y, z_spring + rr * math.sin(a)))
            rows.append(row)
        mb2.grid(rows, mat=0, smooth=True, flip=(sgn < 0))
    mb2.build("Bridge_ArchRing", [M["stone_ring"]], coll, recalc=True)

    # 石栏杆
    mb3 = MB()
    for side in (-1, 1):
        yy = cy + side * (hw - 0.18)
        prev = None
        n = 21
        for i in range(n + 1):
            x = -span + 0.18 + (2 * span - 0.36) * i / n
            z = deck_z(x)
            mb3.box((x, yy, z + 0.46), (0.15, 0.17, 0.92), 0)
            mb3.box((x, yy, z + 0.96), (0.19, 0.21, 0.09), 0)
            if prev is not None:
                mb3.beam(prev, (x, yy, z + 0.82), 0.11, 0.13, 0)
                mb3.beam((prev[0], yy, prev[2] - 0.3), (x, yy, z + 0.3), 0.07, 0.09, 0)
            prev = (x, yy, z + 0.82)
    mb3.build("Bridge_Balustrade", [M["stone"]], coll, recalc=True)

    # 两端石阶
    mb4 = MB()
    for sx in (-1, 1):
        for k in range(3):
            mb4.box((sx * (span + 0.2 + k * 0.36), cy, z_end - 0.11 - k * 0.13),
                    (0.38, BRIDGE_W - 0.25, 0.16), 0)
    mb4.build("Bridge_Steps", [M["stone"]], coll, recalc=True)

    add_sign(coll, M, font, (0, cy - hw - 0.03, 5.32), normal=(0, -1, 0),
             word="永安橋", size=0.32, name="Bridge_Plaque", board_w=1.45)

    for sx in (-1, 1):
        for k in range(2):
            x = sx * (span - 0.62 - k * 2.1)
            for sy in (-1, 1):
                add_lantern(coll, lantern_mesh,
                            (x, cy + sy * (hw + 0.46), deck_z(x) + 1.65),
                            scale=1.2, name="Bridge_Lantern_%d_%d_%d" % (sx, k, sy))


# ----------------------------------------------------------------------------
# 7. WUPENG BOAT
# ----------------------------------------------------------------------------

def build_boat(coll, M, lantern_mesh, name="WupengBoat", anim=True,
               px=2.95, py=7.4, yaw=-38.0):
    rig = bpy.data.objects.new(name + "_Rig", None)
    rig.empty_display_type = "ARROWS"
    rig.empty_display_size = 1.2
    coll.objects.link(rig)

    L, W, KEEL = 5.6, 1.02, -0.32
    stations = 14
    mb = MB()
    secs = []
    for i in range(stations + 1):
        t = i / stations * 2 - 1
        y = t * L / 2
        k = max(0.0, 1 - t * t)
        w = W * (k ** 0.5) + 0.015
        dep = KEEL * (k ** 0.3) - 0.02
        half = []
        for j in range(7):
            a = j / 6 * (math.pi / 2)
            half.append((w * (math.cos(a) ** 0.8), y,
                         0.30 - (0.30 - dep) * (math.sin(a) ** 0.85)))
        secs.append(half + [(-p[0], p[1], p[2]) for p in reversed(half[:-1])])
    base = len(mb.v)
    for sec in secs:
        for p in sec:
            mb._v(p)
    ns = len(secs[0])
    for j in range(len(secs) - 1):
        for i in range(ns - 1):
            mb.face([base + j * ns + i, base + j * ns + i + 1,
                     base + (j + 1) * ns + i + 1, base + (j + 1) * ns + i], 0, True)
    for j in range(len(secs) - 1):
        mb.face([base + j * ns, base + (j + 1) * ns,
                 base + (j + 1) * ns + ns - 1, base + j * ns + ns - 1], 1, False)
    mb.face([base + i for i in range(ns)], 0, True)
    last = base + (len(secs) - 1) * ns
    mb.face([last + i for i in range(ns)][::-1], 0, True)
    for pts in ([sec[0] for sec in secs], [sec[-1] for sec in secs]):
        for i in range(len(pts) - 1):
            mb.beam(pts[i], pts[i + 1], 0.075, 0.075, 1)
    hull = mb.build(name + "_Hull", [M["wood"], M["wood_warm"]], coll, recalc=True)

    mb2 = MB()
    y0c, y1c, rad, zc = -1.85, 1.45, 0.64, 0.28
    rows = []
    for j in range(9):
        y = y0c + (y1c - y0c) * j / 8
        row = []
        for i in range(15):
            a = math.pi * (0.03 + 0.94 * i / 14)
            # 篷体中段略高，两端收口
            bump = 1.0 - 0.35 * abs(j - 4) / 4.0
            row.append((rad * math.cos(a), y, zc + rad * 0.95 * bump * math.sin(a)))
        rows.append(row)
    mb2.grid(rows, mat=0, smooth=True)
    # 竹篾肋骨
    for j in (0, 2, 4, 6, 8):
        y = y0c + (y1c - y0c) * j / 8
        bump = 1.0 - 0.35 * abs(j - 4) / 4.0
        prev = None
        for i in range(15):
            a = math.pi * (0.03 + 0.94 * i / 14)
            pt = (rad * math.cos(a), y, zc + rad * 0.95 * bump * math.sin(a) + 0.012)
            if prev:
                mb2.beam(prev, pt, 0.028, 0.02, 0)
            prev = pt
    canopy = mb2.build(name + "_Canopy", [M["canopy"]], coll, recalc=False)
    sol = canopy.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.035
    sol.offset = 0

    oar_pivot = bpy.data.objects.new(name + "_OarPivot", None)
    oar_pivot.empty_display_size = 0.3
    coll.objects.link(oar_pivot)
    oar_pivot.parent = rig
    oar_pivot.location = (0.0, -1.9, 0.66)
    mb3 = MB()
    mb3.beam((0, -0.2, 0), (0, 2.6, -0.4), 0.065, 0.065, 0)
    mb3.box((0, 2.65, -0.43), (0.045, 0.6, 0.24), 0)
    oar = mb3.build(name + "_Oar", [M["wood_warm"]], coll, recalc=True)
    oar.parent = oar_pivot

    mb4 = MB()
    mb4.beam((0.4, 1.5, 0.33), (0.52, -2.5, 0.92), 0.042, 0.042, 0)
    pole = mb4.build(name + "_Pole", [M["wood_warm"]], coll, recalc=True)
    pole.parent = rig

    mb5 = MB()
    mb5.cyl((0, -1.5, 0.3), (0, -1.57, 1.1), 0.16, 8, 0, smooth=True, r2=0.12)
    mb5.sphere((0, -1.57, 1.26), 0.1, seg=10, rings=6, mat=0, smooth=True)
    mb5.cyl((0, -1.57, 1.32), (0, -1.57, 1.44), 0.29, 10, 1, r2=0.03, smooth=True)
    person = mb5.build(name + "_Boatman", [M["wood_dark"], M["canopy"]], coll, recalc=True)
    person.parent = rig

    mb6 = MB()
    mb6.beam((0.0, 1.5, 0.33), (0.0, 2.1, 1.02), 0.032, 0.032, 0)
    mb6.beam((0.0, 1.66, 0.33), (0.0, 2.1, 1.02), 0.032, 0.032, 0)
    arm = mb6.build(name + "_LanternArm", [M["wood_warm"]], coll, recalc=True)
    arm.parent = rig
    lan = add_lantern(coll, lantern_mesh, (0.0, 2.1, 0.84), scale=1.1,
                      name=name + "_Lantern")
    lan.parent = rig

    for ob in (hull, canopy):
        ob.parent = rig

    if not anim:
        rig.location = (px, py, 0.10)
        rig.rotation_euler = (0, 0, math.radians(yaw))
        oar_pivot.rotation_euler = (0, math.radians(6), 0)
        return rig

    # 动画：缓行 + 起伏 + 摇橹
    y0, y1 = 7.4, 9.6
    step = 6
    for f in range(FRAME_START, FRAME_END + 1, step):
        t = (f - FRAME_START) / (FRAME_END - FRAME_START)
        rig.location = (2.95 + 0.16 * math.sin(t * 2.0),
                        y0 + (y1 - y0) * t,
                        0.10 + 0.035 * math.sin(t * 6.283 * 3.0))
        rig.rotation_euler = (math.radians(1.1) * math.sin(t * 6.283 * 2.0 + 0.6),
                              math.radians(0.7) * math.sin(t * 6.283 * 1.0),
                              math.radians(-38) + math.radians(1.8) * math.sin(t * 6.283 * 1.5))
        rig.keyframe_insert("location", frame=f)
        rig.keyframe_insert("rotation_euler", frame=f)
        oar_pivot.rotation_euler = (0, math.radians(15) * math.sin(t * 6.283 * 2.0), 0)
        oar_pivot.keyframe_insert("rotation_euler", frame=f)
    return rig


# ----------------------------------------------------------------------------
# 8. LANTERN STRINGS
# ----------------------------------------------------------------------------

def add_lantern_string(coll, M, lantern_mesh, y, z, sag=0.55, n=7):
    mb = MB()
    pts = []
    for i in range(n * 3 + 1):
        t = i / (n * 3)
        x = -RIVER_HALF + 2 * RIVER_HALF * t
        pts.append((x, y, z - sag * math.sin(math.pi * t)))
    for i in range(len(pts) - 1):
        mb.beam(pts[i], pts[i + 1], 0.011, 0.011, 0)
    mb.build("LanternString_%d" % int(y), [M["wood_dark"]], coll, recalc=False)
    for i in range(n):
        t = (i + 0.5) / n
        x = -RIVER_HALF + 2 * RIVER_HALF * t
        zz = z - sag * math.sin(math.pi * t) - 0.2
        add_lantern(coll, lantern_mesh, (x, y, zz), scale=0.8,
                    cord=0.13, name="StrLantern_%d_%d" % (int(y), i))


def river_lantern_mesh(M):
    """河灯：小木托 + 发光纸灯罩。"""
    mb = MB()
    mb.cyl((0, 0, 0.0), (0, 0, 0.05), 0.15, 10, 1, smooth=True)
    mb.cyl((0, 0, 0.05), (0, 0, 0.075), 0.11, 10, 1, smooth=True, r2=0.09)
    mb.sphere((0, 0, 0.14), 0.075, seg=12, rings=7, mat=0, scale=(1, 1, 1.3))
    ob = mb.build("RiverLanternMesh", [M["lantern"], M["wood_dark"]],
                  bpy.context.scene.collection, recalc=True)
    me = ob.data
    me.name = "RiverLanternMesh"
    bpy.data.objects.remove(ob)
    return me


def add_river_lanterns(coll, M, mesh, spots):
    for i, (x, y, s) in enumerate(spots):
        ob = bpy.data.objects.new("RiverLantern_%02d" % i, mesh)
        coll.objects.link(ob)
        ob.location = (x, y, 0.0)
        ob.scale = (s, s, s)
        ob.rotation_euler = (0, 0, rng.uniform(0, 6.28))


def add_mooring_post(coll, M, lantern_mesh, x, y, side):
    mb = MB()
    mb.cyl((x, y, QUAY_Z - 0.1), (x, y, QUAY_Z + 1.15), 0.075, 8, 0, smooth=True)
    ob = mb.build("MooringPost", [M["wood_dark"]], coll, recalc=True)
    mb2 = MB()
    mb2.beam((x, y, QUAY_Z + 1.1), (x - side * 0.42, y, QUAY_Z + 1.16), 0.04, 0.04, 0)
    mb2.build("MooringArm", [M["wood_dark"]], coll, recalc=True)
    add_lantern(coll, lantern_mesh, (x - side * 0.42, y, QUAY_Z + 0.92),
                scale=0.85, name="MooringLantern")


# ----------------------------------------------------------------------------
# 9. LIGHTS
# ----------------------------------------------------------------------------

def add_point_light(coll, name, loc, energy, color="#ff8a3c", radius=0.35, shadow=False):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = energy
    ld.color = hexc(color)[:3]
    ld.shadow_soft_size = radius
    ld.use_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    coll.objects.link(ob)
    return ob


def build_lights(coll):
    sd = bpy.data.lights.new("Moon", "SUN")
    sd.energy = 0.8
    sd.color = (0.60, 0.71, 1.0)
    sd.angle = math.radians(8)
    sd.use_shadow = True
    sun = bpy.data.objects.new("Moon", sd)
    sun.rotation_euler = (math.radians(62), 0, math.radians(-32))
    coll.objects.link(sun)

    ad = bpy.data.lights.new("SkyFill", "AREA")
    ad.energy = 110
    ad.size = 26
    ad.color = (0.36, 0.44, 0.72)
    ad.use_shadow = False
    a = bpy.data.objects.new("SkyFill", ad)
    a.location = (0, -10, 18)
    coll.objects.link(a)

    y = -38.0
    i = 0
    while y < 36.0:
        if abs(y - BRIDGE_Y) > 6:
            for side in (-1, 1):
                add_point_light(coll, "PL_%02d" % i,
                                (side * (RIVER_HALF - 0.9), y, 4.3),
                                70.0, "#ff8d45", 0.9, shadow=(i % 7 == 0))
                i += 1
        y += 8.0
    add_point_light(coll, "PL_BridgeA", (-1.6, BRIDGE_Y - 2.8, 2.6), 30, "#ff9450", 1.6, True)
    add_point_light(coll, "PL_BridgeB", (2.4, BRIDGE_Y - 2.2, 6.0), 22, "#ffa05c", 1.2, False)
    add_point_light(coll, "PL_BridgeC", (-2.8, BRIDGE_Y + 2.4, 3.0), 30, "#ffa05c", 1.2, False)
    add_point_light(coll, "PL_Arch", (0.2, BRIDGE_Y, 1.75), 22, "#ffa060", 0.9, False)
    add_point_light(coll, "PL_Boat", (3.2, 8.4, 1.35), 18, "#ffb070", 0.8, False)
    add_point_light(coll, "PL_Cool", (-RIVER_HALF + 0.6, -2.0, 3.4), 18, "#7fd0ff", 0.6)
    # 桥洞之后的远处灯火（给纵深）
    for k, yy in enumerate((24.0, 30.0, 37.0, 45.0)):
        add_point_light(coll, "PL_Far%d" % k, ((-1) ** k * (RIVER_HALF - 1.4), yy, 3.6),
                        26 - k * 4, "#ff9a58", 1.2, False)
    add_point_light(coll, "PL_WaterA", (-3.4, -12.0, 0.85), 10, "#ffa060", 0.7, False)
    add_point_light(coll, "PL_WaterB", (3.0, 1.5, 0.85), 10, "#ffa060", 0.7, False)


# ----------------------------------------------------------------------------
# 10. CAMERA
# ----------------------------------------------------------------------------

def build_camera(coll, sc):
    cd = bpy.data.cameras.new("CAM_Main")
    cd.lens = 30
    cd.sensor_width = 36
    cd.clip_start = 0.1
    cd.clip_end = 400
    cam = bpy.data.objects.new("CAM_Main", cd)
    coll.objects.link(cam)
    sc.camera = cam

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

    for fc in fcurves_of(cam):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.handle_left_type = "AUTO_CLAMPED"
            kp.handle_right_type = "AUTO_CLAMPED"
        if fc.array_index in (0, 2) and "location" in fc.data_path:
            mod = fc.modifiers.new("NOISE")
            mod.strength = 0.03
            mod.scale = 50
            mod.phase = 12 if fc.array_index == 2 else 31
    return cam


# ----------------------------------------------------------------------------
# 11. RENDER / COMPOSITOR
# ----------------------------------------------------------------------------

def setup_render(sc, samples=48):
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.fps = FPS
    sc.frame_start = FRAME_START
    sc.frame_end = FRAME_END
    ev = sc.eevee
    ev.taa_render_samples = samples
    ev.taa_samples = 16
    ev.use_raytracing = True
    ev.ray_tracing_method = "SCREEN"
    ro = ev.ray_tracing_options
    ro.resolution_scale = "1"
    ro.screen_trace_quality = 0.8
    ro.screen_trace_thickness = 0.2
    ro.trace_max_roughness = 0.6
    ro.use_denoise = True
    ro.denoise_spatial = True
    ev.use_shadows = True
    ev.shadow_ray_count = 1
    ev.shadow_step_count = 4
    try:
        ev.shadow_resolution_scale = 0.5
    except Exception:
        pass

    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = EXPOSURE
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.compression = 15
    sc.view_layers[0].use_pass_z = True


def setup_compositor(sc):
    """后期链路：辉光 → 饱和度 → 冷暗部/暖高光 → S 曲线 → 暗角 → 镜头畸变。"""
    ng = bpy.data.node_groups.new("CanalComp", "CompositorNodeTree")
    sc.compositing_node_group = ng
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")

    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.location = (-1000, 0)

    glare = ng.nodes.new("CompositorNodeGlare")
    glare.location = (-780, 120)
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 0.9
    glare.inputs["Smoothness"].default_value = 0.5
    glare.inputs["Strength"].default_value = 0.55
    glare.inputs["Size"].default_value = 0.55
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])

    # 饱和度微提
    hs = ng.nodes.new("CompositorNodeHueSat")
    hs.location = (-560, 120)
    try:
        hs.inputs["Saturation"].default_value = 1.12
        hs.inputs["Value"].default_value = 1.0
    except Exception:
        pass
    ng.links.new(glare.outputs["Image"], hs.inputs["Image"])

    # 暗部偏青、亮部偏暖
    cb = ng.nodes.new("CompositorNodeColorBalance")
    cb.location = (-360, 120)
    try:
        cb.inputs["Type"].default_value = "Lift/Gamma/Gain"
        lifts = [i for i in cb.inputs if i.name == "Lift"]
        gains = [i for i in cb.inputs if i.name == "Gain"]
        if lifts:
            lifts[0].default_value = (0.002, 0.007, 0.015, 1.0)   # 暗部微偏青
        if gains:
            gains[0].default_value = (1.05, 1.00, 0.94, 1.0)      # 高光偏暖
    except Exception as e:
        log("color balance skipped:", e)
    ng.links.new(hs.outputs["Image"], cb.inputs["Image"])

    # S 曲线对比
    cur = ng.nodes.new("CompositorNodeCurveRGB")
    cur.location = (-160, 120)
    try:
        c = cur.mapping.curves[3]
        while len(c.points) > 2:
            c.points.remove(c.points[1])
        c.points[0].location = (0.0, 0.0)
        c.points[1].location = (1.0, 1.0)
        c.points.new(0.26, 0.20)
        c.points.new(0.74, 0.80)
        cur.mapping.update()
    except Exception as e:
        log("curve skipped:", e)
    ng.links.new(cb.outputs["Image"], cur.inputs["Image"])

    # 暗角
    mix = ng.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MIX"
    mix.location = (140, 60)
    mix.inputs[7].default_value = (0.010, 0.016, 0.030, 1.0)   # 暗角颜色
    ng.links.new(cur.outputs["Image"], mix.inputs[6])            # A = 画面
    try:
        ell = ng.nodes.new("CompositorNodeEllipseMask")
        ell.location = (-300, -260)
        ell.inputs["Operation"].default_value = "Add"
        ell.inputs["Value"].default_value = 1.0
        ell.inputs["Position"].default_value = (0.5, 0.5)
        ell.inputs["Size"].default_value = (0.95, 0.95)
        ell.inputs["Rotation"].default_value = 0.0
        blur = ng.nodes.new("CompositorNodeBlur")
        blur.location = (-100, -260)
        blur.inputs["Size"].default_value = 0.22
        blur.inputs["Type"].default_value = "Gaussian"
        ng.links.new(ell.outputs["Mask"], blur.inputs["Image"])
        vig = ng.nodes.new("ShaderNodeMath")
        vig.operation = "MULTIPLY"
        vig.location = (20, -260)
        vig.inputs[1].default_value = 0.22
        ng.links.new(blur.outputs["Image"], vig.inputs[0])
        ng.links.new(vig.outputs[0], mix.inputs[0])
    except Exception as e:
        log("vignette skipped:", e)
        mix.inputs[0].default_value = 0.0

    lens = ng.nodes.new("CompositorNodeLensdist")
    lens.location = (340, 60)
    lens.inputs["Distortion"].default_value = -0.012
    lens.inputs["Dispersion"].default_value = 0.006
    ng.links.new(mix.outputs[2], lens.inputs["Image"])

    gout = ng.nodes.new("NodeGroupOutput")
    gout.location = (560, 60)
    ng.links.new(lens.outputs["Image"], gout.inputs["Image"])
    sc.render.use_compositing = True


# ----------------------------------------------------------------------------
# 12. BUILD
# ----------------------------------------------------------------------------

def build_scene(outdir):
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"

    def coll(name):
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)
        return c

    C_ENV = coll("Env_Water_Bank")
    C_HOUSE = coll("Houses")
    C_BRIDGE = coll("Bridge")
    C_BOAT = coll("Boat")
    C_PROP = coll("Props_Lanterns_Signs")
    C_LIGHT = coll("Lights")
    C_CAM = coll("Camera")

    build_world(sc)
    M = build_materials()

    font = None
    if os.path.exists(FONT_PATH):
        font = bpy.data.fonts.load(FONT_PATH, check_existing=True)
        font.name = "KaiTi"
    log("materials %.1fs" % (time.time() - t0))

    build_water(C_ENV, M)
    build_quay(C_ENV, M)
    lmesh = lantern_mesh(M)
    build_bank_row(C_HOUSE, M, font, lmesh, 1, -50.0, 50.0, "HouseR")
    build_bank_row(C_HOUSE, M, font, lmesh, -1, -50.0, 50.0, "HouseL")
    log("houses %.1fs (objs=%d)" % (time.time() - t0, len(bpy.data.objects)))

    build_backdrop(C_HOUSE, M)
    build_bridge(C_BRIDGE, M, font, lmesh)
    build_boat(C_BOAT, M, lmesh)
    build_boat(C_BOAT, M, lmesh, name="MooredBoat", anim=False,
               px=-3.05, py=3.0, yaw=16.0)
    add_lantern_string(C_PROP, M, lmesh, -9.5, 5.6, sag=0.6, n=7)
    add_lantern_string(C_PROP, M, lmesh, 3.0, 5.4, sag=0.5, n=6)
    rmesh = river_lantern_mesh(M)
    add_river_lanterns(C_PROP, M, rmesh, [
        (-2.6, -18.0, 1.0), (1.8, -15.2, 0.9), (-4.1, -10.5, 1.05),
        (3.2, -7.0, 0.95), (-1.2, -4.2, 1.0), (4.4, -1.0, 0.9),
        (-4.8, 2.2, 1.0), (2.2, 4.0, 0.85), (-2.0, 9.5, 0.95),
        (5.2, 12.0, 0.9), (-3.0, 21.0, 1.0), (1.0, 26.0, 0.9),
    ])
    for y in (-34.0, -26.0, -20.0, -16.0, -9.0, -5.0, 1.5, 6.5, 28.0):
        add_mooring_post(C_PROP, M, lmesh, RIVER_HALF - 0.35, y, 1)
        add_mooring_post(C_PROP, M, lmesh, -(RIVER_HALF - 0.35), y + 3.0, -1)
    log("bridge/boat/strings %.1fs" % (time.time() - t0))

    build_reflection_streaks(C_ENV, M)
    build_lights(C_LIGHT)
    build_camera(C_CAM, sc)
    setup_render(sc, samples=48)
    setup_compositor(sc)
    log("render setup %.1fs" % (time.time() - t0))

    sc.frame_set(1)
    bpy.context.view_layer.update()

    # 把本脚本嵌入 .blend 的文本块，工程自带重建说明
    try:
        src = os.path.abspath(__file__)
        if os.path.exists(src):
            t = bpy.data.texts.load(src)
            t.name = "build_river_town.py"
            log("embedded source into blend text block")
    except Exception as e:
        log("embed skipped:", e)

    os.makedirs(outdir, exist_ok=True)
    blend = os.path.join(outdir, "river_town_night.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("saved", blend)
    return sc, blend


# ----------------------------------------------------------------------------
# 13. RENDER MODES
# ----------------------------------------------------------------------------

def render_still(sc, path, frame, res, samples):
    sc.frame_set(frame)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.eevee.taa_render_samples = samples
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    log("frame %d -> %s (%.1fs)" % (frame, os.path.basename(path), time.time() - t))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    outdir, mode, frame, count, samples = os.path.abspath("."), "build", 210, 32, 48
    res = (1280, 720)
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            outdir = argv[i + 1]; i += 2
        elif a == "--mode":
            mode = argv[i + 1]; i += 2
        elif a == "--frame":
            frame = int(argv[i + 1]); i += 2
        elif a == "--count":
            count = int(argv[i + 1]); i += 2
        elif a == "--samples":
            samples = int(argv[i + 1]); i += 2
        elif a == "--res":
            res = tuple(int(v) for v in argv[i + 1].split("x")); i += 2
        else:
            i += 1

    outdir = os.path.abspath(outdir)
    sc, _ = build_scene(outdir)
    sc.eevee.taa_render_samples = samples

    if mode == "preview":
        d = os.path.join(outdir, "work")
        os.makedirs(d, exist_ok=True)
        for f in (1, 120, 210):
            render_still(sc, os.path.join(d, "prev_%03d.png" % f), f, (1000, 562), 24)
    elif mode == "hero":
        render_still(sc, os.path.join(outdir, "hero.png"), frame, res, max(samples, 96))
    elif mode == "frames":
        d = os.path.join(outdir, "frames")
        os.makedirs(d, exist_ok=True)
        for k in range(count):
            f = int(round(FRAME_START + (FRAME_END - FRAME_START) * k / (count - 1)))
            render_still(sc, os.path.join(d, "frame_%04d.png" % f), f, res, samples)
    log("done")


if __name__ == "__main__":
    main()
