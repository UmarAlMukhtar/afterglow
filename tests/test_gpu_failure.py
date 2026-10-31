import ctypes as C
from types import SimpleNamespace
import unittest
from afterglow.gpu_lyrics import GL, LensLayer


class GPUFailureTests(unittest.TestCase):
    def test_context_failure_is_handled_at_realization(self):
        failures=[]
        owner=SimpleNamespace(make_current=lambda:None,get_error=lambda:'context unavailable',fail=lambda message:failures.append(message))
        LensLayer.realized(owner, owner)
        self.assertTrue(failures)

    def test_failed_shader_is_deleted(self):
        deleted=[]
        fake=SimpleNamespace(CreateShader=lambda kind:42,ShaderSource=lambda *args:None,CompileShader=lambda *args:None,
                             GetShaderiv=lambda shader,kind,pointer:setattr(pointer._obj,'value',0),
                             GetShaderInfoLog=lambda shader,size,length,buffer:setattr(buffer,'value',b'bad shader'),
                             DeleteShader=lambda shader:deleted.append(shader))
        with self.assertRaises(RuntimeError):GL.program(fake)
        self.assertEqual(deleted,[42])

    def test_partial_initialization_cleanup_is_safe(self):
        deleted=[]
        fake=SimpleNamespace(gl=SimpleNamespace(DeleteTextures=lambda *args:deleted.append('texture'),DeleteBuffers=lambda *args:deleted.append('buffer'),DeleteVertexArrays=lambda *args:deleted.append('vao'),DeleteProgram=lambda *args:deleted.append('program')),
                             make_current=lambda:None,get_error=lambda:None,textures={})
        LensLayer.release(fake)
        self.assertEqual(deleted,[])


if __name__=='__main__':unittest.main()
