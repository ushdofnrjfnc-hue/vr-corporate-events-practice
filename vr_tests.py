import secrets
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Tuple, Dict, List, Any
from dataclasses import dataclass
from enum import Enum


# ============================================================
# АЛГОРИТМ 1 и 2: Система приглашений и токенов доступа
# ============================================================

class InvitationManager:
    """Менеджер для создания и управления приглашениями на мероприятия"""

    def __init__(self, db_connection):
        self.db = db_connection

    def generate_invitation_token(self, event_id: int, user_id: int,
                                   expiration_hours: int = 72) -> Tuple[str, datetime]:
        """
        Алгоритм 1: Генерация уникального токена доступа
        Вход: event_id, user_id, expiration_hours
        Выход: token (строка 32 hex-символа), expires_at
        Сложность: O(1)
        """
        current_time = datetime.now()
        expires_at = current_time + timedelta(hours=expiration_hours)

        # Криптографически стойкая случайная строка
        token = secrets.token_hex(16)

        # SHA-256 хеш ТОЛЬКО от токена
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO invitations
            (token_hash, event_id, user_id, expires_at, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (token_hash, event_id, user_id, expires_at.isoformat(), current_time.isoformat()))
        self.db.commit()

        return token, expires_at

    def verify_invitation_token(self, token: str, event_id: int) -> Dict[str, Any]:
        """
        Алгоритм 2: Проверка валидности токена
        Вход: token, event_id
        Выход: dict с access_granted, user_id или error_message
        Сложность: O(log n) по индексу token_hash
        """
        current_time = datetime.now()

        # Хешируем полученный токен тем же способом
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()

        cursor = self.db.cursor()
        cursor.execute("""
            SELECT id, user_id, status, expires_at
            FROM invitations
            WHERE token_hash = ? AND event_id = ?
        """, (token_hash, event_id))

        invitation = cursor.fetchone()

        if not invitation:
            return {'access_granted': False, 'error_message': 'Неверный токен или мероприятие'}

        inv_id, user_id, status, expires_at_str = invitation

        # Парсим строку даты обратно в datetime
        expires_at = datetime.fromisoformat(expires_at_str)

        if status == 'revoked':
            return {'access_granted': False, 'error_message': 'Приглашение отозвано организатором'}

        if current_time > expires_at:
            return {'access_granted': False, 'error_message': 'Срок действия приглашения истек'}

        # Обновляем статус
        if status == 'pending':
            cursor.execute("""
                UPDATE invitations
                SET status = 'accepted', accepted_at = ?
                WHERE id = ?
            """, (current_time.isoformat(), inv_id))

        cursor.execute("""
            UPDATE invitations
            SET status = 'joined', joined_at = ?
            WHERE id = ?
        """, (current_time.isoformat(), inv_id))
        self.db.commit()

        return {'access_granted': True, 'user_id': user_id}


# ============================================================
# АЛГОРИТМ 3: Конструктор виртуальных комнат
# ============================================================

class LightingType(Enum):
    BRIGHT = "bright"
    DIM = "dim"
    NATURAL = "natural"


class RoomTemplate(Enum):
    CONFERENCE_ROOM = "conference_room"
    OPEN_SPACE = "open_space"
    AUDITORIUM = "auditorium"


@dataclass
class Vector3:
    x: float
    y: float
    z: float


@dataclass
class VRObject:
    name: str
    model_path: str
    position: Vector3
    rotation: Vector3
    scale: Vector3
    material: str = "default"


@dataclass
class VirtualRoomConfig:
    room_name: str
    dimensions: Vector3
    lighting_intensity: float
    lighting_type: str
    color_scheme: Dict[str, str]
    objects: List[VRObject]
    spawn_points: List[Vector3]
    capacity: int


class VirtualRoomBuilder:
    """
    Алгоритм 3: Создание виртуальной комнаты из шаблона
    Вход: template_type, capacity, lighting, color_scheme, additional_objects
    Выход: VirtualRoomConfig (JSON-сериализуемый)
    Сложность: O(c), где c - вместимость комнаты
    """

    TEMPLATES = {
        RoomTemplate.CONFERENCE_ROOM: {
            'base_dimensions': Vector3(10, 8, 3),
            'base_objects': [
                VRObject("conference_table", "models/table.obj",
                         Vector3(0, 0, 0), Vector3(0, 0, 0), Vector3(1, 1, 1)),
                VRObject("main_screen", "models/screen.obj",
                         Vector3(0, -3, 1.5), Vector3(0, 90, 0), Vector3(1, 1, 0.1)),
            ],
            'default_materials': {
                'walls': '#E0E0E0', 'floor': '#404040', 'furniture': '#8B4513'
            }
        },
        RoomTemplate.OPEN_SPACE: {
            'base_dimensions': Vector3(15, 15, 4),
            'base_objects': [],
            'default_materials': {
                'walls': '#F5F5F5', 'floor': '#808080', 'furniture': '#000000'
            }
        },
        RoomTemplate.AUDITORIUM: {
            'base_dimensions': Vector3(20, 15, 5),
            'base_objects': [
                VRObject("stage", "models/stage.obj",
                         Vector3(0, 7, 0), Vector3(0, 0, 0), Vector3(1, 1, 1)),
            ],
            'default_materials': {
                'walls': '#2C2C2C', 'floor': '#1A1A1A', 'furniture': '#8B0000'
            }
        }
    }

    COLOR_SCHEMES = {
        'corporate': {'walls': '#4A90E2', 'floor': '#2C3E50', 'furniture': '#34495E'},
        'warm': {'walls': '#F5E6D3', 'floor': '#8B7355', 'furniture': '#D2691E'},
        'modern': {'walls': '#FFFFFF', 'floor': '#1C1C1C', 'furniture': '#FF6B6B'},
        'nature': {'walls': '#E8F5E9', 'floor': '#5D4037', 'furniture': '#388E3C'}
    }

    def build_room(self, template_type: RoomTemplate, capacity: int,
                   lighting: LightingType, color_scheme: str,
                   additional_objects: List[Dict] = None) -> VirtualRoomConfig:
        template = self.TEMPLATES[template_type]

        # Масштабирование по вместимости
        space_per_person = 2.5
        required_space = capacity * space_per_person
        base_dims = template['base_dimensions']
        scale_factor = (required_space / (base_dims.x * base_dims.y)) ** 0.5
        dimensions = Vector3(
            base_dims.x * scale_factor,
            base_dims.y * scale_factor,
            base_dims.z
        )

        # Освещение
        lighting_intensity = {
            LightingType.BRIGHT: 1.0,
            LightingType.DIM: 0.5,
            LightingType.NATURAL: 0.8
        }.get(lighting, 0.8)

        # Цветовая схема
        colors = self.COLOR_SCHEMES.get(color_scheme, template['default_materials'])

        # Объекты
        objects = []
        for obj in template['base_objects']:
            objects.append(VRObject(
                name=obj.name, model_path=obj.model_path,
                position=obj.position, rotation=obj.rotation,
                scale=Vector3(obj.scale.x * scale_factor,
                              obj.scale.y * scale_factor, obj.scale.z),
                material=colors['furniture']
            ))

        # Места для участников
        import math
        if template_type == RoomTemplate.CONFERENCE_ROOM:
            for i in range(capacity):
                side = 0 if i < capacity // 2 else 1
                pos_in_row = i % (capacity // 2 + capacity % 2)
                x = pos_in_row * 0.6
                z = 3.5 if side == 0 else 2.5
                rot_y = 180 if side == 0 else 0
                objects.append(VRObject(
                    name=f"chair_{i}", model_path="models/chair.obj",
                    position=Vector3(x, z, 0),
                    rotation=Vector3(0, rot_y, 0),
                    scale=Vector3(1, 1, 1), material="default"
                ))
        elif template_type == RoomTemplate.AUDITORIUM:
            rows = max(1, capacity // 10)
            seats_per_row = max(1, capacity // rows)
            for row in range(rows):
                for seat in range(min(seats_per_row, capacity - row * seats_per_row)):
                    objects.append(VRObject(
                        name=f"seat_{row}_{seat}",
                        model_path="models/auditorium_seat.obj",
                        position=Vector3(
                            (seat - seats_per_row / 2) * 0.6,
                            5 + row * 1.5, 0.5 + row * 0.3
                        ),
                        rotation=Vector3(0, 0, 0),
                        scale=Vector3(1, 1, 1), material="default"
                    ))
        else:
            for i in range(capacity):
                angle = (i / capacity) * 2 * math.pi
                radius = 5
                objects.append(VRObject(
                    name=f"spot_{i}", model_path="models/floor_marker.obj",
                    position=Vector3(radius * math.cos(angle),
                                     radius * math.sin(angle), 0),
                    rotation=Vector3(0, 0, 0),
                    scale=Vector3(0.5, 0.5, 0.5), material="default"
                ))

        # Пользовательские объекты
        if additional_objects:
            for obj_data in additional_objects:
                objects.append(VRObject(
                    name=obj_data.get('name', 'custom_object'),
                    model_path=obj_data.get('model_path', 'models/box.obj'),
                    position=Vector3(obj_data.get('x', 0),
                                     obj_data.get('z', 0),
                                     obj_data.get('y', 0)),
                    rotation=Vector3(obj_data.get('rot_x', 0),
                                     obj_data.get('rot_y', 0),
                                     obj_data.get('rot_z', 0)),
                    scale=Vector3(obj_data.get('scale_x', 1),
                                  obj_data.get('scale_y', 1),
                                  obj_data.get('scale_z', 1)),
                    material=obj_data.get('material', 'default')
                ))

        # Точки спавна
        spawn_points = []
        perimeter = 2 * (dimensions.x + dimensions.z)
        spacing = perimeter / max(1, capacity)
        for i in range(min(capacity, 20)):
            position = (i * spacing) % perimeter
            if position < dimensions.x:
                x = position - dimensions.x / 2
                z = -dimensions.z / 2 - 1
            elif position < dimensions.x + dimensions.z:
                x = dimensions.x / 2 + 1
                z = (position - dimensions.x) - dimensions.z / 2
            elif position < 2 * dimensions.x + dimensions.z:
                x = dimensions.x / 2 - (position - dimensions.x - dimensions.z)
                z = dimensions.z / 2 + 1
            else:
                x = -dimensions.x / 2 - 1
                z = dimensions.z / 2 - (position - 2 * dimensions.x - dimensions.z)
            spawn_points.append(Vector3(x, 1.6, z))

        return VirtualRoomConfig(
            room_name=f"{template_type.value}_{capacity}persons",
            dimensions=dimensions,
            lighting_intensity=lighting_intensity,
            lighting_type=lighting.value,
            color_scheme=colors,
            objects=objects,
            spawn_points=spawn_points,
            capacity=capacity
        )

    def to_json(self, config: VirtualRoomConfig) -> str:
        """Сериализация в JSON"""
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, '__dict__'):
                return {k: convert(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [convert(item) for item in obj]
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj

        return json.dumps(convert(config), indent=2, ensure_ascii=False)


# ============================================================
# АЛГОРИТМ 4: Обработка голосования
# ============================================================

class PollManager:
    """
    Алгоритм 4: Обработка голосования
    Вход: poll_id, user_id, selected_option
    Выход: success, current_results
    Сложность: O(m log m), где m - количество голосов
    """

    def __init__(self, db_connection):
        self.db = db_connection

    def create_poll(self, event_id: int, question: str,
                    options: List[str]) -> int:
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO polls (event_id, question, options_json, status, created_at)
            VALUES (?, ?, ?, 'active', ?)
        """, (event_id, question, json.dumps(options, ensure_ascii=False),
              datetime.now().isoformat()))
        self.db.commit()
        return cursor.lastrowid

    def cast_vote(self, poll_id: int, user_id: int,
              selected_option: int) -> Dict[str, Any]:
        cursor = self.db.cursor()

        # Проверка: не голосовал ли уже
        cursor.execute("""
            SELECT result_id FROM poll_results
            WHERE poll_id = ? AND user_id = ?
        """, (poll_id, user_id))
        if cursor.fetchone():
            return {'success': False, 'error': 'Пользователь уже проголосовал'}

        # Проверка: активно ли голосование
        cursor.execute("""
            SELECT status FROM polls WHERE poll_id = ?
        """, (poll_id,))
        row = cursor.fetchone()
        if not row or row[0] != 'active':
            return {'success': False, 'error': 'Голосование закрыто'}

        # Запись голоса
        cursor.execute("""
            INSERT INTO poll_results (poll_id, user_id, selected_option, voted_at)
            VALUES (?, ?, ?, ?)
        """, (poll_id, user_id, selected_option, datetime.now().isoformat()))
        self.db.commit()

        # Подсчёт результатов
        cursor.execute("""
            SELECT selected_option, COUNT(*) as cnt
            FROM poll_results
            WHERE poll_id = ?
            GROUP BY selected_option
        """, (poll_id,))
        results = {row[0]: row[1] for row in cursor.fetchall()}

        # Дополняем нулями для всех вариантов
        cursor.execute("SELECT options_json FROM polls WHERE poll_id = ?", (poll_id,))
        options = json.loads(cursor.fetchone()[0])
        for i in range(len(options)):
            if i not in results:
                results[i] = 0

        return {'success': True, 'current_results': results}


# ============================================================
# ТЕСТЫ
# ============================================================

def create_test_database():
    """Создание тестовой БД со всеми таблицами"""
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE,
            event_id INTEGER,
            user_id INTEGER,
            expires_at TEXT,
            status TEXT,
            created_at TEXT,
            accepted_at TEXT,
            joined_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE polls (
            poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            question TEXT,
            options_json TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE poll_results (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER,
            user_id INTEGER,
            selected_option INTEGER,
            voted_at TEXT
        )
    """)

    db.commit()
    return db


def test_invitation_system():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ СИСТЕМЫ ПРИГЛАШЕНИЙ (Алгоритмы 1 и 2)")
    print("=" * 60)

    db = create_test_database()
    manager = InvitationManager(db)

    print("\n[Тест 1] Генерация токена доступа")
    token, expires = manager.generate_invitation_token(event_id=100, user_id=42)
    assert len(token) == 32, "Длина токена должна быть 32 символа"
    print(f"  Токен сгенерирован: {token[:16]}...")
    print(f"  Срок действия до: {expires}")
    print("  [OK] Тест 1 пройден")

    print("\n[Тест 2] Проверка валидного токена")
    result = manager.verify_invitation_token(token, event_id=100)
    assert result['access_granted'] == True, f"Доступ должен быть разрешен, получено: {result}"
    assert result['user_id'] == 42, "ID пользователя должен совпадать"
    print(f"  Доступ разрешен для пользователя {result['user_id']}")
    print("  [OK] Тест 2 пройден")

    print("\n[Тест 3] Проверка неверного токена")
    result = manager.verify_invitation_token("wrong_token_123456789012345678", event_id=100)
    assert result['access_granted'] == False
    print(f"  Доступ запрещен: {result['error_message']}")
    print("  [OK] Тест 3 пройден")

    print("\n[Тест 4] Проверка токена для другого мероприятия")
    result = manager.verify_invitation_token(token, event_id=999)
    assert result['access_granted'] == False
    print(f"  Доступ запрещен: {result['error_message']}")
    print("  [OK] Тест 4 пройден")

    db.close()
    print("\n[OK] Все тесты системы приглашений пройдены!\n")


def test_room_builder():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ КОНСТРУКТОРА КОМНАТ (Алгоритм 3)")
    print("=" * 60)

    builder = VirtualRoomBuilder()

    print("\n[Тест 1] Конференц-зал на 10 человек")
    config = builder.build_room(
        template_type=RoomTemplate.CONFERENCE_ROOM,
        capacity=10,
        lighting=LightingType.BRIGHT,
        color_scheme='corporate',
        additional_objects=[{
            'name': 'whiteboard',
            'model_path': 'models/whiteboard.obj',
            'x': 4, 'z': 0, 'y': 1.5,
            'rot_x': 0, 'rot_y': 90, 'rot_z': 0,
            'scale_x': 1, 'scale_y': 1, 'scale_z': 0.1
        }]
    )

    assert config.capacity == 10
    assert len(config.spawn_points) > 0
    print(f"  Размеры: {config.dimensions.x:.2f} x {config.dimensions.z:.2f} x {config.dimensions.y:.2f} м")
    print(f"  Объектов: {len(config.objects)}")
    print(f"  Точек спавна: {len(config.spawn_points)}")
    print("  [OK] Тест 1 пройден")

    print("\n[Тест 2] Аудитория на 30 человек")
    config = builder.build_room(
        template_type=RoomTemplate.AUDITORIUM,
        capacity=30,
        lighting=LightingType.DIM,
        color_scheme='modern'
    )
    assert config.capacity == 30
    print(f"  Размеры: {config.dimensions.x:.2f} x {config.dimensions.z:.2f} м")
    print(f"  Мест создано: {len([o for o in config.objects if 'seat' in o.name])}")
    print("  [OK] Тест 2 пройден")

    print("\n[Тест 3] Сериализация в JSON")
    json_str = builder.to_json(config)
    assert len(json_str) > 100
    parsed = json.loads(json_str)
    assert 'room_name' in parsed
    print(f"  Размер JSON: {len(json_str)} байт")
    print(f"  JSON валиден, название: {parsed['room_name']}")
    print("  [OK] Тест 3 пройден")

    print("\n[OK] Все тесты конструктора комнат пройдены!\n")


def test_poll_system():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ СИСТЕМЫ ГОЛОСОВАНИЯ (Алгоритм 4)")
    print("=" * 60)

    db = create_test_database()
    poll_mgr = PollManager(db)

    print("\n[Тест 1] Создание голосования")
    poll_id = poll_mgr.create_poll(
        event_id=1,
        question="Как вам мероприятие?",
        options=["Отлично", "Хорошо", "Нормально", "Плохо"]
    )
    assert poll_id > 0
    print(f"  Голосование создано с ID: {poll_id}")
    print("  [OK] Тест 1 пройден")

    print("\n[Тест 2] Голосование трёх пользователей")
    r1 = poll_mgr.cast_vote(poll_id, user_id=1, selected_option=0)
    assert r1['success'] == True
    r2 = poll_mgr.cast_vote(poll_id, user_id=2, selected_option=0)
    assert r2['success'] == True
    r3 = poll_mgr.cast_vote(poll_id, user_id=3, selected_option=1)
    assert r3['success'] == True
    print(f"  Результаты: {r3['current_results']}")
    print("  [OK] Тест 2 пройден")

    print("\n[Тест 3] Повторное голосование запрещено")
    r4 = poll_mgr.cast_vote(poll_id, user_id=1, selected_option=2)
    assert r4['success'] == False
    print(f"  Ошибка: {r4['error']}")
    print("  [OK] Тест 3 пройден")

    db.close()
    print("\n[OK] Все тесты системы голосования пройдены!\n")


# ============================================================
# ГЛАВНЫЙ БЛОК
# ============================================================

if __name__ == "__main__":
    test_invitation_system()
    test_room_builder()
    test_poll_system()

    print("=" * 60)
    print("ВСЕ ТЕСТЫ УСПЕШНО ПРОЙДЕНЫ")
    print("=" * 60)