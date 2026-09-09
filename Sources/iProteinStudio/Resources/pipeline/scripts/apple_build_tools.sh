#!/usr/bin/env bash
# Sourced by setup_pipeline.sh. Keep detection/maintenance paths compiler-free.
configure_apple_build_tools() {
  local sdk cc cxx probe_dir
  sdk="$(xcrun --sdk macosx --show-sdk-path)" || return 1
  cc="$(xcrun --sdk macosx --find clang)" || return 1
  cxx="$(xcrun --sdk macosx --find clang++)" || return 1
  if [[ ! -d "${sdk}" || ! -x "${cc}" || ! -x "${cxx}" ]]; then
    echo "Apple SDK or compiler is missing: SDK=${sdk}, CC=${cc}, CXX=${cxx}" >&2
    return 1
  fi
  export SDKROOT="${sdk}" CC="${cc}" CXX="${cxx}"
  # Recent SDKs contain libc++ headers that may not be found through clang's
  # toolchain-relative search, particularly in managed Python extension builds.
  # Use the headers belonging to the selected SDK; never mix SDK versions.
  if [[ -f "${sdk}/usr/include/c++/v1/cmath" ]]; then
    export CPLUS_INCLUDE_PATH="${sdk}/usr/include/c++/v1${CPLUS_INCLUDE_PATH:+:${CPLUS_INCLUDE_PATH}}"
  fi
  echo "Apple build tools: SDKROOT=${SDKROOT}, CC=${CC}, CXX=${CXX}"
  probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-compiler.XXXXXX")" || return 1
  cat > "${probe_dir}/probe.cpp" <<'CPP'
#include <cmath>
#include <vector>
#include <cstdio>
int main() {
    std::vector<double> values{4.0};
    std::printf("Apple C++ compile/link/run check passed\n");
    return std::sqrt(values.front()) == 2.0 ? 0 : 1;
}
CPP
  if ! "${CXX}" -arch arm64 -mmacosx-version-min=11.0 -std=c++11 \
      -isysroot "${SDKROOT}" "${probe_dir}/probe.cpp" -o "${probe_dir}/probe" \
      || ! "${probe_dir}/probe"; then
    rm -rf "${probe_dir}"
    return 1
  fi
  rm -rf "${probe_dir}"
}
