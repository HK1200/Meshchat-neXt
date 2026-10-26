# ruff: noqa: S101 - this is an instrumentation test payload.
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path

import numpy as np

_native_path = Path(np.core._multiarray_umath.__file__)
with _native_path.open("rb") as _native_stream:
    assert _native_stream.read(4) == b"\x7fELF"
    _native_stream.seek(0)
    _native_sha256 = hashlib.file_digest(_native_stream, "sha256").hexdigest()

passed = []
failures = []


def check(name, fn):
    try:
        fn()
        passed.append(name)
    except Exception as error:
        failures.append({"check": name, "detail": str(error)})


def close(a, b, **kw):
    np.testing.assert_allclose(
        a, b, rtol=kw.get("rtol", 1e-10), atol=kw.get("atol", 1e-10)
    )


assert np.__version__ == "1.26.2", np.__version__
check(
    "broadcasting_and_ufuncs",
    lambda: close(
        np.sin(np.array([[0.0], [np.pi / 2]])) + np.arange(3), [[0, 1, 2], [1, 2, 3]]
    ),
)
for dtype in [np.float32, np.float64, np.complex64, np.complex128]:
    tol = (
        3e-5
        if np.dtype(dtype).itemsize in [4, 8] and dtype in [np.float32, np.complex64]
        else 1e-10
    )
    a = np.array([[4, 1, 0], [1, 3, 1], [0, 1, 2]], dtype=dtype)
    if np.issubdtype(dtype, np.complexfloating):
        a[0, 1] += 0.25j
        a[1, 0] -= 0.25j
    x = np.array([1, 2, 3], dtype=dtype)
    b = a @ x
    check(
        str(dtype) + "_matmul",
        lambda a=a, b=b, tol=tol, x=x: close(
            b, np.einsum("ij,j->i", a, x), rtol=tol, atol=tol
        ),
    )
    check(
        str(dtype) + "_solve",
        lambda a=a, b=b, tol=tol, x=x: close(
            np.linalg.solve(a, b), x, rtol=tol, atol=tol
        ),
    )
    check(
        str(dtype) + "_inverse",
        lambda a=a, tol=tol: close(a @ np.linalg.inv(a), np.eye(3), rtol=tol, atol=tol),
    )
    u, s, vh = np.linalg.svd(a)
    check(
        str(dtype) + "_svd",
        lambda a=a, s=s, tol=tol, u=u, vh=vh: close(
            (u * s) @ vh, a, rtol=tol, atol=tol
        ),
    )
    eig, v = np.linalg.eigh(a)
    check(
        str(dtype) + "_eigh",
        lambda a=a, eig=eig, tol=tol, v=v: close(a @ v, v * eig, rtol=tol, atol=tol),
    )
    q, r = np.linalg.qr(a)
    check(
        str(dtype) + "_qr",
        lambda a=a, q=q, r=r, tol=tol: close(q @ r, a, rtol=tol, atol=tol),
    )
    chol = np.linalg.cholesky(a)
    check(
        str(dtype) + "_cholesky",
        lambda a=a, chol=chol, tol=tol: close(
            chol @ chol.conj().T, a, rtol=tol, atol=tol
        ),
    )
    design = np.vstack([a, a])
    target = design @ x
    fit, residual, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    assert rank == 3
    check(
        str(dtype) + "_least_squares",
        lambda fit=fit, tol=tol, x=x: close(fit, x, rtol=tol, atol=tol),
    )

rng = np.random.default_rng(12345)
real = rng.normal(size=1024)
complex_data = real + 1j * rng.normal(size=1024)
check(
    "fft_complex_roundtrip",
    lambda: close(np.fft.ifft(np.fft.fft(complex_data)), complex_data),
)
check("fft_real_roundtrip", lambda: close(np.fft.irfft(np.fft.rfft(real)), real))
image = rng.normal(size=(16, 32))
check("fft_2d_roundtrip", lambda: close(np.fft.ifft2(np.fft.fft2(image)).real, image))
check(
    "strided_array_copy",
    lambda: close(np.ascontiguousarray(image[:, ::2]), image[:, ::2]),
)
stream = io.BytesIO()
np.save(stream, image, allow_pickle=False)
stream.seek(0)
check("binary_save_load", lambda: close(np.load(stream, allow_pickle=False), image))
a = rng.normal(size=(64, 64))
b = rng.normal(size=(64, 64))
expected = a @ b
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
    futures = [workers.submit(lambda: a @ b) for _ in range(40)]
    for future in futures:
        close(future.result(), expected)
passed.append("four_thread_blas_40_products")
assert np.array_equal(np.unique([3, 1, 3, 2]), [1, 2, 3])
passed.append("integer_sort_unique")
RESULT = json.dumps(
    {
        "numpy": np.__version__,
        "native_multiarray_sha256": _native_sha256,
        "passed": len(passed),
        "failed": len(failures),
        "checks": passed,
        "failures": failures,
    }
)
