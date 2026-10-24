cmake_minimum_required(VERSION 3.22)
project(luoshu_native_font CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(LSNF_HOST_TESTS "Build host unit tests and benchmark" OFF)
option(LSNF_SANITIZE "Build host tests with ASan/UBSan" OFF)
option(LSNF_ANDROID_HARNESS "Build the emulator integration harness library (test only)" OFF)

set(LSNF_CORE_SOURCES src/sfnt_verdict.cpp src/config.cpp src/face_table.cpp src/java_font_policy.cpp)
set(LSNF_COMMON_FLAGS -Wall -Wextra -Werror -fno-exceptions -fno-rtti)

add_library(lsnf_core STATIC ${LSNF_CORE_SOURCES})
target_include_directories(lsnf_core PUBLIC src)
target_compile_options(lsnf_core PRIVATE ${LSNF_COMMON_FLAGS})
set_target_properties(lsnf_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(ANDROID)
  target_compile_options(lsnf_core PRIVATE -fvisibility=hidden -fvisibility-inlines-hidden -Os
                                           -ffunction-sections -fdata-sections)

  # Zygisk module: exports only zygisk_module_entry (version script), static libc++.
  add_library(luoshu_native_font SHARED src/module.cpp src/java_font_hook.cpp)
  target_include_directories(luoshu_native_font PRIVATE src third_party/zygisk)
  target_compile_options(luoshu_native_font PRIVATE ${LSNF_COMMON_FLAGS} -fvisibility=hidden
                         -fvisibility-inlines-hidden -Os -ffunction-sections -fdata-sections)
  target_link_libraries(luoshu_native_font PRIVATE lsnf_core log)
  target_link_options(luoshu_native_font PRIVATE
    -Wl,--gc-sections -Wl,--exclude-libs,ALL -Wl,-z,noexecstack -Wl,--build-id=sha1
    -Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/src/exports.map -s)

  if(LSNF_ANDROID_HARNESS)
    # Test only: same hook code, installed through RegisterNatives inside app_process. Never packaged.
    add_library(luoshu_nf_harness SHARED tests/android/harness.cpp src/java_font_hook.cpp)
    target_include_directories(luoshu_nf_harness PRIVATE src)
    target_compile_options(luoshu_nf_harness PRIVATE ${LSNF_COMMON_FLAGS})
    target_link_libraries(luoshu_nf_harness PRIVATE lsnf_core log dl)
  endif()

  add_executable(lsnf-config src/config_tool.cpp)
  target_compile_options(lsnf-config PRIVATE ${LSNF_COMMON_FLAGS} -Os -ffunction-sections -fdata-sections)
  target_link_libraries(lsnf-config PRIVATE lsnf_core)
  target_link_options(lsnf-config PRIVATE -Wl,--gc-sections -s)
else()
  add_executable(lsnf-config src/config_tool.cpp)
  target_compile_options(lsnf-config PRIVATE ${LSNF_COMMON_FLAGS})
  target_link_libraries(lsnf-config PRIVATE lsnf_core)
endif()

if(LSNF_HOST_TESTS AND NOT ANDROID)
  enable_testing()
  set(LSNF_SAN_FLAGS "")
  if(LSNF_SANITIZE)
    set(LSNF_SAN_FLAGS -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
  endif()

  add_library(lsnf_core_test STATIC ${LSNF_CORE_SOURCES})
  target_include_directories(lsnf_core_test PUBLIC src)
  target_compile_options(lsnf_core_test PRIVATE -Wall -Wextra -Werror -g ${LSNF_SAN_FLAGS})

  foreach(t verdict_test config_test face_table_test java_policy_test)
    add_executable(${t} tests/${t}.cpp)
    target_compile_options(${t} PRIVATE -Wall -Wextra -Werror -g ${LSNF_SAN_FLAGS})
    target_link_libraries(${t} PRIVATE lsnf_core_test)
    target_link_options(${t} PRIVATE ${LSNF_SAN_FLAGS})
  endforeach()

  # Benchmark always links the optimised, sanitizer-free core.
  add_executable(verdict_bench tests/verdict_bench.cpp)
  target_compile_options(verdict_bench PRIVATE -Wall -Wextra -Werror -O2)
  target_link_libraries(verdict_bench PRIVATE lsnf_core)

  set(LSNF_CORPUS "${CMAKE_BINARY_DIR}/corpus" CACHE PATH "Generated test fonts")
  add_test(NAME verdict_test COMMAND verdict_test ${LSNF_CORPUS})
  add_test(NAME config_test COMMAND config_test $<TARGET_FILE:lsnf-config> ${CMAKE_BINARY_DIR})
  add_test(NAME face_table_test COMMAND face_table_test $<TARGET_FILE:lsnf-config> ${CMAKE_BINARY_DIR})
  add_test(NAME java_policy_test COMMAND java_policy_test ${LSNF_CORPUS})
  add_test(NAME verdict_bench COMMAND verdict_bench ${LSNF_CORPUS})
endif()
