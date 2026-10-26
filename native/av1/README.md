# MeshCore photo codec

`vox_av1.c` originates from MIT-licensed jade-on-mesh/meshcore-open-tak commit `c12abb588ab960707b67b63c95bc09d7f9ab2e7e`, `third_party/vox_av1/vox_av1.c`. neXt adds input/output byte and dimension checks, plus a stream-header dimension check before full decoding. License and libaom patent/license notices are included here.

The wrapper encodes raw AV1 OBUs for Open TAK VI1 image payloads, not an AVIF file. neXt currently sends version-1 images, accepts versions 1 and 2, caps transmitted images at the standard 2,750-byte budget and receives at most 64 packets (9,984 bytes). Encoding uses at most 512-pixel RGB inputs; decoded dimensions are limited to 1,024 pixels per side. Only pixels are accepted, so source EXIF, filename, and location metadata cannot enter the encoded image.

After sourcing the workspace's `tools/media-env.sh`, run from this repository:

```sh
python3 scripts/build-meshcore-av1.py
python3 scripts/build-meshcore-av1.py --android-abi arm64-v8a --ndk /path/to/android-ndk
```

The script checks the pinned libaom 3.12.1 source archive against SHA-256 before extraction/building. Downloads and compilation stay in ignored `temp-tests/av1-build`; host and Android binaries are generated locally, never downloaded as executable binaries. Android output goes to `android/app/src/main/jniLibs/<ABI>/libvox_av1.so` and is packaged by the normal Android build. Build each supported ABI before preparing its release. The arm64 build is the one validated on the current two test phones. The host wrapper can alternatively be selected through `MESHCHAT_AV1_LIBRARY`.

Builds without the optional library can continue using text and Codec2 voice. Photo preparation/viewing reports that the photo codec is unavailable. Native-dependent tests explicitly skip when the library is absent; build it first to exercise the real image round trip.
