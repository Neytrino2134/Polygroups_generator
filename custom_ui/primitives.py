"""Pixel-sized analytic coverage for crisp UI shapes at any panel scale."""
import gpu
from gpu_extras.batch import batch_for_shader


def create_shader(fragment, uniforms=()):
    interface = gpu.types.GPUStageInterfaceInfo('airetopo_coverage')
    interface.smooth('VEC2', 'localPos')
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, 'VEC2', 'pos')
    info.vertex_out(interface)
    info.fragment_out(0, 'VEC4', 'fragColor')
    info.push_constant('MAT4', 'ModelViewProjectionMatrix')
    info.push_constant('VEC4', 'bounds')
    info.push_constant('VEC4', 'color')
    for kind, name in uniforms:
        info.push_constant(kind, name)
    info.vertex_source('''
        void main() {
            localPos = pos * bounds.zw;
            gl_Position = ModelViewProjectionMatrix * vec4(bounds.xy + localPos, 0.0, 1.0);
        }
    ''')
    info.fragment_source(fragment)
    shader = gpu.shader.create_from_info(info)
    batch = batch_for_shader(shader, 'TRI_FAN',
                             {'pos': [(0, 0), (1, 0), (1, 1), (0, 1)]})
    return shader, batch


def draw(program, bounds, color, **uniforms):
    shader, batch = program
    # Compiling a shader can invalidate GPU state; apply alpha blending after
    # lazy shader creation as well as at the start of the panel callback.
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('ModelViewProjectionMatrix',
                         gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix())
    shader.uniform_float('bounds', bounds)
    shader.uniform_float('color', color)
    for name, value in uniforms.items():
        shader.uniform_float(name, value)
    batch.draw(shader)


ROUNDED_RECT = '''
    void main() {
        vec2 q = abs(localPos - vec2(1.0) - halfSize) - halfSize + vec2(radius);
        float distance = length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - radius;
        float aa = max(fwidth(distance), 1.0);
        float coverage = 1.0 - smoothstep(-0.5 * aa, 0.5 * aa, distance);
        fragColor = vec4(color.rgb, color.a * coverage);
    }
'''
