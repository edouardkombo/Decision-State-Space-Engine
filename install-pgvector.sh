#!/usr/bin/env bash
set -Eeuo pipefail

DB_NAME="${1:-dsse}"
PGVECTOR_VERSION="${PGVECTOR_VERSION:-v0.8.2}"

log() {
  printf "\n[%s] %s\n" "$(date +%H:%M:%S)" "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

retry_apt_update() {
  sudo apt-get update -y || {
    log "apt update failed once, retrying..."
    sleep 2
    sudo apt-get update -y
  }
}

install_base_packages() {
  log "Installing base packages"
  sudo apt-get install -y \
    ca-certificates \
    curl \
    git \
    build-essential \
    lsb-release \
    postgresql-common
}

configure_pgdg_repo_if_needed() {
  . /etc/os-release

  if [[ -f /etc/apt/sources.list.d/pgdg.list ]]; then
    log "PGDG repo already configured"
    return
  fi

  log "Configuring PGDG repository for ${VERSION_CODENAME}"
  sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
}

ensure_postgres_installed() {
  if command -v psql >/dev/null 2>&1; then
    log "PostgreSQL client already present: $(psql --version)"
    return
  fi

  log "Installing PostgreSQL"
  sudo apt-get install -y postgresql
}

detect_pg_major() {
  if command -v psql >/dev/null 2>&1; then
    psql --version | awk '{print $3}' | cut -d. -f1
    return
  fi

  echo "Could not detect PostgreSQL major version" >&2
  exit 1
}

enable_and_start_postgres() {
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable postgresql >/dev/null 2>&1 || true
    sudo systemctl start postgresql >/dev/null 2>&1 || true
  fi
}

install_pgvector_package_or_build() {
  local pg_major="$1"
  local pkg="postgresql-${pg_major}-pgvector"

  log "Trying package install for ${pkg}"
  if sudo apt-get install -y "${pkg}"; then
    log "Installed pgvector from APT package"
    return
  fi

  log "APT package not available, building pgvector from source"
  sudo apt-get install -y "postgresql-server-dev-${pg_major}"

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT

  git clone --branch "${PGVECTOR_VERSION}" --depth 1 https://github.com/pgvector/pgvector.git "${tmp_dir}/pgvector"
  make -C "${tmp_dir}/pgvector"
  sudo make -C "${tmp_dir}/pgvector" install

  log "Built and installed pgvector from source"
}

ensure_database_exists() {
  local db_name="$1"

  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${db_name}'" | grep -q 1; then
    log "Database '${db_name}' already exists"
    return
  fi

  log "Creating database '${db_name}'"
  sudo -u postgres createdb "${db_name}"
}

enable_vector_extension() {
  local db_name="$1"

  log "Enabling vector extension in database '${db_name}'"
  sudo -u postgres psql -d "${db_name}" -c "CREATE EXTENSION IF NOT EXISTS vector;"
}

verify_install() {
  local db_name="$1"

  log "Verifying installation"
  sudo -u postgres psql -d "${db_name}" -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
}

main() {
  need_cmd sudo
  need_cmd awk
  need_cmd cut
  need_cmd grep

  retry_apt_update
  install_base_packages
  configure_pgdg_repo_if_needed
  retry_apt_update
  ensure_postgres_installed
  enable_and_start_postgres

  PG_MAJOR="$(detect_pg_major)"
  log "Detected PostgreSQL major version: ${PG_MAJOR}"

  install_pgvector_package_or_build "${PG_MAJOR}"
  ensure_database_exists "${DB_NAME}"
  enable_vector_extension "${DB_NAME}"
  verify_install "${DB_NAME}"

  log "Done. pgvector is ready in database '${DB_NAME}'."
  log "Test with:"
  echo "  sudo -u postgres psql -d ${DB_NAME} -c '\\dx'"
}

main "$@"
