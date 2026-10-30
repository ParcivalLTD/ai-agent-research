cmake_minimum_required(VERSION 3.20)
project(SelectBinOpIdentityCombine CXX)

# Find LLVM 17
find_package(LLVM 17 REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)
include(HandleLLVMOptions)

add_definitions(${LLVM_DEFINITIONS})
include_directories(${LLVM_INCLUDE_DIRS})

# Build the pass as a loadable MODULE (shared library for -load-pass-plugin)
add_llvm_pass_plugin(SelectBinOpIdentityCombine
  MODULE
  SelectAddConstCombine.cpp
  DEPENDS
    intrinsics_gen
)

# Ensure C++17 for LLVM 17 compatibility
target_compile_features(SelectBinOpIdentityCombine PRIVATE cxx_std_17)

# Suppress common LLVM plugin warnings
target_compile_options(SelectBinOpIdentityCombine PRIVATE
  $<$<CXX_COMPILER_ID:GNU,Clang>:-Wno-unused-function>
)

# ─── FileCheck regression test ────────────────────────────────────────────────
find_program(FILECHECK_PROG FileCheck HINTS ${LLVM_TOOLS_BINARY_DIR})
find_program(OPT_PROG opt HINTS ${LLVM_TOOLS_BINARY_DIR})

if(FILECHECK_PROG AND OPT_PROG)
  add_custom_target(check-select-binop-identity
    COMMAND ${OPT_PROG}
        -load-pass-plugin $<TARGET_FILE:SelectBinOpIdentityCombine>
        -passes=select-binop-identity
        -S
        ${CMAKE_CURRENT_SOURCE_DIR}/test/select_add_const.ll
        -o -
      | ${FILECHECK_PROG}
        ${CMAKE_CURRENT_SOURCE_DIR}/test/select_add_const.ll
    DEPENDS SelectBinOpIdentityCombine
    COMMENT "Running FileCheck regression tests for SelectBinOpIdentityCombine"
    VERBATIM
  )
endif()

# ─── Installation ─────────────────────────────────────────────────────────────
install(TARGETS SelectBinOpIdentityCombine
  LIBRARY DESTINATION lib/llvm-plugins
)
