# Home Assistant - Wake-on-LAN конфигурация

## 📋 Информация для Home Assistant (192.168.0.120)

### Целевой сервер (Server):
- **IP-адрес**: `192.168.0.33` (проводное подключение)
- **MAC-адрес**: `84:47:09:5e:be:71`
- **WiFi IP**: `192.168.0.200` (резервный)
- **WiFi MAC**: `1c:79:2d:b2:e8:43`
- **Широковещательный адрес**: `192.168.0.255`
- **Порт**: `9` (стандартный порт для Wake-on-LAN)

### Конфигурация в Home Assistant (на 192.168.0.120):

```yaml
# configuration.yaml
wake_on_lan:
  mac_addresses:
    - "84:47:09:5e:be:71"  # Основной MAC (проводное подключение)

# Или для конкретного устройства:
switch:
  - platform: wake_on_lan
    name: "Server (192.168.0.33)"
    mac: "84:47:09:5e:be:71"
    broadcast_address: "192.168.0.255"
    broadcast_port: 9
    host: "192.168.0.33"
```

### Автоматизация для автоматического включения:

```yaml
# automations.yaml
- alias: "Включить Server (192.168.0.33)"
  trigger:
    platform: time
    at: "07:00:00"  # Время включения
  action:
    service: switch.turn_on
    target:
      entity_id: switch.server_192_168_0_33
```

### Проверка статуса сервера:

```yaml
# configuration.yaml
binary_sensor:
  - platform: ping
    name: "Server Status (192.168.0.33)"
    host: "192.168.0.33"
    count: 3
    scan_interval: 60
    consider_home: 180  # 3 минуты
```

## 🔧 Тестирование

### Проверка с сервера 192.168.0.120:
```bash
# Отправка Wake-on-LAN пакета
wakeonlan -i 192.168.0.255 84:47:09:5e:be:71

# Или через наш скрипт
wol-server wake
```

### Проверка с другого устройства в сети:
```bash
# Установка wakeonlan
sudo apt install wakeonlan

# Отправка пакета
wakeonlan -i 192.168.0.255 84:47:09:5e:be:71
```

## 📱 Lovelace карточка

```yaml
type: vertical-stack
cards:
  - type: button
    name: "Server (192.168.0.33)"
    icon: mdi:server
    tap_action:
      action: toggle
      entity: switch.server_192_168_0_33
  - type: entities
    entities:
      - entity: switch.server_192_168_0_33
        name: "Сервер"
      - entity: binary_sensor.server_status_192_168_0_33
        name: "Статус"
```

## 🔒 Безопасность

- **Целевой сервер**: `192.168.0.33` (Server)
- **MAC-адрес**: `84:47:09:5e:be:71`
- **Широковещательный адрес**: `192.168.0.255`
- **Порт**: `9`
- **HA сервер**: `192.168.0.120`

## 📝 Примечания

- Убедитесь, что Wake-on-LAN включен в BIOS/UEFI сервера `192.168.0.33`
- Проверьте настройки сетевой карты в системе
- Для надежности можно использовать оба MAC-адреса (проводной и WiFi)
