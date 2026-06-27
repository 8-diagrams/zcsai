#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${MYSQL_DATABASE:-saas_agent_db}"
SCHEMA_FILE="/docker-entrypoint-initdb.d/schema/database.sql"
MIGRATIONS_DIR="/docker-entrypoint-initdb.d/migrations"

# database.sql is a current schema snapshot through this migration. On a fresh
# Docker init we load the snapshot, record these migrations as already applied,
# then run any newer migration files found in migrations/.
SNAPSHOT_THROUGH_MIGRATION="012_knowledge_base_raw_text.sql"

mysql_root() {
  mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" "$@"
}

mysql_db() {
  mysql_root "${DB_NAME}" "$@"
}

echo "[mysql-init] loading schema snapshot: ${SCHEMA_FILE}"
mysql_root < "${SCHEMA_FILE}"

echo "[mysql-init] preparing schema_migrations"
mysql_db <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
SQL

if [[ -d "${MIGRATIONS_DIR}" ]]; then
  echo "[mysql-init] marking snapshot migrations through ${SNAPSHOT_THROUGH_MIGRATION}"
  for file in "${MIGRATIONS_DIR}"/*.sql; do
    [[ -e "${file}" ]] || continue
    version="$(basename "${file}")"
    if [[ "${version}" > "${SNAPSHOT_THROUGH_MIGRATION}" ]]; then
      continue
    fi
    mysql_db -e "INSERT IGNORE INTO schema_migrations (version) VALUES ('${version}')"
  done

  echo "[mysql-init] applying migrations newer than snapshot"
  for file in "${MIGRATIONS_DIR}"/*.sql; do
    [[ -e "${file}" ]] || continue
    version="$(basename "${file}")"
    applied="$(mysql_db -N -B -e "SELECT COUNT(*) FROM schema_migrations WHERE version='${version}'")"
    if [[ "${applied}" == "1" ]]; then
      echo "[mysql-init] skip ${version}"
      continue
    fi

    echo "[mysql-init] apply ${version}"
    mysql_db < "${file}"
    mysql_db -e "INSERT INTO schema_migrations (version) VALUES ('${version}')"
  done
fi

echo "[mysql-init] schema initialization complete"
