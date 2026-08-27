from __future__ import annotations

from ansible.errors import AnsibleFilterError


def _merge_value(base, override, list_merge):
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = (
                _merge_value(merged[key], value, list_merge) if key in merged else value
            )
        return merged
    if isinstance(base, list) and isinstance(override, list):
        if list_merge == "replace":
            return list(override)
        if list_merge == "keep":
            return list(base)
        if list_merge == "prepend":
            return list(override) + [v for v in base if v not in override]
        if list_merge == "append":
            return list(base) + list(override)
        # append_rp (default): append override, dropping base values it repeats
        return [v for v in base if v not in override] + list(override)
    return override


def merge_systemd_units(layers, list_merge="append_rp"):
    by_key = {}
    order = []
    for layer in layers:
        for entry in layer or []:
            entry = dict(entry or {})
            name = entry.pop("name", None)
            if not name:
                raise AnsibleFilterError("systemd_units entries must include a 'name' key")
            unit_type = entry.get("type")
            if not unit_type:
                raise AnsibleFilterError("systemd_units entries must include a 'type' key")
            key = (name, unit_type)
            if key in by_key:
                by_key[key] = _merge_value(by_key[key], entry, list_merge)
            else:
                by_key[key] = entry
                order.append(key)

    units = []
    for key in order:
        name, unit_type = key
        spec = by_key[key]
        units.append(
            {
                "name": name,
                "type": unit_type,
                "unit": f"{name}.{unit_type}",
                "scope": spec.get("scope", "system"),
                "user": spec.get("user"),
                "state": spec.get("state", "started"),
                "enabled": spec.get("enabled", True),
                "sections": spec.get("sections", {}),
            }
        )
    return units


class FilterModule:
    def filters(self):
        return {"merge_systemd_units": merge_systemd_units}
