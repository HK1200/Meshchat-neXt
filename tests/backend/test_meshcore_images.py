import base64

import pytest

from meshchatnext.src.backend.meshcore_images import decode_image, encode_image, library


@pytest.mark.parametrize(
    "width,height,pixels",
    [(513, 1, ""), (True, 1, ""), (0, 1, ""), (1, 1, "bad"), (1, 1, "AAAAAA==")],
)
def test_invalid_pixels_rejected_before_native_codec(width, height, pixels):
    with pytest.raises(ValueError):
        encode_image(pixels, width, height)


@pytest.mark.parametrize("data", [b"", b"\x03x", b"\x02\xffx", b"x" * 9985])
def test_image_payload_bounds(data):
    with pytest.raises(ValueError):
        decode_image(data)


def test_real_av1_pixels_roundtrip_and_malformed_streams():
    try:
        library()
    except ValueError:
        pytest.skip("Build optional AV1 codec with scripts/build-meshcore-av1.py")
    rgb = bytes(v for y in range(32) for x in range(32) for v in (x * 8, y * 8, 128))
    data, aspect, preview = encode_image(base64.b64encode(rgb).decode(), 32, 32)
    assert data[0] == 1 and 0 < len(data) <= 2750 and aspect == 100
    decoded = decode_image(data)
    assert decoded == {k: preview[k] for k in ("png_base64", "width", "height")}
    assert base64.b64decode(decoded["png_base64"]).startswith(b"\x89PNG")
    assert decode_image(b"\x02\x01x" + data[1:]) == decoded
    for invalid in (
        b"\x01" + data[1:] + data[1:],
        b"\x01bad",
        b"\x01" + bytes(100),
        b"\x01\xff" * 20,
    ):
        with pytest.raises(ValueError):
            decode_image(invalid)
