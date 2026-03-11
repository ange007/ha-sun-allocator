[🇬🇧 English](./examples.md) | [🇺🇦 Українська](./examples_uk.md)

# Приклади

Цей файл містить приклади автоматизацій, Lovelace-карток та дашбордів.

## Приклади автоматизацій

### Увімкнення реле при надлишку потужності

```yaml
automation:
  - alias: "Увімкнути реле при надлишку"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sun_allocator_excess_power
        above: 50
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_esphome_relay
```

### Увімкнення реле при високому відсотку використання

```yaml
automation:
  - alias: "Увімкнути реле при високому % використання"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sun_allocator_usage_percent
        above: 90
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.your_esphome_relay
```

### Увімкнення навантаження на основі поточної максимальної потужності

Автоматизація, яка активується коли є значний нереалізований потенціал потужності:

```yaml
automation:
  - alias: "Увімкнути навантаження при наявності вільної потужності"
    trigger:
      - platform: template
        value_template: >
          {% set current_power = states('sensor.pv_power') | float(0) %}
          {% set max_power = states('sensor.sun_allocator_current_max_power') | float(0) %}
          {% set power_difference = max_power - current_power %}
          {{ power_difference > 100 }}
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.additional_load
```

### Керування за розкладом

Автоматизації для зміни режиму пристрою залежно від часу доби:

```yaml
automation:
  - alias: "Увімкнути бойлер вдень"
    trigger:
      - platform: sun
        event: sunrise
        offset: "01:00:00"
    action:
      - service: sun_allocator.set_relay_mode
        data:
          device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
          mode: Proportional

  - alias: "Вимкнути бойлер вночі"
    trigger:
      - platform: sun
        event: sunset
        offset: "-00:30:00"
    action:
      - service: sun_allocator.set_relay_mode
        data:
          device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
          mode: Off
```

### Приклади виклику служб

#### `sun_allocator.set_relay_mode`

Для конкретної entity:
```yaml
service: sun_allocator.set_relay_mode
data:
  entity_id: select.relay_mode_1
  mode: Proportional
```

Для конкретного пристрою за його ID:
```yaml
service: sun_allocator.set_relay_mode
data:
  device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
  mode: On
```

Для всіх пристроїв:
```yaml
service: sun_allocator.set_relay_mode
data:
  mode: Off
```

#### `sun_allocator.set_relay_power`

Для конкретної entity:
```yaml
service: sun_allocator.set_relay_power
data:
  entity_id: light.sun_allocator_relay
  power: 75
```

Для конкретного пристрою за його ID:
```yaml
service: sun_allocator.set_relay_power
data:
  device_id: 3f7b2a1c-e8d9-4f5a-b6c7-8d9e0f1a2b3c
  power: 50
```

Для всіх пристроїв:
```yaml
service: sun_allocator.set_relay_power
data:
  power: 100
```

## Приклади Lovelace та дашбордів

### Проста картка ефективності

```yaml
type: entities
title: Ефективність сонячних панелей
entities:
  - entity: sensor.sun_allocator_current_max_power
    name: Максимальна можлива потужність (Вт)
  - entity: sensor.pv_power
    name: Поточна потужність (Вт)
  - entity: sensor.sun_allocator_usage_percent
    name: Ефективність (%)
  - type: custom:bar-card
    entity: sensor.sun_allocator_usage_percent
    title: Ефективність панелей
    max: 100
    severity:
      green: 0
      yellow: 70
      red: 90
```

### Дашборд керування кількома пристроями

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Статус SunAllocator
    entities:
      - entity: sensor.sun_allocator_excess_power
        name: Вільна потужність (Вт)
      - entity: sensor.sun_allocator_current_max_power
        name: Поточний максимум (Вт)
      - entity: sensor.sun_allocator_usage_percent
        name: Використання PV (%)

  - type: entities
    title: Бойлер (Високий пріоритет)
    entities:
      - entity: select.water_heater_mode
        name: Режим
      - entity: light.water_heater_relay
        name: Потужність

  - type: entities
    title: Обігрівач (Середній пріоритет)
    entities:
      - entity: select.space_heater_mode
        name: Режим
      - entity: light.space_heater_relay
        name: Потужність

  - type: entities
    title: Насос басейну (Низький пріоритет)
    entities:
      - entity: select.pool_pump_mode
        name: Режим
      - entity: light.pool_pump_relay
        name: Потужність

  - type: gauge
    name: Вільна потужність
    entity: sensor.sun_allocator_excess_power
    min: 0
    max: 500
    severity:
      green: 0
      yellow: 100
      red: 300
```

### Візуалізація розподілу потужності

SunAllocator надає сенсори для візуалізації розподілу потужності між пристроями.

#### Сенсори розподілу потужності

1.  **Основний сенсор розподілу**: `sensor.sun_allocator_power_distribution`
    *   Показує загальну розподілену потужність між усіма пристроями
    *   Атрибути: загальна потужність, залишок, розподіл по пристроях

2.  **Сенсори потужності пристроїв**: `sensor.sun_allocator_device_power_[device_id]`
    *   Один сенсор для кожного пристрою — показує виділену йому потужність.

#### Приклад дашборду розподілу потужності

Цей приклад використовує кастомні картки (`bar-card` та `apexcharts-card`) — встановіть їх через HACS.

```yaml
title: Розподіл потужності SunAllocator
type: vertical-stack
cards:
  - type: entities
    title: Огляд розподілу потужності
    entities:
      - entity: sensor.sun_allocator_power_distribution
        name: Загальна розподілена потужність
        secondary_info: last-changed
      - type: attribute
        entity: sensor.sun_allocator_power_distribution
        attribute: total_power
        name: Загальна доступна потужність
      - type: attribute
        entity: sensor.sun_allocator_power_distribution
        attribute: remaining_power
        name: Залишок потужності
      - type: attribute
        entity: sensor.sun_allocator_power_distribution
        attribute: allocated_power
        name: Розподілена потужність

  - type: custom:apexcharts-card
    title: Розподіл потужності між пристроями
    graph_span: 24h
    header:
      show: true
      title: Розподіл потужності між пристроями
      show_states: true
    series:
      # Замініть на реальні entity ваших пристроїв
      - entity: sensor.sun_allocator_device_power_device1
        name: Бойлер
      - entity: sensor.sun_allocator_device_power_device2
        name: Обігрівач
      - entity: sensor.sun_allocator_device_power_device3
        name: Насос басейну
```

#### Відстеження розподілу потужності в часі

```yaml
type: custom:mini-graph-card
title: Історія розподілу потужності
entities:
  - entity: sensor.sun_allocator_power_distribution
    name: Розподілена потужність
  - entity: sensor.sun_allocator_excess_power
    name: Доступна потужність
hours_to_show: 24
points_per_hour: 4
line_width: 2
show:
  fill: true
  legend: true
```
