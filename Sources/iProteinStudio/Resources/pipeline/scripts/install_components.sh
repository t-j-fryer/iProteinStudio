#!/usr/bin/env bash
# Sourced by setup_pipeline.sh. Keep the parent's installation lock and let
# independent components finish after a component-local failure.
INSTALL_FAILED=()

run_install_component() {
  local key="$1" action="$2" dependency failed
  shift 2
  if [[ -n "${INSTALL_ONLY:-}" ]]; then
    case ",${INSTALL_ONLY}," in
      *,"${key}",*) ;;
      *) return 0 ;;
    esac
  fi
  for dependency in "$@"; do
    for failed in ${INSTALL_FAILED[@]+"${INSTALL_FAILED[@]}"}; do
      if [[ "$dependency" == "$failed" ]]; then
        echo "NHCOMPONENTFAIL|${key}|Requires ${dependency}; retry after its installation succeeds."
        state "$key" incomplete "Required component ${dependency} did not install."
        INSTALL_FAILED+=("$key")
        return 0
      fi
    done
  done
  if (
    # A component must never release the parent's lock on its own exit.
    trap - EXIT
    fail() { echo "NHCOMPONENTFAIL|${key}|$1"; exit 1; }
    "$action"
  ); then
    return 0
  else
    echo "NHCOMPONENTFAIL|${key}|Installation incomplete. See the preceding error in the setup log; independent components will continue."
    state "$key" incomplete "Installation failed; retry from Engines. See setup log."
    INSTALL_FAILED+=("$key")
  fi
}

finish_install_components() {
  if [[ ${#INSTALL_FAILED[@]} -gt 0 ]]; then
    echo "NHDONE|partial|${INSTALL_FAILED[*]}"
    return 2
  fi
  echo "NHDONE|ok"
}
