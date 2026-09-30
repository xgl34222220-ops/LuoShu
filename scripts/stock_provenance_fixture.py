"""Test-only virtual ROM mount views for explicitly registered synthetic fonts.

Production has no opt-out. Geometry unit tests do not have real ROM partitions;
this seam calls the real verifier with modeled kernel mount rows for exact pairs.
Unregistered paths, including provenance-negative fixtures, use the real view.
"""
from pathlib import Path
from unittest.mock import patch
import stock_font_provenance as proof

_registered = set()
_original_verify = proof.verify_stock_path


def _verify(logical, actual):
    key = (str(logical), str(Path(actual).resolve()))
    if key not in _registered:
        return _original_verify(logical, actual)
    partition = Path('/' + Path(logical).parts[1]).resolve()
    expected = str(partition.joinpath(*Path(logical).parts[2:]))
    relative = '/' + str(Path(expected).relative_to(partition))
    base = dict(device='253:77', fs='erofs', source='/dev/block/synthetic-rom',
                options=['ro'], superOptions=['ro'])
    rows = [dict(base, id='10', root='/', point=str(partition)),
            dict(base, id='11', root=relative, point=key[1])]
    with patch.object(proof, '_mounts', return_value=rows):
        return _original_verify(logical, actual)


def synthetic_identity(logical, actual, face=0, build='synthetic-test'):
    _registered.add((str(logical), str(Path(actual).resolve())))
    proof.verify_stock_path = _verify
    identity = proof.stock_identity(logical, actual, face, build)
    assert identity['provenance']['verified'] is True
    return identity
