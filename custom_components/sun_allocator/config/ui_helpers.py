"""UI helpers for Sun Allocator: builder for selectors, label/value, emoji."""

from homeassistant.helpers.selector import selector


class EntitySelectorBuilder:
    """Builds entity selectors with custom options."""

    def __init__(self, icon_map=None):
        """Initialize the EntitySelectorBuilder."""
        self.icon_map = icon_map or {}


    def build(self, entities, domain_filter=None, esphome_only=False, none_option=True):
        """Builds the entity selector options."""
        result = []
        for entity in entities:
            domain = entity.entity_id.split(".")[0]
            if domain_filter and domain not in domain_filter:
                continue
            if esphome_only and ".esphome_" not in entity.entity_id:
                continue
            icon = self.icon_map.get(domain, "")
            friendly = entity.attributes.get("friendly_name", "")
            label = f"{icon} {friendly}" if friendly else f"{icon} {entity.entity_id}"
            result.append({"label": label, "value": str(entity.entity_id)})

        result.sort(key=lambda x: x["label"])

        if none_option:
            result = [{"label": "None", "value": "None"}] + result

        return result


class NumberSelectorBuilder:
    """Builds number selectors."""

    def __init__(self, min_value, max_value, step, mode="box", unit=None):
        """Initialize the NumberSelectorBuilder."""
        self.min = min_value
        self.max = max_value
        self.step = step
        self.mode = mode
        self.unit = unit


    def build(self):
        """Builds the number selector."""
        d = {"min": self.min, "max": self.max, "step": self.step, "mode": self.mode}
        if self.unit:
            d["unit_of_measurement"] = self.unit
        return selector({"number": d})


class BooleanSelectorBuilder:
    """Builds boolean selectors."""

    def build(self):
        """Builds the boolean selector."""
        return selector({"boolean": {}})


class SelectSelectorBuilder:
    """Builds select selectors."""

    def __init__(self, options, mode="dropdown", translation_key=None):
        """Initialize the SelectSelectorBuilder."""
        self.options = options
        self.mode = mode
        self.translation_key = translation_key


    def build(self):
        """Builds the select selector."""
        select_info = {"options": self.options, "mode": self.mode}
        if self.translation_key:
            select_info["translation_key"] = self.translation_key

        return selector({"select": select_info})
