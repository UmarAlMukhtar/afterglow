"""OpenGL mesh lens and perspective, using the system GL library through ctypes."""
from array import array
from bisect import bisect_right
from collections import OrderedDict
import ctypes as C
import ctypes.util
import math
import time
import cairo
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Pango, PangoCairo

from .lyric_scene import STYLES, icon_for, scene_rows

VERTEX = '''#version 330 core
layout(location=0) in vec4 vertex;
uniform vec2 screen;
uniform vec4 rect;
uniform float lens;
uniform float drift;
out vec2 uv;
void main() {
    vec2 pixel = rect.xy + vertex.xy * rect.zw;
    vec3 p = vec3((pixel.x-screen.x*.5)*2.0/screen.y,
                  -(pixel.y-screen.y*.5)*2.0/screen.y,0.0);
    float a = -.17;
    float b = .08 + drift*.045;
    p = vec3(p.x,cos(a)*p.y,sin(a)*p.y);
    p = vec3(cos(b)*p.x+sin(b)*p.z,p.y,-sin(b)*p.x+cos(b)*p.z);
    if(lens > .5) {
        float dome = exp(-dot(p.xy,p.xy*vec2(.7,1.1))*1.5);
        p.xy *= 1.0 + .40*dome;
        p.z += .32*dome;
    }
    float perspective = 2.8/(2.8-p.z);
    gl_Position = vec4(p.x*perspective/(screen.x/screen.y),p.y*perspective,0,1);
    uv = vertex.zw;
}'''

FRAGMENT = '''#version 330 core
in vec2 uv;
uniform sampler2D glyph;
uniform float opacity;
out vec4 color;
void main() { color = texture(glyph, uv)*opacity; }
'''


class GL:
    def __init__(self):
        self.lib = C.CDLL(ctypes.util.find_library('GL') or 'libGL.so.1')
        u, i, f, p = C.c_uint, C.c_int, C.c_float, C.c_void_p
        functions = {
            'CreateShader': (u, [u]), 'ShaderSource': (None, [u,i,C.POINTER(C.c_char_p),p]),
            'CompileShader': (None,[u]), 'GetShaderiv': (None,[u,u,C.POINTER(i)]),
            'GetShaderInfoLog': (None,[u,i,p,C.c_char_p]), 'CreateProgram': (u,[]),
            'AttachShader': (None,[u,u]), 'LinkProgram': (None,[u]),
            'GetProgramiv': (None,[u,u,C.POINTER(i)]), 'GetProgramInfoLog': (None,[u,i,p,C.c_char_p]),
            'DeleteShader': (None,[u]), 'UseProgram': (None,[u]),
            'GenVertexArrays': (None,[i,C.POINTER(u)]), 'BindVertexArray': (None,[u]),
            'GenBuffers': (None,[i,C.POINTER(u)]), 'BindBuffer': (None,[u,u]),
            'BufferData': (None,[u,C.c_ssize_t,p,u]), 'EnableVertexAttribArray': (None,[u]),
            'VertexAttribPointer': (None,[u,i,u,C.c_ubyte,i,p]),
            'GetUniformLocation': (i,[u,C.c_char_p]), 'Uniform1f': (None,[i,f]),
            'Uniform1i': (None,[i,i]), 'Uniform2f': (None,[i,f,f]), 'Uniform4f': (None,[i,f,f,f,f]),
            'GenTextures': (None,[i,C.POINTER(u)]), 'BindTexture': (None,[u,u]),
            'TexParameteri': (None,[u,u,i]), 'PixelStorei': (None,[u,i]),
            'TexImage2D': (None,[u,i,i,i,i,i,u,u,p]), 'ActiveTexture': (None,[u]),
            'DrawArrays': (None,[u,i,i]), 'Enable': (None,[u]), 'BlendFunc': (None,[u,u]),
            'ClearColor': (None,[f,f,f,f]), 'Clear': (None,[u]),
            'DeleteTextures': (None,[i,C.POINTER(u)]), 'DeleteBuffers': (None,[i,C.POINTER(u)]),
            'DeleteVertexArrays': (None,[i,C.POINTER(u)]), 'DeleteProgram': (None,[u]),
        }
        for name, (result, args) in functions.items():
            fn = getattr(self.lib, 'gl' + name)
            fn.restype, fn.argtypes = result, args
            setattr(self, name, fn)

    def program(self):
        shaders = []
        for kind, source in ((0x8B31, VERTEX), (0x8B30, FRAGMENT)):
            shader = self.CreateShader(kind)
            data = C.c_char_p(source.encode())
            self.ShaderSource(shader, 1, C.byref(data), None)
            self.CompileShader(shader)
            okay = C.c_int()
            self.GetShaderiv(shader, 0x8B81, C.byref(okay))
            if not okay.value:
                log = C.create_string_buffer(4096)
                self.GetShaderInfoLog(shader, len(log), None, log)
                raise RuntimeError(log.value.decode(errors='replace'))
            shaders.append(shader)
        program = self.CreateProgram()
        for shader in shaders:
            self.AttachShader(program, shader)
        self.LinkProgram(program)
        okay = C.c_int()
        self.GetProgramiv(program, 0x8B82, C.byref(okay))
        for shader in shaders:
            self.DeleteShader(shader)
        if not okay.value:
            log = C.create_string_buffer(4096)
            self.GetProgramInfoLog(program, len(log), None, log)
            raise RuntimeError(log.value.decode(errors='replace'))
        return program


def color(value):
    return tuple(int(value[i:i+2], 16)/255 for i in (1,3,5))


class LensLayer(Gtk.GLArea):
    def __init__(self, owner, preview=False):
        super().__init__()
        self.owner, self.preview = owner, preview
        self.set_required_version(3, 3)
        self.set_has_alpha(True)
        self.set_auto_render(False)
        self.gl = None
        self.textures = OrderedDict()
        self.document = None
        self.flat = []
        self.focus = None
        self.connect('render', self.render)
        self.connect('unrealize', self.release)

    def initialize(self):
        gl = self.gl = GL()
        self.program = gl.program()
        self.uniforms = {name: gl.GetUniformLocation(self.program, name.encode()) for name in ('screen','rect','lens','drift','glyph','opacity')}
        self.vao, self.buffer = C.c_uint(), C.c_uint()
        gl.GenVertexArrays(1, C.byref(self.vao)); gl.BindVertexArray(self.vao.value)
        gl.GenBuffers(1, C.byref(self.buffer)); gl.BindBuffer(0x8892, self.buffer.value)
        mesh = array('f')
        for y in range(10):
            for x in range(32):
                for dx, dy in ((0,0),(1,0),(1,1),(0,0),(1,1),(0,1)):
                    u, v = (x+dx)/32, (y+dy)/10
                    mesh.extend((u-.5,v-.5,u,v))
        self.vertices = len(mesh)//4
        data = (C.c_float * len(mesh)).from_buffer(mesh)
        gl.BufferData(0x8892, len(mesh)*4, data, 0x88E4)
        gl.EnableVertexAttribArray(0)
        gl.VertexAttribPointer(0, 4, 0x1406, False, 16, None)

    def sprite(self, text, icon, active, size, main, highlight, secondary):
        key = (text,icon,active,size,main,highlight,secondary)
        if key in self.textures:
            self.textures.move_to_end(key)
            return self.textures[key]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        layout = PangoCairo.create_layout(cairo.Context(surface))
        font = Pango.FontDescription('Sans Bold')
        font.set_absolute_size(size*Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        layout.set_single_paragraph_mode(True)
        if layout.get_pixel_size()[0] > size*7.3:
            layout.set_width(int(size*7.3*Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
        ink, logical = layout.get_pixel_extents()
        icon_width = int(size*.9) if icon else 0
        width = max(1, ink.width + 8)
        height = max(1, ink.height + 8)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width+icon_width, height)
        ctx = cairo.Context(surface)
        if active:
            ctx.set_source_rgb(*color(highlight))
            ctx.rectangle(0, 4, width, height-8); ctx.fill()
        ctx.set_source_rgb(*color('#FFFFFF' if active else main))
        ctx.move_to(4-ink.x, 4-ink.y)
        PangoCairo.show_layout(ctx, layout)
        if icon:
            icon_layout = PangoCairo.create_layout(ctx)
            icon_font = Pango.FontDescription('Sans Bold')
            icon_font.set_absolute_size(size*.66*Pango.SCALE)
            icon_layout.set_font_description(icon_font)
            icon_layout.set_text(icon, -1)
            ctx.set_source_rgb(*color(highlight if active else main))
            ctx.move_to(width+size*.1, height*.18)
            PangoCairo.show_layout(ctx, icon_layout)
        surface.flush()
        texture = C.c_uint()
        gl = self.gl
        gl.GenTextures(1, C.byref(texture)); gl.BindTexture(0x0DE1, texture.value)
        gl.TexParameteri(0x0DE1,0x2801,0x2601); gl.TexParameteri(0x0DE1,0x2800,0x2601)
        gl.TexParameteri(0x0DE1,0x2802,0x812F); gl.TexParameteri(0x0DE1,0x2803,0x812F)
        pixels = (C.c_ubyte * len(surface.get_data())).from_buffer(surface.get_data())
        gl.PixelStorei(0x0CF5, 4)
        gl.TexImage2D(0x0DE1,0,0x8058,surface.get_width(),surface.get_height(),0,0x80E1,0x1401,pixels)
        result = (texture.value,surface.get_width(),surface.get_height())
        self.textures[key] = result
        while len(self.textures)>48:
            _, old = self.textures.popitem(last=False)
            number = C.c_uint(old[0]); gl.DeleteTextures(1,C.byref(number))
        return result

    def render(self, area, context):
        if self.get_error():
            self.owner.gpu_error = 'OpenGL lyric lens unavailable; using the basic lyric view'
            return True
        try:
            if self.gl is None:
                self.initialize()
            gl, app = self.gl, self.owner
            gl.ClearColor(0,0,0,0); gl.Clear(0x4000)
            style = STYLES.get(app.settings['style'])
            if not style or not app.settings['lyrics']:
                return True
            doc = app.document
            if doc is not self.document:
                self.document = doc
                self.flat = sorted((w for line in doc.lines for w in line.words), key=lambda w:w.start)
                self.focus = None
            position = app.lyric_position()
            rows = scene_rows(doc, position, self.flat)
            if not rows:
                return True
            width, height = self.get_allocated_width(), self.get_allocated_height()
            scale = min(width/1600,height/900)
            size = max(16, round(132*scale*app.settings['size']))
            main, highlight, secondary = app.settings['lyric_color'], app.settings['lyric_highlight'], app.settings['lyric_secondary']
            if app.settings['palette']=='album' and app.palette != ('#A9E5C2','#EBAE84'):
                main = app.palette[0]
                highlight = '#' + ''.join(f'{int(v*.66*255):02x}' for v in color(main))
                secondary = main
            current_start = self.flat[bisect_right(self.flat,position,key=lambda w:w.start)-1].start
            transition = min(1., max(.0,(position-current_start)/.19)) if not app.settings['reduce_motion'] else 1.
            slide = (1-transition)**3
            gl.UseProgram(self.program); gl.BindVertexArray(self.vao.value)
            gl.Enable(0x0BE2); gl.BlendFunc(1,0x0303)
            gl.ActiveTexture(0x84C0); gl.Uniform1i(self.uniforms['glyph'],0)
            gl.Uniform2f(self.uniforms['screen'],width,height)
            gl.Uniform1f(self.uniforms['lens'],1 if style['lens'] else 0)
            gl.Uniform1f(self.uniforms['drift'],0 if app.settings['reduce_motion'] else math.sin(time.monotonic()*.18))
            visible = rows[-(2 if self.preview else 3):]
            for text, distance, active, progress in visible:
                icon = icon_for(text) if style['icons'] else ''
                texture, tw, th = self.sprite(text,icon,active,size,main if distance>-2 else secondary,highlight,secondary)
                shrink = min(1.,width*.69/max(1,tw))
                y = height*(.61 if self.preview else .66) + (distance+slide)*height*(.22 if self.preview else .14)
                gl.Uniform4f(self.uniforms['rect'],width*.5,y,tw*shrink,th*shrink)
                gl.Uniform1f(self.uniforms['opacity'],1 if distance>=-2 else .40)
                gl.BindTexture(0x0DE1,texture)
                gl.DrawArrays(0x0004,0,self.vertices)
            return True
        except Exception as error:
            self.owner.gpu_error = 'OpenGL lyric lens unavailable; using the basic lyric view'
            print('Lyric renderer:', str(error)[:300])
            return True

    def release(self, *args):
        if not self.gl:
            return
        self.make_current()
        if self.get_error():
            return
        for texture, _, _ in self.textures.values():
            value = C.c_uint(texture); self.gl.DeleteTextures(1,C.byref(value))
        self.textures.clear()
        self.gl.DeleteBuffers(1,C.byref(self.buffer))
        self.gl.DeleteVertexArrays(1,C.byref(self.vao))
        self.gl.DeleteProgram(self.program)
        self.gl = None
