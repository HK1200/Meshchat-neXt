cmake_minimum_required(VERSION 3.24)
project(meshchatnext_windows_sip LANGUAGES C)
if(NOT WIN32 OR NOT MSVC)
  message(FATAL_ERROR "Use a native Windows MSVC development shell")
endif()
set(CMAKE_C_STANDARD 11)
add_executable(meshchatnext-sip ../desktop_sip.c)
target_compile_definitions(meshchatnext-sip PRIVATE WIN32 _WIN32_WINNT=0x0A00)
target_include_directories(meshchatnext-sip PRIVATE "${SOURCE_ROOT}/re-4.12.0/include" "${SOURCE_ROOT}/baresip-4.12.0/include")
target_link_libraries(meshchatnext-sip PRIVATE
  "${SOURCE_ROOT}/baresip-build/libbaresip.lib"
  "${SOURCE_ROOT}/re-build/re-static.lib"
  "${SOURCE_ROOT}/tls-build/library/mbedtls.lib"
  "${SOURCE_ROOT}/tls-build/library/mbedx509.lib"
  "${SOURCE_ROOT}/tls-build/library/mbedcrypto.lib"
  "${SOURCE_ROOT}/opus-build/opus.lib"
  bcrypt qwave iphlpapi wsock32 ws2_32 dbghelp winmm gdi32 crypt32 strmiids ole32 oleaut32)

# libre's message queue uses a private loopback TCP pair to wake DNS workers.
# Compile that translation unit here without the adapter socket-policy include.
# Its symbols satisfy libre's static references before the policy-bound archive
# member is selected. All SIP/RTP socket-creating sources retain adapter binding.
target_sources(meshchatnext-sip PRIVATE
  "${SOURCE_ROOT}/re-4.12.0/src/mqueue/win32/pipe.c")
