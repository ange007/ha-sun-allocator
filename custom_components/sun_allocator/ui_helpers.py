"""UI helpers for Sun Allocator: builder-класи для selector-ів, label/value, emoji, підказки."""
from homeassistant.helpers.selector import selector

class EntitySelectorBuilder:
    def __init__(self, icon_map=None):
        self.icon_map = icon_map or {}

    def build(self, entities, domain_filter=None, esphome_only=False, none_option=True):
        result = []
        for e in entities:
            domain = e.entity_id.split(".")[0]
            if domain_filter and domain not in domain_filter:
                continue
            if esphome_only and ".esphome_" not in e.entity_id:
                continue
            icon = self.icon_map.get(domain, "")
            friendly = e.attributes.get("friendly_name", "")
            label = f"{icon} {friendly}" if friendly else f"{icon} {e.entity_id}"
            result.append({"label": label, "value": e.entity_id})
        result.sort(key=lambda x: x["label"])
        if none_option:
            result = [{"label": "None", "value": "None"}] + result
        return result

class NumberSelectorBuilder:
    def __init__(self, min_value, max_value, step, mode="box", unit=None):
        self.min = min_value
        self.max = max_value
        self.step = step
        self.mode = mode
        self.unit = unit
    def build(self):
        d = {"min": self.min, "max": self.max, "step": self.step, "mode": self.mode}
        if self.unit:
            d["unit_of_measurement"] = self.unit
        return selector({"number": d})

class BooleanSelectorBuilder:
    def build(self):
        return selector({"boolean": {}})

class SelectSelectorBuilder:
    def __init__(self, options, mode="dropdown"):
        self.options = options
        self.mode = mode
    def build(self):
        return selector({"select": {"options": self.options, "mode": self.mode}})

# Додаткові утиліти для label/emoji можна додати тут
