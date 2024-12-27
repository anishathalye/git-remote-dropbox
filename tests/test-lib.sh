BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

section() {
    printf '\e[33m%s\e[0m\n' "$*"
}

fail() {
    printf '\e[31m  fail: %s\e[0m\n' "$*"
    exit 1
}

ok() {
    printf '\e[32m  ...ok\e[0m\n'
}

info() {
    printf '%s\n' "$*"
}

check_env() {
    if [[ "$(whoami)" != vagrant ]]; then
        if [[ "${CI}" != true ]]; then
            echo "error: `basename "$0"` should only be used in a Vagrant VM or in CI"
            exit 2
        fi
    fi
    if [[ -z "${DROPBOX_TOKEN}" ]]; then
        echo "error: \$DROPBOX_TOKEN must be set"
        exit 2
    fi
}

setup_env() {
    export GIT_AUTHOR_EMAIL=author@example.com
    export GIT_AUTHOR_NAME='Author'
    export GIT_COMMITTER_EMAIL=committer@example.com
    export GIT_COMMITTER_NAME='Committer'
    git config --global init.defaultBranch master
    local RANDOM_STR=$(python -c "import random, string; print(''.join(random.choices(string.ascii_letters, k=16)))")
    REPO_DIR="git-remote-dropbox-test/${RANDOM_STR}"
    TMP_DIR=$(mktemp -d)
    cd ${TMP_DIR}
    trap cleanup EXIT
}

cleanup() {
    info 'cleaning up'
    if [[ -n "${TMP_DIR}" ]]; then
        rm -rf ${TMP_DIR}
    fi
    if [[ -n "${REPO_DIR}" ]]; then
        "${BASEDIR}/dropbox_delete.py" "/${REPO_DIR}"
    fi
}

test_run() {
    if [[ "${DEBUG}" == "0" ]]; then
        (eval "$*") >/dev/null 2>&1
    else
        (eval "$*")
    fi
}

test_expect_success() {
    test_run "$@"
    ret=$?
    if [[ "$ret" != "0" ]]; then
        fail "command $* returned non-zero exit status $ret"
    fi
}
