# Ansible Role: systemd

An Ansible Role that defines and manages arbitrary systemd unit files
(`.service`, `.socket`, `.timer`, `.path`, `.mount`, `.target`, etc.),
either system-scoped (`/etc/systemd/system/`) or user-scoped
(`~<user>/.config/systemd/user/`, managed with `systemctl --user`).

## Requirements

- Target host must use systemd as its service manager (PID 1).
- User-scoped units require the owning Linux account to already exist.

## Role Variables

Units are defined in a single three-layer list variable (`systemd_units`).
Each entry carries a `type` field that identifies the systemd unit type,
so any mix of unit types can live in one list without needing separate
per-type variables.

| Variable                      | type       | default       | required        | description                                                                                                             |
| ----------------------------- | ---------- | ------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `systemd_units_default`       | list(Dict) | `[]`          | no              | Base layer, normally left empty; applies to every host with this role. Same schema as `systemd_units` below.            |
| `systemd_units`               | list(Dict) | `[]`          | no              | Main layer, intended for `group_vars` — units shared across a group of hosts.                                           |
| &emsp;`name`                  | String     | None          | yes             | Base unit name without the type suffix (e.g. `name: myapp` with `type: service` deploys `myapp.service`).              |
| &emsp;`type`                  | String     | None          | yes             | Unit type: `service`, `socket`, `timer`, `path`, `mount`, `automount`, `swap`, `target`, `slice`, or `scope`.          |
| &emsp;`scope`                 | String     | `"system"`    | no              | `system` (installed in `/etc/systemd/system/`) or `user` (installed for a specific Linux account).                      |
| &emsp;`user`                  | String     | None          | if scope: user  | Linux account that owns a user-scoped unit.                                                                             |
| &emsp;`state`                 | String     | `"started"`   | no              | Desired `systemctl` state, passed straight to `ansible.builtin.systemd_service`.                                        |
| &emsp;`enabled`               | Boolean    | `true`        | no              | Whether the unit is enabled at boot/login.                                                                              |
| &emsp;`sections`              | Dict       | `{}`          | no              | Unit file sections mirroring the INI structure directly (`Unit`, `Service`, `Timer`, `Install`, ...), see below.        |
| `systemd_units_additional`    | list(Dict) | `[]`          | no              | Additional layer, intended for `host_vars` — units specific to a single host. Same schema as above, merged on top.     |
| `systemd_list_merge_strategy` | String     | `"append_rp"` | no              | Merge strategy for list-valued directives (e.g. `After:`) when a unit's `name`+`type` appears in more than one layer. Same semantics as Ansible's `combine` filter's `list_merge`. |
| `systemd_daemon_reload`       | Boolean    | `true`        | no              | Run `systemctl daemon-reload` (system and/or `--user`) after deploying units.                                           |
| `systemd_enable_linger`       | Boolean    | `true`        | no              | Enable lingering for accounts owning user-scoped units, so those units run without an active login session.              |
| `systemd_linger_method`       | String     | `"file"`      | no              | How linger is enabled: `file` creates `/var/lib/systemd/linger/<user>` directly (no `command` module, but does not signal the running logind immediately); `command` runs `loginctl enable-linger` via D-Bus and takes effect instantly on a live system. |

### `sections`: any systemd directive, for any unit type

`sections` is deliberately not enumerated field-by-field — it is rendered
almost verbatim into the unit file's INI structure, so it accepts any
directive for any unit type without this role having to hardcode
directive names. A scalar becomes `Key=value`; a boolean becomes
`Key=yes`/`Key=no`; a list becomes one repeated `Key=value` line per item
(used for multi-value directives like `After:` or `ExecStartPre:`). See
[`systemd.unit(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)
for directives shared by every unit type (`[Unit]`, `[Install]`), and the
unit-type-specific man pages below for the rest.

## Merging units across layers

The three layers are concatenated in this order:
`systemd_units_default` → `systemd_units` → `systemd_units_additional`.
Entries sharing the same `name` **and** `type` across layers are merged into
a single unit — a later layer overrides the same field from an earlier layer,
and list-valued directives are merged per `systemd_list_merge_strategy`. This
lets you define common units in `group_vars/<group>.yml` and layer
host-specific units or overrides in `host_vars/<host>.yml` without repeating
shared configuration.

## System-scoped vs. user-scoped units

- `scope: system` (default) units live in `/etc/systemd/system/`, are
  managed with plain `systemctl`, and run as whatever user the unit's own
  `[Service]` section specifies (root by default).
- `scope: user` units live in `~<user>/.config/systemd/user/` and are
  managed with `systemctl --user` as that account. Because these units
  should keep running without an interactive login session, the role
  runs `loginctl enable-linger <user>` for every account that owns at
  least one user-scoped unit (controlled by `systemd_enable_linger`).

## Example Configuration

```yaml
systemd_units:
  - name: myapp
    type: service
    sections:
      Unit:
        Description: "My App"
        After: ["network-online.target"]
        Wants: ["network-online.target"]
      Service:
        ExecStart: "/usr/bin/myapp --config /etc/myapp/config.yml"
        Restart: "on-failure"
        User: "myapp"
      Install:
        WantedBy: ["multi-user.target"]

  - name: myapp
    type: socket
    sections:
      Unit:
        Description: "My App socket"
      Socket:
        ListenStream: "/run/myapp.sock"
        SocketMode: "0660"
      Install:
        WantedBy: ["sockets.target"]

systemd_units_additional:
  - name: backup
    type: timer
    scope: user
    user: deploy
    sections:
      Unit:
        Description: "Nightly backup"
      Timer:
        OnCalendar: "daily"
        Persistent: true
      Install:
        WantedBy: ["timers.target"]

  - name: backup
    type: service
    scope: user
    user: deploy
    state: stopped
    enabled: false
    sections:
      Unit:
        Description: "Run backup script"
      Service:
        Type: "oneshot"
        ExecStart: "/home/deploy/bin/backup.sh"
```

```yaml
- hosts: webservers
  roles:
    - systemd
```

## Further Reading

- [`systemd.unit(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html) — syntax and directives shared by every unit type
- [`systemd.service(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
- [`systemd.socket(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html)
- [`systemd.timer(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
- [`systemd.path(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html)
- [`systemd.mount(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.mount.html) / [`systemd.automount(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.automount.html)
- [`systemd.exec(5)`](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html) — execution environment directives usable in `[Service]` and similar sections
- [Arch Wiki: systemd](https://wiki.archlinux.org/title/Systemd) and [Arch Wiki: systemd/User](https://wiki.archlinux.org/title/Systemd/User) — practical background on system vs. user units and lingering

## Dependencies

None.

## License

MIT

## Author Information

Ole Pannbacker
