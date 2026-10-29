import ctypes as c
from types import SimpleNamespace

from meshchatnext.src.backend.lxst_pyogg_ctypes_compat import repair_ogg_stream_state

# Layout from Xiph include/ogg/ogg.h; C long retains its native platform width.
FIELDS = [
    ("body_data", c.POINTER(c.c_ubyte)),
    ("body_storage", c.c_long),
    ("body_fill", c.c_long),
    ("body_returned", c.c_long),
    ("lacing_vals", c.POINTER(c.c_int)),
    ("granule_vals", c.POINTER(c.c_int64)),
    ("lacing_storage", c.c_long),
    ("lacing_fill", c.c_long),
    ("lacing_packet", c.c_long),
    ("lacing_returned", c.c_long),
    ("header", c.c_ubyte * 282),
    ("header_fill", c.c_int),
    ("e_o_s", c.c_int),
    ("b_o_s", c.c_int),
    ("serialno", c.c_long),
    ("pageno", c.c_long),
    ("packetno", c.c_int64),
    ("granulepos", c.c_int64),
]


class Reference(c.Structure):
    _fields_ = FIELDS


def legacy_module():
    fields = [
        (
            name,
            c.c_int
            if name == "lacing_vals"
            else c.c_int64
            if name == "granule_vals"
            else kind,
        )
        for name, kind in FIELDS
    ]
    old = type("Legacy", (c.Structure,), {"_fields_": fields})
    pointer = c.POINTER(old)
    function = SimpleNamespace(argtypes=[pointer, c.c_int])
    library = SimpleNamespace(
        ogg_stream_init=function, CallbackType=c.CFUNCTYPE(c.c_int)
    )
    return SimpleNamespace(
        __name__="fake_ogg",
        ogg_stream_state=old,
        ogg_int64_t=c.c_int64,
        os_p=pointer,
        libogg=library,
    )


def test_layout_matches_native_header_and_prototypes():
    module = legacy_module()
    assert repair_ogg_stream_state(module)
    assert c.sizeof(module.ogg_stream_state) == c.sizeof(Reference)
    for name, _ in FIELDS:
        assert (
            getattr(module.ogg_stream_state, name).offset
            == getattr(Reference, name).offset
        )
    assert module.libogg.ogg_stream_init.argtypes == [module.os_p, c.c_int]
    assert dict(module.ogg_stream_state._fields_)["lacing_vals"] is c.POINTER(c.c_int)
    assert dict(module.ogg_stream_state._fields_)["granule_vals"] is c.POINTER(
        c.c_int64
    )


def test_idempotent_and_keeps_fixed_type():
    module = legacy_module()
    repair_ogg_stream_state(module)
    fixed = module.ogg_stream_state
    assert not repair_ogg_stream_state(module)
    assert module.ogg_stream_state is fixed


def test_unavailable_ogg_library_is_noop():
    assert not repair_ogg_stream_state(SimpleNamespace(libogg=None))
