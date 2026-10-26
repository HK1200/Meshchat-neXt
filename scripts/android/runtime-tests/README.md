# Packaged Android numerical runtime tests

These tests use the installed release APK's NumPy extensions and native dependencies. The test APK is separate and must use the same signing certificate as the target app. No test endpoint or test dependencies are added to the production app.

Prepare assets outside source control (Python3.11 with pip):

```
python3.11 scripts/android/runtime-tests/prepare-assets.py --vendor-dir android/vendor --output .local/android-runtime-assets
cd android
./gradlew :app:assembleReleaseAndroidTest -PmeshchatnextRuntimeTests -PmeshchatnextAbis=arm64-v8a,x86_64
```

Sign the AndroidTest APK with the same private key as the already signed target APK using `apksigner sign --ks KEYSTORE --ks-pass file:PASSWORD_FILE --out TEST_APK UNSIGNED_TEST_APK`. Keep the private files outside Git and public artifacts. Install the target and test APK using an explicit adb device serial.

```
adb -s SERIAL shell am instrument -w -r -e mode bindings com.haadkoe.meshchatnext.test/com.meshchatnext.NumpyInstrumentation
adb -s SERIAL shell am instrument -w -r -e mode suite com.haadkoe.meshchatnext.test/com.meshchatnext.NumpyInstrumentation
```

Instrumentation restarts the target process. Do not run it during a call. App data is retained, but reopen the app afterward. Run `getconf PAGE_SIZE` on each target and record actual APK hashes. The 16 KB image used here is `system-images;android-35;google_apis_ps16k;x86_64`; use a separate ordinary x86_64 image for the 4 KB comparison.

`bindings` checks float32/float64/complex64/complex128 matrix products, solves, inverses, SVD, Hermitian eigendecomposition, QR, Cholesky and least squares, plus FFT, array operations, save/load and concurrent BLAS work. `complex_dot_check.c` independently verifies the Fortran complex-return ABI that the old OpenBLAS classic-Flang detection got wrong with LLVM Flang.

`suite` collects the entire upstream test tree contained in the exact NumPy wheel, with no selected test exclusions and a declared 256 MB test-memory budget. It writes JSON, JUnit XML and output under the target app cache's `numpy-runtime-tests/`. Progress is logged as MeshchatNextNumpyProgress. Distinguish mathematical failures from tests requiring a desktop Python executable, native compilers or other unavailable tools; do not report the entire suite as passed when these fail. Software extended-precision floating-point warning/exception behavior must also be recorded explicitly.

For a non-debuggable target, the matching-certificate runner's `report` mode returns base64 chunks of only its three known result files. Pass `-e file numpy-upstream-results.json -e offset 0` (then increment offset by decoded bytes) to retrieve results. Only a trusted runner signed with the app's private key can instrument the app. Never ship or publicly distribute the test APK as a normal app release asset.

## Resource limits and targeted reruns

The advertised memory budget does not prevent every upstream slow test from creating multi-gigabyte temporary files. Use an emulator with sufficient RAM and free storage. The runner confines pytest and NumPy scratch files to its owned cache tree and cleans generated scratch directories after a completed run. Interrupted runs may leave files behind.

`subset` accepts `-e tests BASE64_JSON`, containing a JSON list of exact relative `numpy/...::case` IDs. Use it to document reruns separately; never replace the original full-suite results. `cleanup` removes only the runner-owned test cache and explicitly named legacy pytest/NumPy temporary files. Uninstall the instrumentation APK and reopen the app after testing.

Instrumentation result code -1 means the runner finished. Determine test success from `pytest_exit_code` and outcome counts in its JSON report. The completed release validation found remaining floating-point warning and desktop-tooling/packaging failures; see `android/release/README.md`.

## Physical-device foreground diagnostics

Long runs in an invisible instrumentation target can stall on some physical devices. In this validation a bounded CPU wake lock alone did not prevent the stall; the explicit foreground target completed. For a **separate diagnostic target**, build with both `-PmeshchatnextRuntimeTests -PmeshchatnextRuntimeForeground`. The second flag adds a small validation activity only to that release target. Pass `-e foreground true` to instrumentation to keep that activity visible, including over the lock screen without unlocking it. Its window keeps the display awake; no global phone settings are changed. Never publish this diagnostic target or the instrumentation APK. Ordinary production builds omit both flags and contain neither the activity nor runner.

`-e trace true` logs individual upstream case IDs and enables a timed Python stack trace in the target's own external-files directory. Cleanup also deletes that one diagnostic file. The normal test script uses native Android logging to avoid introducing Java logging proxies into garbage-collection tests. A bounded 45-minute partial wake lock is released on completion or process death.

Binding and suite reports include `native_multiarray_sha256`: the hash of the extracted NumPy extension actually imported by Python. Check it against the intended wheel, alongside the complete packaged-native inventory, to rule out stale extraction caches when comparing wheel builds.

On the OnePlus9/API34, the original and corrected wheels both stalled at an explicit garbage-collection/refcount test in an invisible target. The opt-in foreground target progressed beyond that case. Keep incomplete attempts separate from completed suite results.
