# Skills.md

This file provides guidance to models like Claude Code (claude.ai/code) or OpenCode when working with code in this repository.

## Environment

All tooling runs inside the local virtual environment. Activate it before running any commands:

```bash
source ansible-venv/bin/activate
```

The venv is excluded from git (`ansible-venv/.gitignore` contains `*`). To recreate it:

```bash
uv venv --python 3.12 ansible-venv
source ansible-venv/bin/activate
uv pip install -r requirements.txt
```

## Key tools (all inside the venv)

| Tool | Version | Purpose |
|------|---------|---------|
| ansible-core | 2.20.5 | Core engine |
| ansible | 13.6.0 | Full collection bundle |
| ansible-lint | 26.4.0 | Lint roles and playbooks |
| molecule | 26.4.0 | Role testing |
| yamllint | 1.38.0 | YAML style checks |
| black | 26.3.1 | Format Python files (custom modules/plugins) |

## Common commands

```bash
# Lint a role
ansible-lint roles/<role-name>/

# Lint everything
ansible-lint

# Run molecule tests for a role
cd roles/<role-name>
molecule test

# Run only a specific molecule scenario
molecule test -s <scenario-name>

# Step through molecule (create → converge → verify without destroy)
molecule converge
molecule verify

# Check YAML style
yamllint roles/<role-name>/

# Format Python files
black plugins/ filter_plugins/
```

## Repository structure

Roles live under `roles/<role-name>/` following the standard Ansible role layout:

```
roles/<role-name>/
  tasks/main.yml
  tasks/00-checks.yml
  tasks/01-install.yml
  tasks/02-configure.yml
  defaults/main.yml
  vars/main.yml
  handlers/main.yml
  templates/
  files/
  meta/main.yml
  molecule/
    default/
      molecule.yml
      converge.yml
      verify.yml
```

Each role has molecule tests and contains its own `molecule/` directory. The default scenario is Debian 13 with Debian 12 as second scenario.

## Task file naming convention

Task files use a numeric prefix to enforce execution order:

| File               | Purpose                                          |
|--------------------|--------------------------------------------------|---------------------|---------------------|
| `00-checks.yml`    | Pre-flight assertions                            | OS variable loading | precondition checks |
| `01-install.yml`   | Package installation                             |
| `02-configure.yml` | Service configuration and all post-install setup |

`tasks/main.yml` imports these files in order via `ansible.builtin.import_tasks`.

All tasks, even import tasks should have a name and be separated with linebreaks for readability.

All task names should include the filename.
E.g. for a file 00-checks.yml:

```yaml
- name: 00-checks | Assert supported OS
  ansible.builtin.assert:
    that:
      - ansible_distribution == "Debian"
      - ansible_distribution_major_version | int >= 12
    fail_msg: "This role supports Debian 12 and later only."
```

## Tasks rules

- Install tasks that use the apt module should always include  update_cache: true and cache_valid_time: 3600
- Never assume the calling playbook already ran `gather_facts: true`. If `00-checks.yml` needs a specific fact (e.g. `ansible_facts.service_mgr`), gather it defensively first, guarded so it's a no-op when the fact is already present:

```yaml
- name: 00-checks | Gather service_mgr fact if not already present
  ansible.builtin.setup:
    gather_subset: service_mgr
  when: ansible_facts['service_mgr'] is not defined
```

## Conventions and rules

## Modules
Use modern replacements for modules and the most specific modules e.g.: ansible.builtin.systemd_service instead of ansible.builtin.service.

### When to write a role vs. a playbook

- If it is worth writing a role for a process, it lives in the central repository and is developed on a branch — never directly on `main`.
- Only write a role when the logic is substantial. If a task occurs rarely or only once, or the role would contain only three or four tasks, write a playbook or standalone task file instead.
- New roles are scaffolded with `ansible-galaxy init roles/<role-name>` to get a standardised project structure.

### Role scope and dependencies

- A role contains only tasks directly related to its own concern (e.g. `cron` configures **only** cron jobs; `openvpn` does **not** configure the network stack).
- Cross-role dependencies are declared under the `dependencies` key in `meta/main.yml` instead of embedding foreign tasks inside the role.
- When a new edge case arises, adapt the role rather than writing a workaround inside an individual project.

### Idempotency and OS support

- Roles must produce idempotent states — running them multiple times must not cause unintended changes.
- Roles must support different operating systems and/or major versions (use `vars/` files per OS family/version and load them in `00-checks.yml`).

### Variables

- Tasks and templates must not be hardcoded — use variables with sensible defaults defined in `defaults/main.yml`.
- Every variable is prefixed with the role name to avoid collisions (e.g. `nginx_port`, `nginx_user`). Pick role names that keep this prefix short and clean rather than stacking redundant words (e.g. role `systemd`, not `systemd_units`, so its variables read `systemd_services`, not `systemd_units_services`).
- Internal| non-configurable variables (e.g. registered results) are prefixed with an underscore (e.g. `register: _command_output`).|
- All names and variables are written in `snake_case` — descriptive enough to be unambiguous, concise enough to avoid noise.
- When a role manages several distinct kinds of configurable "things" (e.g. different systemd unit types), split them into separate typed variables (`systemd_services`, `systemd_timers`, ...) instead of one catch-all variable — easier to find and edit in `group_vars`/`host_vars`.

#### List-of-objects over dicts-keyed-by-name

Prefer a flat **list** as the top-level structure for configurable variables, not a dict keyed by name — lists are easier to loop over (`loop: "{{ var }}"` directly, no `dict2items` needed) and avoid Ansible's dict-merge surprises. Each list entry carries a required `name` (or similarly identifying) field:

```yaml
systemd_services:
  - name: myapp
    sections:
      - Service:
        ExecStart: /usr/bin/myapp
```

not:

```yaml
systemd_services:
  myapp:
    sections:
      Service:
        ExecStart: /usr/bin/myapp
```

#### Layered variables for multi-scope configuration

When a variable needs to be composed across `group_vars` and `host_vars` without one scope clobbering the other, define it in three layers, all sharing the same shape (list or dict):

- `<var>_default` — base layer, normally left empty; only for values that should really apply to every host with the role.
- `<var>` — main layer, intended for `group_vars`.
- `<var>_additional` — additional layer, intended for `host_vars`, merged last.

Combine the three layers early in `00-checks.yml` (or `tasks/main.yml`) into an internal `_<var>` fact, in that order, so later layers override matching entries from earlier ones instead of replacing the whole variable. For dicts, Ansible's `combine(recursive=True, list_merge=...)` filter is usually enough. For lists-of-objects keyed by a `name` field, `combine` does not merge by key — write a small custom filter plugin (see below) that merges entries sharing the same `name` and concatenates the rest, so the same override behavior works for lists too.

#### Custom filter plugins for merge/normalize logic

When the required merge or normalization logic is too complex for Ansible's built-in filters (e.g. merging layered lists-of-objects by a key field, or defaulting/validating every entry's shape), write a role-local filter plugin under `filter_plugins/` rather than reproducing the logic in Jinja across multiple tasks. Format it with `black` (see Common commands). Fail loudly (`raise AnsibleFilterError(...)`) on malformed input (e.g. a list entry missing its required `name`) instead of silently dropping it.

### README format

Every role's `README.md` follows this structure (see `roles/systemd/README.md` for a full example):

- Title: `# Ansible Role: <name>`, one-line description of what it manages.
- `## Requirements` — anything not covered by Ansible itself (external files, pre-existing accounts, etc.).
- `## Role Variables` — a table of every configurable variable:

  | Variable      | type                     | default       | required     | description                               |
  |---------------|--------------------------|---------------|--------------|--------------------------------------------|
  | Variable name | e.g. String / Boolean / list(Dict) | default value | yes / no | What the variable controls and its effect |

  When a variable is a list/dict of objects, show its sub-fields as indented rows directly below it using `&emsp;` prefixes on the Variable column (one `&emsp;` per nesting level).
- One or more `##` sections giving background on the software the role configures — concepts, terminology, gotchas (e.g. "System-scoped vs. user-scoped units") — not just a variable dump.
- `## Example Configuration` — a realistic, complete YAML example (not a toy one-liner).
- `## Further Reading` — links to the upstream software's official docs/man pages for anything the role doesn't fully enumerate (e.g. arbitrary directives passed through a generic `sections`-style variable).
- `## Dependencies`, `## License`, `## Author Information` — standard closing sections.
