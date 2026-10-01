"""Construction-only smoke for the public occlusion graph; no solve or training."""
from collections import Counter
import json
from cadence import Cortex


def build(d, n, observer):
    c = Cortex(seed=2, max_connections=2_000_000)
    sensory = c.input('sensory', shape=d)
    b = c.column('B', patches=n, inputs=sensory)
    r = c.column('R', patches=d, inputs=b)
    if observer:
        context = c.observer('C', patches=n, inputs=b, observes=r)
    else:
        context = c.column('C', patches=2*n, inputs=(b, r))
    y = c.column('Y', patches=5, inputs=(b, context))
    c.output('measured_features', shape=d, reads=r)
    c.output('answer', shape=5, reads=y)
    return c.build()


def run():
    result = []
    for d, n in [(3, 2), (7, 4)]:
        pair = []
        for observer in [False, True]:
            b = build(d, n, observer)
            assert b.graph.n_inputs == d
            context_width = n if observer else 2*n
            assert b.graph.n_patches == d + n + context_width + 5
            params = len(b.weights) + len(b.biases)
            expected_parameters = n*n+(4*d+12)*n+d+5 if observer else 2*n*n+(4*d+18)*n+d+5
            assert params == expected_parameters
            for kind, source, destination in b.graph.edges:
                if kind != 'input':
                    assert source < destination
            rc = Counter(kind for kind, _, dst in b.graph.edges if n + d <= dst < n + d + context_width)
            expected = {'state': n*(n+d), 'residual': n*d} if observer else {'state':2*n*(n+d)}
            assert dict(rc) == expected
            pair.append({'observer':observer, 'parameters':params, 'patches':b.graph.n_patches,'edges':len(b.weights),'context_sources':dict(rc)})
        assert pair[0]['parameters'] - pair[1]['parameters'] == n*n+6*n
        result.append({'input_width':d,'latent_width':n,'arms':pair})
    print(json.dumps({'scope':'public construction only; no numerical queries or training','checks':result},indent=2))

if __name__ == '__main__':
    run()
