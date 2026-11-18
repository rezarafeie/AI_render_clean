import bpy, bmesh, math, json, sys, os
from mathutils import Vector, Euler
from bpy_extras.object_utils import world_to_camera_view

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SHOT = argv[0] if len(argv) > 0 else 'wide'
LIGHT = argv[1] if len(argv) > 1 else 'day'
OUT = argv[2] if len(argv) > 2 else '/home/claude/intro/b3d/out/test.png'
SAMPLES = int(argv[3]) if len(argv) > 3 else 48
PCT = int(argv[4]) if len(argv) > 4 else 100
HERE = os.path.dirname(os.path.abspath(__file__))

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
col = bpy.context.collection

def mat(name, color, rough=0.5, metal=0.0, emit=None, estr=0.0, tex=None, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit is not None:
        b.inputs['Emission Color'].default_value = (*emit, 1)
        b.inputs['Emission Strength'].default_value = estr
    if tex:
        t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(tex)
        m.node_tree.links.new(t.outputs['Color'], b.inputs['Base Color'])
    return m

def add(obj_data, name, loc=(0, 0, 0), rot=(0, 0, 0), m=None, smooth=False):
    o = bpy.data.objects.new(name, obj_data); col.objects.link(o)
    o.location = loc; o.rotation_euler = rot
    if m: o.data.materials.append(m)
    if smooth:
        for p in o.data.polygons: p.use_smooth = True
    return o

def box(name, size, loc, m, rot=(0, 0, 0), bevel=0.0):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if bevel > 0: bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=3, affect='EDGES')
    bm.to_mesh(me); bm.free()
    return add(me, name, loc, rot, m, smooth=bevel > 0)

def cyl(name, r1, r2, h, loc, m, seg=48, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r1, radius2=r2, depth=h)
    bm.to_mesh(me); bm.free()
    o = add(me, name, (loc[0], loc[1], loc[2] + h / 2), rot, m)
    for p in o.data.polygons: p.use_smooth = len(p.vertices) == 4
    return o

def sphere(name, r, loc, m, scale=(1, 1, 1), rot=(0, 0, 0), half=False):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=r)
    if half: bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -1e-5], context='VERTS')
    bm.to_mesh(me); bm.free()
    o = add(me, name, loc, rot, m, smooth=True); o.scale = scale
    return o

def plane(name, w, h, loc, m, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-w / 2, -h / 2, 0), (w / 2, -h / 2, 0), (w / 2, h / 2, 0), (-w / 2, h / 2, 0)], [], [(0, 1, 2, 3)])
    me.uv_layers.new(); uv = me.uv_layers[0].data
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]): uv[i].uv = c
    return add(me, name, loc, rot, m)

def stick(name, p0, p1, r, m):
    p0, p1 = Vector(p0), Vector(p1); dd = p1 - p0
    o = cyl(name, r, r * 0.7, dd.length, (0, 0, 0), m, seg=8)
    o.location = (p0 + p1) / 2; o.rotation_euler = dd.to_track_quat('Z', 'Y').to_euler()
    return o

# ---------- materials ----------
M_wall = mat('wall', (0.86, 0.82, 0.76), 0.9)
M_floor = mat('floor', (0.16, 0.12, 0.10), 0.6)
M_wood = mat('wood', (0.17, 0.085, 0.05), 0.38)
M_metal = mat('metal', (0.02, 0.02, 0.022), 0.45, 0.9)
M_alu = mat('alu', (0.06, 0.06, 0.065), 0.38, 0.85)
M_key = mat('key', (0.012, 0.012, 0.014), 0.6)
M_brass = mat('brass', (0.75, 0.52, 0.22), 0.28, 1.0)
M_cer = mat('ceramic', (0.88, 0.86, 0.82), 0.3)
M_leaf = mat('leaf', (0.05, 0.19, 0.07), 0.45)
M_branch = mat('branch', (0.25, 0.17, 0.11), 0.7)
M_jar = mat('jaraqe', (0.93, 0.40, 0.0), 0.35)
M_eye = mat('eye', (0.01, 0.01, 0.01), 0.3)
BOOKS = [mat('b%d' % i, c, 0.6) for i, c in enumerate([(0.75, 0.16, 0.08), (0.05, 0.08, 0.2), (0.85, 0.6, 0.1), (0.1, 0.3, 0.25), (0.8, 0.78, 0.7), (0.45, 0.1, 0.12)])]

L = {'day':     dict(world=(0.9, 0.82, 0.74), wstr=0.42, sun=(1.0, 0.80, 0.58), sstr=6.5, srot=(58, 0, -52), lamp=0.0, scr=1.3, expo=0.0),
     'dusk':    dict(world=(0.45, 0.30, 0.60), wstr=0.2, sun=(1.0, 0.42, 0.26), sstr=4.2, srot=(74, 0, -62), lamp=4.0, scr=1.6, expo=0.25),
     'night':   dict(world=(0.05, 0.08, 0.22), wstr=0.10, sun=(0.35, 0.45, 1.0), sstr=0.12, srot=(60, 0, -55), lamp=16.0, scr=2.2, expo=0.55),
     'morning': dict(world=(0.95, 0.9, 0.86), wstr=0.6, sun=(1.0, 0.9, 0.76), sstr=5.0, srot=(50, 0, -40), lamp=0.0, scr=1.2, expo=-0.05)}[LIGHT]

M_dome = mat('dome', (0.9, 0.88, 0.84), 0.35, emit=(1.0, 0.62, 0.30), estr=L['lamp'])
M_screen = mat('screen', (0.01, 0.01, 0.01), 0.15, emit=(0.03, 0.03, 0.034), estr=L['scr'])

# ---------- room ----------
plane('floor', 12, 12, (0, 0, 0), M_floor)
plane('wall', 12, 5, (0, 0.62, 2.0), M_wall, rot=(math.radians(90), 0, 0))
box('skirting', (12, 0.02, 0.1), (0, 0.61, 0.05), mat('skirt', (0.8, 0.78, 0.74), 0.5))

# desk
box('desk', (1.75, 0.76, 0.04), (0, 0.2, 0.74), M_wood, bevel=0.004)
for sx in (-0.8, 0.8):
    for sy in (-0.12, 0.52):
        box('leg', (0.03, 0.03, 0.72), (sx, sy, 0.36), M_metal)
    box('rail', (0.03, 0.66, 0.03), (sx, 0.2, 0.7), M_metal)
DZ = 0.76

# laptop
LX, LY = 0.08, 0.16
box('lap_base', (0.34, 0.235, 0.013), (LX, LY, DZ + 0.0065), M_alu, bevel=0.003)
plane('lap_keys', 0.30, 0.115, (LX, LY + 0.035, DZ + 0.0132), M_key)
plane('lap_pad', 0.12, 0.07, (LX, LY - 0.07, DZ + 0.0132), mat('pad', (0.045, 0.045, 0.05), 0.3, 0.8))
TILT = math.radians(-17)  # lid leans back
hinge = Vector((LX, LY + 0.1175, DZ + 0.013))
lid_h = 0.225
up = Vector((0, math.sin(-TILT), math.cos(TILT)))
lid_c = hinge + up * (lid_h / 2)
box('lap_lid', (0.34, 0.007, lid_h), lid_c, M_alu, rot=(TILT, 0, 0), bevel=0.002)
nrm = Vector((0, -math.cos(TILT), math.sin(-TILT)))
scr_w, scr_h = 0.322, 0.2012  # 16:10
scr_c = lid_c + nrm * 0.0042 + up * 0.002
scr = plane('lap_screen', scr_w, scr_h, scr_c, M_screen, rot=(math.radians(90) + TILT, 0, 0))

# lamp
box('lamp_base', (0.14, 0.14, 0.012), (0.66, 0.34, DZ + 0.006), M_brass, bevel=0.004)
cyl('lamp_stem', 0.007, 0.007, 0.30, (0.66, 0.34, DZ + 0.012), M_brass, seg=16)
sphere('lamp_dome', 0.13, (0.66, 0.34, DZ + 0.29), M_dome, scale=(1, 1, 0.78), half=True)
if L['lamp'] > 0:
    pl = bpy.data.lights.new('lampL', 'POINT'); pl.energy = L['lamp'] * 2.2; pl.color = (1.0, 0.62, 0.32); pl.shadow_soft_size = 0.06
    add(pl, 'lampL', (0.66, 0.34, DZ + 0.27))

# vase + branches
cyl('vase', 0.035, 0.05, 0.2, (-0.5, 0.42, DZ), M_cer)
import random
random.seed(4)
for i in range(7):
    a = random.uniform(-0.5, 0.5); b = random.uniform(-0.3, 0.3); ln = random.uniform(0.35, 0.6)
    o = cyl('br%d' % i, 0.003, 0.0015, ln, (-0.5, 0.42, DZ + 0.16), M_branch, seg=6)
    o.rotation_euler = (b, a, 0); o.location = Vector((-0.5 + math.sin(a) * ln / 2, 0.42 - math.sin(b) * ln / 2, DZ + 0.16 + math.cos(a) * ln / 2))
    for k in range(4):
        u = random.uniform(0.4, 1.0)
        sphere('bud', 0.008, (-0.5 + math.sin(a) * ln * u + random.uniform(-.01, .01), 0.42 - math.sin(b) * ln * u, DZ + 0.16 + math.cos(a) * ln * u), M_cer)

# floor plant
cyl('pot', 0.16, 0.2, 0.36, (-1.25, 0.25, 0), M_cer)
for i in range(11):
    a = random.uniform(0, 6.28); h = random.uniform(0.9, 1.75); r = random.uniform(0.1, 0.42)
    x, y = -1.25 + math.cos(a) * r, 0.25 + math.sin(a) * r * 0.6
    stick('stem%d' % i, (-1.25 + math.cos(a) * 0.05, 0.25 + math.sin(a) * 0.05, 0.34), (x, y, h), 0.006, M_leaf)
    sphere('leaf%d' % i, 0.17, (x, y, h), M_leaf, scale=(1.0, 0.55, 0.05), rot=(random.uniform(-0.7, 0.7), random.uniform(-0.9, 0.9), a))

# books + mug
box('bk1', (0.24, 0.17, 0.035), (-0.52, 0.02, DZ + 0.0175), BOOKS[0], rot=(0, 0, 0.12), bevel=0.002)
box('bk2', (0.22, 0.16, 0.028), (-0.515, 0.025, DZ + 0.049), BOOKS[1], rot=(0, 0, -0.08), bevel=0.002)
cyl('mug', 0.042, 0.042, 0.09, (0.44, 0.02, DZ), M_cer)

# frame with poster
box('frame', (0.46, 0.025, 0.6), (-0.42, 0.605, 1.52), M_wood, bevel=0.003)
plane('poster', 0.40, 0.54, (-0.42, 0.59, 1.52), mat('poster', (1, 1, 1), 0.7, tex=os.path.join(HERE, 'poster.png')), rot=(math.radians(90), 0, 0))

# shelf
box('shelf', (0.75, 0.2, 0.03), (0.72, 0.52, 1.6), M_wood, bevel=0.003)
x = 0.42
for i, w in enumerate([0.035, 0.045, 0.03, 0.04, 0.035, 0.05]):
    h = [0.24, 0.27, 0.22, 0.25, 0.26, 0.21][i]
    box('sb%d' % i, (w, 0.16, h), (x + w / 2, 0.52, 1.615 + h / 2), BOOKS[i], rot=(0, 0.0 if i < 5 else -0.18, 0))
    x += w + 0.004
sphere('bowl', 0.05, (0.98, 0.52, 1.615), M_cer, scale=(1, 1, 0.6), rot=(math.pi, 0, 0), half=True)

# Jaraqe figurine (our own spark character)
def star_pts(r, k=0.42, n=14):
    pts = []
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 2; c = a + math.pi / 2; b = a + math.pi / 4
        p0 = Vector((r * math.cos(a), r * math.sin(a))); p2 = Vector((r * math.cos(c), r * math.sin(c))); p1 = Vector((r * k * math.cos(b), r * k * math.sin(b)))
        for j in range(n):
            u = j / n; pts.append((1 - u) ** 2 * p0 + 2 * (1 - u) * u * p1 + u * u * p2)
    return pts
JX, JY, JS = -0.14, -0.04, 0.05
me = bpy.data.meshes.new('jar'); bm = bmesh.new()
vs = [bm.verts.new((p.x, 0, p.y)) for p in star_pts(JS)]
f = bm.faces.new(vs)
r = bmesh.ops.extrude_face_region(bm, geom=[f])
for v in [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]: v.co.y += 0.028
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(me); bm.free()
jar = add(me, 'jar', (JX, JY, DZ + 0.012 + JS), (0, 0, math.radians(-14)), M_jar)
bv = jar.modifiers.new('bv', 'BEVEL'); bv.width = 0.004; bv.segments = 3; bv.limit_method = 'ANGLE'
for sx in (-0.014, 0.014):
    fo = box('foot', (0.012, 0.02, 0.014), (0, 0, 0), M_jar, bevel=0.002); fo.parent = jar; fo.location = (sx, 0.014, -JS - 0.004)
    ey = box('eyeb', (0.0065, 0.004, 0.014), (0, 0, 0), M_eye, bevel=0.0015); ey.parent = jar; ey.location = (sx * 0.72, -0.001, 0.003)

# ---------- light ----------
w = bpy.data.worlds.new('w'); scn.world = w; w.use_nodes = True
bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (*L['world'], 1); bg.inputs[1].default_value = L['wstr']
sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = L['sstr']; sun.color = L['sun']; sun.angle = math.radians(2.5)
so = add(sun, 'sun', (0, 0, 5), tuple(math.radians(a) for a in L['srot']))
# gobo: window frame between the sun and the wall
sd = (so.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
gc = Vector((0.0, 0.3, 1.3)) - sd * 2.6
M_gobo = mat('gobo', (0, 0, 0), 1.0)
gz = sd.to_track_quat('Z', 'Y').to_euler()
R = gz.to_matrix()
box('gv', (0.06, 2.2, 0.01), gc, M_gobo, rot=gz)
for j in (-0.34, 0.34):
    box('gh', (1.7, 0.05, 0.01), gc, M_gobo, rot=gz).location = gc + (R @ Vector((0, j, 0)))
for sgn in (-1, 1):
    box('gside', (3.0, 8.0, 0.01), gc, M_gobo, rot=gz).location = gc + (R @ Vector((sgn * 2.3, 0, 0)))
    box('gtop', (8.0, 3.0, 0.01), gc, M_gobo, rot=gz).location = gc + (R @ Vector((0, sgn * 2.5, 0)))
for o in bpy.data.objects:
    if o.name.startswith('g') and o.data and o.data.materials and o.data.materials[0] == M_gobo: o.visible_camera = False

# ---------- camera ----------
SH = {'wide':   dict(loc=(0.15, -3.05, 1.22), at=(0.0, 0.3, 1.06), lens=40, f=5.6, foc=(LX, LY, 0.9)),
      'med':    dict(loc=(0.42, -1.0, 1.02), at=(0.07, 0.25, 0.88), lens=50, f=2.2, foc=tuple(scr_c)),
      'screen': dict(loc=(-0.12, -0.36, 0.985), at=(0.085, 0.3, 0.872), lens=42, f=3.2, foc=tuple(scr_c)),
      'mascot': dict(loc=(-0.40, -0.50, 0.85), at=(-0.04, 0.04, 0.835), lens=50, f=1.6, foc=(JX, JY, DZ + 0.06)),
      'low':    dict(loc=(0.55, -0.55, 0.80), at=(0.0, 0.2, 0.86), lens=35, f=2.0, foc=tuple(scr_c))}[SHOT]
cam = bpy.data.cameras.new('cam'); co = add(cam, 'cam', SH['loc'])
d = Vector(SH['at']) - Vector(SH['loc']); co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
cam.lens = SH['lens']; cam.sensor_width = 36
cam.dof.use_dof = True; cam.dof.aperture_fstop = SH['f']; cam.dof.focus_distance = (Vector(SH['foc']) - Vector(SH['loc'])).length
scn.camera = co

# ---------- render ----------
scn.render.engine = 'CYCLES'
scn.cycles.device = 'CPU'; scn.cycles.samples = SAMPLES; scn.cycles.use_adaptive_sampling = True; scn.cycles.adaptive_threshold = 0.03
scn.cycles.use_denoising = True
scn.cycles.max_bounces = 5; scn.cycles.diffuse_bounces = 3; scn.cycles.glossy_bounces = 3
scn.render.resolution_x = 1920; scn.render.resolution_y = 1080; scn.render.resolution_percentage = PCT
scn.render.threads_mode = 'AUTO'
scn.view_settings.view_transform = 'AgX'; scn.view_settings.look = 'AgX - Medium High Contrast'; scn.view_settings.exposure = L['expo']
scn.render.image_settings.file_format = 'PNG'
scn.render.filepath = OUT
bpy.context.view_layer.update()
# screen corners in image space (x right, y down, 0..1): TL, TR, BR, BL as seen by the viewer
mw = scr.matrix_world
cs = [mw @ Vector(v) for v in [(-scr_w / 2, scr_h / 2, 0), (scr_w / 2, scr_h / 2, 0), (scr_w / 2, -scr_h / 2, 0), (-scr_w / 2, -scr_h / 2, 0)]]
pts = []
for c in cs:
    v = world_to_camera_view(scn, co, c); pts.append([round(v.x * 1920, 2), round((1 - v.y) * 1080, 2)])
dist = [(c - Vector(SH['loc'])).length for c in cs]
json.dump({'shot': SHOT, 'light': LIGHT, 'screen': pts, 'focus': cam.dof.focus_distance, 'screen_dist': sum(dist) / 4, 'fstop': SH['f'], 'lens': SH['lens']}, open(OUT.replace('.png', '.json'), 'w'))
bpy.ops.render.render(write_still=True)
print('RENDERED', OUT)
