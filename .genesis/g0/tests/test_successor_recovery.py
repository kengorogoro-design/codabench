import json
import pytest
from g0 import Bundle, Ecology


def generator(tmp_path, specs):
    d=tmp_path/'generator'; d.mkdir()
    (d/'bundle.json').write_text('{"entrypoint":"main.py","kind":"generator"}')
    (d/'main.py').write_text('import json\nprint(json.dumps('+repr({'bundles':specs})+'))')
    return Bundle.load(d)


def test_malformed_generation_preserves_all_previous_successors(tmp_path):
    dest=tmp_path/'successors'; dest.mkdir()
    previous=dest/'prior'; previous.mkdir()
    (previous/'checkpoint').write_text('keep')
    good={'files':{'bundle.json':'{"entrypoint":"main.py"}', 'main.py':'print("{}")'}}
    bad={'files':{'../escape':'x'}}
    g=generator(tmp_path,[good,bad])
    eco=Ecology(tmp_path/'ecology')
    with pytest.raises(ValueError):
        eco.generate_successors(g,{},dest)
    assert (previous/'checkpoint').read_text()=='keep'
    assert list(dest.iterdir())==[previous]
    assert not (tmp_path/'escape').exists()


def test_retry_generation_is_idempotent_by_content_identity(tmp_path):
    spec={'files':{'bundle.json':'{"entrypoint":"main.py"}', 'main.py':'print("{}")'}}
    g=generator(tmp_path,[spec])
    eco=Ecology(tmp_path/'ecology')
    a=eco.generate_successors(g,{},tmp_path/'successors')
    b=eco.generate_successors(g,{},tmp_path/'successors')
    assert a[0].bundle_id==b[0].bundle_id
    assert a[0].root==b[0].root
    assert len(list((tmp_path/'successors').iterdir()))==1
