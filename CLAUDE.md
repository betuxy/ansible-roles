# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

All tooling runs inside a local virtual environment. Activate it before running any commands:

```bash
source ansible-venv/bin/activate
```

The venv is excluded from git. To recreate it (requires `uv`):

```bash
uv venv --python 3.12 ansible-venv
source ansible-venv/bin/activate
uv pip install -r requirements.txt
```

If `uv` is not installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Key tools inside the venv: `ansible-core 2.20.5`, `ansible-lint 26.4.0`, `molecule 26.4.0`, `yamllint 1.38.0`, `black 26.3.1`.

## Common commands

```bash
# Lint a single role
ansible-lint roles/<role-name>/

# Lint everything
ansible-lint

# YAML style check
yamllint roles/<role-name>/

# Molecule tests (run from repo root, not from inside the role)
cd roles/<role-name> && molecule test
molecule test -s debian12        # run a specific scenario
molecule converge && molecule verify  # converge + verify without destroy

# Ansible syntax check
ansible-playbook --syntax-check -i localhost, -c local <playbook>.yml
```

## Role structure and conventions

Roles live under `roles/<role-name>/`. Task files use a fixed naming scheme:

| File | Purpose |
|------|---------|
| `tasks/00-checks.yml` | Pre-flight assertions, fact gathering, variable merging |
| `tasks/01-install.yml` | Package installation |
| `tasks/02-configure.yml` | All post-install configuration |

`tasks/main.yml` imports those three files in order via `ansible.builtin.import_tasks`. Every import task must have a name.

Each role has a `molecule/default/` scenario targeting Debian 13 and a `molecule/debian12/` scenario for Debian 12.

## Key coding conventions

**Modules** — always use fully-qualified collection names (`ansible.builtin.apt`, `ansible.builtin.systemd_service`, not `apt` or `service`).

**Facts** — never assume `gather_facts: true` ran. If `00-checks.yml` needs a specific fact, gather it defensively:
```yaml
- name: 00-checks | Gather distribution facts if not already present
  ansible.builtin.setup:
    gather_subset: distribution
  when: ansible_facts['distribution'] is not defined
```

**Variables** — prefix every variable with the role name (e.g. `redis_port`, `apparmor_profiles`). Internal/registered variables get a leading underscore (`_apparmor_profiles`). All names in `snake_case`.

**Layered variables** — when a variable needs to compose across `group_vars` and `host_vars` without clobbering, define three layers:
- `<var>_default` — base layer, normally empty
- `<var>` — main layer, for `group_vars`
- `<var>_additional` — override layer, for `host_vars`

Merge all three into `_<var>` early in `00-checks.yml`. Use list-of-objects (each with a `name` key) rather than dicts keyed by name — easier to loop over and avoids dict-merge surprises.

**apt tasks** — always include `update_cache: true` and `cache_valid_time: 3600`.

**Task names** — prefix with the filename: `00-checks | Assert supported OS`, `02-configure | Deploy redis.conf`.

## Authorship

Use `Ole Pannbacker` as the author name in `meta/main.yml` and anywhere else authorship is recorded. Never write an email address in any file.

## Existing roles

| Role | What it manages |
|------|----------------|
| `redis` | Redis server + Sentinel |
| `systemd` | System- and user-scoped systemd units via layered vars; uses a custom `filter_plugins/systemd.py` for merging list-of-objects by `name` key |
| `apparmor` | AppArmor install and profile management; built-in template for the `autoupdate-shell` confinement profile (see role defaults for the `apparmor_autoupdate_shell` toggle) |
